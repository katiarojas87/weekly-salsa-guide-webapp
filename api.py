#!/usr/bin/env python3
"""
api.py — FastAPI server for the Salsa Events backend

Run:  uvicorn api:app --host 0.0.0.0 --port 8000

Scheduling (Task 4)
-------------------
APScheduler runs the weekly scrape pipeline every Monday at 07:00 Europe/Brussels.
It executes in-process alongside the FastAPI app — no cron or external worker needed.
The app must stay running for the schedule to fire (it does when hosted as a
persistent web service on Replit, a VPS, etc.).

If you prefer a system cron instead (VPS / bare-metal only), disable the
scheduler block below and add to crontab:
    0 7 * * 1  /path/to/venv/bin/python /path/to/run_pipeline.py
"""

import asyncio
import glob
import json
import logging
import os
from datetime import datetime, date, timedelta
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from scrapers import scrape_salsalovers, scrape_latinworld
from scrapers.event_sources import scrape_generic_sources, load_manual_events
from db import init_db, save_events, deactivate_past_events, get_events

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("salsa_api")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Salsa Events API", version="2.0")

# CORS — set ALLOWED_ORIGIN env var to your frontend domain once deployed.
# Example: ALLOWED_ORIGIN=https://your-app.replit.app
# Falls back to "*" in local development only.
_allowed_origin = os.environ.get("ALLOWED_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_allowed_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_next_week_dates():
    """Return list of 7 dates: next Monday through Sunday."""
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_ahead)
    return [next_monday + timedelta(days=i) for i in range(7)]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two (lat, lng) points."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def delete_old_raw_files(keep_start: date):
    """Delete raw JSON files from previous weeks."""
    patterns = ["raw_events_*.json", "salsalovers_raw_*.json", "latinworld_raw_*.json"]
    for pattern in patterns:
        for path in glob.glob(pattern):
            if str(keep_start) not in path:
                os.remove(path)
                logger.info("Deleted old raw file: %s", path)


NL_DAYS = {0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag",
           4: "Vrijdag", 5: "Zaterdag", 6: "Zondag"}
NL_MON  = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"Mei",6:"Jun",
           7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}


# ── Scheduled pipeline (Task 4) ───────────────────────────────────────────────

def run_weekly_pipeline():
    """
    Full weekly pipeline: deactivate past events, scrape all sources, persist.
    Called by APScheduler every Monday at 07:00 Europe/Brussels.
    User-facing API endpoints NEVER call this — they only read from the DB.
    """
    logger.info("=== Weekly pipeline triggered ===")
    try:
        week_dates = get_next_week_dates()
        start_date = week_dates[0]
        out_file   = f"raw_events_{start_date}.json"

        # Step 1: deactivate past events BEFORE saving new ones
        init_db(None)
        deactivated = deactivate_past_events(None, start_date)
        logger.info("Deactivated %d past event(s)", deactivated)

        # One-time guard: don't re-scrape if we already ran this week
        if os.path.exists(out_file):
            logger.info("Already scraped this week (%s) — skipping", out_file)
            return

        # Step 2: scrape (async coroutines run in a fresh event loop)
        loop = asyncio.new_event_loop()
        try:
            salsa = loop.run_until_complete(scrape_salsalovers(week_dates))
            latin = loop.run_until_complete(scrape_latinworld(week_dates))
        finally:
            loop.close()

        generic = scrape_generic_sources(week_dates)
        manual  = load_manual_events("manual_events.json", week_dates)
        all_events = salsa + latin + generic + manual
        logger.info("Scraped %d events total", len(all_events))

        # Step 3: persist to SQLite
        saved = save_events(None, all_events)
        logger.info("Saved/upserted %d events to SQLite", saved)

        # Step 4: write raw JSON and clean up old files
        days = {}
        for d in week_dates:
            day_events = [e for e in all_events if e.get("date") == str(d)]
            days[str(d)] = {
                "date":   str(d),
                "label":  f"{NL_DAYS[d.weekday()]} {d.day} {NL_MON[d.month]}",
                "events": day_events,
            }
        result = {
            "generated_at":      datetime.now().isoformat(),
            "range":             {"start": str(week_dates[0]), "end": str(week_dates[-1])},
            "days":              list(days.values()),
            "total_events":      len(all_events),
            "salsalovers_count": len(salsa),
            "latinworld_count":  len(latin),
            "generic_count":     len(generic),
            "manual_count":      len(manual),
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        delete_old_raw_files(keep_start=start_date)
        logger.info("=== Weekly pipeline complete ===")
    except Exception:
        logger.exception("Weekly pipeline FAILED")


# ── APScheduler — every Monday at 07:00 Europe/Brussels ──────────────────────
# SQLAlchemyJobStore persists the next_run_time to disk so APScheduler can
# detect and fire a missed job (within misfire_grace_time) after a restart.
# Without this, a fresh process has no memory of the missed fire time.
# Note: this only covers restart scenarios. If the process was fully asleep
# past the grace window, UptimeRobot pinging /health prevents that case.
_JOB_STORE_URL = f"sqlite:///{Path(__file__).parent / 'apscheduler_jobs.db'}"
_scheduler = BackgroundScheduler(
    jobstores={"default": SQLAlchemyJobStore(url=_JOB_STORE_URL)},
    timezone="Europe/Brussels",
)
_scheduler.add_job(
    run_weekly_pipeline,
    trigger=CronTrigger(day_of_week="mon", hour=7, minute=0, timezone="Europe/Brussels"),
    id="weekly_pipeline",
    name="Weekly salsa scrape — every Monday 07:00 Brussels",
    replace_existing=True,
    misfire_grace_time=3600,   # allow up to 1 h late if server was briefly down
)


@app.on_event("startup")
def start_scheduler():
    _scheduler.start()
    job = _scheduler.get_job("weekly_pipeline")
    logger.info(
        "Scheduler started. Next run: %s",
        job.next_run_time if job else "unknown",
    )


@app.on_event("shutdown")
def stop_scheduler():
    _scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")

# ── HEALTH ────────────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/health")
async def health():
    """Basic liveness check."""
    return {"status": "ok", "service": "Salsa Events API", "version": "2.0"}


# ── SCHEDULER STATUS ──────────────────────────────────────────────────────────

@app.get("/scheduler/status")
async def scheduler_status():
    """Inspect APScheduler — cron expression and next run time."""
    job = _scheduler.get_job("weekly_pipeline")
    if not job:
        return {"scheduler_running": _scheduler.running, "job": None}
    return {
        "scheduler_running":  _scheduler.running,
        "job_id":             job.id,
        "job_name":           job.name,
        "cron_expression":    str(job.trigger),
        "next_run_time":      job.next_run_time.isoformat() if job.next_run_time else None,
        "misfire_grace_secs": job.misfire_grace_time,
    }

# ── SCRAPE ENDPOINT (manual/admin trigger) ────────────────────────────────────

@app.post("/scrape")
async def scrape():
    """Manually trigger the pipeline (admin use). Not called by the frontend."""
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

        salsa   = await scrape_salsalovers(target_dates)
        latin   = await scrape_latinworld(target_dates)
        generic = scrape_generic_sources(target_dates)
        manual  = load_manual_events("manual_events.json", target_dates)
        all_events = salsa + latin + generic + manual

        init_db(None)
        deactivated = deactivate_past_events(None, start_date)
        saved = save_events(None, all_events)
        logger.info("Manual scrape: deactivated=%d saved=%d", deactivated, saved)

        days = {}
        for d in target_dates:
            day_events = [e for e in all_events if e.get("date") == str(d)]
            days[str(d)] = {
                "date":   str(d),
                "label":  f"{NL_DAYS[d.weekday()]} {d.day} {NL_MON[d.month]}",
                "events": day_events,
            }
        result = {
            "generated_at":      datetime.now().isoformat(),
            "range":             {"start": str(target_dates[0]), "end": str(target_dates[-1])},
            "days":              list(days.values()),
            "total_events":      len(all_events),
            "salsalovers_count": len(salsa),
            "latinworld_count":  len(latin),
            "generic_count":     len(generic),
            "manual_count":      len(manual),
            "cached":            False,
        }
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        delete_old_raw_files(keep_start=start_date)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── EVENTS ENDPOINT (Task 5) ──────────────────────────────────────────────────

@app.get("/events")
async def events(
    lat: float | None = Query(None, description="User latitude (required)"),
    lng: float | None = Query(None, description="User longitude (required)"),
    radius_km: float = Query(30.0, description="Search radius in km (default 30)"),
):
    """
    Return active events within radius_km of the given (lat, lng).

    - lat/lng are REQUIRED — this endpoint is location-based by design.
    - radius_km defaults to 30 km.
    - Events with null geocoordinates are excluded (distance cannot be computed).
    - Results are sorted by distance ascending (closest first).
    - distance_km is computed live per request; it is NOT stored in the database.
    """
    # Require lat/lng — the whole point of this endpoint is proximity filtering
    if lat is None or lng is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "lat and lng query parameters are required. "
                "Example: /events?lat=51.2194&lng=4.4025&radius_km=30"
            ),
        )

    # Read active events from DB — NEVER trigger a live scrape here
    all_active = get_events(None)

    # Exclude events with null coordinates; log how many are dropped
    no_coords = [e for e in all_active if e.get("lat") is None or e.get("lng") is None]
    if no_coords:
        logger.info(
            "Excluded %d active event(s) with null lat/lng from distance calculation",
            len(no_coords),
        )
    geocoded = [e for e in all_active if e.get("lat") is not None and e.get("lng") is not None]

    # Compute distance and filter to radius
    results = []
    for event in geocoded:
        dist = haversine_km(lat, lng, float(event["lat"]), float(event["lng"]))
        if dist <= radius_km:
            # Attach distance_km as a computed field — not persisted anywhere
            results.append({**event, "distance_km": round(dist, 2)})

    # Sort closest first
    results.sort(key=lambda e: e["distance_km"])

    return {
        "count":              len(results),
        "excluded_no_coords": len(no_coords),
        "filter": {
            "lat":       lat,
            "lng":       lng,
            "radius_km": radius_km,
        },
        "events": results,
    }
