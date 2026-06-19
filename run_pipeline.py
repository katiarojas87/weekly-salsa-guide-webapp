#!/usr/bin/env python3
"""
run_pipeline.py
===============
One-command weekly salsa guide pipeline.

Steps:
  1. Scrape next week's events.
  2. Persist normalized events to SQLite.
  3. Save raw JSON for the week.

Usage:
  python run_pipeline.py
  python run_pipeline.py --skip-scrape

Options:
  --skip-scrape  Skip scraping and use existing raw_events file
"""

import argparse
import asyncio
import glob
import json
import os
import sys
from datetime import date, timedelta

from db import init_db, save_events, deactivate_past_events

# ── Day name helpers ──────────────────────────────────────────────────────────

NL_DAYS = {
    0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag",
    4: "Vrijdag",  5: "Zaterdag", 6: "Zondag",
}
NL_MON = {
    1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"Mei",6:"Jun",
    7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec",
}


def get_next_week_dates():
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_ahead)
    return [next_monday + timedelta(days=i) for i in range(7)]


# ── Step 1: Scrape ────────────────────────────────────────────────────────────

async def run_scrape(week_dates: list) -> dict:
    from scrapers import scrape_salsalovers, scrape_latinworld
    from scrapers.event_sources import scrape_generic_sources, load_manual_events

    start_date = week_dates[0]
    out_file   = f"raw_events_{start_date}.json"

    # One-time guard
    if os.path.exists(out_file):
        print(f"  ✅ Already scraped this week — using {out_file}")
        with open(out_file, encoding="utf-8") as f:
            return json.load(f)

    print("  🌐 Scraping salsalovers.be ...")
    salsa = await scrape_salsalovers(week_dates)
    print(f"     → {len(salsa)} events")

    print("  🌐 Scraping latinworld.nl ...")
    latin = await scrape_latinworld(week_dates)
    print(f"     → {len(latin)} events")

    print("  🌐 Loading generic JSON-LD sources ...")
    generic = scrape_generic_sources(week_dates)
    print(f"     → {len(generic)} events")

    print("  🗂️  Loading manual_events.json ...")
    manual = load_manual_events("manual_events.json", week_dates)
    print(f"     → {len(manual)} manual events")

    all_events = salsa + latin + generic + manual

    init_db(None)
    cutoff_date = week_dates[0]
    deactivated = deactivate_past_events(None, cutoff_date)
    if deactivated:
        print(f"  🗄️  Deactivated {deactivated} past event(s) before saving new data")
    saved = save_events(None, all_events)
    print(f"  💾 Saved {saved} events to SQLite database")

    days = {}
    for d in week_dates:
        day_events = [e for e in all_events if e.get("date") == str(d)]
        days[str(d)] = {
            "date":   str(d),
            "label":  f"{NL_DAYS[d.weekday()]} {d.day} {NL_MON[d.month]}",
            "events": day_events,
        }

    from datetime import datetime
    result = {
        "generated_at": datetime.now().isoformat(),
        "range": {"start": str(week_dates[0]), "end": str(week_dates[-1])},
        "days":  list(days.values()),
        "total_events": len(all_events),
        "salsalovers_count": len(salsa),
        "latinworld_count":  len(latin),
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  💾 Saved {out_file}")

    # Delete old raw files
    for pattern in ["raw_events_*.json", "salsalovers_raw_*.json", "latinworld_raw_*.json"]:
        for path in glob.glob(pattern):
            if str(start_date) not in path:
                os.remove(path)

    return result


def find_existing_raw():
    """Find any raw_events JSON from this week."""
    week_dates = get_next_week_dates()
    out_file = f"raw_events_{week_dates[0]}.json"
    if os.path.exists(out_file):
        print(f"  ✅ Found existing raw file: {out_file}")
        with open(out_file, encoding="utf-8") as f:
            return json.load(f)
    return None



# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Weekly salsa pipeline: scrape events and persist to SQLite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py --skip-scrape
  python run_pipeline.py
        """
    )
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Skip scraping and use existing raw_events file")
    args = parser.parse_args()

    print("\n" + "═" * 55)
    print("  🕺 Weekly Salsa Guide Pipeline")
    print("═" * 55)

    week_dates = get_next_week_dates()
    print(f"\n📅 Week: {week_dates[0]} → {week_dates[-1]}")

    print("\n[1/1] Scraping and persisting events ...")
    if args.skip_scrape:
        raw = find_existing_raw()
        if not raw:
            print("  ❌  No raw_events file found. Run without --skip-scrape first.")
            sys.exit(1)
    else:
        raw = asyncio.run(run_scrape(week_dates))

    print(f"       Total events in raw file: {raw.get('total_events', '?')}")
    print("\n  ✅ Pipeline complete. Events are persisted in events.db")


if __name__ == "__main__":
    main()
