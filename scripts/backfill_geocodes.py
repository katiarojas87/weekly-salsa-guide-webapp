#!/usr/bin/env python3
"""Backfill missing lat/lng in events.db using scrapers.utils.geocode."""

import sqlite3

from scrapers.utils import geocode


def main() -> None:
    conn = sqlite3.connect("events.db")
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT id, address, city
        FROM events
        WHERE active = 1
          AND (lat IS NULL OR lng IS NULL)
        ORDER BY id
        """
    ).fetchall()

    updated = 0
    for event_id, address, city in rows:
        coords = None
        for query in [address, city]:
            q = (query or "").strip()
            if not q:
                continue
            coords = geocode(q)
            if coords:
                break
        if not coords:
            continue

        lat, lng = coords
        if lat is None or lng is None:
            continue

        cur.execute(
            "UPDATE events SET lat = ?, lng = ? WHERE id = ?",
            (float(lat), float(lng), event_id),
        )
        updated += 1

    conn.commit()
    conn.close()

    print(f"Updated lat/lng rows: {updated}")


if __name__ == "__main__":
    main()
