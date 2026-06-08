# Weekly Salsa Guide — Project Handoff

## What this project does

Scrapes salsa events for the next Monday–Sunday from two sources, scores them by popularity using Claude, and generates Amazonika-branded Instagram slides (PNG) for each top event. One command runs the full pipeline.

---

## Folder structure

```
weekly-salsa-guide/
├── salsalovers_scraper.py   Scrapes agenda.salsalovers.be (Playwright/Chromium)
├── latinworld_scraper.py    Scrapes latinworld.nl
├── scraper.py               CLI scraper (runs both, saves raw JSON)
├── scorer.py                Pure scoring function — imported by api.py and run_pipeline.py
├── api.py                   FastAPI server for n8n (/scrape and /score endpoints)
├── generate_slides.py       Reads scored JSON → generates Amazonika PNG slides
├── run_pipeline.py          One-command orchestrator: scrape → score → slides
├── requirements.txt         Python dependencies
└── slides/                  Output folder for generated PNGs
```

---

## The one command

```bash
python run_pipeline.py --schedule THU:1,FRI:2,SAT:2,SUN:2
```

**Schedule format:** `DAY:count` pairs, comma-separated. Days omitted are skipped.
Valid day keys: `MON TUE WED THU FRI SAT SUN`

**Flags:**
- `--skip-scrape` — skip scraping, use cached `raw_events_YYYY-MM-DD.json`
- `--save-json` — save `slides/scored_events.json` for debugging
- `--output ./path` — override slide output folder (default: `./slides`)

**Example — re-score and regenerate slides without re-scraping:**
```bash
python run_pipeline.py --schedule MON:1,THU:1,FRI:2,SAT:2,SUN:2 --skip-scrape
```

---

## Environment

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # required for scoring
```

Add to `~/.zshrc` to persist.

**Dependencies:**
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Pipeline steps (run_pipeline.py)

### Step 1 — Scrape
- Imports `scrape_salsalovers()` and `scrape_latinworld()` directly (no HTTP needed)
- **One-time guard:** if `raw_events_YYYY-MM-DD.json` already exists for this week, skips scraping and returns cached data
- Saves: `raw_events_2026-06-08.json` (keyed to next Monday's date)
- Auto-deletes previous week's raw files on success
- Filters events within 120km of Antwerp

### Step 2 — Score
- Calls `scorer.score_events(raw, api_key, schedule)` — no FastAPI needed
- `schedule` dict controls which dates and how many events per day
- Claude model used: `claude-opus-4-5`, max_tokens 8192
- Exclusion rules: drops 100% bachata-only and 100% kizomba-only events strictly
- Scoring weights: Facebook attendees 40%, Instagram followers 25%, organizer reputation 15%, venue prestige 10%, recurring strength 5%, social signals 5%

### Step 3 — Generate slides
- Calls `generate_slides.render_slides(events_with_meta, output_dir)`
- Uses Playwright (headless Chromium) to screenshot each HTML slide → PNG
- Output: `slides/YYYY-MM-DD_rankN_Event_Name.png`
- Slide dimensions: 1080×1350px (Instagram 4:5 portrait)

---

## Slide design — Amazonika Design System

Brand: **Amazonika** — `https://claude.ai/design/p/019e2284-ac63-757e-bd72-e30fc8b5ffca`

Design tokens hardcoded in `generate_slides.py`:

| Token | Value | Usage |
|---|---|---|
| Gold | `#C8922A` | Top banner background |
| Dark ink | `#1C1108` | All text |
| Beige scrim | `rgba(212,180,140,0.72)` | Overlay on photo section |
| Coral | `#C0392B` | FREE badge, description accent |
| Tile bg | `rgba(255,248,236,0.82)` | Info tile background |
| Warm black | `#1A0E05` | Page background |

Fonts (Google Fonts CDN):
- **Bebas Neue** — event name (display)
- **Montserrat** — handle, labels, values
- **Cormorant Garamond italic** — description

Slide structure:
- **Top banner:** gold background + event name (Bebas Neue) + program tags
- **Bottom section:** background photo (or gradient fallback) + beige scrim
  - Handle (`@weeklysalsaguide`)
  - Description in Cormorant italic (first 2 words in coral)
  - 6 info tiles (2×3 grid): Date, Time, Location, Entrance, DJs, More Info
  - "SWIPE FOR THE NEXT DAYS →" pill at bottom

---

## Known issues / next steps

### Background photo (not yet working)
- The scraper has an `image_url` field but all events return empty — the site doesn't expose image URLs in a simple pattern
- The scraper was updated (June 2026) to try 5 extraction patterns in order:
  1. `og:image` meta tag
  2. `__NEXT_DATA__` JSON blob (Next.js)
  3. `strapi.salsalovers.be` CDN src
  4. `data-src` lazy-load attribute
  5. Any `https://` image URL on the page
- **Next step:** run the scraper fresh next week and check if `image_url` is now populated. If still empty, inspect the detail page HTML to find where the event image is embedded.
- **Workaround option:** add a `--bg-image path/to/photo.jpg` flag to `generate_slides.py` to use a fixed default background

### Empty space at bottom of slide
- The 6 info tiles don't fill the full photo section height
- Fix: increase tile padding, add `align-content: stretch` to the grid, or add a 7th tile (e.g. Program/Music genres)
- Currently skipped by user preference

### LatinWorld returning 0 events
- `latinworld_scraper.py` found 0 events in the June 2026 scrape
- May be a rendering/timing issue or the site changed structure
- Worth investigating if events are consistently missing

---

## n8n integration

API server (requires uvicorn):
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Endpoints:
- `GET /` — health check
- `POST /scrape` — runs scrapers, returns raw events JSON (cached if already done this week)
- `POST /score` — accepts raw events JSON, returns ranked events

n8n workflow: `https://krsconsultancy.app.n8n.cloud/workflow/luLTbfKCzTLRclM4`

The API and `run_pipeline.py` are independent — you don't need n8n or uvicorn to run the pipeline locally.

---

## Scraper sources

| Source | URL | Method |
|---|---|---|
| SalsaLovers | `https://agenda.salsalovers.be/parties` | Playwright (Chromium) — site blocks plain HTTP |
| LatinWorld | `https://www.latinworld.nl/salsa/agenda/` | Playwright |

Both scrapers:
- Filter events within 120km of Antwerp (`ANTWERP_COORDS = (51.2194, 4.4025)`)
- Use geocoding (known city coords dict first, then Nominatim fallback)
- Target next Monday → Sunday

---

## Scored event JSON format

Output of `scorer.score_events()`:
```json
{
  "generated_at": "2026-06-06T12:00:00",
  "range": { "start": "2026-06-08", "end": "2026-06-14" },
  "ranked_events": {
    "2026-06-12": [
      {
        "rank": 1,
        "name": "Makutano Friday Party",
        "organizer": "Makutano",
        "djs": "DJ X & DJ Y",
        "time": "22:00 - 04:00",
        "city": "Antwerp",
        "address": "Lange Lobroekstraat 30",
        "price": "€10",
        "program": "Salsa · Bachata",
        "description": "...",
        "score": 82,
        "why": "High FB attendance, recurring event...",
        "facebook_url": "https://facebook.com/...",
        "instagram_url": "https://instagram.com/...",
        "image_url": "",
        "url": "https://agenda.salsalovers.be/parties/...",
        "source": "SalsaLovers"
      }
    ]
  }
}
```

---

## How to generate slides from an existing scored JSON

```bash
python generate_slides.py --input slides/scored_events.json --output slides/
```

---

## User context

- **Brand:** Amazonika (`@weeklysalsaguide` on Instagram)
- **Region:** Belgium + Netherlands, centred on Antwerp, 120km radius
- **Languages in scraped data:** Dutch, French, English — scorer handles all three
- **Posting:** Instagram reels/carousel — slides are 1080×1350px
- **Weekly flow:** Run pipeline Saturday/Sunday → post Monday
