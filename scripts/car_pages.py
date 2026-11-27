"""The cars section: /cars/ and one page per make group (spec 4.11 and section 5)."""
from __future__ import annotations

from formatting import fmt_span
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


def _event_line(latest: dict, rows: list[dict]) -> dict:
    """An event's line: the count from its latest list including the group, and the dates.

    The build never reads the clock, so it gives every edition from the counted one on (on,
    so an upcoming edition with its own list keeps its date) and the browser picks the next.
    """
    r, n = latest["row"], latest["count"]
    text = f"{n} in {r['label']}" + (", provisional" if r["list_provisional"] else "")
    dates = [{"start": d["ed"]["start"], "end": d["ed"]["end"], "tentative": d["ed"]["status"] == "tentative",
              "text": fmt_span(d["ed"]["start"], d["ed"]["end"], year=True)
                      + (" (dates not confirmed)" if d["ed"]["status"] == "tentative" else "")}
             for d in rows if d["slug"] == r["slug"] and d["ed"]["start"] >= r["ed"]["start"]
             and d["ed"]["status"] != "cancelled"]
    return {"ev": r["ev"], "slug": r["slug"], "row": r, "text": text, "dates": dates}


def _group_of(groups: dict[str, list[str]]) -> dict[str, str]:
    return {member: name for name, members in groups.items() for member in members}


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def group_pages(rows: list[dict], groups: dict[str, list[str]]) -> list[dict]:
    """One record per group on lists from enough editions, sorted by slug."""
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
                lists.append({"row": r, "count": n, "when": fmt_span(r["ed"]["start"], r["ed"]["end"], year=True),
                              "text": _n(n, "car")})
        lists.reverse()
        latest_by_event: dict[str, dict] = {}
        for x in lists:  # newest first, so the first seen per event is its latest
            latest_by_event.setdefault(x["row"]["slug"], x)
        events = sorted((_event_line(x, rows) for x in latest_by_event.values()),
                        key=lambda line: line["ev"]["name_en"].casefold())
        pages.append({"name": name, "slug": slug, "title": title, "members": members, "named": named,
                      "path": f"cars/{slug}/",
                      "verified": verified[name], "lists": lists, "events": events,
                      "totals": _counts_text(sum(x["count"] for x in lists), len(lists)),
                      # As the edition page folds its cars: "1 car" alone, "All 3 cars" otherwise.
                      "lists_summary": f"All {len(lists)} entry lists" if len(lists) > 1 else "1 entry list",
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
