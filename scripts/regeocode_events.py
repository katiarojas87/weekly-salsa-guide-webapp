#!/usr/bin/env python3
"""
Re-geocode events in the DB whose coordinates look like city-centre fallbacks.

Runs the updated geocode() logic (address-first) against every active event
that either has null coords or coords that match a known city-centre fallback.

Usage:
  python scripts/regeocode_events.py [--dry-run]
"""
import sys
import sqlite3
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.utils import geocode, KNOWN_COORDS

_DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent))
DB_PATH = _DATA_DIR / "events.db"

# Coordinates that look like city-centre fallbacks (rounded to 4 dp)
CITY_CENTRE_COORDS = {
    (round(lat, 4), round(lng, 4))
    for _, (lat, lng) in KNOWN_COORDS.items()
}


def is_city_centre(lat, lng) -> bool:
    if lat is None or lng is None:
        return True
    return (round(lat, 4), round(lng, 4)) in CITY_CENTRE_COORDS


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no DB changes will be written\n")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, event_name, address, city, lat, lng FROM events WHERE active = 1")
    rows = cur.fetchall()

    updated = 0
    skipped = 0
    failed = 0

    for row in rows:
        eid, name, address, city, lat, lng = row

        if not is_city_centre(lat, lng):
            skipped += 1
            continue

        addr = (address or "").strip()
        if not addr:
            print(f"  SKIP  [{eid}] {name!r} — no address field")
            skipped += 1
            continue

        print(f"  GEOCODE [{eid}] {name!r} | address: {addr!r}")
        result = geocode(addr)

        if not result:
            print(f"    → FAILED (keeping existing: lat={lat}, lng={lng})")
            failed += 1
            continue

        new_lat, new_lng = result
        print(f"    → ({new_lat:.5f}, {new_lng:.5f})  was ({lat}, {lng})")

        if not dry_run:
            cur.execute(
                "UPDATE events SET lat = ?, lng = ? WHERE id = ?",
                (new_lat, new_lng, eid),
            )
        updated += 1

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"\nDone. Updated={updated}  Skipped={skipped}  Failed={failed}")
    if dry_run:
        print("(dry run — no changes committed)")


if __name__ == "__main__":
    main()
