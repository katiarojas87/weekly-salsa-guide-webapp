"""Shared scraper utilities for parsing, fetching, and geocoding."""

import os
import re
from datetime import date, datetime

import requests
from dotenv import load_dotenv

load_dotenv()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

NL_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}

NL_DAYS = {
    4: "Vrijdag", 5: "Zaterdag", 6: "Zondag",
    0: "Maandag", 1: "Dinsdag", 2: "Woensdag", 3: "Donderdag",
}

KNOWN_COORDS = {
    "antwerpen": (51.2194, 4.4025), "antwerp": (51.2194, 4.4025),
    "mortsel": (51.1672, 4.4625), "deurne": (51.2230, 4.4660),
    "ekeren": (51.2790, 4.4150), "brecht": (51.3500, 4.6380),
    "lichtaart": (51.2330, 4.9170), "kasterlee": (51.2410, 4.9650),
    "stekene": (51.2089, 4.0386), "sint-niklaas": (51.1650, 4.1430),
    "lochristi": (51.0970, 3.8270), "gent": (51.0543, 3.7174), "ghent": (51.0543, 3.7174),
    "affligem": (50.9050, 4.1120), "steenokkerzeel": (50.9130, 4.5180),
    "kortrijk": (50.8280, 3.2650), "brussel": (50.8503, 4.3517), "brussels": (50.8503, 4.3517),
    "blankenberge": (51.3128, 3.1320), "brugge": (51.2093, 3.2247),
    "mechelen": (51.0259, 4.4776), "leuven": (50.8798, 4.3517),
    "turnhout": (51.3220, 4.9440), "hasselt": (50.9307, 5.3378), "lint": (51.1320, 4.4870),
    "rotterdam": (51.9244, 4.4777), "breda": (51.5719, 4.7683), "tilburg": (51.5555, 5.0913),
    "den haag": (52.0705, 4.3007), "scheveningen": (52.1080, 4.2730),
    "dordrecht": (51.8133, 4.6901), "eindhoven": (51.4416, 5.4697),
    "ermelo": (52.2988, 5.6211),
    "middelburg": (51.4988, 3.6109), "vlissingen": (51.4426, 3.5737),
    "terneuzen": (51.3360, 3.8280), "hulst": (51.2810, 4.0570), "goes": (51.5040, 3.8880),
    "bergen op zoom": (51.4940, 4.2870), "roosendaal": (51.5310, 4.4650),
    "utrecht": (52.0907, 5.1214), "leiden": (52.1601, 4.4970), "leiderdorp": (52.1619, 4.5400),
    "delft": (52.0116, 4.3570), "amsterdam": (52.3676, 4.9041), "amstelveen": (52.3114, 4.8701),
    "haarlem": (52.3874, 4.6462), "almere": (52.3508, 5.2647), "nijmegen": (51.8126, 5.8372),
    "arnhem": (51.9851, 5.8987), "amersfoort": (52.1561, 5.3878),
    "nieuw vennep": (52.2640, 4.6336), "hoofddorp": (52.3030, 4.6890), "rhenen": (51.9606, 5.5719),
    "zwolle": (52.5168, 6.0830), "enschede": (52.2215, 6.8937), "groningen": (53.2194, 6.5665),
    "mol": (51.1909, 5.1166), "nivelle": (50.5982, 4.3285), "nivelles": (50.5982, 4.3285),
    "ottignies-louvain-la-neuve": (50.6690, 4.6110),
}


_geocache: dict = {}
_LOCATIONIQ_KEY = os.environ.get("LOCATIONIQ_API_KEY", "")
_LOCATIONIQ_URL = "https://us1.locationiq.com/v1/search"

# Rough (lat_min, lat_max, lng_min, lng_max) boxes used to reject LocationIQ
# matches that land nowhere near the country we already know the event is in
# (e.g. a Netherlands address wrongly geocoded to a "Belgium"-qualified query).
_COUNTRY_BBOX = {
    "belgium":     (49.3, 51.6, 2.3, 6.5),
    "netherlands": (50.6, 53.7, 3.1, 7.3),
}


def _country_order(country: str) -> list:
    c = (country or "").strip().lower()
    if "nether" in c or "nederl" in c or "holland" in c:
        return ["Netherlands", "Belgium"]
    return ["Belgium", "Netherlands"]


def _in_bbox(lat: float, lng: float, country: str) -> bool:
    box = _COUNTRY_BBOX.get((country or "").strip().lower())
    if not box:
        return True
    lat_min, lat_max, lng_min, lng_max = box
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def inner_text(html: str) -> str:
    text = re.sub(r'&nbsp;', ' ', html)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&#\d+;', '', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def parse_dutch_date(text: str):
    if not text:
        return None
    t = str(text).strip().lower()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = re.search(
        r"(\d{1,2})\s+(" + "|".join(NL_MONTHS) + r")(?:\s+(\d{4}))?",
        t,
    )
    if m:
        try:
            return date(
                int(m.group(3)) if m.group(3) else date.today().year,
                NL_MONTHS[m.group(2)],
                int(m.group(1)),
            )
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(t.replace('z', '+00:00')).date()
    except Exception:
        pass
    return None


def fetch_html(url: str, timeout: int = 20):
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.text
    except Exception:
        return ""


def _looks_like_address(text: str) -> bool:
    """True if the string appears to be a street address rather than a city name."""
    return bool(re.search(r'\d', text))


def geocode(location: str, country: str = None):
    """Return (lat, lng) for a location string.

    Street addresses (containing digits) are sent to LocationIQ first so that
    the specific location is returned, not a city-centre fallback.
    Pure city names use KNOWN_COORDS first for speed, then LocationIQ.

    `country`, when known (e.g. from the event's own JSON-LD address), is
    queried first and used to sanity-check the result — otherwise a bad
    LocationIQ match for the wrong country (e.g. "Amsterdam, Belgium"
    resolving to some unrelated Belgian point) gets accepted as-is.
    """
    key = str(location).strip().lower()
    if not key:
        return None
    cache_key = f"{key}|{(country or '').strip().lower()}"
    if cache_key in _geocache:
        return _geocache[cache_key]

    is_address = _looks_like_address(key)

    if not is_address:
        # Fast path for city-only names
        for city_key, coords in KNOWN_COORDS.items():
            if re.search(r'\b' + re.escape(city_key) + r'\b', key):
                _geocache[cache_key] = coords
                return coords

    # Try LocationIQ — known country first (if any), then the other, then bare
    if _LOCATIONIQ_KEY:
        countries = _country_order(country)
        for query, query_country in [(f"{location}, {c}", c) for c in countries] + [(location, None)]:
            try:
                resp = requests.get(
                    _LOCATIONIQ_URL,
                    params={"key": _LOCATIONIQ_KEY, "q": query, "format": "json", "limit": 1},
                    timeout=10,
                )
                if resp.ok:
                    data = resp.json()
                    if data:
                        lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
                        if query_country and not _in_bbox(lat, lng, query_country):
                            continue
                        _geocache[cache_key] = (lat, lng)
                        return (lat, lng)
            except Exception:
                pass

    # Last resort for full addresses: fall back to city-centre from KNOWN_COORDS
    if is_address:
        for city_key, coords in KNOWN_COORDS.items():
            if re.search(r'\b' + re.escape(city_key) + r'\b', key):
                _geocache[cache_key] = coords
                return coords

    _geocache[cache_key] = None
    return None
