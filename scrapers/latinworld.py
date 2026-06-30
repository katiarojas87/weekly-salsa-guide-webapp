#!/usr/bin/env python3
"""
latinworld_scraper.py
=====================
Scrapes www.latinworld.nl/salsa/agenda/ for salsa/bachata events.

Structure (confirmed by inspection):
  - Date headers: <td colspan="4" class="bg-primary"><b>vrijdag 29 mei 2026: week 22</b></td>
  - Event rows below each header with a link to detail page
  - Detail page has a <table style="width: 100%"> with rows:
      datum, tijd, entree, Muziek/dans, dj's/artiesten, etc.
  - Only include events where Muziek/dans contains 'salsa' or 'bachata' or 'kizomba' or 'sbk'

Run standalone:
  python latinworld_scraper.py
  -> saves latinworld_raw_YYYY-MM-DD.json

Or import:
  from latinworld_scraper import scrape_latinworld
"""

import asyncio
import json
import re
import sys
import time
import random
from datetime import date, timedelta, datetime
from scrapers.utils import KNOWN_COORDS, geocode, inner_text, parse_dutch_date

# --- CONFIG ---
LATINWORLD_URL  = "https://www.latinworld.nl/salsa/agenda/?periode=1"
BASE_URL        = "https://www.latinworld.nl/"

LATIN_GENRES = ['salsa', 'bachata', 'kizomba', 'sbk', 'son cubano', 'cubaanse salsa',
                'merengue', 'cumbia', 'latin', 'timba']

NL_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}
NL_DAYS = {4: "Vrijdag", 5: "Zaterdag", 6: "Zondag",
           0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag"}

# --- GEOCODING ---

# Use shared `geocode`, `inner_text`, and `parse_dutch_date` from `scrapers.utils`.
# Keep source-specific helpers (lat/lng enrichment) below and call into the shared utils.

def lookup_known_coordinates(*parts: str) -> tuple:
    for part in parts:
        key = str(part or "").strip().lower()
        if not key:
            continue
        for city_key, coords in KNOWN_COORDS.items():
            if city_key in key:
                return coords
    return None, None


def get_coordinates(city: str, address: str = "") -> tuple:
    """Return (lat, lng) for an event.

    Priority:
    1. Full street address geocoded via Nominatim (most accurate).
    2. City-centre from KNOWN_COORDS (fast city-level fallback).
    3. Nominatim on bare city name.
    """
    # Geocode the full address — geocode() uses Nominatim first for street addresses
    addr = (address or "").strip()
    if addr:
        result = geocode(addr)
        if result:
            return result[0], result[1]

    # Fall back to city-centre (city name only, never address string)
    lat, lng = lookup_known_coordinates(city)
    if lat is not None and lng is not None:
        return lat, lng

    c = (city or "").strip()
    if c:
        result = geocode(c)
        if result:
            return result[0], result[1]

    return None, None

# HTML parsing uses shared `inner_text` from scrapers.utils

# --- PARSE LISTING PAGE ---

def parse_listing(html: str, target_dates: list) -> list:
    target_set = set(str(d) for d in target_dates)
    events = []
    current_date = None

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)

    for row in rows:
        if 'bg-primary' in row and 'colspan' in row:
            header_text = inner_text(row)
            header_text = re.sub(r':?\s*week\s*\d+', '', header_text, flags=re.IGNORECASE).strip()
            parsed = parse_dutch_date(header_text)
            if parsed:
                current_date = parsed
            continue

        if not current_date or str(current_date) not in target_set:
            continue

        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 3:
            continue

        link_m = re.search(
            r'href=["\']([^"\']*latin[^"\']+)["\'][^>]*>(.*?)</a>',
            cells[2], re.DOTALL | re.IGNORECASE
        )
        if not link_m:
            continue

        raw_url   = link_m.group(1)
        if raw_url.startswith('http'):
            event_url = raw_url
        elif raw_url.startswith('/'):
            event_url = BASE_URL.rstrip('/') + raw_url
        else:
            event_url = BASE_URL.rstrip('/') + '/' + raw_url

        raw_name  = inner_text(link_m.group(2))
        name      = re.sub(r'\s+\d+\s*$', '', raw_name).strip()
        if not name or len(name) < 3:
            continue

        city = inner_text(cells[0]).strip()

        time_raw = inner_text(cells[1])
        time_m   = re.search(r'(\d{1,2})[:\.](\d{2})', time_raw)
        event_time = f"{time_m.group(1)}:{time_m.group(2)}" if time_m else ""

        organizer = inner_text(cells[3]).strip() if len(cells) > 3 else ""

        events.append({
            "source":        "LatinWorld",
            "url":           event_url,
            "name":          name,
            "venue":         "",
            "organizer":     organizer,
            "date":          str(current_date),
            "day":           NL_DAYS.get(current_date.weekday(), "").lower(),
            "time":          event_time,
            "city":          city,
            "address":       "",
            "price":         "",
            "djs":           "",
            "music_genres":  "",
            "description":   "",
            "facebook_url":  "",
            "instagram_url": "",
            "is_free":       False,
            "image_url":     "",
            "lat":           None,
            "lng":           None,
        })

    print(f"  Found {len(events)} LatinWorld events for target weekend")
    return events

# --- PARSE DETAIL PAGE ---

def parse_detail(html: str, event: dict) -> dict:
    updated = dict(event)

    def looks_like_country(text: str) -> bool:
        t = (text or "").strip().lower()
        return any(k in t for k in ["netherlands", "nederland", "belgium", "belgie", "belgië"])

    # Venue is optional: extract first non-empty text anchor to /latin/dansscholen/.
    venue_matches = re.findall(
        r'<a[^>]+href=["\'][^"\']*latin/dansscholen/[^/"\'][^"\']*["\'][^>]*>(.*?)</a>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    for vm in venue_matches:
        venue = inner_text(vm).strip()
        if venue.lower() == "latin dansscholen":
            continue
        if venue:
            updated["venue"] = venue
            break

    # Organizer selector: link to /organisaties/ path is the consistent source.
    org_m = re.search(
        r'<td[^>]*>\s*<a[^>]+href=["\'][^"\']*organisaties/[^"\']*["\'][^>]*>(.*?)</a>\s*</td>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if org_m:
        organizer = inner_text(org_m.group(1)).strip()
        if organizer:
            updated["organizer"] = organizer

    # Common detail-row structure on LatinWorld:
    # organizer(/organisaties/) + address + city + country in adjacent <td> cells.
    oac_m = re.search(
        r'<td[^>]*>\s*<a[^>]+href=["\'][^"\']*organisaties/[^"\']*["\'][^>]*>.*?</a>\s*</td>\s*'
        r'<td[^>]*>\s*([^<][^<]*?)\s*</td>\s*'
        r'<td[^>]*>\s*([^<][^<]*?)\s*</td>\s*'
        r'<td[^>]*>\s*([^<][^<]*?)\s*</td>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if oac_m:
        addr = inner_text(oac_m.group(1)).strip()
        cty = inner_text(oac_m.group(2)).strip()
        ctry = inner_text(oac_m.group(3)).strip()
        if addr:
            updated["address"] = addr
        if cty:
            updated["city"] = cty
        if ctry:
            updated["country"] = ctry

    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    parsed_rows = []

    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) < 2:
            continue

        label = inner_text(cells[0]).strip().lower()
        value = inner_text(cells[1]).strip()
        parsed_rows.append((label, value))

        if not value:
            continue

        if 'tijd' in label:
            updated['time'] = value

        elif 'entree' in label:
            updated['price'] = value
            updated['is_free'] = bool(re.search(r'\bgratis\b|\bfree\b|\b0\s*euro\b', value, re.IGNORECASE))

        elif 'muziek' in label or 'dans' in label:
            updated['music_genres'] = value
            genres_lower = value.lower()
            updated['_is_latin'] = any(g in genres_lower for g in LATIN_GENRES)

        elif "dj" in label or "artiest" in label:
            updated['djs'] = value

        elif 'locatie' in label or 'venue' in label:
            if not updated.get('organizer'):
                updated['organizer'] = value

        elif 'adres' in label or 'address' in label:
            updated['address'] = value
            if not updated.get('city') or updated['city'] == '':
                city_m = re.search(r'\d{4}\s*[A-Z]{0,2}\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-]{2,25})', value)
                if city_m:
                    updated['city'] = city_m.group(1).strip()

        elif 'land' in label or 'country' in label:
            updated['country'] = value

    for label, value in parsed_rows:
        if value and ('omschrijving' in label or 'beschrijving' in label or 'description' in label):
            updated['description'] = value[:300]
            break

    # If venue is missing, use organizer as a conservative fallback label.
    if not updated.get('venue') and updated.get('organizer'):
        updated['venue'] = updated['organizer']

    # LatinWorld often puts city/country in blank-label rows after the address row.
    for idx, (label, value) in enumerate(parsed_rows):
        if 'adres' in label or 'address' in label:
            # Next non-empty blank-label row -> city
            for j in range(idx + 1, min(idx + 5, len(parsed_rows))):
                nl, nv = parsed_rows[j]
                if nv and nl == "":
                    if not updated.get('city'):
                        updated['city'] = nv
                        continue
                    if not updated.get('country') and looks_like_country(nv):
                        updated['country'] = nv
                        break
            break

    if not updated.get('description'):
        div_blocks = re.findall(r'<div[^>]*>([\s\S]*?)</div>', html, re.IGNORECASE)
        for block in div_blocks:
            paragraphs = re.findall(r'<p[^>]*>([\s\S]*?)</p>', block, re.IGNORECASE)
            texts = [inner_text(p) for p in paragraphs if inner_text(p).strip()]
            if len(texts) >= 2:
                desc = '\n'.join(texts).strip()
                if len(desc) > 80:
                    updated['description'] = desc[:2000]
                    break

    fb = re.search(r'href="(https://(?:www\.)?facebook\.com/(?:events/)?\S+)"', html)
    if fb:
        updated['facebook_url'] = fb.group(1)

    ig = re.search(r'href="(https://(?:www\.)?instagram\.com/[^"?]+)"', html)
    if ig:
        updated['instagram_url'] = ig.group(1)

    img = re.search(r'<img[^>]+src="(https://[^"]+\.(?:jpg|jpeg|png|webp))[^"]*"', html, re.IGNORECASE)
    if img:
        updated['image_url'] = img.group(1)

    # Country fallback for rows where the site omits the country cell.
    if not updated.get('country'):
        text = f"{updated.get('address', '')} {updated.get('city', '')}".lower()
        if any(k in text for k in ['belgium', 'belgie', 'belgië']):
            updated['country'] = 'Belgium'
        elif text.strip():
            updated['country'] = 'Netherlands'

    return updated

# --- BROWSER CONFIG ---

BROWSER_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-zygote",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
]
BROWSER_CTX = dict(
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    viewport={"width": 1280, "height": 900},
    locale="nl-NL",
    timezone_id="Europe/Amsterdam",
    extra_http_headers={"Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"},
)

# --- MAIN SCRAPE FUNCTION ---

async def scrape_latinworld(target_dates: list) -> list:
    from playwright.async_api import async_playwright

    print("\nLoading LatinWorld...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx     = await browser.new_context(**BROWSER_CTX)
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = await ctx.new_page()

        try:
            await page.goto(LATINWORLD_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ⚠️  {e}")

        for _ in range(6):
            await page.keyboard.press("End")
            await asyncio.sleep(0.8)

        html = await page.content()
        print(f"  HTML size: {len(html):,} chars")

        events = parse_listing(html, target_dates)
        if not events:
            print("  Warning: no LatinWorld events found for this weekend")
            await browser.close()
            return []

        sem = asyncio.Semaphore(2)

        async def fetch_detail(event):
            async with sem:
                dp = await ctx.new_page()
                try:
                    await dp.goto(event['url'], wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(random.uniform(0.4, 0.9))
                    detail_html = await dp.content()
                    return parse_detail(detail_html, event)
                except Exception as e:
                    print(f"  ⚠️  {event['name'][:30]}: {e}")
                    return event
                finally:
                    await dp.close()

        enriched = await asyncio.gather(*[fetch_detail(e) for e in events])
        await browser.close()

    raw_events = list(enriched)
    print(f"  Raw events in target range: {len(raw_events)}")

    def is_bachata_only(name: str) -> bool:
        name_lower = name.lower()
        has_bachata = 'bachata' in name_lower
        has_other   = any(w in name_lower for w in ['salsa', 'sbk', 'kizomba', 'latin', 'son', 'timba', 'cumbia'])
        return has_bachata and not has_other

    def is_kizomba_only(name: str, genres: str) -> bool:
        """True if the event is purely kizomba/semba/urban with NO salsa.
        This feed is salsa-first, so kizomba-only events are excluded."""
        text = f"{name} {genres}".lower()
        has_other = any(w in text for w in ['salsa', 'bachata', 'sbk', 'latin', 'son', 'timba', 'cumbia'])
        if has_other:
            return False
        has_kizomba = any(w in text for w in ['kizomba', 'semba', 'urban kizz', 'urbankizz', ' kizz'])
        return has_kizomba

    excluded_bachata_only = 0
    excluded_kizomba_only = 0
    filtered_events = []
    for e in raw_events:
        name = e.get('name', '')
        genres = e.get('music_genres', '')

        if is_bachata_only(name):
            excluded_bachata_only += 1
            continue
        if is_kizomba_only(name, genres):
            excluded_kizomba_only += 1
            continue
        filtered_events.append(e)

    kept_events = []
    for e in filtered_events:
        lat, lng = get_coordinates(e.get('city', ''), e.get('address', ''))
        evt = {**e}
        evt['lat'] = lat
        evt['lng'] = lng
        evt = {k: v for k, v in evt.items() if not k.startswith('_')}
        kept_events.append(evt)

    print(
        "  Funnel (LatinWorld): "
        f"raw={len(raw_events)}, "
        f"bachata_only_excluded={excluded_bachata_only}, "
        f"kizomba_only_excluded={excluded_kizomba_only}, "
        f"kept={len(kept_events)}"
    )
    return kept_events

# --- STANDALONE RUN ---

async def main():
    print("=" * 60)
    print("  🌎 LatinWorld Scraper — @kaatsandoval")
    print("=" * 60)

    # Auto-calculate next Monday → Sunday
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    start_date = today + timedelta(days=days_ahead)
    target_dates = [start_date + timedelta(days=i) for i in range(7)]
    print(f"\n📅 Date Range: {target_dates[0]} → {target_dates[-1]}")

    events = await scrape_latinworld(target_dates)

    if not events:
        print("\n❌ No events found.")
        sys.exit(0)

    NL_MON = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"Mei",6:"Jun",
              7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}
    days = {}
    for d in target_dates:
        day_events = [e for e in events if e['date'] == str(d)]
        days[str(d)] = {
            "date":   str(d),
            "label":  f"{NL_DAYS[d.weekday()]} {d.day} {NL_MON[d.month]}",
            "events": day_events,
        }

    output = {
        "generated_at": datetime.now().isoformat(),
        "source": "LatinWorld",
        "range": {
            "start": str(target_dates[0]),
            "end":   str(target_dates[-1]),
        },
        "days": list(days.values()),
        "total_events": len(events),
    }

    out_file = f"latinworld_raw_{target_dates[0]}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved: {out_file}")
    print("\n📊 Summary:")
    for day_data in output["days"]:
        print(f"  {day_data['label']}: {len(day_data['events'])} events")

    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
