#!/usr/bin/env python3
"""
generate_slides.py
==================
Reads scored_events JSON → generates one Instagram slide (PNG) per event.
Visual design: Sabrosura Sundays Carousel v2 · Amazonika Design System.

Usage:
  python generate_slides.py --input scored_events.json --output ./slides/
  python generate_slides.py --input scored_events.json  # outputs to ./slides/

Input JSON format (from scorer.py):
  {
    "ranked_events": {
      "2026-06-09": [ { "rank":1, "name":"...", ... }, ... ],
      ...
    }
  }

Output:
  slides/2026-06-09_rank1_Event_Name.png
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# ── Amazonika design tokens (colors_and_type.css v2) ─────────────────────────

FONTS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Bebas+Neue"
    "&family=Montserrat:wght@400;500;600;700"
    "&family=Cormorant+Garamond:ital,wght@1,400;1,500;1,600"
    "&display=swap"
)

# Matches the design system token values exactly
DS = {
    "bg_page":       "#F5EBDD",
    "bg_surface":    "#FBF4E8",
    "ink_1":         "#241310",   # primary text — AAA on cream
    "ink_2":         "#5A3D2A",   # secondary text
    "ink_3":         "#7A5A44",   # tertiary/captions
    "accent":        "#C9462C",   # terracotta — CTAs, FREE pill, highlights
    "accent_deep":   "#9F3220",   # press/active
    "cat_life":      "#D4A24A",   # gold ochre — header band background
    "earth_3":       "#A8845E",   # decorative ring border
    "border":        "rgba(36,19,16,0.16)",
    "border_subtle": "rgba(36,19,16,0.08)",
    "ease":          "cubic-bezier(0.22, 0.61, 0.36, 1)",
}

# Beige scrim over photo (warm, accessible — matches v2)
SCRIM = "linear-gradient(to bottom, rgba(230,210,178,0.55) 0%, rgba(200,168,118,0.52) 42%, rgba(120,88,50,0.68) 100%)"
# Swipe pill background
PILL_BG = "rgba(240,225,195,0.82)"
# Icon tile background
TILE_BG = "rgba(240,228,208,0.88)"
TILE_BORDER = "rgba(60,40,20,0.18)"


# ── SVG icons (Lucide, stroke only, earth-brown at 1.75px) ───────────────────

ICON = {
    "calendar": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<rect width="18" height="18" x="3" y="4" rx="2"></rect>'
        '<path d="M3 10h18"></path><path d="M8 2v4"></path><path d="M16 2v4"></path>'
        '</svg>'
    ),
    "clock": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline>'
        '</svg>'
    ),
    "pin": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"></path>'
        '<circle cx="12" cy="10" r="3"></circle>'
        '</svg>'
    ),
    "ticket": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z">'
        '</path><path d="M13 5v2"></path><path d="M13 11v2"></path><path d="M13 17v2"></path>'
        '</svg>'
    ),
    "headphones": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H4a1 1 0 0 1-1-1v-6a9 9 0 0 1 18 0v6a1 1 0 0 1-1 1h-2a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"></path>'
        '</svg>'
    ),
    "music2": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 18V5l12-2v13"></path>'
        '<circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle>'
        '</svg>'
    ),
    "bookmark": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path>'
        '</svg>'
    ),
    "share": (
        '<svg viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle>'
        '<circle cx="18" cy="19" r="3"></circle>'
        '<line x1="8.6" y1="13.5" x2="15.4" y2="17.5"></line>'
        '<line x1="15.4" y1="6.5" x2="8.6" y2="10.5"></line>'
        '</svg>'
    ),
    "arrow_right": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>'
        '</svg>'
    ),
}


# ── Default background images (round-robin across slides) ────────────────────

_HERE = Path(__file__).parent  # absolute path to the project root

DEFAULT_BG_IMAGES = [
    str((_HERE / "defualt images" / "salsa1.png").resolve()),
    str((_HERE / "defualt images" / "salsa2.png").resolve()),
    str((_HERE / "defualt images" / "salsa3.png").resolve()),
    str((_HERE / "defualt images" / "salsa4.png").resolve()),
]


# ── Claude: translate + rewrite description ───────────────────────────────────

def _make_punchy_description(raw_description: str, event_name: str, api_key: str) -> str:
    """Translate any language → English, rewrite warm & punchy, max 2 lines (~180 chars)."""
    if not raw_description.strip():
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=120,
            messages=[{
                "role": "user",
                "content": (
                    f"Event: {event_name}\n"
                    f"Original description (may be Dutch/French/English): {raw_description}\n\n"
                    "Rewrite this as a punchy, warm, exciting 1–2 line English description "
                    "for an Instagram slide. Max 180 characters. No quotes, no hashtags. "
                    "Capture the vibe — summery, social, dance energy. Output only the description text."
                )
            }]
        )
        return msg.content[0].text.strip()
    except Exception:
        return raw_description  # fallback to original if API call fails


# ── HTML slide template ───────────────────────────────────────────────────────

def make_slide_html(event: dict, slide_index: int, total_slides: int, punchy_desc: str = "") -> str:
    name        = event.get("name", "Salsa Night").upper()
    organizer   = event.get("organizer", "")
    djs_raw     = event.get("djs", "") or ""
    time_str    = event.get("time", "") or ""
    city        = event.get("city", "") or ""
    address     = event.get("address", "") or ""
    price       = event.get("price", "") or ""
    program     = event.get("program", "Salsa") or "Salsa"
    image_url   = event.get("image_url", "") or ""
    date_str    = event.get("date", "") or ""
    source      = event.get("source", "salsalovers.be") or ""

    # --- Adaptive font size: prevent long names from overflowing the header
    name_len = len(name)
    if name_len <= 14:
        name_font = "130px"
    elif name_len <= 20:
        name_font = "108px"
    elif name_len <= 28:
        name_font = "88px"
    elif name_len <= 36:
        name_font = "72px"
    else:
        name_font = "58px"

    # --- Date label (English weekday + day + month abbreviation)
    EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    EN_MON  = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    date_label = date_str
    if date_str:
        try:
            from datetime import datetime
            d = datetime.strptime(date_str, "%Y-%m-%d")
            date_label = f"{EN_DAYS[d.weekday()]} {d.day} {EN_MON[d.month - 1]}"
        except Exception:
            pass

    # --- Entrance pill
    price_upper = price.strip().upper()
    is_free = not price_upper or price_upper in ("FREE", "GRATIS", "0", "€0", "FREE ENTRY")
    if is_free:
        entrance_html = '<span class="pill-free">Free</span>'
    else:
        entrance_html = f'<span class="row__value-text">{price}</span>'

    # --- Photo background — always use file:// absolute URLs so Playwright finds them
    if image_url:
        bg_url = image_url  # remote URL, works as-is
    else:
        abs_path = DEFAULT_BG_IMAGES[(slide_index - 1) % len(DEFAULT_BG_IMAGES)]
        bg_url = f"file://{abs_path}"
    bg_css = f"background-image: url('{bg_url}'); background-size: cover; background-position: center 50%; filter: brightness(1.3);"

    # --- DJs display (wrap long names)
    djs_main = djs_raw[:38] if djs_raw else "TBA"
    djs_sub  = djs_raw[38:78] if len(djs_raw) > 38 else ""

    # --- Handle — always @weeklysalsaguide (the account posting this content)
    handle = "@weeklysalsaguide"

    # --- Swipe hint
    if slide_index < total_slides:
        swipe_text = "SWIPE FOR THE NEXT DAYS"
    else:
        swipe_text = "FOLLOW FOR WEEKLY UPDATES"

    # --- Punchy editorial description (pre-translated English from Claude)
    desc_html = ""
    if punchy_desc:
        words = punchy_desc.split(" ", 3)
        if len(words) >= 3:
            desc_html = f'<b>{words[0]} {words[1]}</b> ' + " ".join(words[2:])
        else:
            desc_html = punchy_desc

    # --- Location: address as main, city as sub (or just city if no address)
    location_main = address if address else city
    location_sub  = city if (address and city and city not in address) else ""

    # --- Program / music genres
    program = (event.get("program", "") or event.get("music_genres", "") or "Salsa").strip()
    # Clean up separators for display
    program_display = re.sub(r'\s*[·•|/]\s*', ' · ', program)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080">
<title>{name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="{FONTS_URL}" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  /* ── Amazonika DS tokens ───────────────────────── */
  :root {{
    --ink-1:        {DS["ink_1"]};
    --ink-2:        {DS["ink_2"]};
    --ink-3:        {DS["ink_3"]};
    --accent:       {DS["accent"]};
    --cat-life:     {DS["cat_life"]};
    --bg-surface:   {DS["bg_surface"]};
    --border:       {DS["border"]};
    --border-sub:   {DS["border_subtle"]};
    --font-display: "Bebas Neue", "Anton", Impact, sans-serif;
    --font-body:    "Montserrat", "Helvetica Neue", system-ui, sans-serif;
    --font-accent:  "Cormorant Garamond", "Playfair Display", Georgia, serif;
    --ease:         {DS["ease"]};
  }}

  html, body {{
    width: 1080px; height: 1350px;
    overflow: hidden;
    background: #15100c;
  }}

  /* ── Slide container ────────────────────────────── */
  .slide {{
    width: 1080px; height: 1350px;
    display: flex; flex-direction: column;
    overflow: hidden;
    position: relative;
  }}

  /* ── GOLD HEADER BAND ──────────────────────────── */
  .det__head {{
    flex: none;
    height: 360px;
    background: var(--cat-life);
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: 0 64px 46px;
    overflow: hidden;
    position: relative;
    z-index: 2;
  }}
  /* Decorative rings — top-right corner */
  .det__head::before {{
    content: "";
    position: absolute; right: -120px; top: -120px;
    width: 380px; height: 380px; border-radius: 999px;
    border: 2px solid rgba(58,36,25,0.22);
    pointer-events: none;
  }}
  .det__head::after {{
    content: "";
    position: absolute; right: -40px; top: -40px;
    width: 220px; height: 220px; border-radius: 999px;
    border: 2px solid rgba(58,36,25,0.18);
    pointer-events: none;
  }}

  /* SAVE & SHARE — top-right of the gold header */
  .det__save {{
    position: absolute; top: 46px; right: 64px; z-index: 3;
    display: flex; align-items: center; gap: 14px;
    color: var(--ink-1);
    font-family: var(--font-body);
    font-weight: 700; font-size: 26px; letter-spacing: 0.10em; text-transform: uppercase;
  }}
  .det__save svg {{
    width: 30px; height: 30px;
    stroke: var(--ink-1); stroke-width: 2; fill: none;
    stroke-linecap: round; stroke-linejoin: round;
  }}

  /* Event name */
  .det__name {{
    font-family: var(--font-display);
    font-size: 130px; line-height: 0.84; letter-spacing: -0.01em;
    text-transform: uppercase;
    color: var(--ink-1);
    text-align: center;
    transform: translateY(-30%);
    position: relative; z-index: 3;
    word-break: break-word;
  }}

  /* ── PHOTO BODY ─────────────────────────────────── */
  .det__body {{
    flex: 1;
    position: relative;
    overflow: hidden;
    display: flex; flex-direction: column;
  }}
  .det__bg {{
    position: absolute; inset: 0; z-index: 0;
    {bg_css}
  }}
  .det__scrim {{
    position: absolute; inset: 0; z-index: 1;
    background: {SCRIM};
  }}

  /* ── CONTENT (over photo) ───────────────────────── */
  .det__content {{
    position: relative; z-index: 2;
    flex: 1;
    display: flex; flex-direction: column;
    padding: 0;
  }}

  /* Handle — sits just below the gold/photo dividing line */
  .det__handle {{
    flex: none;
    color: var(--ink-1);
    padding: 30px 64px 0;
    font-family: var(--font-body);
    font-weight: 700; font-size: 29px; letter-spacing: 0.04em;
  }}
  .det__handle .at {{ color: var(--accent); font-weight: 800; }}

  /* Punchy editorial description */
  .det__desc {{
    flex: none;
    color: var(--ink-1);
    padding: 0 64px;
    margin: 22px auto 0;
    font-family: var(--font-accent);
    font-style: italic; font-weight: 500;
    font-size: 38px; line-height: 1.12; letter-spacing: 0.005em;
    text-align: center; text-wrap: pretty; max-width: 920px;
  }}
  .det__desc b {{ color: var(--accent); font-weight: 600; font-style: italic; }}

  /* 2×3 info grid */
  .det__list {{
    flex: 1;
    padding: 36px 64px 20px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    column-gap: 40px; row-gap: 28px;
    align-content: start;
  }}
  .row {{ display: flex; align-items: center; gap: 26px; }}
  .row__icon {{
    width: 76px; height: 76px; flex: none;
    border-radius: 12px;
    background: {TILE_BG};
    border: 1px solid {TILE_BORDER};
    display: flex; align-items: center; justify-content: center;
  }}
  .row__icon svg {{
    width: 36px; height: 36px;
    stroke: var(--ink-1); stroke-width: 1.75; fill: none;
  }}
  .row__text {{ display: flex; flex-direction: column; gap: 4px; }}
  .row__label {{
    font-family: var(--font-body);
    font-weight: 700; font-size: 15px; letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--ink-2);
  }}
  .row__value {{
    font-family: var(--font-body);
    font-weight: 600; font-size: 30px; line-height: 1.1;
    color: var(--ink-1);
  }}
  .row__value-text {{
    font-family: var(--font-body);
    font-weight: 600; font-size: 30px; line-height: 1.1;
    color: var(--ink-1);
  }}
  .row__sub {{
    font-family: var(--font-body);
    font-size: 21px; font-weight: 500;
    color: var(--ink-2);
    margin-top: 2px;
  }}

  /* FREE pill */
  .pill-free {{
    display: inline-flex; align-items: center;
    background: var(--accent); color: #FFFCF5;
    font-family: var(--font-body); font-weight: 700;
    font-size: 27px; letter-spacing: 0.06em;
    padding: 6px 20px; border-radius: 6px;
    text-transform: uppercase; margin-top: 2px;
  }}

  /* Swipe hint pill */
  .det__swipe {{
    flex: none;
    align-self: center;
    margin: 0 auto 48px;
    display: flex; align-items: center; justify-content: center; gap: 12px;
    font-family: var(--font-body); font-weight: 700; font-size: 18px;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--ink-1);
    background: {PILL_BG};
    backdrop-filter: blur(4px);
    padding: 10px 28px; border-radius: 40px;
  }}
  .det__swipe svg {{
    width: 22px; height: 22px;
    stroke: var(--ink-1); stroke-width: 2.2; fill: none; flex: none;
  }}

  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ transition-duration: 0.001ms !important; }}
  }}
</style>
</head>
<body>
<div class="slide">

  <!-- ── GOLD HEADER BAND ── -->
  <div class="det__head">
    <div class="det__save">
      {ICON["bookmark"]}
      {ICON["share"]}
      <span>Save &amp; share</span>
    </div>
    <div class="det__name" style="font-size:{name_font}">{name}</div>
  </div>

  <!-- ── PHOTO BODY ── -->
  <div class="det__body">
    <div class="det__bg"></div>
    <div class="det__scrim"></div>
    <div class="det__content">

      <div class="det__handle"><span><span class="at">@</span>weeklysalsaguide</span></div>

      {f'<p class="det__desc">{desc_html}</p>' if desc_html else ''}

      <div class="det__list">

        <!-- DATE -->
        <div class="row">
          <span class="row__icon">{ICON["calendar"]}</span>
          <div class="row__text">
            <div class="row__label">Date</div>
            <div class="row__value">{date_label or "TBA"}</div>
          </div>
        </div>

        <!-- TIME -->
        <div class="row">
          <span class="row__icon">{ICON["clock"]}</span>
          <div class="row__text">
            <div class="row__label">Time</div>
            <div class="row__value">{time_str or "TBA"}</div>
          </div>
        </div>

        <!-- LOCATION -->
        <div class="row">
          <span class="row__icon">{ICON["pin"]}</span>
          <div class="row__text">
            <div class="row__label">Location</div>
            <div class="row__value">{location_main or "TBA"}</div>
            {f'<div class="row__sub">{location_sub}</div>' if location_sub else ''}
          </div>
        </div>

        <!-- ENTRANCE -->
        <div class="row">
          <span class="row__icon">{ICON["ticket"]}</span>
          <div class="row__text">
            <div class="row__label">Entrance</div>
            {entrance_html}
          </div>
        </div>

        <!-- DJS -->
        <div class="row">
          <span class="row__icon">{ICON["headphones"]}</span>
          <div class="row__text">
            <div class="row__label">DJs</div>
            <div class="row__value">{djs_main}</div>
            {f'<div class="row__sub">&amp; {djs_sub}</div>' if djs_sub else ''}
          </div>
        </div>

        <!-- PROGRAM -->
        <div class="row">
          <span class="row__icon">{ICON["music2"]}</span>
          <div class="row__text">
            <div class="row__label">Program</div>
            <div class="row__value" style="font-size:24px;">{program_display}</div>
          </div>
        </div>

      </div><!-- /det__list -->

      <div class="det__swipe">
        <span>{swipe_text}</span>
        {ICON["arrow_right"]}
      </div>

    </div><!-- /det__content -->
  </div><!-- /det__body -->

</div><!-- /slide -->
</body>
</html>"""


# ── Screenshot via Playwright ─────────────────────────────────────────────────

def render_slides(events_with_meta: list, output_dir: Path, api_key: str = ""):
    """Render each event HTML → PNG using Playwright headless Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌  Playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    total = len(events_with_meta)
    output_paths = []

    # Pre-translate all descriptions before opening the browser
    print("  ✍️  Translating descriptions ...")
    punchy_descs = []
    for _, _, event in events_with_meta:
        raw = (event.get("description", "") or "").strip()
        if raw and api_key:
            punchy_descs.append(_make_punchy_description(raw, event.get("name", ""), api_key))
        else:
            punchy_descs.append(raw)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1080, "height": 1350})

        for i, ((date_key, rank, event), punchy_desc) in enumerate(zip(events_with_meta, punchy_descs), 1):
            html = make_slide_html(event, slide_index=i, total_slides=total, punchy_desc=punchy_desc)
            safe_name = re.sub(r"[^\w\-]", "_", event.get("name", "event"))[:40]
            filename = f"{date_key}_rank{rank}_{safe_name}.png"
            out_path = output_dir / filename

            tmp_html = output_dir / f"_tmp_{i}.html"
            tmp_html.write_text(html, encoding="utf-8")

            page.goto(f"file://{tmp_html.resolve()}")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(out_path), clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
            tmp_html.unlink()

            print(f"  ✅ [{i}/{total}] {filename}")
            output_paths.append(out_path)

        browser.close()

    return output_paths


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate Amazonika Sabrosura v2-style Instagram slides from scored events"
    )
    parser.add_argument("--input",  "-i", required=True, help="Path to scored_events JSON file")
    parser.add_argument("--output", "-o", default="./slides", help="Output directory for PNGs (default: ./slides)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌  Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    ranked = data.get("ranked_events", data)

    events_with_meta = []
    for date_key, day_events in ranked.items():
        if not isinstance(day_events, list):
            continue
        for event in day_events:
            rank = event.get("rank", 1)
            if "date" not in event:
                event["date"] = date_key
            events_with_meta.append((date_key, rank, event))

    if not events_with_meta:
        print("⚠️  No events found in input file.")
        sys.exit(0)

    events_with_meta.sort(key=lambda x: (x[0], x[1]))

    output_dir = Path(args.output)
    print(f"\n🎨  Generating {len(events_with_meta)} slide(s) → {output_dir}/\n")
    paths = render_slides(events_with_meta, output_dir)
    print(f"\n✅  Done! {len(paths)} PNG(s) saved to {output_dir}/")


if __name__ == "__main__":
    main()
