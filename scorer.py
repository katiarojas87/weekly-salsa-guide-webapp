#!/usr/bin/env python3
"""
scorer.py
=========
Pure scoring function — no FastAPI dependency.
Imported by both api.py and run_pipeline.py.
"""

import json
import re
from datetime import datetime

import anthropic


def build_schedule_text(schedule: dict) -> str:
    """
    schedule: { "2026-06-09": 1, "2026-06-14": 2, ... }
    Returns the density instructions string for the prompt.
    """
    if not schedule:
        return (
            "- A maximum of 1 event for Monday, Tuesday, Wednesday, and Thursday.\n"
            "- A maximum of 2 events for Friday, Saturday, and Sunday."
        )
    lines = []
    for date_key, count in sorted(schedule.items()):
        try:
            d = datetime.strptime(date_key, "%Y-%m-%d")
            day_name = d.strftime("%A")
        except ValueError:
            day_name = date_key
        lines.append(f"- {date_key} ({day_name}): maximum {count} event(s)")
    return "\n".join(lines)


def build_output_format(schedule: dict, date_range: dict) -> str:
    """Build the JSON output format example for the prompt."""
    if schedule:
        entries = []
        for date_key, count in sorted(schedule.items()):
            entries.append(f'  "{date_key}": [top events (max {count})]')
        return "{\n" + ",\n".join(entries) + "\n}"
    else:
        start = date_range.get("start", "?")
        end   = date_range.get("end",   "?")
        return (
            f'{{\n'
            f'  "{start}": [top events (max 1)],\n'
            f'  "...": [...],\n'
            f'  "{end}": [top events (max 2)]\n'
            f'}}'
        )


def score_events(raw: dict, api_key: str, schedule: dict = None) -> dict:
    """
    Score and rank events using Claude.

    Args:
        raw:      Raw events dict from the scraper
                  { "days": [...], "range": {"start":..., "end":...} }
        api_key:  Anthropic API key
        schedule: Optional { "YYYY-MM-DD": max_count } per day.
                  If None, uses default (1 weekday / 2 weekend).

    Returns:
        { "generated_at": ..., "range": ..., "ranked_events": { "YYYY-MM-DD": [...] } }
    """
    days       = raw.get("days", [])
    date_range = raw.get("range", {})

    # Only score days that are in the schedule (if provided)
    if schedule:
        days = [d for d in days if d["date"] in schedule]

    sections = []
    for day in days:
        label  = day["label"]
        events = day["events"]
        if not events:
            sections.append(f"# {label}\nNo events.")
            continue
        lines = []
        for i, e in enumerate(events, 1):
            lines.append(
                f"{i}. {e.get('name','')}\n"
                f"   Organizer: {e.get('organizer','')}\n"
                f"   DJs: {e.get('djs','')}\n"
                f"   Time: {e.get('time','')}\n"
                f"   City: {e.get('city','')}\n"
                f"   Address: {e.get('address','')}\n"
                f"   Price: {e.get('price','')}\n"
                f"   Music: {e.get('music_genres','')}\n"
                f"   Description: {str(e.get('description',''))[:200]}\n"
                f"   Facebook: {e.get('facebook_url','')}\n"
                f"   Instagram: {e.get('instagram_url','')}\n"
                f"   Source: {e.get('source','')}\n"
                f"   URL: {e.get('url','')}"
            )
        sections.append(f"# {label}\n" + "\n".join(lines))

    events_text = "\n\n".join(sections)
    schedule_text = build_schedule_text(schedule)
    output_format = build_output_format(schedule, date_range)

    prompt = f"""You are an expert salsa social scene analyst for Belgium and the Netherlands.

Here are the events for the targeted week ({date_range.get("start","?")} to {date_range.get("end","?")}):

{events_text}

-----------------------------------
EXCLUSION RULES
-----------------------------------

BEFORE scoring, remove any event that is 100% bachata-only.
This feed is for SALSA dancers. Salsa or salsa-mixed events always rank above non-salsa ones.
- EXCLUDE events where the program contains ONLY "Bachata" with no salsa.
- EXCLUDE events with names like "Bachata Gala", "Bachata Dreams", "Bachata Only".
- ALSO EXCLUDE events that are 100% kizomba-only (program is only Kizomba / Semba / Urban Kizz,
  with NO salsa). Names/programs like "Kizomba Beach Festival", "Kizomba Bash", "Urban Kizz",
  "Semba", "Urban" with no salsa component must be removed.
- An event is KEPT only if its program clearly contains SALSA (salsa alone, or salsa mixed with
  bachata/kizomba/merengue/etc. is fine). If salsa is not present, exclude it.
- Events may be in Dutch, French, or English — apply exclusion rules regardless of language.
- If fewer than the requested maximum exist for a given day, include all available.
  It is acceptable for a day to have FEWER events (or none) if no salsa events qualify that day.

-----------------------------------
SCORING MODEL
-----------------------------------

Final Score =
    Facebook Attendees * 0.40
  + Instagram Followers * 0.25
  + Organizer Reputation * 0.15
  + Venue Prestige * 0.10
  + Event Frequency / Recurring Reputation * 0.05
  + Google / Social Signals * 0.05

Evaluate:
- Facebook: going/interested count, engagement, sold-out reputation
- Instagram: organizer/venue/event account quality (engagement > raw followers)
- Organizer: known in BE/NL Latin scene, teacher/DJ reputation, community prestige
- Venue: iconic/premium, historic dance venues, rooftop/waterfront
- Recurring: weekly/monthly socials outperform random one-offs
- Social signals: online mentions, reposts, community hype across platforms

IMPORTANT REASONING RULES:
- Think like a real salsa dancer in Belgium and the Netherlands
- Do NOT rank only by numbers — infer prestige, hype, exclusivity, community importance
- French-language events (Brussels, Wallonia) are equally important — do not underrank them
- Consider: famous DJs, live bands, workshops, special/anniversary editions, outdoor socials

-----------------------------------
OUTPUT FORMAT
-----------------------------------

Respond ONLY with valid JSON — no markdown, no explanation.
{output_format}

Each event object:
{{"rank":1,"name":"","organizer":"","djs":"","time":"","city":"",
  "address":"","price":"","program":"Salsa · Bachata · SBK",
  "description":"","score":85,"why":"reason",
  "facebook_url":"","instagram_url":"","image_url":"","url":"","source":""}}

-----------------------------------
DENSITY — STRICT MAXIMUM PER DAY:
-----------------------------------
{schedule_text}
If fewer valid salsa events exist for any day, include all available (can be zero)."""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}]
    )

    text  = message.content[0].text
    clean = re.sub(r"```(?:json)?\s*", "", text).strip()
    clean = re.sub(r"```\s*$", "", clean).strip()

    ranked = json.loads(clean)

    return {
        "generated_at": datetime.now().isoformat(),
        "range":         date_range,
        "ranked_events": ranked,
    }
