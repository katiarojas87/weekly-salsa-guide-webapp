#!/usr/bin/env python3
"""
scrape_and_push.py
==================
Run the full scraper pipeline locally, then push the results to the
Render API via POST /push-events.

Run manually:
  python scripts/scrape_and_push.py

Scheduled (macOS crontab — Monday 07:00):
  0 7 * * 1 /Users/kaatsandoval/.pyenv/versions/lewagon/bin/python \
    "/Users/kaatsandoval/code/katiarojas87/weekly-salsa-guide webapp/scripts/scrape_and_push.py" \
    >> "/Users/kaatsandoval/code/katiarojas87/weekly-salsa-guide webapp/logs/scrape.log" 2>&1
"""

import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests as _requests
from dotenv import load_dotenv

# Project root is one level up from scripts/
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from scrapers import scrape_salsalovers, scrape_latinworld, scrape_salsavida
from scrapers.event_sources import scrape_generic_sources, load_manual_events

API_URL     = os.environ.get("RENDER_API_URL", "https://weekly-salsa-guide-webapp.onrender.com")
PUSH_SECRET = os.environ.get("PUSH_SECRET", "")


def get_scrape_dates():
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    return [this_monday + timedelta(days=i) for i in range(14)]


async def _scrape(target_dates):
    errors = {}

    print("  SalsaLovers...", flush=True)
    try:
        salsa = await scrape_salsalovers(target_dates)
    except Exception as exc:
        print(f"  SalsaLovers FAILED: {exc}")
        salsa = []
        errors["salsalovers"] = str(exc)

    print("  LatinWorld...", flush=True)
    try:
        latin = await scrape_latinworld(target_dates)
    except Exception as exc:
        print(f"  LatinWorld FAILED: {exc}")
        latin = []
        errors["latinworld"] = str(exc)

    print("  SalsaVida...", flush=True)
    try:
        vida = scrape_salsavida(target_dates)
    except Exception as exc:
        print(f"  SalsaVida FAILED: {exc}")
        vida = []
        errors["salsavida"] = str(exc)

    generic = scrape_generic_sources(target_dates)
    manual  = load_manual_events(str(ROOT / "manual_events.json"), target_dates)

    return salsa, latin, vida, generic, manual, errors


def push(events, target_dates, errors):
    if not PUSH_SECRET:
        print("ERROR: PUSH_SECRET not set in .env — cannot push to Render")
        sys.exit(1)

    payload = {
        "events":    events,
        "range":     {"start": str(target_dates[0]), "end": str(target_dates[-1])},
        "errors":    errors,
    }

    url = f"{API_URL}/push-events"
    print(f"\nPushing {len(events)} events to {url} ...", flush=True)
    resp = _requests.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {PUSH_SECRET}"},
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"Render response: {json.dumps(result, indent=2)}")
    return result


def main():
    target_dates = get_scrape_dates()
    next_monday  = target_dates[7]
    print(f"=== scrape_and_push ===")
    print(f"Window : {target_dates[0]} → {target_dates[-1]}")
    print(f"Target : {API_URL}\n")

    salsa, latin, vida, generic, manual, errors = asyncio.run(_scrape(target_dates))
    all_events = salsa + latin + vida + generic + manual

    this_week = [e for e in all_events if e.get("date", "") < str(next_monday)]
    next_week  = [e for e in all_events if e.get("date", "") >= str(next_monday)]

    print(f"\nScrape results:")
    print(f"  SalsaLovers : {len(salsa)}")
    print(f"  LatinWorld  : {len(latin)}")
    print(f"  SalsaVida   : {len(vida)}")
    print(f"  Generic     : {len(generic)}")
    print(f"  Manual      : {len(manual)}")
    print(f"  TOTAL       : {len(all_events)}  (this week: {len(this_week)}, next week: {len(next_week)})")
    if errors:
        print(f"  Errors      : {errors}")

    push(all_events, target_dates, errors)
    print("\nDone.")


if __name__ == "__main__":
    main()
