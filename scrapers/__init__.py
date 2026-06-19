"""Salsa scraper package."""

from .salsalovers import scrape_salsalovers
from .latinworld import scrape_latinworld
from .event_sources import scrape_generic_sources, load_manual_events

__all__ = [
    'scrape_salsalovers',
    'scrape_latinworld',
    'scrape_generic_sources',
    'load_manual_events',
]
