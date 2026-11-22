"""Share cards: the images a link preview shows."""
from __future__ import annotations

import functools
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from formatting import fmt_fee, fmt_span
from maps import MAP_HEIGHT, MAP_OUTLINE, MAP_WIDTH, map_point, venue_pin
from photos import photo_info
from settings import ROOT, SHARE_SIZE, SITE_NAME, SITE_URL

FONTS = ROOT / "scripts" / "fonts"

# Drawn at twice the size and halved, because Pillow does not antialias shapes.
CARD_SCALE = 2
CARD_PAD = 64
CARD_TITLE_SIZES = (72, 60)
CARD_TITLE_LINES = 3
CARD_LINE_SIZE = 36
CARD_MAP_HEIGHT = 400
CARD_BAND = 16
# The light theme's tokens (spec 6.5): a share card has no dark mode.
CARD_COLOURS = {"ink": "#1C1C1C", "muted": "#5C5C5C", "rule": "#E0E0E0", "brand": "#8C1C24",
                "background": "#FFFFFF"}


@functools.lru_cache(maxsize=None)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size * CARD_SCALE)


@functools.lru_cache(maxsize=1)
def _map_rings() -> tuple:
    rings = json.loads(MAP_OUTLINE.read_text(encoding="utf-8"))
    return tuple(tuple(map_point(lat, lon) for lon, lat in ring) for ring in rings)


def _card_text_width() -> float:
    map_w = MAP_WIDTH * CARD_MAP_HEIGHT / MAP_HEIGHT
    return (SHARE_SIZE[0] - 2 * CARD_PAD - map_w - 48) * CARD_SCALE


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str] | None:
    """Greedy word wrap, or None when a single word is wider than the line."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font.getlength(trial) <= width:
            line = trial
        elif not line or font.getlength(word) > width:
            return None
        else:
            lines.append(line)
            line = word
    return lines + [line]


def card_layout(title: str, lines: list[tuple[str, str]]) -> dict | None:
    """The title at the largest size that fits, or None when nothing fits.

    Never shrunk past the last size: a smaller title would be unreadable in a feed, so the
    fix is a shorter name, the same rule as the video captions.
    """
    width = _card_text_width()
    small = _font("LiberationSans-Regular.ttf", CARD_LINE_SIZE)
    if any(small.getlength(text) > width for text, _ in lines):
        return None
    for size in CARD_TITLE_SIZES:
        wrapped = _wrap(title, _font("LiberationSans-Bold.ttf", size), width)
        if wrapped and len(wrapped) <= CARD_TITLE_LINES:
            return {"title": wrapped, "size": size, "lines": lines}
    return None


def draw_card(layout: dict, dots: list[tuple[float, float]], path: Path) -> None:
    S, (W, H), c = CARD_SCALE, SHARE_SIZE, CARD_COLOURS
    img = Image.new("RGB", (W * S, H * S), c["background"])
    d = ImageDraw.Draw(img)
    k = CARD_MAP_HEIGHT * S / MAP_HEIGHT
    x0 = (W - CARD_PAD) * S - MAP_WIDTH * k
    y0 = ((H - CARD_BAND) * S - CARD_MAP_HEIGHT * S) / 2
    for ring in _map_rings():
        d.polygon([(x0 + x * k, y0 + y * k) for x, y in ring], fill=c["rule"])
    r = 12 * S
    for lat, lon in dots:
        x, y = map_point(lat, lon)
        cx, cy = x0 + x * k, y0 + y * k
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c["brand"], outline=c["background"], width=4 * S)
    d.text((CARD_PAD * S, CARD_PAD * S), SITE_NAME, font=_font("LiberationSerif-Regular.ttf", 40), fill=c["brand"])
    y = 160 * S
    bold = _font("LiberationSans-Bold.ttf", layout["size"])
    for line in layout["title"]:
        d.text((CARD_PAD * S, y), line, font=bold, fill=c["ink"])
        y += round(layout["size"] * 1.15) * S
    y += 24 * S
    small = _font("LiberationSans-Regular.ttf", CARD_LINE_SIZE)
    for text, colour in layout["lines"]:
        d.text((CARD_PAD * S, y), text, font=small, fill=c[colour])
        y += round(CARD_LINE_SIZE * 1.4) * S
    d.rectangle((0, (H - CARD_BAND) * S, W * S, H * S), fill=c["brand"])
    path.parent.mkdir(parents=True, exist_ok=True)
    # An exact halving: reduce averages each 2x2 block, the right filter and far faster than LANCZOS.
    img.reduce(CARD_SCALE).save(path, "PNG")


def plan_cards(events: dict, rows: list[dict]) -> tuple[dict, list, list[str]]:
    """The share image for every page, the cards to draw, and any name too long for one.

    Returns (og by page key, [(path, layout, dots)], errors). Page keys are "site", an event
    slug, or an edition's path. Runs before the output folder is touched, so a name that
    does not fit fails the build with the last site still in place.
    """
    og, todo, errors = {}, [], []

    def card(key: str, rel: str, title: str, lines: list, dots: list, where: str) -> None:
        layout = card_layout(title, lines)
        if layout is None:
            errors.append(f"{where}: {title!r} does not fit the share card in {CARD_TITLE_LINES} lines. "
                          f"Shorten the name; the card never shrinks it further")
            return
        todo.append((rel, layout, dots))
        alt = ". ".join([title] + [text for text, _ in lines]) + "."
        og[key] = {"url": f"{SITE_URL}/{rel}", "alt": alt}

    def pins(*pins) -> list:
        return [(p["lat"], p["lon"]) for p in pins if p]

    card("site", "static/cards/site.png", "Classic car events in Japan",
         [("Japanese and imported", "muted"), ("Dates, access and admission", "muted")],
         pins(*(venue_pin(ev) for _, ev in sorted(events.items()))), "SITE_NAME")
    for slug, ev in sorted(events.items()):
        photo = photo_info(ev)
        shared = {"url": f"{SITE_URL}/{photo['share']}", "alt": photo["alt"]} if photo and photo["share"] else None
        if shared:
            og[slug] = shared
        else:
            lines = [(ev["prefecture"], "ink")]
            if ev["spectator_fee_jpy"] is not None:
                lines.append((fmt_fee(ev["spectator_fee_jpy"]), "muted"))
            card(slug, f"static/cards/events/{slug}.png", ev["name_en"], lines, pins(venue_pin(ev)),
                 f"events/{slug}.yml")
        for r in rows:
            if r["slug"] != slug or not r["has_page"]:
                continue
            if shared:
                og[r["path"]] = shared
                continue
            status = {"tentative": "Dates not confirmed", "cancelled": "Cancelled"}.get(r["ed"]["status"])
            lines = ([(status, "brand")] if status else []) + [
                (fmt_span(r["ed"]["start"], r["ed"]["end"], year=True), "ink"), (r["prefecture"], "muted")]
            card(r["path"], f"static/cards/{r['path'].rstrip('/')}.png", r["full_name"], lines,
                 pins(r["pin"]), f"events/{slug}/{r['id']}.yml")
    return og, todo, errors
