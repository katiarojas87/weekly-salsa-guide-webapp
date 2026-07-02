#!/usr/bin/env python3
"""
salsalovers_scraper.py
======================
Scrapes agenda.salsalovers.be/parties
"""

import asyncio
import json
import re
import sys
import time
import random
from datetime import date, timedelta, datetime
from scrapers.utils import KNOWN_COORDS, geocode, inner_text, parse_dutch_date

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BASE_URL        = "https://agenda.salsalovers.be"
TARGET_URL      = f"{BASE_URL}/parties"

NL_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}
NL_DAYS = {4: "Vrijdag", 5: "Zaterdag", 6: "Zondag",
           0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag"}

# ─── HELPERS ──────────────────────────────────────────────────────────────────
# Shared parsing and geocoding helpers are imported from scrapers.utils.

# ─── GEOCODING ────────────────────────────────────────────────────────────────
# Source-specific geocoding helper remains below for lat/lng enrichment only.


def lookup_known_coordinates(*parts: str) -> tuple:
    for part in parts:
        key = str(part or "").strip().lower()
        if not key:
            continue
        for city_key, coords in KNOWN_COORDS.items():
            # Word-boundary match — a plain substring check would let e.g.
            # "olen" falsely match inside "volendam".
            if re.search(r'\b' + re.escape(city_key) + r'\b', key):
                return coords
    return None, None


def get_coordinates(city: str, address: str = "", coords=None) -> tuple:
    """Return (lat, lng) for an event.

    Priority:
    1. Explicit coords extracted from the event page HTML.
    2. City-centre from KNOWN_COORDS — checked via the `city` field directly,
       not by hoping the city name appears inside `address`. LocationIQ has
       repeatedly returned wrong-country matches for addresses with no
       country hint, so a verified city-centre beats a LocationIQ guess.
    3. Full street address geocoded via LocationIQ (only if city is unknown).
    4. LocationIQ on the bare city name.
    """
    if coords:
        return coords[0], coords[1]

    lat, lng = lookup_known_coordinates(city)
    if lat is not None and lng is not None:
        return lat, lng

    addr = (address or "").strip()
    if addr:
        result = geocode(addr)
        if result:
            return result[0], result[1]

    c = (city or "").strip()
    if c:
        result = geocode(c)
        if result:
            return result[0], result[1]

    return None, None


def is_bachata_only(name: str) -> bool:
    text = (name or "").lower()
    has_bachata = 'bachata' in text
    has_other = any(word in text for word in ['salsa', 'sbk', 'kizomba', 'latin', 'son', 'timba', 'cumbia'])
    return has_bachata and not has_other


def is_kizomba_only(name: str, description: str = "") -> bool:
    text = f"{name or ''} {description or ''}".lower()
    has_other = any(word in text for word in ['salsa', 'bachata', 'sbk', 'latin', 'son', 'timba', 'cumbia'])
    if has_other:
        return False
    return any(word in text for word in ['kizomba', 'semba', 'urban kizz', 'urbankizz', ' kizz'])

# ─── STEP 1: COLLECT URLS FROM LISTING ───────────────────────────────────────

def collect_urls(html: str) -> list:
    seen = set()
    urls = []
    for m in re.finditer(r'href="(/parties/([a-f0-9]{24}))"', html, re.IGNORECASE):
        party_id = m.group(2)
        if party_id not in seen:
            seen.add(party_id)
            urls.append({
                "id":  party_id,
                "url": f"{BASE_URL}{m.group(1)}",
            })
    if not urls:
        # Likely a Cloudflare challenge page or empty response
        is_cf = "cloudflare" in html.lower() or "challenge" in html.lower() or "__cf_" in html
        print(f"  WARNING: 0 event URLs found on listing page (cloudflare_challenge={is_cf}, html_size={len(html):,})")
    else:
        print(f"  Found {len(urls)} unique event URLs on listing page")
    return urls

# ─── STEP 2: PARSE DETAIL PAGE ────────────────────────────────────────────────

def parse_detail(html: str, stub: dict) -> dict:
    event = {
        "source":        "SalsaLovers",
        "id":            stub["id"],
        "url":           stub["url"],
        "name":          "",
        "venue":         "",
        "organizer":     "",
        "date":          "",
        "date_text":     "",
        "day":           "",
        "time":          "",
        "address":       "",
        "city":          "",
        "description":   "",
        "price":         "",
        "is_free":       False,
        "facebook_url":  "",
        "instagram_url": "",
        "image_url":     "",
        "coordinates":   None,
    }

    # Name
    name_m = re.search(
        r'class="[^"]*c-event__header__title[^"]*"[^>]*>\s*([^<]+?)\s*</div>',
        html, re.IGNORECASE
    )
    if name_m:
        name = name_m.group(1).strip()
        if name and len(name) > 2 and 'salsalovers' not in name.lower():
            event['name'] = name

    if not event['name']:
        for jld_raw in re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        ):
            try:
                data = json.loads(jld_raw.strip())
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get('@type') in ('Event', 'DanceEvent', 'SocialEvent'):
                        if item.get('name'):
                            event['name'] = item['name'].strip()
                            break
            except Exception:
                pass

    # Date
    date_m = re.search(
        r'(vrijdag|zaterdag|zondag|maandag|dinsdag|woensdag|donderdag)\s+'
        r'(\d{1,2})\s+'
        r'(januari|februari|maart|april|mei|juni|juli|augustus|'
        r'september|oktober|november|december)'
        r'(?:\s+(\d{4}))?',
        html, re.IGNORECASE
    )
    if date_m:
        day_word   = date_m.group(1)
        day_num    = int(date_m.group(2))
        month_word = date_m.group(3).lower()
        year       = int(date_m.group(4)) if date_m.group(4) else date.today().year
        try:
            event_date        = date(year, NL_MONTHS[month_word], day_num)
            event['date']     = str(event_date)
            event['date_text']= f"{day_word} {day_num} {month_word} {year}"
            event['day']      = NL_DAYS.get(event_date.weekday(), "").lower()
        except ValueError:
            pass

    if not event['date']:
        for jld_raw in re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        ):
            try:
                data = json.loads(jld_raw.strip())
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get('startDate'):
                        sd = item['startDate'][:10]
                        parsed = parse_dutch_date(sd)
                        if parsed:
                            event['date']     = str(parsed)
                            event['date_text']= str(parsed)
                            event['day']      = NL_DAYS.get(parsed.weekday(), "").lower()
                        break
            except Exception:
                pass

    # Time
    deuren_m = re.search(
        r'Deuren:</div>\s*<div[^>]*>\s*(\d{1,2})u(\d{2})\s*</div>',
        html, re.IGNORECASE
    )
    einde_m = re.search(
        r'Einde:</div>\s*<div[^>]*>\s*(\d{1,2})u(\d{2})\s*</div>',
        html, re.IGNORECASE
    )

    if deuren_m and einde_m:
        start = f"{deuren_m.group(1)}:{deuren_m.group(2)}"
        end   = f"{einde_m.group(1)}:{einde_m.group(2)}"
        event['time'] = f"{start} - {end}"
    elif deuren_m:
        event['time'] = f"{deuren_m.group(1)}:{deuren_m.group(2)}"
    elif einde_m:
        event['time'] = f"{einde_m.group(1)}:{einde_m.group(2)}"

    # Address
    m = re.search(
        r'class="[^"]*c-event__location__address[^"]*"[^>]*>(.*?)</',
        html, re.DOTALL | re.IGNORECASE
    )
    if m:
        address = inner_text(m.group(1))
        event['address'] = address
        city_m = re.search(
            r'\d{4}\s*[A-Z]{0,2}\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s\-]{1,25})',
            address
        )
        if city_m:
            event['city'] = city_m.group(1).strip()
        elif ',' in address:
            event['city'] = address.split(',')[-1].strip()

    if not event['address']:
        for jld_raw in re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL
        ):
            try:
                data = json.loads(jld_raw.strip())
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item.get('location'), dict):
                        addr = item['location'].get('address', {})
                        if isinstance(addr, dict):
                            street = addr.get('streetAddress', '')
                            city   = addr.get('addressLocality', '')
                            event['address'] = f"{street}, {city}".strip(', ')
                            event['city']    = city
                        elif isinstance(addr, str):
                            event['address'] = addr
                        break
            except Exception:
                pass

    # Venue
    venue_m = re.search(
        r'class="[^"]*c-event__location__name[^"]*"[^>]*>\s*([^<]+?)\s*</div>',
        html, re.IGNORECASE
    )
    if venue_m:
        event['venue'] = venue_m.group(1).strip()

    # Organizer
    org_m = re.search(
        r'c-event__header__sub-title[^>]*>\s*(?:Georganiseerd door\s*)?([^<]+?)\s*</div>',
        html, re.IGNORECASE
    )
    if org_m:
        organizer = org_m.group(1).strip()
        organizer = re.sub(r'^Georganiseerd door\s*', '', organizer, flags=re.IGNORECASE).strip()
        if organizer:
            event['organizer'] = organizer

    # Description
    desc_container = re.search(
        r'class="[^"]*c-event__description[^"]*"[^>]*>([\s\S]{10,5000})',
        html, re.IGNORECASE
    )
    if desc_container:
        block = desc_container.group(1)
        paragraphs = re.findall(r'<p[^>]*>([\s\S]*?)</p>', block, re.IGNORECASE)
        if paragraphs:
            desc = '\n'.join(inner_text(p) for p in paragraphs if inner_text(p)).strip()
            event['description'] = desc[:2000]
            event['is_free'] = bool(re.search(
                r'\bgratis\b|\bfree\b|\bentrada gratis\b', desc, re.IGNORECASE
            ))

    # Price
    price_m = re.search(
        r'(?:inkom|entrance|prijs|price|€)\s*[:\-]?\s*([€$]?\s*\d+(?:[,\.]\d+)?)',
        html, re.IGNORECASE
    )
    if price_m:
        event['price'] = price_m.group(0).strip()
    elif event['is_free']:
        event['price'] = 'Gratis'

    # Image — try multiple patterns in order of reliability
    image_url = ""

    # 1. og:image meta tag (most reliable)
    og_m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if not og_m:
        og_m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.IGNORECASE)
    if og_m:
        image_url = og_m.group(1).strip()

    # 2. __NEXT_DATA__ JSON blob (Next.js SPA)
    if not image_url:
        next_m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        if next_m:
            try:
                nd = json.loads(next_m.group(1))
                # Walk common paths
                for path in [
                    ["props", "pageProps", "event", "image"],
                    ["props", "pageProps", "party", "image"],
                    ["props", "pageProps", "data", "image"],
                ]:
                    obj = nd
                    for key in path:
                        obj = obj.get(key, {}) if isinstance(obj, dict) else {}
                    if isinstance(obj, str) and obj.startswith("http"):
                        image_url = obj
                        break
                    elif isinstance(obj, dict):
                        image_url = obj.get("url", "") or obj.get("src", "")
                        if image_url:
                            break
            except Exception:
                pass

    # 3. strapi CDN src
    if not image_url:
        strapi_m = re.search(
            r'src="(https://strapi\.salsalovers\.be/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
            html, re.IGNORECASE
        )
        if strapi_m:
            image_url = strapi_m.group(1)

    # 4. any data-src or src with image extension (lazy-loaded)
    if not image_url:
        lazy_m = re.search(
            r'data-src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
            html, re.IGNORECASE
        )
        if lazy_m:
            image_url = lazy_m.group(1)

    # 5. any https image URL anywhere in the page
    if not image_url:
        any_m = re.search(
            r'(https://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp))(?:[?&][^\s"\'<>]*)?',
            html, re.IGNORECASE
        )
        if any_m:
            candidate = any_m.group(1)
            # Skip tiny icons/logos (likely < 200px)
            if not any(x in candidate for x in ["icon", "logo", "favicon", "avatar"]):
                image_url = candidate

    if image_url:
        event['image_url'] = image_url

    # Facebook
    fb_event = re.search(r'href="(https://(?:www\.)?facebook\.com/events/\d+[^"]*)"', html)
    fb_page  = re.search(
        r'href="(https://(?:www\.)?facebook\.com/(?!events|share|sharer|login|dialog)[^"]{3,})"',
        html
    )
    if fb_event:
        event['facebook_url'] = fb_event.group(1)
    elif fb_page:
        event['facebook_url'] = fb_page.group(1)

    # Instagram
    ig = re.search(r'href="(https://(?:www\.)?instagram\.com/[^"?]+)"', html)
    if ig:
        event['instagram_url'] = ig.group(1)

    # Coordinates
    coord_m = re.search(
        r'"lat(?:itude)?"\s*[=:]\s*"?(-?\d+\.\d+)"?.{0,50}'
        r'"l(?:ng|on)(?:gitude)?"\s*[=:]\s*"?(-?\d+\.\d+)"?',
        html, re.DOTALL | re.IGNORECASE
    )
    if not coord_m:
        coord_m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+),\d+z', html)
    if coord_m:
        event['coordinates'] = [float(coord_m.group(1)), float(coord_m.group(2))]

    return event

# ─── BROWSER CONFIG ───────────────────────────────────────────────────────────

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
    locale="nl-BE",
    timezone_id="Europe/Brussels",
    extra_http_headers={"Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8"},
)

# ─── MAIN SCRAPE FUNCTION ─────────────────────────────────────────────────────

async def scrape_salsalovers(target_dates: list) -> list:
    from playwright.async_api import async_playwright

    target_set = set(str(d) for d in target_dates)

    print("\nLoading SalsaLovers listing...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx     = await browser.new_context(**BROWSER_CTX)
        await ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = await ctx.new_page()

        try:
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ⚠️  Timeout (normal for Cloudflare): {e}")

        prev = 0
        for _ in range(12):
            await page.keyboard.press("End")
            await asyncio.sleep(1.2)
            h = await page.evaluate("document.body.scrollHeight")
            if h == prev:
                break
            prev = h

        html = await page.content()
        print(f"  HTML size: {len(html):,} chars")

        stubs = collect_urls(html)
        if not stubs:
            await browser.close()
            return []

        sem = asyncio.Semaphore(1)

        async def fetch_detail(stub):
            async with sem:
                dp = await ctx.new_page()
                try:
                    await dp.goto(stub['url'], wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(random.uniform(0.4, 0.8))
                    detail_html = await dp.content()
                    return parse_detail(detail_html, stub)
                except Exception as e:
                    print(f"  ⚠️  {stub['id']}: {e}")
                    return None
                finally:
                    await dp.close()

        print(f"  Fetching {len(stubs)} detail pages...")
        results = await asyncio.gather(*[fetch_detail(s) for s in stubs])
        await browser.close()

    # Filter by date
    weekend_events = []
    for e in results:
        if e and e.get('date') in target_set:
            weekend_events.append(e)

    print(f"  Raw events in target range: {len(weekend_events)}")

    excluded_bachata_only = 0
    excluded_kizomba_only = 0
    kept = []
    for e in weekend_events:
        name = e.get('name', '')
        description = e.get('description', '')

        if is_bachata_only(name):
            excluded_bachata_only += 1
            continue
        if is_kizomba_only(name, description):
            excluded_kizomba_only += 1
            continue

        lat, lng = get_coordinates(e.get('city', ''), e.get('address', ''), e.get('coordinates'))
        evt = {k: v for k, v in e.items() if not k.startswith('_') and k != 'coordinates'}
        evt['lat'] = lat
        evt['lng'] = lng
        kept.append(evt)

    print(
        "  Funnel (SalsaLovers): "
        f"raw={len(weekend_events)}, "
        f"bachata_only_excluded={excluded_bachata_only}, "
        f"kizomba_only_excluded={excluded_kizomba_only}, "
        f"kept={len(kept)}"
    )
    return kept

# ─── STANDALONE RUN ───────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  💃 SalsaLovers Scraper — @kaatsandoval")
    print("=" * 60)

    # Auto-calculate next Monday → Sunday
    today = date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    start_date = today + timedelta(days=days_ahead)
    target_dates = [start_date + timedelta(days=i) for i in range(7)]
    print(f"\n📅 Date Range: {target_dates[0]} → {target_dates[-1]}")

    events = await scrape_salsalovers(target_dates)

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
        "source":       "SalsaLovers",
        "range": {
            "start": str(target_dates[0]),
            "end":   str(target_dates[-1]),
        },
        "days":         list(days.values()),
        "total_events": len(events),
    }

    out_file = f"salsalovers_raw_{target_dates[0]}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved: {out_file}")
    print("\n📊 Summary:")
    for day_data in output["days"]:
        print(f"  {day_data['label']}: {len(day_data['events'])} events")

    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
