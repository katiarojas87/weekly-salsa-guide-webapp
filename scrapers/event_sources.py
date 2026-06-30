#!/usr/bin/env python3
"""Generic event source loader.

This module lets the scraper load additional public event pages and manual
entries beyond the two built-in sources.

The generic scraper does not yet support logged-in-only social feeds, but it
can discover events from pages exposing standard event schema / JSON-LD.
"""

import json
import os
import re
import time
from datetime import date, datetime
from urllib.parse import urlparse

import requests
from scrapers.utils import fetch_html

TARGET_FIELDS = [
    "source", "id", "url", "name", "organizer", "date", "date_text",
    "day", "time", "address", "city", "description", "price", "is_free",
    "facebook_url", "instagram_url", "image_url", "coordinates",
    "music_genres", "djs", "program",
]

SOCIAL_PATTERNS = {
    "facebook_url": re.compile(r"https?://(?:www\.)?facebook\.com/(?:events/)?[^\s'\"<>]+", re.IGNORECASE),
    "instagram_url": re.compile(r"https?://(?:www\.)?instagram\.com/[^\s'\"<>]+", re.IGNORECASE),
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _load_json(path: str):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    # ISO 8601 / YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            return date.fromisoformat(m.group(0))
        except ValueError:
            pass
    # Common formats like '29 mei 2026'
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if m:
        try:
            return date.fromisoformat(f"{m.group(3)}-{m.group(2)}-{m.group(1)}")
        except Exception:
            pass
    # Fallback parse using datetime.fromisoformat on full timestamp.
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).date()
    except Exception:
        pass
    return None


def _extract_social_urls(text: str):
    if not text:
        return {}
    found = {}
    for field, pattern in SOCIAL_PATTERNS.items():
        match = pattern.search(text)
        if match:
            found[field] = match.group(0).rstrip(' .')
    return found


def _normalize_event(raw: dict, source: str = "Generic", source_url: str = "") -> dict:
    event = {
        "source": source,
        "id": raw.get("id") or raw.get("url") or raw.get("name") or source_url,
        "url": raw.get("url") or source_url,
        "name": raw.get("name") or raw.get("headline") or raw.get("title") or "",
        "organizer": raw.get("organizer") or raw.get("author") or "",
        "date": raw.get("date") or "",
        "date_text": raw.get("date_text") or raw.get("date") or "",
        "day": raw.get("day") or "",
        "time": raw.get("time") or "",
        "address": raw.get("address") or "",
        "city": raw.get("city") or "",
        "description": raw.get("description") or "",
        "price": raw.get("price") or "",
        "is_free": raw.get("is_free", False),
        "facebook_url": raw.get("facebook_url", ""),
        "instagram_url": raw.get("instagram_url", ""),
        "image_url": raw.get("image_url", ""),
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "coordinates": raw.get("coordinates"),
        "music_genres": raw.get("music_genres", ""),
        "djs": raw.get("djs", ""),
        "program": raw.get("program", ""),
    }
    if not event["date"]:
        parsed = _parse_date(raw.get("startDate") or raw.get("datePosted") or raw.get("dateCreated"))
        if parsed:
            event["date"] = str(parsed)
            event["date_text"] = event["date_text"] or str(parsed)
            event["day"] = event["day"] or parsed.strftime("%A").lower()
    elif isinstance(event["date"], date):
        event["date"] = str(event["date"])
    if not event["facebook_url"] or not event["instagram_url"]:
        social = _extract_social_urls(event.get("description", "") + " " + event.get("url", "") + " " + source_url)
        for field, url in social.items():
            event[field] = event[field] or url
    return event


def _find_json_ld(html: str):
    candidates = re.findall(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    results = []
    for raw in candidates:
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to repair common issues with unescaped control characters
            raw_clean = re.sub(r"\s+", " ", raw)
            try:
                data = json.loads(raw_clean)
            except json.JSONDecodeError:
                continue
        if isinstance(data, dict):
            if data.get("@graph"):
                results.extend(data["@graph"])
            else:
                results.append(data)
        elif isinstance(data, list):
            results.extend(data)
    return results


def _parse_json_ld_events(html: str, source_url: str):
    entries = []
    for item in _find_json_ld(html):
        type_value = item.get("@type") or item.get("type")
        if isinstance(type_value, list):
            event_types = [t.lower() for t in type_value]
        elif isinstance(type_value, str):
            event_types = [type_value.lower()]
        else:
            event_types = []
        if any(t in event_types for t in ["event", "danceevent", "socialevent", "musicevent", "danceevent"]):
            event = {
                "id": item.get("@id") or item.get("url"),
                "url": item.get("url") or item.get("sameAs") or source_url,
                "name": item.get("name") or item.get("headline") or "",
                "description": item.get("description") or "",
                "startDate": item.get("startDate") or item.get("start_date") or item.get("datePublished"),
                "endDate": item.get("endDate"),
                "location": item.get("location") or {},
                "organizer": item.get("organizer") or item.get("author") or "",
                "offers": item.get("offers") or {},
                "image_url": item.get("image") or "",
            }
            location = event["location"]
            if isinstance(location, dict):
                address = location.get("address")
                if isinstance(address, dict):
                    event["address"] = address.get("streetAddress", "")
                    event["city"] = address.get("addressLocality", "")
                    if not event["address"]:
                        event["address"] = address.get("streetAddress", "")
                else:
                    event["address"] = address or ""
                event["city"] = event["city"] or location.get("addressLocality", "") or location.get("name", "")
                if not event["city"] and isinstance(location.get("name"), str):
                    event["city"] = location.get("name")
            event["price"] = ""
            if event["offers"]:
                if isinstance(event["offers"], dict):
                    event["price"] = event["offers"].get("price") or event["offers"].get("priceSpecification", {}).get("price") or ""
                elif isinstance(event["offers"], list):
                    first = event["offers"][0]
                    if isinstance(first, dict):
                        event["price"] = first.get("price") or ""
            event["facebook_url"] = ""
            event["instagram_url"] = ""
            if isinstance(item.get("sameAs"), str):
                urls = _extract_social_urls(item.get("sameAs"))
                event.update(urls)
            elif isinstance(item.get("sameAs"), list):
                for same in item.get("sameAs", []):
                    urls = _extract_social_urls(str(same))
                    event.update(urls)
            entries.append(event)
    return entries


def _event_matches_week(event: dict, target_set: set):
    event_date = _parse_date(event.get("date") or event.get("startDate"))
    if not event_date:
        return False
    return str(event_date) in target_set


def load_event_sources(config_path: str = "event_sources.json"):
    config = _load_json(config_path)
    if not isinstance(config, list):
        return []
    return config


def load_manual_events(path: str = "manual_events.json", target_dates: list | None = None):
    raw = _load_json(path)
    if not isinstance(raw, list):
        return []
    events = []
    target_set = {str(d) for d in target_dates} if target_dates else None
    for item in raw:
        event = _normalize_event(item, source=item.get("source", "manual"), source_url=item.get("url", ""))
        if not event["date"] and item.get("date"):
            event["date"] = str(item.get("date"))
        if target_set is None or event["date"] in target_set:
            events.append(event)
    return events


def scrape_generic_sources(target_dates: list, config_path: str = "event_sources.json"):
    target_set = {str(d) for d in target_dates}
    sources = load_event_sources(config_path)
    scraped = []
    for source in sources:
        urls = source.get("urls", [])
        source_tag = source.get("source_tag") or source.get("name") or "Generic"
        for url in urls:
            html = fetch_html(url)
            if not html:
                continue
            parsed = _parse_json_ld_events(html, url)
            for item in parsed:
                event = _normalize_event(item, source=source_tag, source_url=url)
                if event["date"] in target_set:
                    scraped.append(event)
    return scraped
