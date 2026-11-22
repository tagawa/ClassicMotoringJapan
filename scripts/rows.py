"""One row per edition, the shape every page and file is rendered from."""
from __future__ import annotations

from calendars import google_calendar_url
from charts import decade_chart, makes_chart, route_chart
from formatting import _local_dt, fmt_edition, fmt_leaf, fmt_range, fmt_span
from maps import course_map, map_point, route_map, venue_pin
from page_meta import build_jsonld, event_notes_phrase, list_phrase
from settings import COUNTRIES, SITE_URL, UID_DOMAIN, VIDEO_EMBED_URL, VIDEO_WATCH_URL

# Order of the table's columns. A column no car fills is dropped, not left blank.
CAR_COLUMNS = (("entry_no", "No.", True), ("year", "Year", True), ("make", "Make", False),
               ("model", "Model", False), ("colour", "Colour", False))


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
                   "videos": ed.get("videos"), "course": ed.get("course")}
        # A video mostly exists only once an edition has run, so its presence marks the page
        # as a look back, with no clock involved: what it was like first, the timetable last.
        # An organiser's pre-event guide is the exception, and leading with it suits it too.
        # Before the day, a time trial's course is what a spectator has come to see.
        order = (("videos", "course", "cars", "route") if present["videos"]
                 else ("course", "route", "cars", "videos"))
        sections = [name for name in order if present[name]]
        page_parts = [{"route": "Route", "cars": cars_label, "videos": "Videos", "course": "Course map"}[name]
                      for name in sections]
        has_page = bool(page_parts)
        # Counted from what each section shows, so a jump cannot promise more than it lands on.
        n_cars, n_videos = len(present["cars"] or []), len(present["videos"] or [])
        n_days = len(ed.get("route") or [])
        jump_text = {
            "course": "Course map",
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
            "has_page": has_page, "sections": sections, "jumps": jumps, "parts_phrase": parts_phrase, "event_notes": event_notes_phrase(ev), "path": path, "abs_url": f"{SITE_URL}/{path}",
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
            "route_map": (route_map(ed["route"]) if ed.get("route")
                          and all("lat" in p for day in ed["route"] for p in day["checkpoints"]) else None),
            "course": course_map(ed["course"]) if ed.get("course") else None,
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
    # And forward to the next edition, so a page found by search leads on to the dates to keep,
    # and back to the one before, so an event's history can be stepped through from any edition.
    for r in rows:
        r["next"] = next((n for n in rows if n["slug"] == r["slug"] and n["ed"]["start"] > r["ed"]["start"]), None)
        r["previous"] = next((p for p in reversed(rows)
                              if p["slug"] == r["slug"] and p["ed"]["start"] < r["ed"]["start"]), None)
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
