#!/usr/bin/env python3
"""
scrapers/salsavida.py
======================
Scrapes https://www.salsavida.com/ for salsa/bachata/latin events in Belgium
and the Netherlands.

Strategy
--------
- Pull event URLs from country listing pages + major NL city pages (Amsterdam,
  Rotterdam, Utrecht) where the country page under-represents local weekly events.
- Each event detail page carries a JSON-LD <script type="application/ld+json">
  block with startDate/endDate, location (address + lat/lng), organizer, and
  description — used as primary data source.
- HTML meta / og tags used as fallback for name and image.
- No Playwright needed: server-rendered HTML, no anti-scraping measures.

Standalone run:
    python scrapers/salsavida.py
    -> prints 3-5 sample events to stdout, saves salsavida_raw_YYYY-MM-DD.json

Import:
    from scrapers.salsavida import scrape_salsavida
    events = scrape_salsavida(target_dates)
"""

import json
import re
import sys
import time
import random
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from scrapers.utils import fetch_html, geocode, inner_text, NL_DAYS

# ─── CONFIG ──────────────────────────────────────────────────────────────────

BASE_URL = "https://www.salsavida.com"

# Country-level listing pages — returned events are already filtered to upcoming
LISTING_PAGES = [
    f"{BASE_URL}/guides/belgium/",
    f"{BASE_URL}/guides/netherlands/amsterdam/",
    f"{BASE_URL}/guides/netherlands/rotterdam/",
    f"{BASE_URL}/guides/netherlands/utrecht/",
    f"{BASE_URL}/guides/netherlands/",           # catches less-covered NL cities
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

LATIN_GENRES = [
    "salsa", "bachata", "kizomba", "sbk", "son cubano", "cubaanse salsa",
    "merengue", "cumbia", "latin", "timba", "zouk", "mambo", "rueda",
]

# ─── CANONICAL EVENT TEMPLATE ────────────────────────────────────────────────

def _empty_event() -> dict:
    return {
        "source":        "SalsaVida",
        "source_id":     "",
        "url":           "",
        "name":          "",
        "date":          "",
        "day":           "",
        "time":          "",
        "venue":         "",
        "organizer":     "",
        "address":       "",
        "city":          "",
        "country":       "",
        "lat":           None,
        "lng":           None,
        "price":         "",
        "is_free":       False,
        "description":   "",
        "facebook_url":  "",
        "instagram_url": "",
        "image_url":     "",
        "music_genres":  "",
        "djs":           "",
        "source_meta":   {},
    }

# ─── FILTER HELPERS ──────────────────────────────────────────────────────────

def _is_bachata_only(name: str, desc: str = "") -> bool:
    text = f"{name} {desc}".lower()
    has_bachata = "bachata" in text
    has_other = any(w in text for w in ["salsa", "sbk", "kizomba", "latin", "son", "timba", "cumbia", "zouk", "rueda", "mambo"])
    return has_bachata and not has_other


def _is_kizomba_only(name: str, desc: str = "") -> bool:
    text = f"{name} {desc}".lower()
    has_other = any(w in text for w in ["salsa", "bachata", "sbk", "latin", "son", "timba", "cumbia", "zouk", "rueda", "mambo"])
    if has_other:
        return False
    return any(w in text for w in ["kizomba", "semba", "urban kizz", "urbankizz", " kizz"])

# ─── LISTING SCRAPE ──────────────────────────────────────────────────────────

def collect_event_urls(target_dates: list) -> list:
    """Fetch all listing pages and return deduplicated event detail URLs
    whose slug path may correspond to target_dates (broad — detail page
    confirms actual date)."""
    target_set = set(str(d) for d in target_dates)
    seen: set = set()
    urls: list = []

    for page_url in LISTING_PAGES:
        html = fetch_html(page_url)
        if not html:
            print(f"  Warning: could not fetch listing {page_url}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/event/" not in href:
                continue
            if href not in seen:
                seen.add(href)
                urls.append(href)
        time.sleep(random.uniform(0.3, 0.7))

    print(f"  Collected {len(urls)} unique SalsaVida event URLs across all listing pages")
    return urls

# ─── DETAIL PAGE PARSE ───────────────────────────────────────────────────────

def parse_detail(url: str, target_set: set) -> list:
    """Fetch a detail page and return a list of canonical events (may be 0, 1,
    or more if the page represents a recurring event with multiple occurrence
    dates within target_set)."""
    html = fetch_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    # ── JSON-LD ──────────────────────────────────────────────────────────────
    ld_events: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("Event", "DanceEvent", "SocialEvent", "MusicEvent"):
                    ld_events.append(item)
        except Exception:
            pass

    if not ld_events:
        return []

    # og:image fallback
    og_img = ""
    m = soup.find("meta", property="og:image")
    if m:
        og_img = m.get("content", "")

    results = []
    for ld in ld_events:
        start_raw = ld.get("startDate", "")
        end_raw   = ld.get("endDate", "")

        if not start_raw:
            continue

        # Parse ISO date
        try:
            start_dt = datetime.fromisoformat(start_raw)
            event_date = str(start_dt.date())
        except Exception:
            event_date = start_raw[:10] if len(start_raw) >= 10 else ""

        if not event_date or event_date not in target_set:
            continue

        event = _empty_event()
        event["url"] = url
        event["source_id"] = url.rstrip("/").rsplit("/", 1)[-1]

        # Name
        event["name"] = ld.get("name", "").strip()
        if not event["name"]:
            og_t = soup.find("meta", property="og:title")
            if og_t:
                event["name"] = og_t.get("content", "").split(" - ")[0].strip()

        # Date / time
        event["date"] = event_date
        try:
            event["day"] = NL_DAYS.get(start_dt.date().weekday(), "").lower()
        except Exception:
            pass

        try:
            start_time = start_dt.strftime("%H:%M")
            if end_raw:
                end_dt = datetime.fromisoformat(end_raw)
                event["time"] = f"{start_time} - {end_dt.strftime('%H:%M')}"
            else:
                event["time"] = start_time
        except Exception:
            pass

        # Location
        loc = ld.get("location", {})
        if isinstance(loc, dict):
            event["venue"] = loc.get("name", "")
            addr = loc.get("address", {})
            if isinstance(addr, dict):
                street = addr.get("streetAddress", "")
                city   = addr.get("addressLocality", "")
                country = addr.get("addressCountry", "")
                event["address"] = street
                event["city"]    = city
                event["country"] = _normalize_country(country)
            elif isinstance(addr, str):
                event["address"] = addr
            # Coordinates from JSON-LD geo — most reliable, no API call needed
            geo = loc.get("geo", {})
            if isinstance(geo, dict):
                try:
                    event["lat"] = float(geo.get("latitude") or 0) or None
                    event["lng"] = float(geo.get("longitude") or 0) or None
                except Exception:
                    pass

        # Geocode fallback if no lat/lng from JSON-LD
        if event["lat"] is None and (event["city"] or event["address"]):
            coords = geocode(event["city"] or event["address"], event.get("country"))
            if coords:
                event["lat"], event["lng"] = coords[0], coords[1]

        # Country fallback from URL path
        if not event["country"]:
            if "/event/belgium/" in url:
                event["country"] = "Belgium"
            elif "/event/netherlands/" in url:
                event["country"] = "Netherlands"

        # Organizer
        org = ld.get("organizer", {})
        if isinstance(org, dict):
            event["organizer"] = org.get("name", "")
        elif isinstance(org, str):
            event["organizer"] = org
        if not event["organizer"] and event["venue"]:
            event["organizer"] = event["venue"]

        # Description
        desc = ld.get("description", "")
        event["description"] = desc[:2000] if desc else ""

        # Price / is_free
        offers = ld.get("offers", {})
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            price_val = offers.get("price", "")
            currency  = offers.get("priceCurrency", "")
            if str(price_val) == "0" or str(price_val) == "0.0":
                event["is_free"] = True
                event["price"]   = "Free"
            elif price_val:
                event["price"] = f"{currency} {price_val}".strip()
        if not event["price"]:
            desc_lower = event["description"].lower()
            if re.search(r"\bfree\b|\bgratis\b", desc_lower):
                event["is_free"] = True
                event["price"]   = "Free"

        # Image
        images = ld.get("image", [])
        if isinstance(images, str):
            images = [images]
        if isinstance(images, list) and images:
            candidate = images[0]
            # Prefer a non-default/non-placeholder image
            if "default" not in candidate.lower() and candidate.startswith("http"):
                event["image_url"] = candidate
        if not event["image_url"] and og_img and "default" not in og_img.lower():
            event["image_url"] = og_img

        # Social links — from visible HTML
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not event["facebook_url"] and "facebook.com" in href and "/events/" in href:
                event["facebook_url"] = href
            elif not event["facebook_url"] and "facebook.com" in href and "/groups/" not in href:
                event["facebook_url"] = href
            if not event["instagram_url"] and "instagram.com" in href:
                event["instagram_url"] = href.split("?")[0]

        # Music genres from tags/text
        tags_text = " ".join(
            t.get_text(strip=True).lower()
            for t in soup.find_all(class_=re.compile(r"tag|genre|label", re.I))
        )
        found_genres = [g for g in LATIN_GENRES if g in tags_text or g in event["name"].lower() or g in event["description"].lower()]
        event["music_genres"] = ", ".join(sorted(set(found_genres)))

        # source_meta: salsavida event type label (Social, Lesson, Festival…)
        breadcrumb = soup.find(class_=re.compile(r"breadcrumb", re.I))
        event_type_m = re.search(r'\b(Social|Lesson|Festival|Party|Concert|Workshop)\b',
                                  soup.get_text(" ", strip=True)[:400], re.I)
        event["source_meta"] = {
            "event_type": event_type_m.group(1) if event_type_m else "",
        }

        results.append(event)

    return results

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _normalize_country(raw: str) -> str:
    r = (raw or "").strip().upper()
    if r in ("BE", "BEL", "BELGIUM"):
        return "Belgium"
    if r in ("NL", "NLD", "NETHERLANDS", "THE NETHERLANDS"):
        return "Netherlands"
    if raw and len(raw) > 2:
        return raw.strip().title()
    return raw

# ─── MAIN SCRAPE FUNCTION ────────────────────────────────────────────────────

def scrape_salsavida(target_dates: list) -> list:
    target_set = set(str(d) for d in target_dates)

    print("\nLoading SalsaVida listings...")
    event_urls = collect_event_urls(target_dates)

    kept:             list = []
    excluded_bachata: int  = 0
    excluded_kizomba: int  = 0
    checked:          int  = 0

    for url in event_urls:
        checked += 1
        try:
            events = parse_detail(url, target_set)
        except Exception as exc:
            print(f"  Warning: {url}: {exc}")
            events = []
        for ev in events:
            if _is_bachata_only(ev["name"], ev["description"]):
                excluded_bachata += 1
                continue
            if _is_kizomba_only(ev["name"], ev["description"]):
                excluded_kizomba += 1
                continue
            kept.append(ev)
        time.sleep(random.uniform(0.2, 0.5))

    print(
        f"  Funnel (SalsaVida): checked={checked}, "
        f"in_range={len(kept) + excluded_bachata + excluded_kizomba}, "
        f"bachata_only_excluded={excluded_bachata}, "
        f"kizomba_only_excluded={excluded_kizomba}, "
        f"kept={len(kept)}"
    )
    return kept

# ─── STANDALONE RUN ──────────────────────────────────────────────────────────

async def main():
    from datetime import date, timedelta
    import json

    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    start_date = today + timedelta(days=days_ahead)
    target_dates = [start_date + timedelta(days=i) for i in range(7)]

    print("=" * 60)
    print("  💃 SalsaVida Scraper — @kaatsandoval")
    print("=" * 60)
    print(f"\nDate Range: {target_dates[0]} → {target_dates[-1]}")

    events = scrape_salsavida(target_dates)

    if not events:
        print("\nNo events found.")
        sys.exit(0)

    NL_MON = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"Mei",6:"Jun",
              7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}
    days: dict = {}
    for d in target_dates:
        day_events = [e for e in events if e["date"] == str(d)]
        days[str(d)] = {
            "date":   str(d),
            "label":  f"{NL_DAYS[d.weekday()]} {d.day} {NL_MON[d.month]}",
            "events": day_events,
        }

    output = {
        "generated_at": datetime.now().isoformat(),
        "source":       "SalsaVida",
        "range":        {"start": str(target_dates[0]), "end": str(target_dates[-1])},
        "days":         list(days.values()),
        "total_events": len(events),
    }

    out_file = f"salsavida_raw_{target_dates[0]}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved: {out_file}")
    print("\nSummary:")
    for day_data in output["days"]:
        print(f"  {day_data['label']}: {len(day_data['events'])} events")

    print("\nSample events (up to 5):")
    for ev in events[:5]:
        print(f"  [{ev['date']}] {ev['name'][:60]} @ {ev['city']} | lat={ev['lat']} lng={ev['lng']}")
        required_keys = [
            "source","source_id","url","name","date","day","time","venue","organizer",
            "address","city","country","lat","lng","price","is_free","description",
            "facebook_url","instagram_url","image_url","music_genres","djs","source_meta",
        ]
        missing = [k for k in required_keys if k not in ev]
        if missing:
            print(f"    MISSING KEYS: {missing}")
        else:
            print(f"    Schema OK — all {len(required_keys)} keys present")

    print("\nDone!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
