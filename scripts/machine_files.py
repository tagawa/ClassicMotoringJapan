"""Files written for agents rather than readers: the JSON API, llms.txt and the catalogues."""
from __future__ import annotations

import json

from formatting import prose_text
from settings import FEED_FILE, SITE_LEDE, SITE_NAME, SITE_URL


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
            "cutoff_year": r["cutoff_year"],
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


def build_llms_txt(rows: list[dict], events: dict, car_groups: list[dict] = ()) -> str:
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
            # The line opens with the event's prefecture, so an edition held elsewhere says where.
            notes = [r["prefecture"]] if r["prefecture"] != ev["prefecture"] else []
            if r["ed"]["status"] != "confirmed":
                notes.append(r["ed"]["status"])
            dates.append(f"{when} ({', '.join(notes)})" if notes else when)
        lines.append(f"- [{ev['name_en']}]({SITE_URL}/events/{slug}/): "
                     f"{ev['prefecture']}. {'; '.join(dates)}.")
        for r in ev_rows:
            if r["has_page"]:
                lines.append(f"  - [{r['full_name']}]({r['abs_url']}): {r['parts_phrase'].lower()}.")
    lines += ["", "## Cars", "",
              f"- [Cars by make]({SITE_URL}/cars/): every make on a published entry list, with its counts."]
    lines += [f"  - [{page['title']}]({SITE_URL}/{page['path']}): events where these cars have run, "
              "and every list including them." for page in car_groups]
    lines += ["", "## Site", "",
              f"- [About]({SITE_URL}/about/): where the facts come from, how they are checked, "
              "and where to report an error.",
              f"- [Japanese]({SITE_URL}/ja/): the site in Japanese, from the same data: dates, venues, "
              "admission, routes and entry lists.",
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
    """RFC 9727 API catalog. The About page lists the feeds, so service-doc points at it;
    there is no OpenAPI description to offer as service-desc and none is claimed."""
    doc = [{"href": f"{SITE_URL}/about/", "type": "text/html", "title": f"About {SITE_NAME}"}]
    linkset = [{"anchor": f"{SITE_URL}/api/events.json", "service-doc": doc},
               {"anchor": f"{SITE_URL}/{FEED_FILE}", "service-doc": doc}]
    return json.dumps({"linkset": linkset}, indent=2, ensure_ascii=False) + "\n"
