#!/usr/bin/env python3
"""Build Classic Motoring Japan: data/ -> site/.

Validation runs first. Any problem fails the build with a list of errors.
Nothing here reads the clock, so the same data always produces the same files.
Upcoming vs past is decided in the visitor's browser (see templates/home.html).

An event can run more than once a year. Each run is an edition file:
  data/events/<slug>/2026.yml          one run that year
  data/events/<slug>/2026-spring.yml   several runs that year, one file each
The file name is the edition's permanent ID: it forms the page URL and the calendar UID.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
from xml.sax.saxutils import escape as xml_escape

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

SITE_NAME = "Classic Motoring Japan"
SITE_URL = "https://classicmotoringjapan.com"
# Also the search snippet, the share text and the llms.txt summary, so it has to say
# what the site covers without the home page's heading above it.
SITE_LEDE = ("Events across Japan for classic cars, Japanese and imported: when and where to watch, "
             "how to get there, and what you'll see.")
ABOUT_DESCRIPTION = ("How Classic Motoring Japan's event listings are translated from, and checked "
                     "against, each organiser's own announcements.")
ISSUES_URL = "https://github.com/tagawa/ClassicMotoringJapan/issues"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@ClassicMotoringJapan"
# Crawling is allowed; training on the text is not. Declared where a crawler already looks.
CONTENT_SIGNAL = "search=yes, ai-input=yes, ai-train=no"
# ARD renamed its manifest; the old path is still what scanners and older consumers read.
ARD_PATH = ".well-known/ard.json"
ARD_PREDECESSOR_PATH = ".well-known/ai-catalog.json"
UID_DOMAIN = "classicmotoringjapan.com"
# Public by design: search engines fetch /<key>.txt to confirm a ping came from this site.
# Changing it only means the next deploy resubmits every page (see scripts/indexnow.py).
INDEXNOW_KEY = "f257bb565b29833c5531031252154d80"
# Thunderbird has never read X-WR-CALNAME (bugzilla 168176, open since 2002): it names a
# subscribed calendar after the last path segment, so the file name has to read as a name.
FEED_FILE = "classic-car-events.ics"
GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/render"

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))
STATUSES = {"confirmed", "tentative", "cancelled"}
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EDITION_FILE_RE = re.compile(r"^(?P<year>\d{4})(?:-(?P<edition>[a-z0-9]+(?:-[a-z0-9]+)*))?$")
# Japan's bounding box, Yonaguni to Minamitorishima. A swapped or mistyped pair lands
# outside it, which is the only coordinate mistake a build can catch on its own.
JAPAN_LAT = (24.0, 46.0)
JAPAN_LON = (122.0, 154.0)
# The home page maps: the four main islands and their neighbours, not the whole range above.
# A venue outside this box fails a test rather than a dot being clipped at the edge.
MAP_LON = (128.5, 146.0)
MAP_LAT = (30.0, 45.7)
MAP_SCALE = 10
# Longitude squeezed to its length at 36N, the middle of Honshu, so the islands keep their shape.
MAP_X = math.cos(math.radians(36)) * MAP_SCALE
MAP_WIDTH = round((MAP_LON[1] - MAP_LON[0]) * MAP_X, 1)
MAP_HEIGHT = round((MAP_LAT[1] - MAP_LAT[0]) * MAP_SCALE, 1)
MAP_OUTLINE = ROOT / "data" / "japan_outline.json"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# The privacy-enhanced domain: YouTube sets no cookies until the visitor presses play.
VIDEO_EMBED_URL = "https://www.youtube-nocookie.com/embed/"
VIDEO_WATCH_URL = "https://www.youtube.com/watch?v="
URL_RE = re.compile(r"^https?://\S+$")
# The one piece of markup prose may carry. https only: the target is fixed at build time,
# so there is no reason to link anywhere insecure, and nothing else can reach an href.
LINK_RE = re.compile(r"\[([^\[\]]+)\]\((https://[^\s()]+)\)")
# Long prose buries the facts inside it, and a skim-reader never finds them.
PROSE_MAX_WORDS = 75
# Advice, not facts. Cutting one of these loses nothing a visitor came for: the page
# says what is true and lets the reader draw the conclusion. Deliberately narrow, so a
# match is always a real one; judgement calls the list cannot make are in CLAUDE.md.
EDITORIAL_PHRASES = (
    "the practical way to", "the best way to", "the easiest way to",
    "worth a look", "worth a visit", "worth the trip", "well worth", "worth it",
    "don't miss", "do not miss", "not to be missed",
    "a must", "must-see", "must see", "must-visit", "must visit",
    "perfect for", "ideal for", "be sure to", "make sure to",
    "if you're looking for", "highly recommended", "we recommend",
    "a great place to", "a good place to", "no visit is complete",
)
# Whitespace in a phrase spans the line breaks a folded YAML scalar leaves behind.
EDITORIAL_RE = re.compile(
    r"\b(" + "|".join(r"\s+".join(map(re.escape, phrase.split())) for phrase in EDITORIAL_PHRASES) + r")\b"
)
# Percent of the axis. An open-ended checkpoint has no width of its own but still
# has to be visible, so every bar gets a floor.
CHART_MIN_BAR = 1.0

EVENT_REQUIRED = {
    "slug": "str", "name_en": "str", "official_url": "url",
    "prefecture": "str", "venue_en": "str", "spectator_fee_jpy": "fee",
    "last_verified": "date",
}
EVENT_OPTIONAL = {
    # Plenty of Japanese car events are named only in Latin script and have no Japanese
    # form at all. Printing the Latin name again under lang="ja" would tell a screen
    # reader to read it with Japanese pronunciation rules.
    "name_ja": "str",
    "organizer": "str", "summary_en": "prose", "street_address": "str",
    "nearest_station": "prose", "access_notes_en": "prose", "typical_eras": "strlist",
    "typical_scale": "str", "spectator_notes_en": "prose", "photography_notes_en": "prose",
    "lat": "lat", "lon": "lon",
    # The newest build year the organiser accepts, only where a source states one exactly.
    "cutoff_year": "int",
}
EDITION_REQUIRED = {
    "slug": "str", "year": "int", "status": "status", "start": "date", "end": "date",
    "source_url": "url", "last_verified": "date", "sequence": "count",
}
EDITION_OPTIONAL = {
    "start_time": "time", "end_time": "time", "venue_en": "str", "street_address": "str",
    # For an event that moves: the prefecture this edition ran in, when it is not the event's.
    "prefecture": "str",
    "route_en": "prose", "route": "route", "list_as_of": "date", "cars": "cars",
    "lat": "lat", "lon": "lon", "videos": "videos",
    # For an event whose limit moves each year: this edition's, when it is not the event's.
    "cutoff_year": "int",
}
ROUTE_DAY_REQUIRED = {"date": "date", "checkpoints": "checkpoints"}
CHECKPOINT_REQUIRED = {"start_time": "time", "place_en": "str", "prefecture": "str"}
CHECKPOINT_OPTIONAL = {"end_time": "time", "place_ja": "str"}
# The ID alone, not a URL, so the embed domain is chosen once, in VIDEO_EMBED_URL.
VIDEO_REQUIRED = {"youtube_id": "youtube_id", "label_en": "str"}
# Fields the templates render into a single block. The cap has to apply to what a
# reader actually sees there, not to each field measured on its own.
COMBINED_PROSE = (("nearest_station", "access_notes_en"),)
# A source that names the models a show will have on the floor gives neither an entry
# number nor a year, and a model's production span is not the age of the car on the stand.
CAR_REQUIRED = {"make": "str", "model": "str"}
CAR_OPTIONAL = {"entry_no": "str", "year": "int", "colour": "str", "country": "country"}


def _stripes(colours, across: bool) -> str:
    """Equal bands on the 30 by 20 field every flag is drawn on."""
    size = (30 if across else 20) / len(colours)
    return "".join(
        f'<path fill="{c}" d="M{round(i * size, 2)} 0h{round(size, 2)}v20h-{round(size, 2)}z"/>' if across
        else f'<path fill="{c}" d="M0 {round(i * size, 2)}h30v{round(size, 2)}H0z"/>'
        for i, c in enumerate(colours))


# The /ja/ page's lede and meta description, the same sentence, as on the home page.
JA_LEDE = ("日本各地のクラシックカーイベントの日程です。"
           "ルート、エントリーリスト、動画などの詳細は英語のページにあります。")

# The /ja/ page's prefecture names, keyed by the romanised form the data uses (no macrons).
# Validation rejects any other value, so a typo or a first event in a new prefecture
# fails the build here rather than printing nothing on that page.
PREFECTURES_JA = {
    "Hokkaido": "北海道", "Aomori": "青森県", "Iwate": "岩手県", "Miyagi": "宮城県",
    "Akita": "秋田県", "Yamagata": "山形県", "Fukushima": "福島県", "Ibaraki": "茨城県",
    "Tochigi": "栃木県", "Gunma": "群馬県", "Saitama": "埼玉県", "Chiba": "千葉県",
    "Tokyo": "東京都", "Kanagawa": "神奈川県", "Niigata": "新潟県", "Toyama": "富山県",
    "Ishikawa": "石川県", "Fukui": "福井県", "Yamanashi": "山梨県", "Nagano": "長野県",
    "Gifu": "岐阜県", "Shizuoka": "静岡県", "Aichi": "愛知県", "Mie": "三重県",
    "Shiga": "滋賀県", "Kyoto": "京都府", "Osaka": "大阪府", "Hyogo": "兵庫県",
    "Nara": "奈良県", "Wakayama": "和歌山県", "Tottori": "鳥取県", "Shimane": "島根県",
    "Okayama": "岡山県", "Hiroshima": "広島県", "Yamaguchi": "山口県", "Tokushima": "徳島県",
    "Kagawa": "香川県", "Ehime": "愛媛県", "Kochi": "高知県", "Fukuoka": "福岡県",
    "Saga": "佐賀県", "Nagasaki": "長崎県", "Kumamoto": "熊本県", "Oita": "大分県",
    "Miyazaki": "宮崎県", "Kagoshima": "鹿児島県", "Okinawa": "沖縄県",
}

# Where an organiser's list says a car was built: ISO 3166 code, the name read out in place
# of the flag, and the flag itself. Drawn here, not fetched, so the site still ships no image
# files and needs no emoji font, which Windows lacks for flags. Colours are each country's own.
# Any id inside a drawing starts "flag-" and is its alone, since one page can carry them all.
COUNTRIES = {
    "DE": ("Germany", _stripes(("#000000", "#DD0000", "#FFCC00"), across=False)),
    "FR": ("France", _stripes(("#000091", "#FFFFFF", "#E1000F"), across=True)),
    # The red saltire is counterchanged, which the clip path does: each arm shows on one side
    # of its diagonal only. Widths are the flag's own, scaled from a height of 30 to 20.
    "GB": ("Britain",
           '<clipPath id="flag-gb-arms"><path d="M15 10h15v10zv10H0zH0V0zV0h15z"/></clipPath>'
           '<path fill="#012169" d="M0 0h30v20H0z"/>'
           '<path stroke="#FFFFFF" stroke-width="4" d="M0 0l30 20M30 0L0 20"/>'
           '<path stroke="#C8102E" stroke-width="2.67" clip-path="url(#flag-gb-arms)" d="M0 0l30 20M30 0L0 20"/>'
           '<path stroke="#FFFFFF" stroke-width="6.67" d="M15 0v20M0 10h30"/>'
           '<path stroke="#C8102E" stroke-width="4" d="M15 0v20M0 10h30"/>'),
    "IT": ("Italy", _stripes(("#009246", "#FFFFFF", "#CE2B37"), across=True)),
    "JP": ("Japan", '<path fill="#FFFFFF" d="M0 0h30v20H0z"/><circle fill="#BC002D" cx="15" cy="10" r="6"/>'),
    "SE": ("Sweden", '<path fill="#006AA7" d="M0 0h30v20H0z"/><path fill="#FECC02" d="M9.38 0h3.75v20H9.38zM0 8h30v4H0z"/>'),
    # Fifty stars do not survive at this size, so the canton carries a grid of dots.
    "US": ("USA",
           _stripes(("#B22234", "#FFFFFF") * 6 + ("#B22234",), across=False)
           + '<path fill="#3C3B6E" d="M0 0h12v10.77H0z"/>'
           + "".join(f'<circle fill="#FFFFFF" cx="{1.5 + 2.25 * col}" cy="{1.6 + 2.5 * row}" r="0.5"/>'
                     for row in range(4) for col in range(5))),
}
# Order of the table's columns. A column no car fills is dropped, not left blank.
CAR_COLUMNS = (("entry_no", "No.", True), ("year", "Year", True), ("make", "Make", False),
               ("model", "Model", False), ("colour", "Colour", False))


class BuildError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


class ValidationError(BuildError):
    """Problems in data/."""


# Validation

def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check_editorial(v: str, where: str, errors: list[str]) -> None:
    """Refuse prose that tells the reader what to think instead of what is true."""
    # NFKC folds full-width forms; the apostrophe swap is separate because it does not.
    text = unicodedata.normalize("NFKC", v).lower().replace("\u2019", "'")
    for match in EDITORIAL_RE.finditer(text):
        # Report the phrase, not the line break a folded scalar happened to put inside it.
        phrase = " ".join(match.group(0).split())
        errors.append(
            f"{where}: {phrase!r} is advice, not a fact, and the page is a reference. "
            f"Cut it, or replace it with the fact it stands in for"
        )


def prose_text(v: str) -> str:
    """Prose as a reader hears it: each link reduced to its text."""
    return LINK_RE.sub(r"\1", v)


def prose_html(v: str) -> Markup:
    """Prose for a page: escaped throughout, with each link made an anchor."""
    out, pos = [], 0
    for m in LINK_RE.finditer(v):
        out += [escape(v[pos:m.start()]),
                Markup('<a href="{}">{}</a>').format(m.group(2), m.group(1))]
        pos = m.end()
    out.append(escape(v[pos:]))
    return Markup("").join(out)


def _check_links(v: str, where: str, errors: list[str]) -> None:
    """A link that does not parse would reach the page as raw brackets, so refuse it."""
    if re.search(r"<a\b", v, re.I):
        errors.append(f"{where}: HTML is shown as literal text. Write a link as [text](https://...)")
    elif re.search(r"[\[\]]", prose_text(v)):
        errors.append(f"{where}: a link must be written exactly as [text](https://...), "
                      f"with no space between ] and ( and an https:// address")


def _check_value(kind: str, v, where: str, errors: list[str]) -> None:
    if kind == "str":
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{where}: must be non-empty text, got {v!r}")
    elif kind == "url":
        if not isinstance(v, str) or not URL_RE.match(v):
            errors.append(f"{where}: must be a full http(s) URL, got {v!r}")
    elif kind == "date":
        if type(v) is not dt.date:
            errors.append(f"{where}: must be an unquoted date like 2026-10-18, got {v!r}")
    elif kind == "fee":
        # null is its own state: the organizer has not announced the admission. It is not
        # 0, which is a positive claim that watching costs nothing.
        if v is not None and (not _is_int(v) or v < 0):
            errors.append(f"{where}: must be a whole number of 0 or more, or null where the "
                          f"organizer has not announced the admission, got {v!r}")
    elif kind in ("int", "count"):
        if not _is_int(v) or (kind != "int" and v < 0):
            errors.append(f"{where}: must be a whole number{' of 0 or more' if kind != 'int' else ''}, got {v!r}")
    elif kind == "status":
        if v not in STATUSES:
            errors.append(f"{where}: must be one of {sorted(STATUSES)}, got {v!r}")
    elif kind == "country":
        if v not in COUNTRIES:
            errors.append(f"{where}: must be one of {sorted(COUNTRIES)}, the countries the site has a "
                          f"flag for, got {v!r}")
    elif kind == "time":
        if _is_int(v):
            errors.append(
                f'{where}: YAML read this as the number {v}. Write it as a quoted string, '
                f'e.g. "{v // 60:02d}:{v % 60:02d}"'
            )
        elif not isinstance(v, str) or not TIME_RE.match(v):
            errors.append(f'{where}: must be a quoted 24-hour time like "08:00", got {v!r}')
    elif kind in ("lat", "lon"):
        low, high = JAPAN_LAT if kind == "lat" else JAPAN_LON
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"{where}: must be a decimal number, got {v!r}")
        elif not low <= v <= high:
            errors.append(f"{where}: {v} is outside Japan ({low} to {high}). "
                          f"Check that lat and lon have not been swapped")
    elif kind == "strlist":
        if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
            errors.append(f"{where}: must be a list of text values, got {v!r}")
    elif kind == "prose":
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{where}: must be non-empty text, got {v!r}")
        else:
            _check_links(v, where, errors)
            # Measured on what a reader sees, so a long URL costs nothing.
            v = prose_text(v)
            if len(v.split()) > PROSE_MAX_WORDS:
                errors.append(
                    f"{where}: {len(v.split())} words is too long to skim (limit {PROSE_MAX_WORDS}). "
                    f"Prose this long hides the facts inside it. Break it into bullet points, a table "
                    f"or a diagram, or move the detail into structured fields such as `route` or `cars`"
                )
            _check_editorial(v, where, errors)
    elif kind == "youtube_id":
        if not isinstance(v, str) or not YOUTUBE_ID_RE.match(v):
            errors.append(f"{where}: must be the 11-character video ID, the part of the address "
                          f"after watch?v=, got {v!r}")
    elif kind in ("cars", "route", "checkpoints", "videos"):
        if not isinstance(v, list) or not v:
            errors.append(f"{where}: must be a non-empty list")


def _check_fields(obj, required: dict, optional: dict, where: str, errors: list[str]) -> bool:
    if not isinstance(obj, dict):
        errors.append(f"{where}: expected a set of fields, got {type(obj).__name__}")
        return False
    for key in obj:
        if key is False:
            errors.append(f"{where}: a bare `no:` key is read by YAML as false. Use `entry_no:` instead")
        elif key not in required and key not in optional:
            errors.append(f"{where}: unknown field {key!r}")
    for key, kind in required.items():
        if key not in obj:
            errors.append(f"{where}: missing required field {key!r}")
        else:
            _check_value(kind, obj[key], f"{where}: {key}", errors)
    for key, kind in optional.items():
        if key in obj:
            _check_value(kind, obj[key], f"{where}: {key}", errors)
    return True


def _check_slug(name: str, where: str, errors: list[str]) -> bool:
    if SLUG_RE.match(name):
        return True
    errors.append(f"{where}: name {name!r} must use only lowercase letters, digits and single hyphens, "
                  f"e.g. autumn-rally")
    return False


def _load_yaml(path: Path, rel: str, errors: list[str]):
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        errors.append(f"{rel}: YAML syntax error: {e}")
        return None


def _check_combined_prose(ev: dict, rel: str, errors: list[str]) -> None:
    for group in COMBINED_PROSE:
        present = [(key, ev[key]) for key in group if isinstance(ev.get(key), str)]
        if len(present) < 2:
            continue
        total = sum(len(prose_text(value).split()) for _, value in present)
        if total > PROSE_MAX_WORDS:
            names = " and ".join(repr(key) for key, _ in present)
            errors.append(
                f"{rel}: {names} render as one block on the page and come to {total} words "
                f"together (limit {PROSE_MAX_WORDS}). Shorten them, or break the detail out "
                f"into bullet points, a table or a diagram"
            )


def _check_coords(obj: dict, rel: str, errors: list[str]) -> None:
    """Half a pair points nowhere, so the build refuses it rather than dropping the link."""
    if ("lat" in obj) != ("lon" in obj):
        errors.append(f"{rel}: give lat and lon together, or neither")


def _check_route(route, start, end, rel: str, errors: list[str]) -> None:
    """Days run in order inside the edition's dates, checkpoints in order inside a day."""
    if not isinstance(route, list):
        return
    previous_day = None
    for i, day in enumerate(route, 1):
        where = f"{rel}: route day {i}"
        if not _check_fields(day, ROUTE_DAY_REQUIRED, {}, where, errors):
            continue
        date = day.get("date")
        if type(date) is dt.date:
            if type(start) is dt.date and type(end) is dt.date and not start <= date <= end:
                errors.append(f"{where}: {date} is outside the edition's {start} to {end}")
            if previous_day is not None and date <= previous_day:
                errors.append(f"{where}: {date} does not come after day {i - 1} ({previous_day})")
            previous_day = date
        if not isinstance(day.get("checkpoints"), list):
            continue
        latest = None
        for j, point in enumerate(day["checkpoints"], 1):
            spot = f"{where}, checkpoint {j}"
            if not _check_fields(point, CHECKPOINT_REQUIRED, CHECKPOINT_OPTIONAL, spot, errors):
                continue
            begins, ends = point.get("start_time"), point.get("end_time")
            if isinstance(begins, str) and isinstance(ends, str) and ends <= begins:
                errors.append(f"{spot}: end_time {ends} is not after start_time {begins}")
            if isinstance(begins, str):
                if latest is not None and begins < latest:
                    errors.append(f"{spot}: {begins} comes before checkpoint {j - 1} at {latest}")
                latest = begins


class _UniqueKeyLoader(yaml.SafeLoader):
    """YAML keeps the last of two identical keys without a word, so a make entered twice
    with different countries would quietly take the second. This loader refuses instead."""


def _unique_mapping(loader, node):
    keys = [loader.construct_object(key) for key, _ in node.value]
    for key in keys:
        if keys.count(key) > 1:
            raise yaml.constructor.ConstructorError(None, None, f"{key} is listed twice", node.start_mark)
    return loader.construct_mapping(node)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_makes(data_dir: Path) -> dict:
    """data/makes.yml: each make's home country, or None where no one country fits.

    It is for a car whose list prints no country of its own; the file says more. A site
    without the file builds without flags from makes.
    """
    path = data_dir / "makes.yml"
    if not path.exists():
        return {}
    try:
        makes = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.constructor.ConstructorError as e:
        raise ValidationError([f"makes.yml: {e.problem}"])
    except yaml.YAMLError as e:
        raise ValidationError([f"makes.yml: YAML syntax error: {e}"])
    if not isinstance(makes, dict):
        raise ValidationError(["makes.yml: must be a list of makes, each with a country, e.g. Lancia: IT"])
    errors = [f"makes.yml: {make}: must be one of {sorted(COUNTRIES)}, the countries the site has a flag for, "
              f"or null where no one country fits, got {code!r}"
              for make, code in makes.items() if code is not None and code not in COUNTRIES]
    if errors:
        raise ValidationError(errors)
    return makes


def _check_prefecture(item: dict, rel: str, errors: list[str]) -> None:
    value = item.get("prefecture")
    if isinstance(value, str) and value not in PREFECTURES_JA:
        errors.append(f"{rel}: prefecture {value!r} is not one of the 47 in PREFECTURES_JA "
                      f"(romanised without macrons, e.g. Hyogo)")


def load_and_validate(data_dir: Path) -> tuple[dict, list]:
    """Return (events by slug, editions). Raise ValidationError listing every problem."""
    errors: list[str] = []
    events: dict[str, dict] = {}
    editions: list[dict] = []
    events_dir = data_dir / "events"

    for path in sorted(events_dir.glob("*.yml")):
        rel = path.relative_to(data_dir).as_posix()
        if not _check_slug(path.stem, rel, errors):
            continue
        ev = _load_yaml(path, rel, errors)
        if ev is None or not _check_fields(ev, EVENT_REQUIRED, EVENT_OPTIONAL, rel, errors):
            continue
        if ev.get("slug") != path.stem:
            errors.append(f"{rel}: slug {ev.get('slug')!r} must match the file name {path.stem!r}")
            continue
        _check_combined_prose(ev, rel, errors)
        _check_coords(ev, rel, errors)
        _check_prefecture(ev, rel, errors)
        events[path.stem] = ev

    for path in sorted(events_dir.glob("*/*.yml")):
        rel = path.relative_to(data_dir).as_posix()
        slug_dir = path.parent.name
        if not _check_slug(slug_dir, rel, errors):
            continue
        name = EDITION_FILE_RE.match(path.stem)
        if not name:
            errors.append(f"{rel}: file name must be the year (2026.yml) or the year plus an edition "
                          f"(2026-spring.yml), in lowercase letters, digits and hyphens")
            continue
        ed = _load_yaml(path, rel, errors)
        if ed is None or not _check_fields(ed, EDITION_REQUIRED, EDITION_OPTIONAL, rel, errors):
            continue
        if ed.get("slug") != slug_dir:
            errors.append(f"{rel}: slug {ed.get('slug')!r} must match the folder name {slug_dir!r}")
        if slug_dir not in events:
            errors.append(f"{rel}: no matching event file events/{slug_dir}.yml")
        if str(ed.get("year")) != name["year"]:
            errors.append(f"{rel}: year {ed.get('year')!r} must match the file name {path.name!r}")
        start, end = ed.get("start"), ed.get("end")
        if type(start) is dt.date and type(end) is dt.date:
            if end < start:
                errors.append(f"{rel}: end {end} is before start {start}")
            if _is_int(ed.get("year")) and start.year != ed["year"]:
                errors.append(f"{rel}: start {start} is not in year {ed['year']}")
        _check_coords(ed, rel, errors)
        _check_prefecture(ed, rel, errors)
        if "prefecture" in ed and "venue_en" not in ed:
            # Alone it would print the event's venue in a prefecture that venue is not in.
            errors.append(f"{rel}: prefecture on an edition needs venue_en too")
        has_st, has_et = "start_time" in ed, "end_time" in ed
        if has_st != has_et:
            errors.append(f"{rel}: give start_time and end_time together, or neither")
        elif has_st and isinstance(ed["start_time"], str) and isinstance(ed["end_time"], str):
            # Each day's hours, however many days the edition spans.
            if ed["end_time"] <= ed["start_time"]:
                errors.append(f"{rel}: end_time must be after start_time")
        cars = ed.get("cars")
        if ("cars" in ed) != ("list_as_of" in ed):
            errors.append(f"{rel}: cars and list_as_of must be given together")
        if isinstance(cars, list):
            seen = set()
            for i, car in enumerate(cars, 1):
                where = f"{rel}: cars item {i}"
                if _check_fields(car, CAR_REQUIRED, CAR_OPTIONAL, where, errors):
                    no = car.get("entry_no")
                    if isinstance(no, str):
                        if no in seen:
                            errors.append(f"{where}: duplicate entry_no {no!r}")
                        seen.add(no)
            # Same rule as a checkpoint's prefecture: a column filled for some rows and not
            # others cannot be scanned, so a number is given for every car or for none. A
            # year is not held to it: organisers leave the odd one blank, and dropping the
            # car to keep the column full would lose more than the gap does.
            filled = sum(1 for car in cars if isinstance(car, dict) and "entry_no" in car)
            if 0 < filled < len(cars):
                errors.append(f"{rel}: give entry_no on every car or on none "
                              f"({filled} of {len(cars)} have one)")
        _check_route(ed.get("route"), start, end, rel, errors)
        if isinstance(ed.get("videos"), list):
            for i, video in enumerate(ed["videos"], 1):
                _check_fields(video, VIDEO_REQUIRED, {}, f"{rel}: videos item {i}", errors)
        editions.append({"data": ed, "id": path.stem, "edition": name["edition"]})

    if errors:
        raise ValidationError(errors)
    return events, editions


# Formatting

def fmt_day(d: dt.date) -> str:
    return f"{d.day} {d:%b %Y}"


def fmt_range(start: dt.date, end: dt.date) -> str:
    if start == end:
        return fmt_day(start)
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}\u2013{end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%b} \u2013 {end.day} {end:%b %Y}"
    return f"{fmt_day(start)} \u2013 {fmt_day(end)}"


def fmt_span(start: dt.date, end: dt.date, year: bool = False) -> str:
    """A date or a run of days with weekdays, which is what a weekend is planned by.

    The year is left to a heading above it unless asked for, but a span across the new
    year always names both, since one heading cannot.
    """
    def day(d: dt.date) -> str:
        return f"{d:%a} {d.day}"
    if start.year != end.year:
        return f"{day(start)} {start:%b %Y} to {day(end)} {end:%b %Y}"
    tail = f" {end.year}" if year else ""
    if start == end:
        return f"{day(start)} {start:%b}{tail}"
    if start.month == end.month:
        return f"{day(start)} to {day(end)} {end:%b}{tail}"
    return f"{day(start)} {start:%b} to {day(end)} {end:%b}{tail}"


def fmt_leaf(start: dt.date, end: dt.date) -> tuple[str, str]:
    """A date as the home list's calendar leaf draws it: weekdays on the band, days beneath.

    The month heading above names the month, so the days name one only when they cross into the next.
    """
    if start == end:
        return f"{start:%a}", f"{start.day}"
    weekdays = f"{start:%a}\u2013{end:%a}"
    if (start.year, start.month) == (end.year, end.month):
        return weekdays, f"{start.day}\u2013{end.day}"
    return weekdays, f"{start.day} {start:%b}\u2013{end.day} {end:%b}"


def _minutes(hhmm: str) -> int:
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def route_chart(route) -> dict | None:
    """Day shapes on one shared axis: which day starts late, which one runs long.

    Derived from the same checkpoints the tables render, so the picture cannot
    disagree with the numbers beside it.
    """
    if not route:
        return None
    points = [(p, _minutes(p["start_time"]),
               _minutes(p["end_time"]) if p.get("end_time") else _minutes(p["start_time"]))
              for day in route for p in day["checkpoints"]]
    axis_start = min(begins for _, begins, _ in points) // 60 * 60
    # One hour past the last stop, so a bar that starts on the hour still sits inside.
    axis_end = (max(finishes for _, _, finishes in points) // 60 + 1) * 60
    span = axis_end - axis_start

    days = []
    for number, day in enumerate(route, 1):
        windows = [(_minutes(p["start_time"]),
                    _minutes(p["end_time"]) if p.get("end_time") else _minutes(p["start_time"]))
                   for p in day["checkpoints"]]
        stops = len(windows)
        days.append({
            "when": f"Day {number}, {day['date']:%a} {day['date'].day} {day['date']:%b}",
            "summary": (f"{_hhmm(min(b for b, _ in windows))} to {_hhmm(max(f for _, f in windows))}, "
                        f"{stops} stop{'' if stops == 1 else 's'}"),
            "bars": [{"left": round((begins - axis_start) / span * 100, 2),
                      "width": round(max((finishes - begins) / span * 100, CHART_MIN_BAR), 2)}
                     for begins, finishes in windows],
        })
    return {"start": _hhmm(axis_start), "end": _hhmm(axis_end), "days": days}

def with_countries(cars, makes: dict):
    """Each car with the country its flag shows: its own where it has one, else its make's."""
    if not cars:
        return cars
    return [{**car, "country": country} if (country := car.get("country") or makes.get(car["make"])) else car
            for car in cars]


def car_columns(cars) -> list[dict]:
    """The columns the table shows: the ones at least one car fills."""
    return [{"key": key, "label": label, "num": num} for key, label, num in CAR_COLUMNS
            if any(key in car for car in cars or [])]


def decade_chart(cars) -> dict | None:
    """How an entry list falls by decade, counted from the rows the table renders.

    A decade with no cars keeps its row, so a gap in the field stays visible instead of
    closing up and reading as a run. A list without years has nothing to count. Cars the
    organiser gave no year for are counted in a closing line, so the strip still adds up
    to the table it sits above.
    """
    years = [car["year"] for car in cars or [] if "year" in car]
    if not years:
        return None
    counts: dict[int, int] = {}
    for year in years:
        decade = year // 10 * 10
        counts[decade] = counts.get(decade, 0) + 1
    peak = max(counts.values())
    rows = []
    for decade in range(min(counts), max(counts) + 10, 10):
        n = counts.get(decade, 0)
        rows.append({
            "label": f"{decade}s",
            "count": n,
            "unit": "car" if n == 1 else "cars",
            "width": round(max(n / peak * 100, CHART_MIN_BAR), 2) if n else 0,
        })
    undated = len(cars) - len(years)
    return {"rows": rows,
            "rest": f"No year given: {undated} car{'' if undated == 1 else 's'}" if undated else None}


def makes_chart(cars) -> dict | None:
    """Which makes an entry list has several of, counted from the rows the table renders.

    A make with one car would only repeat its table row, so those share a single line.
    Counted only when every row has an entry number: there a row is a car, whereas a
    show's announced line-up names models, and two models are not two cars.
    """
    if not cars or not all("entry_no" in car for car in cars):
        return None
    counts: dict[str, int] = {}
    for car in cars:
        counts[car["make"]] = counts.get(car["make"], 0) + 1
    several = sorted(((make, n) for make, n in counts.items() if n > 1),
                     key=lambda pair: (-pair[1], pair[0].casefold()))
    rows = [{"label": make, "count": n, "unit": "cars",
             "width": round(max(n / several[0][1] * 100, CHART_MIN_BAR), 2)} for make, n in several]
    singles = len(counts) - len(several)
    rest = None
    if singles:
        # "and" only when there are rows above for it to follow on from.
        rest = (("and " if rows else "")
                + (f"{singles} makes with one car each" if singles > 1 else "1 make with one car"))
    return {"rows": rows, "rest": rest}


def year_chart(rows: list[dict]) -> list[dict]:
    """Where a year's editions fall across its months: which season the hobby runs in."""
    years = []
    for year in sorted({r["year"] for r in rows}):
        editions = [r["ed"] for r in rows if r["year"] == year]
        days = dt.date(year, 12, 31).timetuple().tm_yday
        first, last = min(e["start"] for e in editions), max(e["start"] for e in editions)
        when = f"{first:%b}" if first.month == last.month else f"{first:%b} to {last:%b}"
        years.append({
            "year": year,
            "label": f"{year}: {len(editions)} event{'' if len(editions) == 1 else 's'}, {when}",
            "bars": [{"left": round((e["start"].timetuple().tm_yday - 1) / days * 100, 2),
                      "width": round(max(((e["end"] - e["start"]).days + 1) / days * 100,
                                         CHART_MIN_BAR), 2),
                      "cancelled": e["status"] == "cancelled",
                      # The browser greys the bars whose last day has passed; the build never reads the clock.
                      "end": e["end"].isoformat()}
                     for e in editions],
        })
    return years


def fmt_weekday(d: dt.date) -> str:
    return f"{d:%A} {d.day} {d:%B}"


def fmt_domain(url: str) -> str:
    # A source is named by where it is, since it is often a listing, a blog or a video
    # rather than the organiser's own page, and a domain is true of all of them.
    host = urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host


def fmt_fee(fee: int | None) -> str:
    # Self-describing, because the home page prints it with no label beside it.
    if fee is None:
        return "Admission not announced"
    return "Free to watch" if fee == 0 else f"\u00a5{fee:,}"


# Weekdays from a fixed string, never the locale, which differs between this Mac and the Actions runner.
WEEKDAYS_JA = "月火水木金土日"


def fmt_span_ja(start: dt.date, end: dt.date) -> str:
    """fmt_span for the /ja/ page: the month heading carries the year unless the span crosses it."""
    def day(d: dt.date) -> str:
        return f"{d.day}日({WEEKDAYS_JA[d.weekday()]})"
    if start.year != end.year:
        return f"{start.year}年{start.month}月{day(start)}〜{end.year}年{end.month}月{day(end)}"
    if start == end:
        return f"{start.month}月{day(start)}"
    if start.month == end.month:
        return f"{start.month}月{day(start)}〜{day(end)}"
    return f"{start.month}月{day(start)}〜{end.month}月{day(end)}"


def fmt_month_ja(key: str) -> str:
    year, month = key.split("-")
    return f"{year}年{int(month)}月"


def fmt_fee_ja(fee: int | None) -> str:
    if fee is None:
        return "入場料未発表"
    return "入場無料" if fee == 0 else f"入場料 {fee:,}円"


def fmt_edition(edition: str) -> str:
    return edition.replace("-", " ").capitalize()


def _local_dt(d: dt.date, hhmm: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST)


# Map links

def venue_pin(ev: dict, ed: dict | None = None) -> dict | None:
    """Where a map link points, or None when no coordinates have been recorded.

    Coordinates belong to the venue they were taken at, so an edition that names a venue of
    its own does not inherit the event's pin: no link beats a link to the wrong field.
    """
    if ed and "lat" in ed:
        source = ed
    elif ed and ed.get("venue_en"):
        return None
    else:
        source = ev
    if "lat" not in source:
        return None
    # ll fixes the point and q only labels the pin, so the label cannot move it.
    label = (ed or {}).get("venue_en") or ev["venue_en"]
    return {"lat": source["lat"], "lon": source["lon"],
            "url": f"https://maps.apple.com/?ll={source['lat']},{source['lon']}&q={quote(label)}"}


# Maps

def map_point(lat: float, lon: float) -> tuple[float, float]:
    """The one projection: the coastline and every dot go through it, so they cannot disagree."""
    return round((lon - MAP_LON[0]) * MAP_X, 1), round((MAP_LAT[1] - lat) * MAP_SCALE, 1)


def japan_path() -> str:
    rings = json.loads(MAP_OUTLINE.read_text(encoding="utf-8"))
    return " ".join("M" + " ".join("%g,%g" % map_point(lat, lon) for lon, lat in ring) + "Z"
                    for ring in rings)


# iCalendar

def ics_text(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_fold(line: str) -> str:
    """Fold to 75 octets per physical line without splitting a UTF-8 character."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts, cur, limit = [], b"", 75
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > limit:
            parts.append(cur.decode("utf-8"))
            cur, limit = b"", 74
        cur += cb
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def event_location(r: dict) -> str:
    return f"{r['venue']}, {r['prefecture']}, Japan"


def event_details(r: dict) -> str:
    return "\n".join(filter(None, (r["ev"].get("name_ja"), r["abs_url"],
                                   f"Last verified {r['ed']['last_verified']}")))


def ics_event_lines(r: dict) -> list[str]:
    ed = r["ed"]
    lines = ["BEGIN:VEVENT", f"UID:{r['uid']}",
             f"DTSTAMP:{ed['last_verified']:%Y%m%d}T000000Z",
             f"SEQUENCE:{ed['sequence']}"]
    if r["is_timed"]:
        fmt = "%Y%m%dT%H%M%SZ"
        lines += [f"DTSTART:{r['start_dt'].astimezone(dt.timezone.utc):{fmt}}",
                  f"DTEND:{r['day_end_dt'].astimezone(dt.timezone.utc):{fmt}}"]
        if r["rrule"]:
            lines.append(f"RRULE:{r['rrule']}")
    else:
        lines += [f"DTSTART;VALUE=DATE:{ed['start']:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{ed['end'] + dt.timedelta(days=1):%Y%m%d}"]
    lines += [
        f"SUMMARY:{ics_text(r['display_name'])}",
        f"LOCATION:{ics_text(event_location(r))}",
    ]
    if r["pin"]:
        lines.append(f"GEO:{r['pin']['lat']};{r['pin']['lon']}")
    lines += [
        f"URL:{r['abs_url']}",
        f"DESCRIPTION:{ics_text(event_details(r))}",
        f"STATUS:{ed['status'].upper()}",
        "END:VEVENT",
    ]
    return lines


def ics_calendar(header: list[str], rows: list[dict]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{SITE_NAME}//Events//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"] + header
    for r in rows:
        lines += ics_event_lines(r)
    lines.append("END:VCALENDAR")
    return "".join(ics_fold(line) + "\r\n" for line in lines)


def google_calendar_url(r: dict) -> str:
    """Google's add-event form, filled in. Its Android app cannot open an .ics file at all."""
    details = event_details(r)
    if r["is_timed"] and not r["rrule"]:
        fmt = "%Y%m%dT%H%M%SZ"
        dates = (f"{r['start_dt'].astimezone(dt.timezone.utc):{fmt}}/"
                 f"{r['day_end_dt'].astimezone(dt.timezone.utc):{fmt}}")
    else:
        # An exclusive end, as in the feed. Google's form documents no repeat rule, so a
        # multi-day timed edition goes as all-day with its daily hours written out.
        dates = f"{r['ed']['start']:%Y%m%d}/{r['ed']['end'] + dt.timedelta(days=1):%Y%m%d}"
        if r["is_timed"]:
            details = (f"{r['ed']['start_time']} to {r['ed']['end_time']} Japan time each day\n"
                       + details)
    return GOOGLE_CALENDAR_URL + "?" + urlencode(
        {"action": "TEMPLATE", "text": r["display_name"], "dates": dates,
         "location": event_location(r), "details": details}, quote_via=quote)


def build_ics(rows: list[dict]) -> str:
    return ics_calendar([
        f"X-WR-CALNAME:{ics_text(SITE_NAME)}",
        # RFC 7986's spelling of the same thing. Neither reaches Thunderbird; see FEED_FILE.
        f"NAME:{ics_text(SITE_NAME)}",
    ], rows)


# Structured data

def build_jsonld(r: dict) -> Markup:
    ev, ed = r["ev"], r["ed"]
    address = {"@type": "PostalAddress", "addressRegion": r["prefecture"], "addressCountry": "JP"}
    street = ed.get("street_address") or ev.get("street_address")
    if street:
        address["streetAddress"] = street
    place = {"@type": "Place", "name": r["venue"], "address": address}
    if r["pin"]:
        place["geo"] = {"@type": "GeoCoordinates",
                        "latitude": r["pin"]["lat"], "longitude": r["pin"]["lon"]}
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": r["full_name"],
        "startDate": r["start_dt"].isoformat() if r["is_timed"] else ed["start"].isoformat(),
        "endDate": r["end_dt"].isoformat() if r["is_timed"] else ed["end"].isoformat(),
        "eventStatus": "https://schema.org/EventCancelled" if ed["status"] == "cancelled"
                       else "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": place,
        "url": r["abs_url"],
    }
    # An unannounced admission is not a free one, and false would be a claim of its own.
    if ev["spectator_fee_jpy"] is not None:
        data["isAccessibleForFree"] = ev["spectator_fee_jpy"] == 0
        # No offer url: Google means a ticket page by it, and the data has none.
        data["offers"] = {"@type": "Offer", "price": ev["spectator_fee_jpy"], "priceCurrency": "JPY"}
    if ev.get("summary_en"):
        data["description"] = prose_text(ev["summary_en"]).strip()
    if ev.get("organizer"):
        # No url: official_url is often a tourism listing or a blog post, not the organiser's site.
        data["organizer"] = {"@type": "Organization", "name": ev["organizer"]}
    return jsonld_markup(data)


def jsonld_markup(data: dict) -> Markup:
    # "</" would close the script element early, whatever the JSON around it says.
    return Markup(json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/"))


def build_website_jsonld() -> Markup:
    """Where Google takes the site name shown in its results from. Home page only."""
    return jsonld_markup({"@context": "https://schema.org", "@type": "WebSite",
                          "name": SITE_NAME, "url": f"{SITE_URL}/"})


def build_breadcrumbs(r: dict) -> Markup:
    """The edition page's trail. The last entry is the page itself, so it carries no link."""
    items = [("Home", f"{SITE_URL}/"),
             (r["ev"]["name_en"], f"{SITE_URL}/events/{r['slug']}/"),
             (r["label"], None)]
    return jsonld_markup({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": n, "name": name, **({"item": url} if url else {})}
                            for n, (name, url) in enumerate(items, 1)],
    })


# Descriptions: what a search snippet or a shared link says before the page is opened

SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def event_description(ev: dict) -> str:
    """The summary's first sentence, since a snippet shows about 155 characters."""
    if ev.get("summary_en"):
        return SENTENCE_END_RE.split(" ".join(prose_text(ev["summary_en"]).split()), 1)[0]
    return f"Dates, venue and admission for {ev['name_en']} in {ev['prefecture']}."


def edition_description(r: dict) -> str:
    """Status first, so a cancelled edition's snippet cannot read like a normal listing."""
    status = {"cancelled": "Cancelled. ", "tentative": "Dates not confirmed. "}.get(r["ed"]["status"], "")
    return f"{status}{r['parts_phrase']} for {r['full_name']}: {r['when']}, {r['venue']}, {r['prefecture']}."


def list_phrase(parts: list[str]) -> str:
    """["Route", "Entry list", "Videos"] -> "Route, entry list and videos"."""
    return " and ".join(filter(None, [", ".join(parts[:-1]), *parts[-1:]])).lower().capitalize()


def event_notes_phrase(ev: dict) -> str | None:
    """The event page's notes, named for the edition page's link to them. None if it has none."""
    kinds = [kind for kind, present in (
        ("access", ev.get("nearest_station") or ev.get("access_notes_en")),
        ("spectator", ev.get("spectator_notes_en")),
        ("photography", ev.get("photography_notes_en"))) if present]
    return f"{list_phrase(kinds)} notes" if kinds else None


# Build

def make_rows(events: dict, editions: list, makes: dict | None = None) -> list[dict]:
    rows = []
    for item in editions:
        ed, ed_id = item["data"], item["id"]
        ev = events[ed["slug"]]
        slug, year = ed["slug"], ed["year"]
        edition = fmt_edition(item["edition"]) if item["edition"] else None
        display_name = f"{ev['name_en']} {edition}" if edition else ev["name_en"]
        cars = with_countries(ed.get("cars"), makes or {})
        columns = car_columns(ed.get("cars"))
        # Cars with entry numbers entered something and can withdraw; cars without are
        # exhibits a show has announced, which it can change without anyone pulling out.
        cars_label, cars_caveat = (("Entry list", "cars may withdraw or change")
                                   if any(c["key"] == "entry_no" for c in columns)
                                   else ("Cars on display", "the line-up may change"))
        present = {"route": ed.get("route") or ed.get("route_en"), "cars": ed.get("cars"),
                   "videos": ed.get("videos")}
        # A video mostly exists only once an edition has run, so its presence marks the page
        # as a look back, with no clock involved: what it was like first, the timetable last.
        # An organiser's pre-event guide is the exception, and leading with it suits it too.
        order = ("videos", "cars", "route") if present["videos"] else ("route", "cars", "videos")
        sections = [name for name in order if present[name]]
        page_parts = [{"route": "Route", "cars": cars_label, "videos": "Videos"}[name] for name in sections]
        has_page = bool(page_parts)
        # Counted from what each section shows, so a jump cannot promise more than it lands on.
        n_cars, n_videos = len(present["cars"] or []), len(present["videos"] or [])
        n_days = len(ed.get("route") or [])
        jump_text = {
            "videos": f"Videos ({n_videos})",
            "cars": f"{cars_label} ({n_cars} {'car' if cars_label == 'Entry list' else 'model'}"
                    f"{'' if n_cars == 1 else 's'})",
            "route": f"Route ({n_days} day{'' if n_days == 1 else 's'})" if n_days else "Route",
        }
        jumps = [{"id": name, "text": jump_text[name]} for name in sections] if len(sections) > 1 else []
        # "Route, entry list and videos": one wording for the title, the link and the snippet.
        parts_phrase = list_phrase(page_parts)
        path = f"events/{slug}/{ed_id}/" if has_page else f"events/{slug}/"
        is_timed = "start_time" in ed
        r = {
            "ev": ev, "ed": ed, "slug": slug, "year": year, "id": ed_id,
            "edition": edition, "display_name": display_name,
            "full_name": f"{display_name} {year}",
            "label": f"{edition} {year}" if edition else str(year),
            "has_page": has_page, "sections": sections, "jumps": jumps, "page_parts": page_parts, "parts_phrase": parts_phrase, "event_notes": event_notes_phrase(ev), "path": path, "abs_url": f"{SITE_URL}/{path}",
            "uid": f"{slug}-{ed_id}@{UID_DOMAIN}",
            # A saved copy never updates, so only a date that should not move is offered as one.
            "ics_path": f"events/{slug}/{ed_id}.ics" if ed["status"] == "confirmed" else None,
            "is_timed": is_timed,
            "venue": ed.get("venue_en") or ev["venue_en"],
            "prefecture": ed.get("prefecture") or ev["prefecture"],
            "pin": venue_pin(ev, ed),
            "dot": None,
            "has_route": bool(present["route"]),
            "cutoff_year": ed.get("cutoff_year") or ev.get("cutoff_year"),
            "when": fmt_range(ed["start"], ed["end"]),
            "when_day": fmt_span(ed["start"], ed["end"]),
            # A list published before the event can still change, but once we have
            # re-checked the source after the event ended, what we show is the last word.
            "chart": route_chart(ed.get("route")),
            "decades": decade_chart(ed.get("cars")),
            "makes": makes_chart(ed.get("cars")),
            "cars": cars,
            # The flags this page's list uses, each to be drawn once ahead of the table.
            "flags": [{"code": code, "name": COUNTRIES[code][0], "art": COUNTRIES[code][1]}
                      for code in sorted({car["country"] for car in cars or [] if "country" in car})],
            "videos": [{"label": v["label_en"], "title": f"{display_name} {year}, {v['label_en']}",
                        "embed": VIDEO_EMBED_URL + v["youtube_id"], "watch": VIDEO_WATCH_URL + v["youtube_id"]}
                       for v in ed.get("videos") or []],
            "car_columns": columns, "cars_label": cars_label, "cars_caveat": cars_caveat,
            "list_provisional": ("list_as_of" in ed and ed["list_as_of"] < ed["end"]
                                 and ed["last_verified"] <= ed["end"]),
        }
        if is_timed:
            # The times are each day's hours. JSON-LD spans first opening to last closing;
            # calendars get the first day's hours repeated, never one block through the nights.
            r["start_dt"] = _local_dt(ed["start"], ed["start_time"])
            r["end_dt"] = _local_dt(ed["end"], ed["end_time"])
            r["day_end_dt"] = _local_dt(ed["start"], ed["end_time"])
            days = (ed["end"] - ed["start"]).days + 1
            r["rrule"] = f"FREQ=DAILY;COUNT={days}" if days > 1 else None
            r["when_full"] = (f"{fmt_span(ed['start'], ed['end'], year=True)}, "
                              f"{ed['start_time']} to {ed['end_time']} Japan time"
                              + (" each day" if days > 1 else ""))
        else:
            r["when_full"] = fmt_span(ed["start"], ed["end"], year=True)
        if r["pin"]:
            r["dot"] = map_point(r["pin"]["lat"], r["pin"]["lon"])
        r["google_url"] = google_calendar_url(r) if r["ics_path"] else None
        r["jsonld"] = build_jsonld(r)
        rows.append(r)
    rows.sort(key=lambda r: (r["ed"]["start"], r["slug"], r["id"]))
    # Each edition points back to the latest earlier one with videos. Earlier by date,
    # not by today, because the build never reads the clock.
    latest_with_videos: dict[str, dict] = {}
    for r in rows:
        r["previous_videos"] = latest_with_videos.get(r["slug"])
        if r["videos"]:
            latest_with_videos[r["slug"]] = r
    # And forward to the next edition, so a page found by search leads on to the dates to keep.
    for r in rows:
        r["next"] = next((n for n in rows if n["slug"] == r["slug"] and n["ed"]["start"] > r["ed"]["start"]), None)
    return rows


def month_groups(rows: list[dict]) -> list[dict]:
    """The home list as a calendar: each month in date order, each date in it once.

    Editions share a date only when their first and last days both match, because the
    browser moves a date to Past by its last day, and a shared one has to move as one.
    """
    months: list[dict] = []
    for r in rows:
        start, end = r["ed"]["start"], r["ed"]["end"]
        key = f"{start:%Y-%m}"
        if not months or months[-1]["key"] != key:
            months.append({"key": key, "label": f"{start:%B %Y}", "days": []})
        days = months[-1]["days"]
        day = next((d for d in days if (d["start"], d["end"]) == (start, end)), None)
        if day is None:
            day = {"start": start, "end": end, "when": r["when_day"], "leaf": fmt_leaf(start, end), "rows": []}
            days.append(day)
        day["rows"].append(r)
    return months


# Files written for agents rather than readers

def build_api(rows: list[dict]) -> str:
    """The same editions the pages and the calendar carry, as JSON.

    Every field is read straight off the validated data, so the feed cannot state
    something the page beside it contradicts. A field the data does not hold is left
    out rather than guessed at, which keeps "free" (0) distinct from "not recorded".
    """
    records = []
    for r in rows:
        ev, ed, pin = r["ev"], r["ed"], r["pin"]
        rec = {
            "id": f"{r['slug']}-{r['id']}",
            "name": r["full_name"],
            "event": ev["name_en"],
            "name_ja": ev.get("name_ja"),
            "edition": r["edition"],
            "year": r["year"],
            "status": ed["status"],
            "start": ed["start"],
            "end": ed["end"],
            "start_time": ed.get("start_time"),
            "end_time": ed.get("end_time"),
            "all_day": not r["is_timed"],
            "venue": r["venue"],
            "prefecture": r["prefecture"],
            "street_address": ed.get("street_address") or ev.get("street_address"),
            "lat": pin["lat"] if pin else None,
            "lon": pin["lon"] if pin else None,
            "spectator_fee_jpy": ev["spectator_fee_jpy"],
            "url": r["abs_url"],
            "official_url": ev["official_url"],
            "source_url": ed["source_url"],
            "last_verified": ed["last_verified"],
            "cars_as_of": ed.get("list_as_of"),
            "cars": r["cars"],
            "route": ed.get("route"),
            "route_en": prose_text(ed["route_en"]) if "route_en" in ed else None,
            "videos": ed.get("videos"),
        }
        records.append({k: v for k, v in rec.items() if v is not None})
    feed = {"name": SITE_NAME, "url": f"{SITE_URL}/", "description": SITE_LEDE,
            "timezone": "Asia/Tokyo", "events": records}
    # default=str renders the dates YAML parsed into date objects as plain ISO strings.
    return json.dumps(feed, indent=2, ensure_ascii=False, default=str) + "\n"


def build_llms_txt(rows: list[dict], events: dict) -> str:
    lines = [f"# {SITE_NAME}", "", f"> {SITE_LEDE}", "",
             "Each record is transcribed from the organiser's own page and carries the date "
             "it was last checked against it. All dates and times are Japan time.", "",
             "## Events", ""]
    for slug, ev in sorted(events.items()):
        ev_rows = [r for r in rows if r["slug"] == slug]
        # r["label"] carries the year, which r["when"] already ends with.
        dates = []
        for r in ev_rows:
            when = f"{r['edition']}: {r['when']}" if r["edition"] else r["when"]
            status = r["ed"]["status"]
            dates.append(when if status == "confirmed" else f"{when} ({status})")
        lines.append(f"- [{ev['name_en']}]({SITE_URL}/events/{slug}/): "
                     f"{ev['prefecture']}. {'; '.join(dates)}.")
        for r in ev_rows:
            if r["has_page"]:
                lines.append(f"  - [{r['full_name']}]({r['abs_url']}): {r['parts_phrase'].lower()}.")
    lines += ["", "## Site", "",
              f"- [About]({SITE_URL}/about/): where the facts come from, how they are checked, "
              "and where to report an error.",
              f"- [Japanese timetable]({SITE_URL}/ja/): every edition's dates, hours, prefecture "
              "and admission, in Japanese.",
              "", "## Data", "",
              f"- [Events as JSON]({SITE_URL}/api/events.json): every edition above, with venue, "
              "dates, admission, coordinates, entry list and route.",
              f"- [Calendar feed]({SITE_URL}/{FEED_FILE}): the same editions as iCalendar.",
              f"- [Sitemap]({SITE_URL}/sitemap.xml): every page on the site.", ""]
    return "\n".join(lines)


def build_ard_catalog() -> str:
    """Agentic Resource Discovery manifest: what this site publishes and what it answers.

    Served at both ARD paths. /.well-known/ard.json is the name the current spec makes
    normative and the only one a conformant consumer must fetch; ai-catalog.json is its
    predecessor, which is what agent-readiness scanners and older consumers still read.
    The document validates against both schemas unchanged, so it is written twice, not forked.
    """
    host = SITE_URL.split("://", 1)[1]
    catalog = {
        "specVersion": "1.0",
        "host": {"displayName": SITE_NAME, "documentationUrl": f"{SITE_URL}/"},
        "entries": [
            {"identifier": f"urn:air:{host}:api:events",
             "displayName": f"{SITE_NAME} events feed",
             "type": "application/json",
             "url": f"{SITE_URL}/api/events.json",
             "description": "Every classic car event edition on the site: dates, venue, prefecture, "
                            "coordinates, admission, entry list and route, each with the date it was "
                            "last checked against its source.",
             "tags": ["classic-cars", "japan", "events"],
             "representativeQueries": [
                 "classic car events in Japan in 2026",
                 "when is the next historic car rally in Japan",
                 "which prewar cars are entered at a Japanese classic car meeting",
                 "admission price for a classic car show in Japan",
             ]},
            {"identifier": f"urn:air:{host}:feed:calendar",
             "displayName": f"{SITE_NAME} calendar feed",
             "type": "text/calendar",
             "url": f"{SITE_URL}/{FEED_FILE}",
             "description": "The same editions as an iCalendar subscription, with Japan-time starts "
                            "converted by the calendar client.",
             "tags": ["classic-cars", "japan", "calendar"],
             "representativeQueries": [
                 "subscribe to a calendar of Japanese classic car events",
                 "iCalendar feed for classic car events in Japan",
             ]},
            {"identifier": f"urn:air:{host}:docs:llms",
             "displayName": f"{SITE_NAME} site guide",
             "type": "text/markdown",
             "url": f"{SITE_URL}/llms.txt",
             "description": "Plain-text index of every event and edition page, and of the machine "
                            "formats the same data is published in.",
             "tags": ["classic-cars", "japan", "index"],
             "representativeQueries": [
                 "English guide to classic car events in Japan",
                 "where to watch classic cars in Japan",
             ]},
        ],
    }
    return json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"


def build_api_catalog() -> str:
    """RFC 9727 API catalog. The site documents the data, so service-doc points at it;
    there is no OpenAPI description to offer as service-desc and none is claimed."""
    doc = [{"href": f"{SITE_URL}/", "type": "text/html", "title": SITE_NAME}]
    linkset = [{"anchor": f"{SITE_URL}/api/events.json", "service-doc": doc},
               {"anchor": f"{SITE_URL}/{FEED_FILE}", "service-doc": doc}]
    return json.dumps({"linkset": linkset}, indent=2, ensure_ascii=False) + "\n"


def reset_out_dir(out_dir: Path) -> None:
    """Empty out_dir, but only if it is empty or holds a previous build."""
    if out_dir.exists():
        # Any .ics, so that renaming the feed does not make the last build unrecognisable.
        previous_build = (out_dir / "index.html").is_file() and any(out_dir.glob("*.ics"))
        if any(out_dir.iterdir()) and not previous_build:
            raise BuildError([f"{out_dir}: not empty and not a previous build, so it was left untouched. "
                              f"Choose another --out folder"])
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)


def build(data_dir: Path, out_dir: Path,
          templates_dir: Path = ROOT / "templates", static_dir: Path = ROOT / "static") -> None:
    events, editions = load_and_validate(data_dir)
    rows = make_rows(events, editions, load_makes(data_dir))

    env = Environment(loader=FileSystemLoader(templates_dir),
                      autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.globals["countries"] = COUNTRIES
    env.filters["fee"] = fmt_fee
    env.filters["domain"] = fmt_domain
    env.filters["prose"] = prose_html
    env.filters["weekday"] = fmt_weekday
    env.filters["span_ja"] = fmt_span_ja
    env.filters["month_ja"] = fmt_month_ja
    env.filters["fee_ja"] = fmt_fee_ja
    env.filters["pref_ja"] = PREFECTURES_JA.__getitem__
    host = SITE_URL.split("://", 1)[1]
    common = {"site_name": SITE_NAME, "site_url": SITE_URL, "site_lede": SITE_LEDE,
              "ard_path": ARD_PATH, "ard_predecessor_path": ARD_PREDECESSOR_PATH,
              "issues_url": ISSUES_URL, "youtube_channel_url": YOUTUBE_CHANNEL_URL, "feed_file": FEED_FILE, "ics_url": f"{SITE_URL}/{FEED_FILE}", "webcal_url": f"webcal://{host}/{FEED_FILE}"}

    reset_out_dir(out_dir)
    # Every other static file is served from static/, but browsers ask for /favicon.ico
    # by name with no link tag, so that one is copied to the site root instead.
    shutil.copytree(static_dir, out_dir / "static", ignore=shutil.ignore_patterns("favicon.ico"))
    shutil.copy2(static_dir / "favicon.ico", out_dir / "favicon.ico")

    def write(rel: str, text: str) -> None:
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")

    all_verified = [e["last_verified"] for e in events.values()] + [x["data"]["last_verified"] for x in editions]
    latest = max(all_verified) if all_verified else None
    write("index.html", env.get_template("home.html").render(
        **common, root="", canonical=f"{SITE_URL}/", title=f"Classic car events in Japan | {SITE_NAME}", hreflang=True,
        description=SITE_LEDE, months=month_groups(rows), years=year_chart(rows), latest=latest, jsonld=[build_website_jsonld()],
        japan=japan_path() if any(r["dot"] for r in rows) else None,
        map_box=f"0 0 {MAP_WIDTH:g} {MAP_HEIGHT:g}", map_ratio=MAP_HEIGHT / MAP_WIDTH))

    write("ja/index.html", env.get_template("ja.html").render(
        **common, root="../", canonical=f"{SITE_URL}/ja/", lang="ja", hreflang=True,
        title=f"日本のクラシックカーイベント | {SITE_NAME}", description=JA_LEDE,
        months=month_groups(rows), latest=latest, jsonld=[]))

    sitemap = [(f"{SITE_URL}/", latest), (f"{SITE_URL}/ja/", latest)]
    for slug, ev in sorted(events.items()):
        ev_rows = [r for r in rows if r["slug"] == slug]
        verified = max([ev["last_verified"]] + [r["ed"]["last_verified"] for r in ev_rows])
        write(f"events/{slug}/index.html", env.get_template("event.html").render(
            **common, root="../../", canonical=f"{SITE_URL}/events/{slug}/",
            title=f"{ev['name_en']}: Visitor Guide | {SITE_NAME}", description=event_description(ev),
            ev=ev, rows=ev_rows, verified=verified, pin=venue_pin(ev),
            jsonld=[r["jsonld"] for r in ev_rows if not r["has_page"]]))
        sitemap.append((f"{SITE_URL}/events/{slug}/", verified))
        for r in ev_rows:
            if not r["has_page"]:
                continue
            ed = r["ed"]
            write(f"{r['path']}index.html", env.get_template("edition.html").render(
                **common, root="../../../", canonical=r["abs_url"],
                title=f"{r['full_name']}: {r['parts_phrase']} | {SITE_NAME}",
                description=edition_description(r),
                ev=ev, r=r, ed=ed, jsonld=[r["jsonld"], build_breadcrumbs(r)]))
            sitemap.append((r["abs_url"], ed["last_verified"]))

    write("about/index.html", env.get_template("about.html").render(
        **common, root="../", canonical=f"{SITE_URL}/about/", title=f"About | {SITE_NAME}",
        description=ABOUT_DESCRIPTION, jsonld=[]))
    # The page describes the site, not the data, so no verified date stands behind it.
    sitemap.append((f"{SITE_URL}/about/", None))

    # Pages serves this for a missing path at any depth, so links must be root-absolute.
    write("404.html", env.get_template("404.html").render(
        **common, root="/", canonical=None, title=f"Page not found | {SITE_NAME}",
        events=sorted(events.values(), key=lambda e: e["name_en"].casefold()), jsonld=[]))

    write(FEED_FILE, build_ics(rows))
    # No calendar name, so the app adds the event to one the visitor already has.
    for r in rows:
        if r["ics_path"]:
            write(r["ics_path"], ics_calendar([], [r]))
    write("robots.txt", f"User-agent: *\nContent-Signal: {CONTENT_SIGNAL}\nAllow: /\n\n"
                        f"Sitemap: {SITE_URL}/sitemap.xml\n"
                        f"Agentmap: {SITE_URL}/{ARD_PATH}\n")
    write("api/events.json", build_api(rows))
    write("llms.txt", build_llms_txt(rows, events))
    ard = build_ard_catalog()
    write(ARD_PATH, ard)
    write(ARD_PREDECESSOR_PATH, ard)
    write(".well-known/api-catalog", build_api_catalog())
    write(f"{INDEXNOW_KEY}.txt", INDEXNOW_KEY)

    urls = "".join(f"  <url><loc>{xml_escape(u)}</loc>"
                   + (f"<lastmod>{d.isoformat()}</lastmod>" if d else "") + "</url>\n"
                   for u, d in sorted(sitemap, key=lambda entry: entry[0]))
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "</urlset>\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the site from data/ into site/.")
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--out", type=Path, default=ROOT / "site")
    args = ap.parse_args()
    try:
        build(args.data, args.out)
    except BuildError as e:
        print(f"Build failed: {len(e.errors)} problem(s)", file=sys.stderr)
        for err in e.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"Built {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
