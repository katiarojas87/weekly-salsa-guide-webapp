#!/usr/bin/env python3
"""
scraper.py
==========
Main coordinator. Runs both scrapers and combines results.

Uses:
  - salsalovers_scraper.py  → scrapes agenda.salsalovers.be
  - latinworld_scraper.py   → scrapes latinworld.nl

- Automatically targets next Monday → Sunday.
- One-time guard: skips if this week's raw_events file already exists.
- Auto-deletes previous week's raw JSON files on success.

Saves: raw_events_YYYY-MM-DD.json
Next step: run scorer.py (or POST to /score via api.py)

Run:
  python scraper.py
"""

import asyncio
import glob
import json
import os
import sys
from datetime import date, timedelta, datetime

from salsalovers_scraper import scrape_salsalovers
from latinworld_scraper import scrape_latinworld

NL_DAYS = {4: "Vrijdag", 5: "Zaterdag", 6: "Zondag",
           0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag"}
NL_MON  = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"Mei",6:"Jun",
           7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}


def get_next_week_dates():
    """Return list of 7 dates: next Monday through Sunday."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_ahead)
    return [next_monday + timedelta(days=i) for i in range(7)]


def delete_old_raw_files(keep_start: date):
    """Delete raw JSON files from previous weeks."""
    patterns = [
        "raw_events_*.json",
        "salsalovers_raw_*.json",
        "latinworld_raw_*.json",
    ]
    keep_prefix = str(keep_start)
    deleted = []
    for pattern in patterns:
        for path in glob.glob(pattern):
            if keep_prefix not in path:
                os.remove(path)
                deleted.append(path)
    if deleted:
        print(f"\n🗑️  Deleted {len(deleted)} old file(s): {', '.join(deleted)}")


async def main():
    print("=" * 60)
    print("  🕺 Salsa Events Scraper — @kaatsandoval")
    print("=" * 60)

    target_dates = get_next_week_dates()
    start_date   = target_dates[0]
    out_file     = f"raw_events_{start_date}.json"

    print(f"\n📅 Date Range: {target_dates[0]} → {target_dates[-1]}")

    # ── One-time guard ────────────────────────────────────────────────────────
    if os.path.exists(out_file):
        print(f"\n✅ Already scraped this week ({out_file}). Nothing to do.")
        sys.exit(0)

    # ── Run both scrapers ─────────────────────────────────────────────────────
    salsa_events = await scrape_salsalovers(target_dates)
    latin_events = await scrape_latinworld(target_dates)

    all_events = salsa_events + latin_events
    print(f"\n📋 Total: {len(all_events)} events "
          f"(SalsaLovers: {len(salsa_events)}, LatinWorld: {len(latin_events)})")

    if not all_events:
        print("\n❌ No events found for this week.")
        sys.exit(0)

    # ── Group by date ─────────────────────────────────────────────────────────
    days = {}
    for d in target_dates:
        day_events = [e for e in all_events if e.get('date') == str(d)]
        days[str(d)] = {
            "date":   str(d),
            "label":  f"{NL_DAYS[d.weekday()]} {d.day} {NL_MON[d.month]}",
            "events": day_events,
        }

    output = {
        "generated_at":      datetime.now().isoformat(),
        "instagram_account": "@kaatsandoval",
        "range": {
            "start": str(target_dates[0]),
            "end":   str(target_dates[-1]),
        },
        "days": list(days.values()),
        "total_events": len(all_events),
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved: {out_file}")
    print("\n📊 Summary:")
    for day_data in output["days"]:
        print(f"  {day_data['label']}: {len(day_data['events'])} events")

    # ── Auto-delete previous week's files ─────────────────────────────────────
    delete_old_raw_files(keep_start=start_date)

    print(f"\n✅ Done! Now run: python scorer.py {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
