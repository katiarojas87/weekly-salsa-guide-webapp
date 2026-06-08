#!/usr/bin/env python3
"""
run_pipeline.py
===============
One-command weekly salsa guide pipeline.

Steps:
  1. Scrape (one-time guard — skips if already done this week)
  2. Score top events via Claude (only the days you specify)
  3. Generate Amazonika-style Instagram slides → ./slides/

Usage:
  python run_pipeline.py --schedule THU:1,FRI:2,SAT:2,SUN:2
  python run_pipeline.py --schedule MON:1,WED:1,SAT:2

Schedule format:
  MON/TUE/WED/THU/FRI/SAT/SUN  :  number of events for that day
  Days you omit are skipped entirely.

Options:
  --schedule   Comma-separated DAY:COUNT pairs (required)
  --output     Output folder for PNGs (default: ./slides)
  --skip-scrape  Skip scraping and use existing raw_events file
  --save-json  Save intermediate scored_events.json for debugging
"""

import argparse
import asyncio
import glob
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# ── Day name helpers ──────────────────────────────────────────────────────────

DAY_ABBR = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3,
    "FRI": 4, "SAT": 5, "SUN": 6,
}

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


def parse_schedule(schedule_str: str, week_dates: list) -> dict:
    """
    Parse 'THU:1,FRI:2,SAT:2,SUN:2' into { "2026-06-12": 1, "2026-06-13": 2, ... }
    """
    schedule = {}
    for part in schedule_str.upper().split(","):
        part = part.strip()
        if ":" not in part:
            print(f"⚠️  Skipping invalid schedule entry: '{part}' (expected DAY:COUNT)")
            continue
        day_abbr, count_str = part.split(":", 1)
        day_abbr = day_abbr.strip()
        if day_abbr not in DAY_ABBR:
            print(f"⚠️  Unknown day abbreviation: '{day_abbr}' — use MON/TUE/WED/THU/FRI/SAT/SUN")
            continue
        try:
            count = int(count_str.strip())
        except ValueError:
            print(f"⚠️  Invalid count for {day_abbr}: '{count_str}'")
            continue
        target_weekday = DAY_ABBR[day_abbr]
        for d in week_dates:
            if d.weekday() == target_weekday:
                schedule[str(d)] = count
                break
    return schedule


# ── Step 1: Scrape ────────────────────────────────────────────────────────────

async def run_scrape(week_dates: list) -> dict:
    from salsalovers_scraper import scrape_salsalovers
    from latinworld_scraper import scrape_latinworld

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

    all_events = salsa + latin

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


def find_existing_raw() -> dict | None:
    """Find any raw_events JSON from this week."""
    week_dates = get_next_week_dates()
    out_file = f"raw_events_{week_dates[0]}.json"
    if os.path.exists(out_file):
        print(f"  ✅ Found existing raw file: {out_file}")
        with open(out_file, encoding="utf-8") as f:
            return json.load(f)
    return None


# ── Step 2: Score ─────────────────────────────────────────────────────────────

def run_score(raw: dict, schedule: dict) -> dict:
    from scorer import score_events

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("❌  ANTHROPIC_API_KEY not set. Export it first:")
        print("    export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    total_events = sum(
        len(day["events"])
        for day in raw.get("days", [])
        if day["date"] in schedule
    )
    print(f"  🤖 Scoring {total_events} events across {len(schedule)} day(s) via Claude ...")
    return score_events(raw, api_key=api_key, schedule=schedule)


# ── Step 3: Generate slides ───────────────────────────────────────────────────

def run_generate(scored: dict, output_dir: Path):
    from generate_slides import render_slides

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    ranked = scored.get("ranked_events", {})
    events_with_meta = []
    for date_key, day_events in ranked.items():
        if not isinstance(day_events, list):
            continue
        for event in day_events:
            rank = event.get("rank", 1)
            if "date" not in event:
                event["date"] = date_key
            events_with_meta.append((date_key, rank, event))

    events_with_meta.sort(key=lambda x: (x[0], x[1]))

    if not events_with_meta:
        print("  ⚠️  No events to render after scoring.")
        return []

    print(f"  🎨 Rendering {len(events_with_meta)} slide(s) ...")
    return render_slides(events_with_meta, output_dir, api_key=api_key)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Weekly salsa pipeline: scrape → score → slides",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py --schedule THU:1,FRI:2,SAT:2,SUN:2
  python run_pipeline.py --schedule MON:1,SAT:2 --output ./my_slides
  python run_pipeline.py --schedule FRI:1,SAT:2 --skip-scrape --save-json
        """
    )
    parser.add_argument("--schedule",    "-s", required=True,
                        help="e.g. THU:1,FRI:2,SAT:2,SUN:2")
    parser.add_argument("--output",      "-o", default="./slides",
                        help="Output folder for PNG slides (default: ./slides)")
    parser.add_argument("--skip-scrape", action="store_true",
                        help="Skip scraping, use existing raw_events file")
    parser.add_argument("--save-json",   action="store_true",
                        help="Save scored_events.json alongside slides")
    args = parser.parse_args()

    print("\n" + "═" * 55)
    print("  🕺 Weekly Salsa Guide Pipeline")
    print("═" * 55)

    # ── Dates ──
    week_dates = get_next_week_dates()
    print(f"\n📅 Week: {week_dates[0]} → {week_dates[-1]}")

    # ── Schedule ──
    schedule = parse_schedule(args.schedule, week_dates)
    if not schedule:
        print("❌  No valid days in schedule. Exiting.")
        sys.exit(1)
    print(f"\n📋 Schedule:")
    for date_key, count in sorted(schedule.items()):
        from datetime import datetime
        d = datetime.strptime(date_key, "%Y-%m-%d")
        print(f"    {NL_DAYS[d.weekday()]} {date_key}  →  max {count} event(s)")

    # ── Step 1: Scrape ──
    print("\n[1/3] Scraping events ...")
    if args.skip_scrape:
        raw = find_existing_raw()
        if not raw:
            print("  ❌  No raw_events file found. Run without --skip-scrape first.")
            sys.exit(1)
    else:
        raw = asyncio.run(run_scrape(week_dates))
    print(f"       Total events in raw file: {raw.get('total_events', '?')}")

    # ── Step 2: Score ──
    print("\n[2/3] Scoring ...")
    scored = run_score(raw, schedule)
    total_selected = sum(
        len(v) for v in scored.get("ranked_events", {}).values()
        if isinstance(v, list)
    )
    print(f"       Selected {total_selected} top event(s)")

    output_dir = Path(args.output)
    if args.save_json:
        json_path = output_dir / "scored_events.json"
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(scored, f, ensure_ascii=False, indent=2)
        print(f"       💾 Saved {json_path}")

    # ── Step 3: Slides ──
    print(f"\n[3/3] Generating slides → {output_dir}/")
    paths = run_generate(scored, output_dir)

    print(f"\n{'═' * 55}")
    print(f"  ✅ Done!  {len(paths)} slide(s) ready in {output_dir}/")
    print("═" * 55 + "\n")


if __name__ == "__main__":
    main()
