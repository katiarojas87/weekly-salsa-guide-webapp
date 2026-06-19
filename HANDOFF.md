# Weekly Salsa Guide — Backend Handoff

## What this repo does

Scrapes weekly salsa events from active sources, normalizes the data, persists it to SQLite, and exposes event search via a FastAPI API.

## Active files

- `api.py` — FastAPI server with `/scrape`, `/events`, and `/health`
- `run_pipeline.py` — CLI entry point to scrape the current week and persist to `events.db`
- `scraper.py` — alternate CLI scraper that saves raw weekly JSON
- `scrapers/salsalovers.py` — scraper for agenda.salsalovers.be
- `scrapers/latinworld.py` — scraper for latinworld.nl
- `scrapers/event_sources.py` — generic JSON-LD and manual event loader
- `db.py` — SQLite persistence, deduplication, and active-event filtering
- `requirements.txt` — Python dependencies

## Removed legacy functionality

This repo no longer uses Claude/Anthropic scoring, slide generation, Cloudinary upload, or n8n-specific workflow code. The current backend is focused on event ingestion, persistence, and query.

## Run the pipeline

```bash
python run_pipeline.py
```

This will:
- scrape next Monday–Sunday events from the active sources
- save `raw_events_YYYY-MM-DD.json`
- persist normalized events into `events.db`
- deactivate older past events

## Start the API

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

## API endpoints

- `GET /` — health check
- `POST /scrape` — run this week's scrape and persist events
- `GET /events` — query active events from SQLite
  - optional query params: `date`, `city`, `lat`, `lng`, `radius_km`

## Notes

- Old raw JSON files are cleaned up automatically after a new weekly scrape.
- Active events are served from `events.db`; past events are marked inactive when new data is loaded.
- The current codebase is backend-only and does not include slide or Cloudinary functionality.
