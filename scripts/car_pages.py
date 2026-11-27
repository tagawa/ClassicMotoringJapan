"""The cars section: /cars/ and one page per make group (spec 4.11 and section 5)."""
from __future__ import annotations

from datetime import date

from formatting import fmt_range, fmt_span
from settings import COUNTRIES, PAGE_MIN_EDITIONS
from validate import make_slug

# The organiser's list did not name the make, so there is nothing for a reader to follow.
NO_LINE = {"Unknown"}
INDEX_DESCRIPTION = ("Every car make on the published entry lists of classic car events in Japan, "
                     "with how many cars and events each appears at.")


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


# A show's announced model counts as one car here: a visitor finding two where one was
# announced won't mind (owner, 2026-11-23). The edition pages still tell the two apart.
# Entry lists, not events: the page lists fewer events than lists, and "at 22 events" read against them.
def _counts_text(cars: int, lists: int) -> str:
    return f"{_n(cars, 'car')} on {_n(lists, 'entry list')}"


def _dates(slug: str, since, rows: list[dict]) -> list[dict]:
    """The build never reads the clock, so a line gives every edition from its evidence on (on,
    so an upcoming edition with its own list keeps its date) and the browser picks the next."""
    return [{"start": d["ed"]["start"], "end": d["ed"]["end"], "tentative": d["ed"]["status"] == "tentative",
             "text": fmt_span(d["ed"]["start"], d["ed"]["end"], year=True)
                     + (" (dates not confirmed)" if d["ed"]["status"] == "tentative" else "")}
            for d in rows if d["slug"] == slug and d["ed"]["start"] >= since and d["ed"]["status"] != "cancelled"]


def _event_line(latest: dict, rows: list[dict]) -> dict:
    """An event's line from its latest list including the group: the count, and the dates."""
    r, n = latest["row"], latest["count"]
    text = f"{n} in {r['label']}" + (", provisional" if r["list_provisional"] else "")
    return {"ev": r["ev"], "slug": r["slug"], "row": r, "path": r["path"], "text": text,
            "dates": _dates(r["slug"], r["ed"]["start"], rows)}


def _photo_line(ph: dict, rows: list[dict]) -> dict | None:
    """An event's line from a photo taken there: the year, linked to the edition's page when it has one."""
    ev_rows = [r for r in rows if r["slug"] == ph["event"]]
    if not ev_rows:
        return None
    r = next((r for r in ev_rows if r["id"] == ph.get("edition")), None)
    since = r["ed"]["start"] if r else date(ph["year"], 1, 1)
    return {"ev": ev_rows[0]["ev"], "slug": ph["event"], "row": r, "photo_year": ph["year"],
            "path": r["path"] if r and r["has_page"] else f"events/{ph['event']}/",
            "text": f"Photographed in {ph['year']}", "dates": _dates(ph["event"], since, rows)}


def _photo_editions(lists: list[dict], photos: list[dict], rows: list[dict]) -> list[dict]:
    """The folded list's line for each edition a photo names that no list including the group covers."""
    covered = {(x["row"]["slug"], x["row"]["id"]) for x in lists}
    found = {}
    for ph in (item["data"] for item in photos if item["data"].get("edition")):
        key = (ph["event"], ph["edition"])
        r = next((r for r in rows if (r["slug"], r["id"]) == key), None)
        if r and key not in covered:
            found[key] = {"row": r, "count": None, "photo": True, "text": "Photographed",
                          "path": r["path"] if r["has_page"] else f"events/{r['slug']}/",
                          "when": fmt_range(r["ed"]["start"], r["ed"]["end"])}
    return list(found.values())


def _sightings(lists: list[dict], photos: list[dict], rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Every event and edition a group's page has evidence of, from its entry lists and its photos
    (spec 4.11): the events table A to Z, and the folded list newest first. A new kind of evidence
    belongs here, so neither can miss what the page shows elsewhere."""
    folded = sorted(lists + _photo_editions(lists, photos, rows), key=lambda x: x["row"]["ed"]["start"], reverse=True)
    latest_by_event: dict[str, dict] = {}
    for x in lists:  # newest first, so the first seen per event is its latest
        latest_by_event.setdefault(x["row"]["slug"], x)
    lines = {slug: _event_line(x, rows) for slug, x in latest_by_event.items()}
    # An event with a list keeps its count; of several photos at one event, the latest year speaks.
    for ph in sorted((item["data"] for item in photos if item["data"].get("event")), key=lambda ph: -ph["year"]):
        if ph["event"] not in lines and (line := _photo_line(ph, rows)):
            lines[ph["event"]] = line
    return sorted(lines.values(), key=lambda line: line["ev"]["name_en"].casefold()), folded


def unlisted_photo_events(pages: list[dict], car_photos: dict) -> list[str]:
    """The build's guard: a page whose photo names an event its table lacks (spec 4.11)."""
    errors = []
    for page in pages:
        listed = {line["slug"] for line in page["events"]}
        folded = {(x["row"]["slug"], x["row"]["id"]) for x in page["lists"]}
        for item in car_photos.get(page["name"], []):
            ph = item["data"]
            if ph.get("event") and ph["event"] not in listed:
                errors.append(f"car_photos.yml: {ph['file']} was taken at {ph['event']}, but the "
                              f"{page['name']} page's events table does not list it")
            if ph.get("edition") and (ph["event"], ph["edition"]) not in folded:
                errors.append(f"car_photos.yml: {ph['file']} was taken at {ph['event']} {ph['edition']}, but "
                              f"the {page['name']} page's folded entry lists do not hold that edition")
    return errors


def _group_of(groups: dict[str, list[str]]) -> dict[str, str]:
    return {member: name for name, members in groups.items() for member in members}


def _lists_summary(lists: int, photos: int) -> str:
    """As the edition page folds its cars: "1 entry list" alone, "All 3 ..." otherwise."""
    text = _n(lists, "entry list") + (f" and {_n(photos, 'photo')}" if photos else "")
    return f"All {text}" if lists + photos > 1 else text


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def group_pages(rows: list[dict], groups: dict[str, list[str]], car_photos: dict | None = None) -> list[dict]:
    """One record per group on lists from enough editions, sorted by slug. Photos add events to a
    page's table but never decide whether the page exists, which lists alone do."""
    owner = _group_of(groups)
    editions: dict[str, set] = {}
    verified: dict[str, object] = {}
    counts: dict[str, int] = {}
    for r in rows:
        for car in r["cars"] or []:
            make, checked = car["make"], r["ed"]["last_verified"]
            name = owner.get(make, make)
            editions.setdefault(name, set()).add(r["uid"])
            verified[name] = max(verified.get(name, checked), checked)
            counts[make] = counts.get(make, 0) + 1
    pages = []
    for name, seen in editions.items():
        if name in NO_LINE or len(seen) < PAGE_MIN_EDITIONS:
            continue
        members = groups.get(name, [name])
        # A member with a single car would only lengthen the title (Nissan Diesel).
        named = ([m for m in members if counts.get(m, 0) >= 2]
                 or [m for m in members if counts.get(m)])
        title, slug = _join(named), make_slug(name)
        lists = []
        for r in rows:
            n = sum(1 for car in r["cars"] or [] if owner.get(car["make"], car["make"]) == name)
            if n:
                lists.append({"row": r, "count": n, "when": fmt_range(r["ed"]["start"], r["ed"]["end"]),
                              "text": _n(n, "car"), "path": r["path"]})
        lists.reverse()
        events, folded = _sightings(lists, (car_photos or {}).get(name, []), rows)
        photographed = len(folded) - len(lists)
        pages.append({"name": name, "slug": slug, "title": title, "members": members, "named": named,
                      "path": f"cars/{slug}/",
                      # The folded list: entry lists, and editions known only from a photo (count None).
                      "verified": verified[name], "lists": folded, "events": events,
                      "totals": _counts_text(sum(x["count"] for x in lists), len(lists)),
                      # As the edition page folds its cars: "1 car" alone, "All 3 cars" otherwise.
                      "lists_summary": _lists_summary(len(lists), photographed),
                      "description": f"Classic car events in Japan where {title} cars have run, from published "
                                     f"entry lists, with each event's next date."})
    return sorted(pages, key=lambda page: page["slug"])


def make_index(rows: list[dict], makes: dict, groups: dict[str, list[str]], pages: list[dict]) -> list[dict]:
    """One row per make on any list, A to Z, pointing to its group's page where one exists."""
    owner = _group_of(groups)
    page_of = {page["name"]: page for page in pages}
    tally: dict[str, list] = {}  # make: [cars, editions]
    for r in rows:
        for make in {car["make"] for car in r["cars"] or []}:
            counts = tally.setdefault(make, [0, 0])
            counts[0] += sum(1 for car in r["cars"] if car["make"] == make)
            counts[1] += 1
    lines = []
    for make in sorted(set(tally) - NO_LINE, key=str.casefold):
        page = page_of.get(owner.get(make, make))
        cars, events = tally[make]
        # A visitor scans for the make they follow, so a member whose page is titled by
        # another make first says which page holds it.
        note = page["title"] if page and page["named"][0] != make else None
        lines.append({"make": make, "page": page, "page_note": note,
                      "country": makes.get(make), "cars": cars, "events": events})
    return lines


def index_flags(lines: list[dict]) -> list[dict]:
    """The flags /cars/ uses, each to be drawn once ahead of the list."""
    return [{"code": code, "art": COUNTRIES[code][1]}
            for code in sorted({line["country"] for line in lines if line["country"]})]
