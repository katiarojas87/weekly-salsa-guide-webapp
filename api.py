#!/usr/bin/env python3
"""
api.py — FastAPI server for the Salsa Events backend (read-only on Render)

Scraping is handled locally by scripts/scrape_and_push.py, which pushes
events via POST /push-events. Render never runs Playwright.

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""

import logging
import os
from datetime import datetime, date
from math import radians, sin, cos, sqrt, atan2

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from db import init_db, save_events, deactivate_past_events, get_events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("salsa_api")

app = FastAPI(title="Salsa Events API", version="3.0")

_allowed_origin = os.environ.get("ALLOWED_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_allowed_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


@app.on_event("startup")
def startup():
    init_db(None)
    logger.info("DB initialised. API ready.")


# ── HEALTH ────────────────────────────────────────────────────────────────────

@app.get("/")
@app.get("/health")
async def health():
    return {"status": "ok", "service": "Salsa Events API", "version": "3.0"}


# ── PUSH EVENTS (called by local scraper) ─────────────────────────────────────

@app.post("/push-events")
async def push_events(request: Request):
    """
    Receive scraped events from scripts/scrape_and_push.py and persist to DB.
    Secured with PUSH_SECRET env var (Authorization: Bearer <secret>).
    """
    secret = os.environ.get("PUSH_SECRET", "")
    auth   = request.headers.get("Authorization", "")
    if not secret or auth != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload    = await request.json()
    events     = payload.get("events", [])
    range_info = payload.get("range", {})
    scraper_errors = payload.get("errors", {})

    start_str = range_info.get("start") or str(date.today())
    try:
        cutoff = date.fromisoformat(start_str)
    except ValueError:
        cutoff = date.today()

    deactivated = deactivate_past_events(None, cutoff)
    saved       = save_events(None, events)

    logger.info(
        "push-events: deactivated=%d saved=%d range=%s→%s errors=%s",
        deactivated, saved,
        range_info.get("start"), range_info.get("end"),
        scraper_errors or "none",
    )

    return {
        "ok":                 True,
        "deactivated":        deactivated,
        "saved":              saved,
        "range":              range_info,
        "errors_from_scraper": scraper_errors,
        "received_at":        datetime.utcnow().isoformat(),
    }


# ── EVENTS (user-facing) ──────────────────────────────────────────────────────

@app.get("/events")
async def events(
    lat:       float | None = Query(None),
    lng:       float | None = Query(None),
    radius_km: float        = Query(30.0),
):
    """Return active events within radius_km of (lat, lng), sorted by distance."""
    if lat is None or lng is None:
        raise HTTPException(
            status_code=400,
            detail="lat and lng are required. Example: /events?lat=51.22&lng=4.40&radius_km=30",
        )

    today_str  = str(date.today())
    all_active = [e for e in get_events(None) if (e.get("date") or "") >= today_str]

    no_coords = [e for e in all_active if e.get("lat") is None or e.get("lng") is None]
    if no_coords:
        logger.info("Excluded %d event(s) with null coords", len(no_coords))
    geocoded = [e for e in all_active if e.get("lat") is not None and e.get("lng") is not None]

    results = []
    for ev in geocoded:
        dist = haversine_km(lat, lng, float(ev["lat"]), float(ev["lng"]))
        if dist <= radius_km:
            results.append({**ev, "distance_km": round(dist, 2)})

    results.sort(key=lambda e: e["distance_km"])

    return {
        "count":               len(results),
        "excluded_no_coords":  len(no_coords),
        "filter":              {"lat": lat, "lng": lng, "radius_km": radius_km},
        "events":              results,
    }
