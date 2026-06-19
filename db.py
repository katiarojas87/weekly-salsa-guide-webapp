#!/usr/bin/env python3
"""SQLite persistence for scraped events.

Provides:
- `init_db(db_path)` to create schema
- `upsert_event(db_path, event)` to insert or update with simple dedupe rules
- `save_events(db_path, events)` to save a list of events
- `get_events(db_path, date=None)` to fetch events (optionally by date)
- `deactivate_past_events(db_path, cutoff_date)` to mark old events inactive

Schema (table `events`): columns match normalized event schema plus metadata.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

DEFAULT_DB = Path(__file__).parent / "events.db"


def init_db(db_path: Optional[str] = None) -> Path:
    path = Path(db_path or DEFAULT_DB)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            event_name TEXT,
            date TEXT,
            time TEXT,
            venue TEXT,
            organizer TEXT,
            address TEXT,
            city TEXT,
            country TEXT,
            lat REAL,
            lng REAL,
            price TEXT,
            source_url TEXT,
            image_url TEXT,
            description TEXT,
            active INTEGER DEFAULT 1,
            inserted_at TEXT
        )
        """
    )
    # Lightweight migration for existing DBs created before organizer existed.
    cur.execute("PRAGMA table_info(events)")
    existing_cols = {row[1] for row in cur.fetchall()}
    if "organizer" not in existing_cols:
        cur.execute("ALTER TABLE events ADD COLUMN organizer TEXT")

    # Indexes to speed up lookups and simple dedupe checks
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_name_date ON events(event_name, date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_city ON events(city)")
    conn.commit()
    conn.close()
    return path


def _row_to_event(row: Tuple) -> Dict:
    (id_, event_name, date_, time_, venue, organizer, address, city, country, lat, lng,
     price, source_url, image_url, description, active, inserted_at) = row
    return {
        "id": id_,
        "event_name": event_name,
        "date": date_,
        "time": time_,
        "venue": venue,
        "organizer": organizer,
        "address": address,
        "city": city,
        "country": country,
        "lat": lat,
        "lng": lng,
        "price": price,
        "source_url": source_url,
        "image_url": image_url,
        "description": description,
        "active": bool(active),
        "inserted_at": inserted_at,
    }


def find_duplicate(conn: sqlite3.Connection, event: Dict) -> Optional[int]:
    """Find a candidate duplicate event id or None.

    Heuristics (in order):
    - exact `source_url` match
    - same `event_name` and `date` and same `venue` or `address`
    - same `event_name` and `date` and nearby lat/lng (within ~1km -> ~0.01deg)
    """
    cur = conn.cursor()
    src = event.get("source_url")
    if src:
        cur.execute("SELECT id FROM events WHERE source_url = ?", (src,))
        r = cur.fetchone()
        if r:
            return r[0]

    name = event.get("event_name") or ""
    date_ = event.get("date") or ""
    venue = event.get("venue") or ""
    address = event.get("address") or ""

    if name and date_:
        cur.execute(
            "SELECT id, venue, address, lat, lng FROM events WHERE event_name = ? AND date = ?",
            (name, date_),
        )
        for row in cur.fetchall():
            eid, v, a, lat, lng = row
            # Exact venue/address match
            if venue and v and venue.strip().lower() == v.strip().lower():
                return eid
            if address and a and address.strip().lower() == a.strip().lower():
                return eid
            # Geolocation proximity (if both rows have coords)
            try:
                if lat is not None and lng is not None and event.get("lat") and event.get("lng"):
                    dlat = abs(float(lat) - float(event.get("lat")))
                    dlng = abs(float(lng) - float(event.get("lng")))
                    if dlat < 0.01 and dlng < 0.01:
                        return eid
            except Exception:
                pass

    return None


def _normalize_event(event: Dict) -> Dict:
    """Normalize scraper output keys to DB schema keys."""
    src = (event.get("source") or "").strip().lower()
    country = event.get("country")
    if not country and src == "salsalovers":
        country = "Belgium"

    lat = event.get("lat")
    lng = event.get("lng")
    coords = event.get("coordinates")
    if (lat is None or lng is None) and isinstance(coords, (list, tuple)) and len(coords) == 2:
        lat, lng = coords[0], coords[1]

    normalized = dict(event)
    normalized["event_name"] = event.get("event_name") or event.get("name")
    normalized["source_url"] = event.get("source_url") or event.get("url")
    normalized["venue"] = event.get("venue")
    normalized["organizer"] = event.get("organizer")
    normalized["country"] = country
    normalized["lat"] = lat
    normalized["lng"] = lng
    return normalized


def upsert_event(db_path: Optional[str], event: Dict) -> int:
    path = db_path or DEFAULT_DB
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    event = _normalize_event(event)

    eid = find_duplicate(conn, event)
    now = datetime.utcnow().isoformat()
    if eid:
        # update fields conservatively (prefer non-empty values)
        cur.execute("SELECT * FROM events WHERE id = ?", (eid,))
        existing = cur.fetchone()
        if existing:
            updated = {}
            keys = [
                "event_name", "date", "time", "venue", "organizer", "address", "city", "country",
                "lat", "lng", "price", "source_url", "image_url", "description"
            ]
            for i, k in enumerate(keys, start=1):
                val = event.get(k)
                if val is None or val == "":
                    updated[k] = existing[i]
                else:
                    updated[k] = val
            cur.execute(
                """
                UPDATE events SET
                                    event_name = ?, date = ?, time = ?, venue = ?, organizer = ?, address = ?, city = ?, country = ?,
                  lat = ?, lng = ?, price = ?, source_url = ?, image_url = ?, description = ?,
                  active = 1, inserted_at = ?
                WHERE id = ?
                """,
                (
                                        updated["event_name"], updated["date"], updated["time"], updated["venue"], updated["organizer"],
                    updated["address"], updated["city"], updated["country"],
                    updated["lat"], updated["lng"], updated["price"], updated["source_url"],
                    updated["image_url"], updated["description"], now, eid,
                ),
            )
            conn.commit()
            conn.close()
            return eid

    # insert new
    cur.execute(
        """
        INSERT INTO events (
            event_name, date, time, venue, organizer, address, city, country,
            lat, lng, price, source_url, image_url, description, active, inserted_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)
        """,
        (
            event.get("event_name"), event.get("date"), event.get("time"), event.get("venue"), event.get("organizer"),
            event.get("address"), event.get("city"), event.get("country"),
            event.get("lat"), event.get("lng"), event.get("price"), event.get("source_url"),
            event.get("image_url"), event.get("description"), now,
        ),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid


def save_events(db_path: Optional[str], events: List[Dict]) -> int:
    init_db(db_path)
    count = 0
    for ev in events:
        upsert_event(db_path, ev)
        count += 1
    return count


def get_events(db_path: Optional[str], date_filter: Optional[str] = None) -> List[Dict]:
    path = db_path or DEFAULT_DB
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    if date_filter:
        cur.execute("SELECT * FROM events WHERE date = ? AND active = 1", (date_filter,))
    else:
        cur.execute("SELECT * FROM events WHERE active = 1")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_event(r) for r in rows]


def deactivate_past_events(db_path: Optional[str], cutoff: date) -> int:
    """Mark events with `date` < cutoff as inactive. Returns affected count."""
    path = db_path or DEFAULT_DB
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cutoff_str = str(cutoff)
    cur.execute("UPDATE events SET active = 0 WHERE date < ?", (cutoff_str,))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected


if __name__ == "__main__":
    p = init_db()
    print(f"Initialized DB at: {p}")
