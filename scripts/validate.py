"""Loading data/ and checking it. Any problem fails the build with a list of errors."""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from pathlib import Path

import yaml

from formatting import prose_text
from maps import COURSE_VIEWBOX, course_steps
from page_meta import event_description
from photos import PHOTOS_DIR, PHOTO_LICENSES, PHOTO_MIN_WIDTH, _open_photo, photo_metadata
from settings import COUNTRIES, PREFECTURES_JA, SHARE_SIZE

STATUSES = {"confirmed", "tentative", "cancelled"}
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EDITION_FILE_RE = re.compile(r"^(?P<year>\d{4})(?:-(?P<edition>[a-z0-9]+(?:-[a-z0-9]+)*))?$")
# Japan's bounding box, Yonaguni to Minamitorishima. A swapped or mistyped pair lands
# outside it, which is the only coordinate mistake a build can catch on its own.
JAPAN_LAT = (24.0, 46.0)
JAPAN_LON = (122.0, 154.0)

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

PHOTO_REQUIRED = {"alt_en": "str", "year": "int"}
# Someone else's photo: all three, or none for the site's own.
PHOTO_CREDIT = {"credit": "str", "license": "license", "source_url": "url"}

URL_RE = re.compile(r"^https?://\S+$")

# Long prose buries the facts inside it, and a skim-reader never finds them.
PROSE_MAX_WORDS = 75
# An event page's meta description, about what a result snippet shows. Edition descriptions
# are built only from facts such as the venue name, so they are left uncapped (spec 8).
DESCRIPTION_MAX_CHARS = 160
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
# American spellings a visitor would read, with the British form the message offers.
# Deliberately narrow: words with a valid British use (meter, license, curb, tire) stay off.
AMERICAN_SPELLINGS = {
    "color": "colour", "colors": "colours", "colored": "coloured", "colorful": "colourful",
    "program": "programme", "programs": "programmes",
    "center": "centre", "centers": "centres", "centered": "centred",
    "theater": "theatre", "catalog": "catalogue", "gray": "grey",
    "organize": "organise", "organized": "organised", "organizes": "organises",
    "organizing": "organising", "organizer": "organiser", "organizers": "organisers",
    "organization": "organisation", "organizations": "organisations",
    "traveler": "traveller", "travelers": "travellers", "traveling": "travelling",
    "favorite": "favourite", "neighborhood": "neighbourhood",
    "kilometer": "kilometre", "kilometers": "kilometres", "tires": "tyres",
}
AMERICAN_RE = re.compile(r"\b(" + "|".join(AMERICAN_SPELLINGS) + r")\b", re.IGNORECASE)
# Proper names spelt the American way, which the spelling check skips.
AMERICAN_SPELLING_NAMES = ("Hiruzen Kogen Center",)
# Visitors read "event" for one running of an event; enthusiasts don't say edition (owner, 2026-11-23).
EDITION_RE = re.compile(r"\beditions?\b", re.IGNORECASE)

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
    # The venue as its own Japanese sources print it, for the Japanese pages (spec 6.6).
    "venue_ja": "str",
    "organizer": "str", "summary_en": "prose", "street_address": "str",
    "nearest_station": "prose", "access_notes_en": "prose", "typical_eras": "strlist",
    "typical_scale": "str", "spectator_notes_en": "prose", "photography_notes_en": "prose",
    "lat": "lat", "lon": "lon",
    # The newest build year the organiser accepts, only where a source states one exactly.
    "cutoff_year": "int",
    "photo": "photo",
}
EDITION_REQUIRED = {
    "slug": "str", "year": "int", "status": "status", "start": "date", "end": "date",
    "source_url": "url", "last_verified": "date", "sequence": "count",
}
EDITION_OPTIONAL = {
    "start_time": "time", "end_time": "time", "venue_en": "str", "venue_ja": "str", "street_address": "str",
    # For an event that moves: the prefecture this edition ran in, when it is not the event's.
    "prefecture": "str",
    "route_en": "prose", "route": "route", "list_as_of": "date", "cars": "cars",
    "lat": "lat", "lon": "lon", "videos": "videos",
    # For an event whose limit moves each year: this edition's, when it is not the event's.
    "cutoff_year": "int",
    # Written by tools/course.py from the organiser's course map, never by hand.
    "course": "course",
}
COURSE_REQUIRED = {"line": "course_line"}
# Only while the organiser serves the PDF; an archive copy gets a credit without a link.
COURSE_OPTIONAL = {"map_url": "url", "cones": "course_points"}

ROUTE_DAY_REQUIRED = {"date": "date", "checkpoints": "checkpoints"}
CHECKPOINT_REQUIRED = {"start_time": "time", "place_en": "str", "prefecture": "str"}
CHECKPOINT_OPTIONAL = {"end_time": "time", "place_ja": "str", "lat": "lat", "lon": "lon"}
# The ID alone, not a URL, so the embed domain is chosen once, in VIDEO_EMBED_URL.
VIDEO_REQUIRED = {"youtube_id": "youtube_id", "label_en": "str"}
VIDEO_OPTIONAL = {"label_ja": "str"}
# Fields the templates render into a single block. The cap has to apply to what a
# reader actually sees there, not to each field measured on its own.
COMBINED_PROSE = (("nearest_station", "access_notes_en"),)
# A source that names the models a show will have on the floor gives neither an entry
# number nor a year, and a model's production span is not the age of the car on the stand.
CAR_REQUIRED = {"make": "str", "model": "str"}
CAR_OPTIONAL = {"entry_no": "str", "year": "int", "colour": "str", "country": "country"}


class BuildError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


class ValidationError(BuildError):
    """Problems in data/."""


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v) -> bool:
    return _is_int(v) or isinstance(v, float)


def _is_pairs(v) -> bool:
    return isinstance(v, list) and all(
        isinstance(p, list) and len(p) == 2 and all(_is_number(n) for n in p) for p in v)


def _in_course_frame(point) -> bool:
    x0, y0, width, height = COURSE_VIEWBOX
    return x0 <= point[0] <= x0 + width and y0 <= point[1] <= y0 + height


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


def _check_house_style(v: str, where: str, errors: list[str]) -> None:
    """Refuse em dashes and American spellings in English text."""
    if "\u2014" in v:
        errors.append(f"{where}: contains an em dash. Use a comma, colon or semicolon, "
                      f"or rewrite the sentence")
    for name in AMERICAN_SPELLING_NAMES:
        v = v.replace(name, "")
    for match in AMERICAN_RE.finditer(v):
        word = match.group(0)
        errors.append(f"{where}: {word!r} is American spelling; write "
                      f"{AMERICAN_SPELLINGS[word.lower()]!r}. If it is part of a proper name, "
                      f"add the name to AMERICAN_SPELLING_NAMES in scripts/validate.py")


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
    elif kind == "license":
        if v not in PHOTO_LICENSES:
            errors.append(f"{where}: must be one of {sorted(PHOTO_LICENSES)}, the licences that allow "
                          f"cropping and ask only for a credit, got {v!r}")
    elif kind == "photo":
        if _check_fields(v, PHOTO_REQUIRED, PHOTO_CREDIT, where, errors):
            given = [k for k in PHOTO_CREDIT if k in v]
            if 0 < len(given) < len(PHOTO_CREDIT):
                errors.append(f"{where}: give credit, license and source_url together for someone "
                              f"else's photo, or none of them for the site's own")
    elif kind in ("cars", "route", "checkpoints", "videos"):
        if not isinstance(v, list) or not v:
            errors.append(f"{where}: must be a non-empty list")
    elif kind == "course":
        _check_fields(v, COURSE_REQUIRED, COURSE_OPTIONAL, where, errors)
    elif kind == "course_line":
        if not _is_pairs(v) or len(v) < 4 or (len(v) - 1) % 3:
            errors.append(f"{where}: must be [x, y] pairs, a start point then three per curve, "
                          f"as tools/course.py writes them")
        # Points on the drawn curve, not control points, which can sit well outside it.
        elif not all(_in_course_frame(point) for step in course_steps(v) for point in step):
            errors.append(f"{where}: runs outside the course frame COURSE_VIEWBOX, so this map "
                          f"is not on SHCC's template and needs its own frame first")
    elif kind == "course_points":
        if not _is_pairs(v) or not v:
            errors.append(f"{where}: must be a non-empty list of [x, y] pairs, as tools/course.py writes them")
        elif not all(_in_course_frame(point) for point in v):
            errors.append(f"{where}: a point lies outside the course frame COURSE_VIEWBOX")


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
    # Every English text field, prose or not: a label or place name is read as much as a summary.
    for key, kind in {**required, **optional}.items():
        if key in obj and kind in ("str", "prose", "strlist") and not key.endswith("_ja"):
            values = obj[key] if isinstance(obj[key], list) else [obj[key]]
            for value in values:
                if isinstance(value, str):
                    _check_house_style(value, f"{where}: {key}", errors)
                    # A car's make and model are the maker's names ("Limited Edition"), not ours.
                    if key not in ("make", "model") and EDITION_RE.search(value):
                        errors.append(f"{where}: {key}: write 'event', not 'edition'; an ordinal takes "
                                      f"the event's own noun ('the 20th rally')")
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


def _check_description(ev: dict, rel: str, errors: list[str]) -> None:
    if not ev.get("summary_en"):
        return
    description = event_description(ev)
    if len(description) > DESCRIPTION_MAX_CHARS:
        errors.append(
            f"{rel}: the first sentence of summary_en is the page's search snippet and runs to "
            f"{len(description)} characters (limit {DESCRIPTION_MAX_CHARS}). Shorten that sentence, "
            f"or split it in two"
        )


def _check_coords(obj: dict, rel: str, errors: list[str]) -> None:
    """Half a pair points nowhere, so the build refuses it rather than dropping the link."""
    if ("lat" in obj) != ("lon" in obj):
        errors.append(f"{rel}: give lat and lon together, or neither")


def _check_route(route, start, end, rel: str, errors: list[str]) -> None:
    """Days run in order inside the edition's dates, checkpoints in order inside a day."""
    if not isinstance(route, list):
        return
    # A route map with a stop missing would draw a straight line past it without a word.
    points = [p for day in route if isinstance(day, dict) and isinstance(day.get("checkpoints"), list)
              for p in day["checkpoints"] if isinstance(p, dict)]
    located = sum("lat" in p for p in points)
    if 0 < located < len(points):
        errors.append(f"{rel}: route: give coordinates on all of its checkpoints or none "
                      f"({located} of {len(points)} have them)")
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
            _check_coords(point, spot, errors)
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


def _load_unique_yaml(path: Path):
    """A data table where a key listed twice is an error, not YAML's silent last-one-wins."""
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.constructor.ConstructorError as e:
        raise ValidationError([f"{path.name}: {e.problem}"])
    except yaml.YAMLError as e:
        raise ValidationError([f"{path.name}: YAML syntax error: {e}"])


def load_makes(data_dir: Path) -> dict:
    """data/makes.yml: each make's home country, or None where no one country fits.

    It is for a car whose list prints no country of its own; the file says more. A site
    without the file builds without flags from makes.
    """
    path = data_dir / "makes.yml"
    if not path.exists():
        return {}
    makes = _load_unique_yaml(path)
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
        _check_description(ev, rel, errors)
        _check_coords(ev, rel, errors)
        _check_prefecture(ev, rel, errors)
        _check_photo(ev, data_dir, rel, errors)
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
                _check_fields(video, VIDEO_REQUIRED, VIDEO_OPTIONAL, f"{rel}: videos item {i}", errors)
        editions.append({"data": ed, "id": path.stem, "edition": name["edition"]})

    for path in sorted((data_dir / PHOTOS_DIR).glob("*")):
        rel = path.relative_to(data_dir).as_posix()
        if path.name.startswith("."):
            continue
        if path.suffix != ".jpg":
            errors.append(f"{rel}: photos must be JPEG files named <slug>.jpg")
        elif not (events_dir / f"{path.stem}.yml").is_file():
            errors.append(f"{rel}: no matching event file events/{path.stem}.yml")
        elif path.stem in events and "photo" not in events[path.stem]:
            # Otherwise a photo could go live with no alt text and no credit.
            errors.append(f"{rel} has no photo field in events/{path.stem}.yml")

    if errors:
        raise ValidationError(errors)
    return events, editions


def _check_photo(ev: dict, data_dir: Path, rel: str, errors: list[str]) -> None:
    if not isinstance(ev.get("photo"), dict):
        return
    src = data_dir / PHOTOS_DIR / f"{ev['slug']}.jpg"
    src_rel = src.relative_to(data_dir).as_posix()
    if not src.is_file():
        errors.append(f"{rel}: photo is given but {src_rel} does not exist")
        return
    try:
        kinds = photo_metadata(src)
        w, h = _open_photo(src).size
    except OSError as e:
        errors.append(f"{src_rel}: not a readable JPEG ({e})")
        return
    if kinds:
        # By the time the build sees it, the file is in the public repository.
        errors.append(f"{src_rel} still carries {', '.join(kinds)}, which can hold the GPS position, "
                      f"the camera's serial number and the photographer's name. The file is already "
                      f"public: run the original through tools/photo.py and upload the result")
        return
    # The hero is cropped to 2:1 and the share image to 1200x630, so both have to fit.
    need_h = max(PHOTO_MIN_WIDTH // 2, SHARE_SIZE[1])
    if w < PHOTO_MIN_WIDTH or h < need_h:
        errors.append(f"{src_rel}: {w}x{h} is too small. It needs at least {PHOTO_MIN_WIDTH} wide and "
                      f"{need_h} high, so the page stays sharp on a high-density screen")


def make_slug(name: str) -> str:
    """A make page's URL word: Citroën gives citroen, TOM'S gives toms."""
    name = unicodedata.normalize("NFKD", name.replace("'", "").replace("\u2019", ""))
    name = "".join(ch for ch in name if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def load_make_groups(data_dir: Path, makes: dict) -> dict[str, list[str]]:
    """data/make_groups.yml (spec 4.11): group name to members in file order.

    Every make in makes.yml that no group names is a group of one, so each make has
    exactly one group and every group a slug.
    """
    path = data_dir / "make_groups.yml"
    listed = (_load_unique_yaml(path) if path.exists() else None) or {}
    if not isinstance(listed, dict):
        raise ValidationError(["make_groups.yml: must be one group per line, e.g. Nissan: [Nissan, Datsun]"])
    errors: list[str] = []
    owner: dict[str, str] = {}
    for name, members in listed.items():
        if not (isinstance(members, list) and members and all(isinstance(m, str) for m in members)):
            errors.append(f"make_groups.yml: {name}: must be a list of makes, e.g. {name}: [{name}, Other]")
            continue
        if members[0] != name:
            errors.append(f"make_groups.yml: {name}: the list must start with {name}, the make the group is named after")
        for member in members:
            if member not in makes:
                errors.append(f"make_groups.yml: {name}: {member} is not a make in makes.yml")
            elif member in owner:
                errors.append(f"make_groups.yml: {member} is in two groups, {owner[member]} and {name}")
            else:
                owner[member] = name
    groups = {name: members for name, members in listed.items() if isinstance(members, list)}
    groups.update({make: [make] for make in makes if make not in owner})
    by_slug: dict[str, list[str]] = {}
    for name in groups:
        by_slug.setdefault(make_slug(name), []).append(name)
    errors += [f"make_groups.yml: {' and '.join(names)} would share the page cars/{slug}/; "
               f"group them, or rename one in makes.yml"
               for slug, names in by_slug.items() if len(names) > 1]
    if errors:
        raise ValidationError(errors)
    return groups
