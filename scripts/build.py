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
import hashlib
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

from calendars import build_ics, ics_calendar
from car_pages import INDEX_DESCRIPTION, group_pages, index_flags, make_index
from cards import draw_card, plan_cards
from charts import year_chart
from formatting import (fmt_domain, fmt_fee, fmt_fee_ja, fmt_month_ja, fmt_span_ja, fmt_weekday, mark_ja,
                        prose_html)
from machine_files import build_api, build_api_catalog, build_ard_catalog, build_llms_txt
from maps import MAP_HEIGHT, MAP_WIDTH, japan_path, venue_pin
from page_meta import build_breadcrumbs, build_website_jsonld, edition_description, event_description
from photos import photo_info, write_photo
from rows import make_rows, month_groups
from settings import (ABOUT_DESCRIPTION, ARD_PATH, ARD_PREDECESSOR_PATH, CONTENT_SIGNAL, CONTENT_USAGE,
                      COUNTRIES, FEED_FILE, INDEXNOW_KEY, ISSUES_URL, JA_LEDE, PREFECTURES_JA, ROOT,
                      SHARE_SIZE, SITE_LEDE, SITE_NAME, SITE_URL, YOUTUBE_CHANNEL_URL)
from validate import BuildError, load_and_validate, load_make_groups, load_makes

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
    makes = load_makes(data_dir)
    groups = load_make_groups(data_dir, makes)
    rows = make_rows(events, editions, makes)
    car_groups = group_pages(rows, groups)
    # Each make in an edition's car table links to its group's page, where one exists.
    make_pages = {member: page["path"] for page in car_groups for member in page["members"]}
    og, cards, errors = plan_cards(events, rows)
    if errors:
        raise BuildError(errors)

    env = Environment(loader=FileSystemLoader(templates_dir),
                      autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    env.globals["countries"] = COUNTRIES
    env.filters["fee"] = fmt_fee
    env.filters["domain"] = fmt_domain
    env.filters["prose"] = prose_html
    env.filters["mark_ja"] = mark_ja
    env.filters["weekday"] = fmt_weekday
    env.filters["span_ja"] = fmt_span_ja
    env.filters["month_ja"] = fmt_month_ja
    env.filters["fee_ja"] = fmt_fee_ja
    env.filters["pref_ja"] = PREFECTURES_JA.__getitem__
    host = SITE_URL.split("://", 1)[1]
    common = {"site_name": SITE_NAME, "site_url": SITE_URL, "site_lede": SITE_LEDE,
              "ard_path": ARD_PATH, "ard_predecessor_path": ARD_PREDECESSOR_PATH,
              "issues_url": ISSUES_URL, "youtube_channel_url": YOUTUBE_CHANNEL_URL, "feed_file": FEED_FILE, "share_size": SHARE_SIZE, "ics_url": f"{SITE_URL}/{FEED_FILE}", "webcal_url": f"webcal://{host}/{FEED_FILE}"}

    reset_out_dir(out_dir)
    # Every other static file is served from static/, but browsers ask for /favicon.ico
    # by name with no link tag, so that one is copied to the site root instead.
    shutil.copytree(static_dir, out_dir / "static", ignore=shutil.ignore_patterns("favicon.ico"))
    shutil.copy2(static_dir / "favicon.ico", out_dir / "favicon.ico")
    for ev in events.values():
        if ev.get("photo"):
            write_photo(ev, data_dir, out_dir)
    for rel, layout, dots in cards:
        draw_card(layout, dots, out_dir / rel)
    for image in og.values():
        # Platforms cache an image by its URL, so a card with new dates needs a new one.
        if "?v=" not in image["url"]:
            data = (out_dir / image["url"].removeprefix(f"{SITE_URL}/")).read_bytes()
            image["url"] += f"?v={hashlib.sha256(data).hexdigest()[:8]}"

    def write(rel: str, text: str) -> None:
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="")

    all_verified = [e["last_verified"] for e in events.values()] + [x["data"]["last_verified"] for x in editions]
    latest = max(all_verified) if all_verified else None
    write("index.html", env.get_template("home.html").render(
        **common, root="", canonical=f"{SITE_URL}/", title=f"Classic car events in Japan | {SITE_NAME}", hreflang=True,
        description=SITE_LEDE, og_image=og["site"], months=month_groups(rows), years=year_chart(rows), latest=latest, jsonld=[build_website_jsonld()],
        japan=japan_path() if any(r["dot"] for r in rows) else None,
        map_box=f"0 0 {MAP_WIDTH:g} {MAP_HEIGHT:g}", map_ratio=MAP_HEIGHT / MAP_WIDTH))

    write("ja/index.html", env.get_template("ja.html").render(
        **common, root="../", canonical=f"{SITE_URL}/ja/", lang="ja", hreflang=True,
        title=f"日本のクラシックカーイベント | {SITE_NAME}", description=JA_LEDE, og_image=og["site"],
        months=month_groups(rows), latest=latest, jsonld=[]))

    sitemap = [(f"{SITE_URL}/", latest), (f"{SITE_URL}/ja/", latest)]
    for slug, ev in sorted(events.items()):
        ev_rows = [r for r in rows if r["slug"] == slug]
        verified = max([ev["last_verified"]] + [r["ed"]["last_verified"] for r in ev_rows])
        write(f"events/{slug}/index.html", env.get_template("event.html").render(
            **common, root="../../", canonical=f"{SITE_URL}/events/{slug}/",
            title=f"{ev['name_en']}: Visitor Guide", description=event_description(ev),
            ev=ev, rows=ev_rows, verified=verified, pin=venue_pin(ev),
            photo=photo_info(ev), og_image=og[slug],
            jsonld=[r["jsonld"] for r in ev_rows if not r["has_page"] and r["jsonld"]]))
        sitemap.append((f"{SITE_URL}/events/{slug}/", verified))
        for r in ev_rows:
            if not r["has_page"]:
                continue
            ed = r["ed"]
            write(f"{r['path']}index.html", env.get_template("edition.html").render(
                **common, root="../../../", canonical=r["abs_url"],
                title=f"{r['full_name']}: {r['parts_phrase']}",
                description=edition_description(r),
                ev=ev, r=r, ed=ed, photo=photo_info(ev), og_image=og[r["path"]], make_pages=make_pages,
                jsonld=[block for block in (r["jsonld"], build_breadcrumbs(r)) if block]))
            sitemap.append((r["abs_url"], ed["last_verified"]))

    write("about/index.html", env.get_template("about.html").render(
        **common, root="../", canonical=f"{SITE_URL}/about/", title=f"About | {SITE_NAME}",
        description=ABOUT_DESCRIPTION, og_image=og["site"], jsonld=[]))
    # The page describes the site, not the data, so no verified date stands behind it.
    sitemap.append((f"{SITE_URL}/about/", None))

    cars_verified = max((r["ed"]["last_verified"] for r in rows if r["cars"]), default=None)
    make_lines = make_index(rows, makes, groups, car_groups)
    write("cars/index.html", env.get_template("cars.html").render(
        **common, root="../", canonical=f"{SITE_URL}/cars/", title=f"Cars by make | {SITE_NAME}",
        description=INDEX_DESCRIPTION, og_image=og["site"], lines=make_lines, flags=index_flags(make_lines),
        latest=cars_verified, jsonld=[]))
    sitemap.append((f"{SITE_URL}/cars/", cars_verified))
    for page in car_groups:
        # No brand suffix: the title names something on its own (spec 8).
        write(f"{page['path']}index.html", env.get_template("car_group.html").render(
            **common, root="../../", canonical=f"{SITE_URL}/{page['path']}",
            title=f"{page['title']} at classic car events in Japan", description=page["description"],
            og_image=og["site"], page=page, latest=page["verified"], jsonld=[]))
        sitemap.append((f"{SITE_URL}/{page['path']}", page["verified"]))

    # Pages serves this for a missing path at any depth, so links must be root-absolute.
    write("404.html", env.get_template("404.html").render(
        **common, root="/", canonical=None, title=f"Page not found | {SITE_NAME}",
        events=sorted(events.values(), key=lambda e: e["name_en"].casefold()), jsonld=[]))

    write(FEED_FILE, build_ics(rows))
    # No calendar name, so the app adds the event to one the visitor already has.
    for r in rows:
        if r["ics_path"]:
            write(r["ics_path"], ics_calendar([], [r]))
    write("robots.txt", f"User-agent: *\nContent-Signal: {CONTENT_SIGNAL}\nContent-Usage: {CONTENT_USAGE}\nAllow: /\n\n"
                        f"Sitemap: {SITE_URL}/sitemap.xml\n"
                        f"Agentmap: {SITE_URL}/{ARD_PATH}\n")
    write("api/events.json", build_api(rows))
    write("llms.txt", build_llms_txt(rows, events, car_groups))
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
