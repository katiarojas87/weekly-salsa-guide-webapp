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
    # "leuven" was previously (50.8798, 4.3517) — Brussels' longitude, a
    # copy-paste bug caught by the Fix 4 coordinate audit. Corrected below.
    "mechelen": (51.0259, 4.4776), "leuven": (50.8798, 4.7005),
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
    "ottignies-louvain-la-neuve": (50.6690, 4.6110), "louvain-la-neuve": (50.6690, 4.6110),
    # Belgium — added after Stekene/Middelkerke geocoding incidents
    "aalst": (50.9383, 4.0392), "boechout": (51.1636, 4.4964),
    "charleroi": (50.4116, 4.4445), "dendermonde": (51.0312, 4.0981),
    "genk": (50.9655, 5.5001), "kessel-lo": (50.8852, 4.7314),
    "liege": (50.6451, 5.5736), "liège": (50.6451, 5.5736),
    "meerhout": (51.1317, 5.0772), "middelkerke": (51.1897, 2.7742),
    "mons": (50.4550, 3.9520), "olen": (51.1439, 4.8597),
    "oostende": (51.2259, 2.9195), "ostend": (51.2259, 2.9195),
    "roeselare": (50.9450, 3.1244), "schepdaal": (50.8349, 4.1920),
    "snaaskerke": (51.1746, 2.9375), "waterloo": (50.7175, 4.3978),
    "westmalle": (51.2969, 4.6938), "wijnegem": (51.2271, 4.5225),
    # Netherlands — same batch
    "alkmaar": (52.6009, 4.8171), "alphen aan den rijn": (52.1131, 4.6408),
    "bilthoven": (52.1290, 5.2046), "capelle aan den ijssel": (51.9313, 4.5884),
    "deventer": (52.2695, 6.2365), "elst": (51.9188, 5.8453),
    "goirle": (51.5056, 5.0338), "gouda": (52.0115, 4.7106),
    "heerenveen": (52.9985, 5.9231), "heerhugowaard": (52.6631, 4.8327),
    "hilversum": (52.2241, 5.1719), "lelystad": (52.5367, 5.3610),
    "leusden": (52.1304, 5.4287), "perkpolder": (51.3983, 4.0164),
    "the hague": (52.0800, 4.3113), "volendam": (52.4964, 5.0683),
    "zaandam": (52.4425, 4.8299), "zandvoort": (52.3720, 4.5302),
    "zeist": (52.0893, 5.2276), "s-hertogenbosch": (51.6889, 5.3031),
    "den bosch": (51.6889, 5.3031),
}


_geocache: dict = {}
_LOCATIONIQ_KEY = os.environ.get("LOCATIONIQ_API_KEY", "")
_LOCATIONIQ_URL = "https://us1.locationiq.com/v1/search"

def _known_city_match(key: str):
    """Return (lat, lng) from KNOWN_COORDS if a known city name appears as a
    whole word in `key`, else None."""
    for city_key, coords in KNOWN_COORDS.items():
        if re.search(r'\b' + re.escape(city_key) + r'\b', key):
            return coords
    return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


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


def geocode(location: str, country: str = None, city: str = None):
    """Geocode a location (usually a full street address) via LocationIQ.

    One query: the address plus the country we already know the event is
    in. Trust the result unless LocationIQ's own returned country
    disagrees with ours, the point falls offshore, or the city has a
    KNOWN_COORDS entry and the result lands >20km from it (catches
    same-country wrong-city misses like Hasselt -> Brussels). A
    2026-07-02 audit of 182 real addresses found LocationIQ correct
    ~85% of the time, and correct results are precise venue matches —
    KNOWN_COORDS is a fallback here, not a shortcut.

    `city`, when the caller already knows it separately from `location`
    (e.g. an address with no city name in the text), is used only for the
    KNOWN_COORDS validation above — without it, that check silently never
    fires for addresses that don't happen to mention their own city.
    """
    key = str(location).strip()
    if not key:
        return None
    cache_key = f"{key.lower()}|{(country or '').strip().lower()}"
    if cache_key in _geocache:
        return _geocache[cache_key]

    known = _known_city_match((city or key).lower())
    result = None

    if _LOCATIONIQ_KEY:
        query = f"{key}, {country}" if country else key
        try:
            resp = requests.get(
                _LOCATIONIQ_URL,
                params={"key": _LOCATIONIQ_KEY, "q": query, "format": "json",
                        "limit": 1, "addressdetails": 1},
                timeout=10,
            )
            data = resp.json() if resp.ok else []
        except Exception as exc:
            print(f"  [geocode] request failed for {query!r}: {exc}")
            data = []

        if not data:
            print(f"  [geocode] no result for {query!r}")
        else:
            top = data[0]
            lat, lng = float(top["lat"]), float(top["lon"])
            returned_country = (top.get("address") or {}).get("country", "").lower()
            expected_country = (country or "").lower()
            dist = _haversine_km(lat, lng, known[0], known[1]) if known else None
            country_mismatch = (
                expected_country and returned_country
                and expected_country not in returned_country
                and returned_country not in expected_country
            )
            if country_mismatch:
                print(f"  [geocode] REJECTED {query!r}: expected {country}, got {returned_country} ({lat},{lng})")
            elif lng < 2.0:
                print(f"  [geocode] REJECTED {query!r}: offshore (lng={lng})")
            elif dist is not None and dist > 20:
                print(f"  [geocode] REJECTED {query!r}: {dist:.1f}km from known city centre")
            else:
                print(f"  [geocode] ACCEPTED {query!r}: ({lat},{lng}) — {top.get('display_name')}")
                result = (lat, lng)

    if result is None and known:
        print(f"  [geocode] fallback to KNOWN_COORDS city-centre: {known}")
        result = known

    _geocache[cache_key] = result
    return result
