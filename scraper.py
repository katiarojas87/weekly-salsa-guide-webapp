#!/usr/bin/env python3
"""
scraper.py
==========
Main coordinator. Runs both scrapers and combines results.

Uses:
  - scrapers.salsalovers  → scrapes agenda.salsalovers.be
  - scrapers.latinworld   → scrapes latinworld.nl

- Automatically targets next Monday → Sunday.
- One-time guard: skips if this week's raw_events file already exists.
- Auto-deletes previous week's raw JSON files on success.

Saves: raw_events_YYYY-MM-DD.json
Next step: run the backend or use `run_pipeline.py` to persist events to SQLite.

Run:
  python scraper.py
"""
import asyncio
import glob
import json
import os
import sys
from datetime import date, timedelta, datetime

from scrapers import scrape_salsalovers, scrape_latinworld, scrape_salsavida
from scrapers.event_sources import scrape_generic_sources, load_manual_events
from db import init_db, save_events, deactivate_past_events

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
        "salsavida_raw_*.json",
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

    # ── Run all scrapers ──────────────────────────────────────────────────────
    source_runs = [
        ("SalsaLovers",   scrape_salsalovers,  True),
        ("LatinWorld",    scrape_latinworld,   True),
        ("SalsaVida",     scrape_salsavida,    False),
        ("EventSources",  scrape_generic_sources, False),
        ("ManualEvents",  lambda dates: load_manual_events("manual_events.json", dates), False),
    ]
    results = {}

    for name, func, is_async in source_runs:
        try:
            print(f"  🌐 Running {name} ...")
            events = await func(target_dates) if is_async else func(target_dates)
            results[name] = events or []
            print(f"     → {len(results[name])} events")
        except Exception as exc:
            print(f"  ⚠️  {name} failed: {exc}")
            results[name] = []

    all_events = []
    for events in results.values():
        all_events.extend(events)

    summary = ", ".join(f"{name}: {len(evts)}" for name, evts in results.items())
    print(f"\n📋 Total: {len(all_events)} events ({summary})")

    if not all_events:
        print("\n❌ No events found for this week.")
        sys.exit(0)

    init_db(None)
    cutoff_date = target_dates[0]
    deactivated = deactivate_past_events(None, cutoff_date)
    if deactivated:
        print(f"\n🗄️  Deactivated {deactivated} past event(s) before saving new data")

    saved = save_events(None, all_events)
    print(f"\n💾 Saved {saved} events to SQLite database")

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

    print(f"\n✅ Done! Raw events saved to {out_file}. Use `run_pipeline.py` or the API to persist and query events.")


if __name__ == "__main__":
    asyncio.run(main())
