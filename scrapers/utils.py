"""Shared scraper utilities for parsing, fetching, and geocoding."""

import re
import time
from datetime import date, datetime

import requests
from geopy.geocoders import Nominatim

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
_geo = Nominatim(user_agent="scraper_utils/1.0", timeout=10)


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


def geocode(location: str):
    key = str(location).strip().lower()
    if not key:
        return None
    if key in _geocache:
        return _geocache[key]
    for city_key, coords in KNOWN_COORDS.items():
        if city_key in key:
            _geocache[key] = coords
            return coords
    time.sleep(1.1)
    for query in [f"{location}, Netherlands", f"{location}, Belgium", location]:
        try:
            loc = _geo.geocode(query)
            if loc:
                coords = (loc.latitude, loc.longitude)
                _geocache[key] = coords
                return coords
        except Exception:
            pass
    _geocache[key] = None
    return None
