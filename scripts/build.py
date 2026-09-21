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
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

SITE_NAME = "Classic Motoring Japan"
SITE_URL = "https://classicmotoringjapan.com"
UID_DOMAIN = "classicmotoringjapan.com"
# Thunderbird has never read X-WR-CALNAME (bugzilla 168176, open since 2002): it names a
# subscribed calendar after the last path segment, so the file name has to read as a name.
FEED_FILE = "classic-car-events.ics"

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))
STATUSES = {"confirmed", "tentative", "cancelled"}
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
EDITION_FILE_RE = re.compile(r"^(?P<year>\d{4})(?:-(?P<edition>[a-z0-9]+(?:-[a-z0-9]+)*))?$")
# Japan's bounding box, Yonaguni to Minamitorishima. A swapped or mistyped pair lands
# outside it, which is the only coordinate mistake a build can catch on its own.
JAPAN_LAT = (24.0, 46.0)
JAPAN_LON = (122.0, 154.0)
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
URL_RE = re.compile(r"^https?://\S+$")
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
    "slug": "str", "name_en": "str", "name_ja": "str", "official_url": "url",
    "prefecture": "str", "venue_en": "str", "spectator_fee_jpy": "fee",
    "last_verified": "date",
}
EVENT_OPTIONAL = {
    "organizer": "str", "summary_en": "prose", "street_address": "str",
    "nearest_station": "prose", "access_notes_en": "prose", "typical_eras": "strlist",
    "typical_scale": "str", "spectator_notes_en": "prose", "photography_notes_en": "prose",
    "lat": "lat", "lon": "lon",
}
EDITION_REQUIRED = {
    "slug": "str", "year": "int", "status": "status", "start": "date", "end": "date",
    "source_url": "url", "last_verified": "date", "sequence": "count",
}
EDITION_OPTIONAL = {
    "start_time": "time", "end_time": "time", "venue_en": "str", "street_address": "str",
    "route_en": "prose", "route": "route", "list_as_of": "date", "cars": "cars",
    "lat": "lat", "lon": "lon",
}
ROUTE_DAY_REQUIRED = {"date": "date", "checkpoints": "checkpoints"}
CHECKPOINT_REQUIRED = {"start_time": "time", "place_en": "str", "prefecture": "str"}
CHECKPOINT_OPTIONAL = {"end_time": "time", "place_ja": "str"}
# Fields the templates render into a single block. The cap has to apply to what a
# reader actually sees there, not to each field measured on its own.
COMBINED_PROSE = (("nearest_station", "access_notes_en"),)
CAR_REQUIRED = {"entry_no": "str", "year": "int", "make": "str", "model": "str"}
CAR_OPTIONAL = {"colour": "str"}


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
    elif kind in ("int", "count", "fee"):
        if not _is_int(v) or (kind != "int" and v < 0):
            errors.append(f"{where}: must be a whole number{' of 0 or more' if kind != 'int' else ''}, got {v!r}")
    elif kind == "status":
        if v not in STATUSES:
            errors.append(f"{where}: must be one of {sorted(STATUSES)}, got {v!r}")
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
            if len(v.split()) > PROSE_MAX_WORDS:
                errors.append(
                    f"{where}: {len(v.split())} words is too long to skim (limit {PROSE_MAX_WORDS}). "
                    f"Prose this long hides the facts inside it. Break it into bullet points, a table "
                    f"or a diagram, or move the detail into structured fields such as `route` or `cars`"
                )
            _check_editorial(v, where, errors)
    elif kind in ("cars", "route", "checkpoints"):
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
        total = sum(len(value.split()) for _, value in present)
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
        has_st, has_et = "start_time" in ed, "end_time" in ed
        if has_st != has_et:
            errors.append(f"{rel}: give start_time and end_time together, or neither")
        elif has_st and start == end and isinstance(ed["start_time"], str) and isinstance(ed["end_time"], str):
            if ed["end_time"] <= ed["start_time"]:
                errors.append(f"{rel}: end_time must be after start_time on a one-day event")
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
        _check_route(ed.get("route"), start, end, rel, errors)
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


def decade_chart(cars) -> dict | None:
    """How an entry list falls by decade, counted from the rows the table renders.

    A decade with no cars keeps its row, so a gap in the field stays visible instead of
    closing up and reading as a run.
    """
    if not cars:
        return None
    counts: dict[int, int] = {}
    for car in cars:
        decade = car["year"] // 10 * 10
        counts[decade] = counts.get(decade, 0) + 1
    peak = max(counts.values())
    rows = []
    for decade in range(min(counts), max(counts) + 10, 10):
        n = counts.get(decade, 0)
        rows.append({
            "label": f"{decade}s",
            "count": n,
            "text": f"{n} car{'' if n == 1 else 's'}" if n else "none",
            "width": round(max(n / peak * 100, CHART_MIN_BAR), 2) if n else 0,
        })
    return {"total": len(cars), "rows": rows}


def year_chart(rows: list[dict]) -> list[dict]:
    """Where a year's editions fall across its months: which season the hobby runs in."""
    years = []
    for year in sorted({r["year"] for r in rows}):
        editions = [r["ed"] for r in rows if r["year"] == year]
        days = dt.date(year, 12, 31).timetuple().tm_yday
        first, last = min(e["start"] for e in editions), max(e["start"] for e in editions)
        when = f"{first:%b}" if first.month == last.month else f"{first:%b} to {last:%b}"
        years.append({
            "label": f"{year}: {len(editions)} event{'' if len(editions) == 1 else 's'}, {when}",
            "bars": [{"left": round((e["start"].timetuple().tm_yday - 1) / days * 100, 2),
                      "width": round(max(((e["end"] - e["start"]).days + 1) / days * 100,
                                         CHART_MIN_BAR), 2),
                      "cancelled": e["status"] == "cancelled"}
                     for e in editions],
        })
    return years


def fmt_weekday(d: dt.date) -> str:
    return f"{d:%A} {d.day} {d:%B}"


def fmt_fee(fee: int) -> str:
    return "Free to watch" if fee == 0 else f"\u00a5{fee:,}"


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


def build_ics(rows: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{SITE_NAME}//Events//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{ics_text(SITE_NAME)}",
        # RFC 7986's spelling of the same thing. Neither reaches Thunderbird; see FEED_FILE.
        f"NAME:{ics_text(SITE_NAME)}",
    ]
    for r in rows:
        ed, ev = r["ed"], r["ev"]
        lines += ["BEGIN:VEVENT", f"UID:{r['uid']}",
                  f"DTSTAMP:{ed['last_verified']:%Y%m%d}T000000Z",
                  f"SEQUENCE:{ed['sequence']}"]
        if r["is_timed"]:
            fmt = "%Y%m%dT%H%M%SZ"
            lines += [f"DTSTART:{r['start_dt'].astimezone(dt.timezone.utc):{fmt}}",
                      f"DTEND:{r['end_dt'].astimezone(dt.timezone.utc):{fmt}}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{ed['start']:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{ed['end'] + dt.timedelta(days=1):%Y%m%d}"]
        lines += [
            f"SUMMARY:{ics_text(r['display_name'])}",
            f"LOCATION:{ics_text(r['venue'] + ', ' + ev['prefecture'] + ', Japan')}",
        ]
        if r["pin"]:
            lines.append(f"GEO:{r['pin']['lat']};{r['pin']['lon']}")
        lines += [
            f"URL:{r['abs_url']}",
            "DESCRIPTION:" + ics_text(f"{ev['name_ja']}\n{r['abs_url']}\nLast verified {ed['last_verified']}"),
            f"STATUS:{ed['status'].upper()}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(ics_fold(line) + "\r\n" for line in lines)


# Structured data

def build_jsonld(r: dict) -> Markup:
    ev, ed = r["ev"], r["ed"]
    address = {"@type": "PostalAddress", "addressRegion": ev["prefecture"], "addressCountry": "JP"}
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
        "isAccessibleForFree": ev["spectator_fee_jpy"] == 0,
    }
    if ev.get("summary_en"):
        data["description"] = ev["summary_en"].strip()
    if ev.get("organizer"):
        data["organizer"] = {"@type": "Organization", "name": ev["organizer"], "url": ev["official_url"]}
    text = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return Markup(text)


# Build

def make_rows(events: dict, editions: list) -> list[dict]:
    rows = []
    for item in editions:
        ed, ed_id = item["data"], item["id"]
        ev = events[ed["slug"]]
        slug, year = ed["slug"], ed["year"]
        edition = fmt_edition(item["edition"]) if item["edition"] else None
        display_name = f"{ev['name_en']} {edition}" if edition else ev["name_en"]
        page_parts = [part for part, present in (("Route", ed.get("route") or ed.get("route_en")),
                                                 ("Entry list", ed.get("cars"))) if present]
        has_page = bool(page_parts)
        path = f"events/{slug}/{ed_id}/" if has_page else f"events/{slug}/"
        is_timed = "start_time" in ed
        r = {
            "ev": ev, "ed": ed, "slug": slug, "year": year, "id": ed_id,
            "edition": edition, "display_name": display_name,
            "full_name": f"{display_name} {year}",
            "label": f"{edition} {year}" if edition else str(year),
            "has_page": has_page, "page_parts": page_parts, "path": path, "abs_url": f"{SITE_URL}/{path}",
            "uid": f"{slug}-{ed_id}@{UID_DOMAIN}",
            "is_timed": is_timed,
            "venue": ed.get("venue_en") or ev["venue_en"],
            "pin": venue_pin(ev, ed),
            "when": fmt_range(ed["start"], ed["end"]),
            # A list published before the event can still change, but once we have
            # re-checked the source after the event ended, what we show is the last word.
            "chart": route_chart(ed.get("route")),
            "decades": decade_chart(ed.get("cars")),
            "list_provisional": ("list_as_of" in ed and ed["list_as_of"] < ed["end"]
                                 and ed["last_verified"] <= ed["end"]),
        }
        if is_timed:
            r["start_dt"] = _local_dt(ed["start"], ed["start_time"])
            r["end_dt"] = _local_dt(ed["end"], ed["end_time"])
            if ed["start"] == ed["end"]:
                r["when_full"] = f"{r['when']}, {ed['start_time']} to {ed['end_time']} Japan time"
            else:
                r["when_full"] = (f"{fmt_day(ed['start'])} {ed['start_time']} to "
                                  f"{fmt_day(ed['end'])} {ed['end_time']}, Japan time")
        else:
            r["when_full"] = r["when"]
        r["jsonld"] = build_jsonld(r)
        rows.append(r)
    rows.sort(key=lambda r: (r["ed"]["start"], r["slug"], r["id"]))
    return rows


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
    rows = make_rows(events, editions)

    env = Environment(loader=FileSystemLoader(templates_dir),
                      autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.filters["fee"] = fmt_fee
    env.filters["weekday"] = fmt_weekday
    host = SITE_URL.split("://", 1)[1]
    common = {"site_name": SITE_NAME, "site_url": SITE_URL,
              "ics_url": f"{SITE_URL}/{FEED_FILE}", "webcal_url": f"webcal://{host}/{FEED_FILE}"}

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
    max_year = max((r["year"] for r in rows), default=None)
    title = f"Classic Car Events in Japan {max_year}" if max_year else "Classic Car Events in Japan"

    write("index.html", env.get_template("home.html").render(
        **common, root="", canonical=f"{SITE_URL}/", title=f"{title} | {SITE_NAME}",
        rows=rows, years=year_chart(rows), latest=latest, jsonld=[]))

    sitemap = [(f"{SITE_URL}/", latest)]
    for slug, ev in sorted(events.items()):
        ev_rows = [r for r in rows if r["slug"] == slug]
        verified = max([ev["last_verified"]] + [r["ed"]["last_verified"] for r in ev_rows])
        write(f"events/{slug}/index.html", env.get_template("event.html").render(
            **common, root="../../", canonical=f"{SITE_URL}/events/{slug}/",
            title=f"{ev['name_en']}: Visitor Guide | {SITE_NAME}",
            ev=ev, rows=ev_rows, verified=verified, pin=venue_pin(ev),
            jsonld=[r["jsonld"] for r in ev_rows if not r["has_page"]]))
        sitemap.append((f"{SITE_URL}/events/{slug}/", verified))
        for r in ev_rows:
            if not r["has_page"]:
                continue
            ed = r["ed"]
            write(f"{r['path']}index.html", env.get_template("edition.html").render(
                **common, root="../../../", canonical=r["abs_url"],
                title=f"{r['full_name']}: {' and '.join(r['page_parts'])} | {SITE_NAME}",
                ev=ev, r=r, ed=ed, jsonld=[r["jsonld"]]))
            sitemap.append((r["abs_url"], ed["last_verified"]))

    write(FEED_FILE, build_ics(rows))
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")

    urls = "".join(f"  <url><loc>{xml_escape(u)}</loc><lastmod>{d.isoformat()}</lastmod></url>\n"
                   for u, d in sorted(sitemap) if d)
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
