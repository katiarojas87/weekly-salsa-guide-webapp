#!/usr/bin/env python3
"""
api.py — FastAPI server for the Salsa Events backend
Exposes scraping and event query endpoints

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import asyncio, glob, json, os
from datetime import datetime, date, timedelta

# Import your existing scrapers and DB helpers
from scrapers import scrape_salsalovers, scrape_latinworld
from scrapers.event_sources import scrape_generic_sources, load_manual_events
from db import init_db, save_events, deactivate_past_events, get_events

app = FastAPI(title="Salsa Events API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_next_week_dates():
    """Return list of 7 dates: next Monday through Sunday."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_ahead)
    return [next_monday + timedelta(days=i) for i in range(7)]


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import radians, sin, cos, sqrt, atan2
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def filter_events(events: list, city: str | None = None, lat: float | None = None,
                  lng: float | None = None, radius_km: float | None = None) -> list:
    filtered = []
    for event in events:
        if city:
            if city.lower() not in str(event.get("city", "")).lower():
                continue
        if lat is not None and lng is not None and radius_km is not None:
            if event.get("lat") is None or event.get("lng") is None:
                continue
            dist = haversine_distance(lat, lng, float(event["lat"]), float(event["lng"]))
            if dist > radius_km:
                continue
        filtered.append(event)
    return filtered


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
        generic = scrape_generic_sources(target_dates)
        manual = load_manual_events("manual_events.json", target_dates)
        all_events = salsa + latin + generic + manual

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
            "generic_count": len(generic),
            "manual_count": len(manual),
            "cached": False,
        }

        # ── Save this week's file ─────────────────────────────────────────────
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # ── Persist data to SQLite and prune old events ─────────────────────────
        init_db(None)
        cutoff_date = target_dates[0]
        deactivated = deactivate_past_events(None, cutoff_date)
        if deactivated:
            print(f"  🗄️  Deactivated {deactivated} past event(s) before saving new data")
        saved = save_events(None, salsa + latin + generic + manual)
        print(f"  💾 Saved {saved} events to SQLite database")

        # ── Delete previous week's files ──────────────────────────────────────
        delete_old_raw_files(keep_start=start_date)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── EVENTS ENDPOINT ──────────────────────────────────────────────────────
@app.get("/events")
async def events(
    date: str | None = Query(None, description="Filter by event date, e.g. 2026-06-19"),
    city: str | None = Query(None, description="Filter by event city or partial city name"),
    lat: float | None = Query(None, description="Latitude for live distance filtering"),
    lng: float | None = Query(None, description="Longitude for live distance filtering"),
    radius_km: float | None = Query(None, description="Radius in kilometers for live distance filtering"),
):
    try:
        events = get_events(None, date_filter=date)
        filtered = filter_events(events, city=city, lat=lat, lng=lng, radius_km=radius_km)
        return {
            "count": len(filtered),
            "filter": {
                "date": date,
                "city": city,
                "lat": lat,
                "lng": lng,
                "radius_km": radius_km,
            },
            "events": filtered,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
