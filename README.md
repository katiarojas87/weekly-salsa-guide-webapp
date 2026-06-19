# Weekly Salsa Guide

This repository shows nearby salsa events, classes, and congresses based on the user's location.

## Overview

The project scrapes weekly event data, stores normalized events in SQLite, and serves a FastAPI API that filters active events live by distance.

## What it does

- Scrapes upcoming salsa events from active source websites.
- Normalizes event data.
- Persists events to SQLite.
- Serves event search through a FastAPI API.

## Important files

| File | Purpose |
|---|---|
| `run_pipeline.py` | Weekly scraping pipeline entry point |
| `scraper.py` | Scraper orchestration helpers |
| `api.py` | FastAPI API with health, scheduler, and `/events` endpoint |
| `db.py` | SQLite schema and persistence helpers |
| `scrapers/` | Source-specific scrapers and utilities |
| `manual_events.json` | Fallback/manual event data |
| `event_sources.json` | Generic event source list |
| `requirements.txt` | Python dependencies |

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Commands

```bash
python run_pipeline.py
uvicorn api:app --host 0.0.0.0 --port 8000
```

## API

- `GET /health` — liveness check
- `POST /scrape` — manual admin trigger for the weekly scrape pipeline
- `GET /events?lat=...&lng=...&radius_km=...` — returns active events within range, sorted by computed distance

## Scheduling

The API runs an APScheduler job every Monday at 07:00 Europe/Brussels and persists scheduler state to `apscheduler_jobs.db` so missed runs can be recovered after a restart within the configured grace window.
