#!/usr/bin/env python3
"""
api.py — FastAPI server for n8n integration
Exposes scraper.py and scorer.py as HTTP endpoints

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio, glob, json, os, re
from datetime import datetime, date, timedelta
from pathlib import Path
import anthropic

# Import your existing scrapers
from salsalovers_scraper import scrape_salsalovers
from latinworld_scraper import scrape_latinworld
from scorer import score_events

app = FastAPI(title="Salsa Events API", version="1.0")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def get_next_week_dates():
    """Return list of 7 dates: next Monday through Sunday."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_ahead)
    return [next_monday + timedelta(days=i) for i in range(7)]


def delete_old_raw_files(keep_start: date):
    """Delete raw JSON files from previous weeks."""
    patterns = ["raw_events_*.json", "salsalovers_raw_*.json", "latinworld_raw_*.json"]
    keep_prefix = str(keep_start)
    deleted = []
    for pattern in patterns:
        for path in glob.glob(pattern):
            if keep_prefix not in path:
                os.remove(path)
                deleted.append(path)
    return deleted

# ── HEALTH CHECK ─────────────────────────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "ok", "service": "Salsa Events API"}

# ── SCRAPE ENDPOINT ──────────────────────────────────────────────────────
@app.post("/scrape")
async def scrape():
    """Run both scrapers and return combined raw events.
    One-time guard: if this week's raw file already exists, returns the cached data."""
    try:
        target_dates = get_next_week_dates()
        start_date   = target_dates[0]
        out_file     = f"raw_events_{start_date}.json"

        # ── One-time guard ────────────────────────────────────────────────────
        if os.path.exists(out_file):
            with open(out_file, encoding="utf-8") as f:
                cached = json.load(f)
            cached["cached"] = True
            return cached

        salsa = await scrape_salsalovers(target_dates)
        latin = await scrape_latinworld(target_dates)
        all_events = salsa + latin

        NL_DAYS = {4:"Vrijdag",5:"Zaterdag",6:"Zondag",
                   0:"Maandag",1:"Dinsdag",2:"Woensdag",3:"Donderdag"}
        NL_MON  = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"Mei",6:"Jun",
                   7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}

        days = {}
        for d in target_dates:
            day_events = [e for e in all_events if e.get("date") == str(d)]
            days[str(d)] = {
                "date":   str(d),
                "label":  f"{NL_DAYS[d.weekday()]} {d.day} {NL_MON[d.month]}",
                "events": day_events,
            }

        result = {
            "generated_at": datetime.now().isoformat(),
            "range": {
                "start": str(target_dates[0]),
                "end":   str(target_dates[-1]),
            },
            "days": list(days.values()),
            "total_events": len(all_events),
            "salsalovers_count": len(salsa),
            "latinworld_count": len(latin),
            "cached": False,
        }

        # ── Save this week's file ─────────────────────────────────────────────
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # ── Delete previous week's files ──────────────────────────────────────
        delete_old_raw_files(keep_start=start_date)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── SCORE ENDPOINT ───────────────────────────────────────────────────────
@app.post("/score")
async def score(raw: dict):
    """Receive raw events JSON, call Claude, return ranked top events per day."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

    try:
        result = score_events(raw, api_key=ANTHROPIC_API_KEY)
        return result
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Claude returned invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
