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
from markupsafe import Markup

from calendars import build_ics, ics_calendar
from car_pages import INDEX_DESCRIPTION, group_pages, index_flags, make_index
from cards import draw_card, plan_cards
from charts import year_chart
from formatting import mark_ja, prose_html, prose_para
from languages import (CARS_DESCRIPTION_JA, FILTERS, LANGUAGE_NAMES, LANGUAGES, PREFIX, TEXT, countries, event_text,
                       group_text, local, months_text, row_text, years_text)
from machine_files import build_api, build_api_catalog, build_ard_catalog, build_llms_txt
from maps import MAP_HEIGHT, MAP_WIDTH, japan_path, venue_pin
from page_meta import build_breadcrumbs, build_website_jsonld, edition_description, event_description
from photos import car_photo_info, edition_cars, photo_car, photo_info, write_car_photo, write_photo
from rows import make_rows, month_groups
from settings import (ABOUT_DESCRIPTION, ARD_PATH, ARD_PREDECESSOR_PATH, CONTENT_SIGNAL, CONTENT_USAGE,
                      FEED_FILE, INDEXNOW_KEY, ISSUES_URL, JA_LEDE, PREFECTURES_JA, ROOT,
                      SHARE_SIZE, SITE_LEDE, SITE_NAME, SITE_URL, YOUTUBE_CHANNEL_URL)
from validate import BuildError, load_and_validate, load_car_photos, load_make_groups, load_makes

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


def local_rows(rows: list[dict], lang: str) -> list[dict]:
    """The rows as a page in that language shows them, their links to each other kept."""
    if lang == "en":
        return rows
    laid = {id(r): {**r, **row_text(r, lang)} for r in rows}
    for r in laid.values():
        for key in ("previous", "next", "previous_videos"):
            if r[key] is not None:
                r[key] = laid[id(r[key])]
    return list(laid.values())


def pair(path: str, lang: str, root: str) -> dict:
    """A page's links to itself in every language: hreflang for search engines, the header for people."""
    return {"alternates": [(code, f"{SITE_URL}/{PREFIX[code]}{path}") for code in LANGUAGES],
            "others": [{"lang": code, "name": LANGUAGE_NAMES[code], "href": f"{root}{PREFIX[code]}{path}"}
                       for code in LANGUAGES if code != lang]}


def build(data_dir: Path, out_dir: Path,
          templates_dir: Path = ROOT / "templates", static_dir: Path = ROOT / "static") -> None:
    events, editions = load_and_validate(data_dir)
    makes = load_makes(data_dir)
    groups = load_make_groups(data_dir, makes)
    rows = make_rows(events, editions, makes)
    car_groups = group_pages(rows, groups)
    # Each make in an edition's car table links to its group's page, where one exists.
    make_pages = {member: page["path"] for page in car_groups for member in page["members"]}
    car_photos = load_car_photos(data_dir, groups, events, editions, {page["name"] for page in car_groups})
    photographed = edition_cars(car_photos, make_pages)
    og, cards, errors = plan_cards(events, rows)
    if errors:
        raise BuildError(errors)
    for page in car_groups:
        # One photo per group for now (spec 4.12); someone else's is never shared (8.3).
        for item in car_photos.get(page["name"], [])[:1]:
            info = car_photo_info(item, rows, events)
            if info["share"]:
                og[page["path"]] = {"url": f"{SITE_URL}/{info['share']}", "alt": info["alt"]}

    def make_env(lang: str) -> Environment:
        # One environment per language: the same filter names, bound to that language's formatters.
        env = Environment(loader=FileSystemLoader(templates_dir),
                          autoescape=select_autoescape(["html"]),
                          trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
        env.globals.update(t=TEXT[lang], lang=lang, countries=countries(lang),
                           # Marks Latin text on a page in another language (spec 6.6).
                           mark_en=Markup("") if lang == "en" else Markup(' lang="en"'),
                           local=lambda obj, base: local(lang, obj, base))
        env.filters.update(FILTERS[lang])
        env.filters["prose"] = prose_html
        env.filters["prose_para"] = prose_para
        env.filters["mark_ja"] = mark_ja
        return env

    envs = {lang: make_env(lang) for lang in LANGUAGES}
    env = envs["en"]
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
    for items in car_photos.values():
        for item in items:
            write_car_photo(item, data_dir, out_dir)
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
    japan = japan_path() if any(r["dot"] for r in rows) else None
    for lang in LANGUAGES:
        home = PREFIX[lang]
        root = "../" * home.count("/")
        write(f"{home}index.html", envs[lang].get_template("home.html").render(
            **common, **pair("", lang, root), root=root, home="", canonical=f"{SITE_URL}/{home}",
            title=f"{TEXT[lang]['home_title']} | {SITE_NAME}", description=SITE_LEDE if lang == "en" else JA_LEDE,
            og_image=og["site"], months=months_text(month_groups(local_rows(rows, lang)), lang),
            years=years_text(year_chart(rows), rows, lang), latest=latest,
            # The WebSite block describes the whole site, once.
            jsonld=[build_website_jsonld()] if lang == "en" else [],
            japan=japan, map_box=f"0 0 {MAP_WIDTH:g} {MAP_HEIGHT:g}", map_ratio=MAP_HEIGHT / MAP_WIDTH))

    sitemap = [(f"{SITE_URL}/", latest), (f"{SITE_URL}/ja/", latest)]
    for lang in LANGUAGES:
        home = PREFIX[lang]
        lang_rows = local_rows(rows, lang)
        for slug, ev in sorted(events.items()):
            ev_rows = [r for r in lang_rows if r["slug"] == slug]
            verified = max([ev["last_verified"]] + [r["ed"]["last_verified"] for r in ev_rows])
            path = f"events/{slug}/"
            root = "../" * (path.count("/") + home.count("/"))
            shown = {**ev, **event_text(ev, lang)}
            write(f"{home}{path}index.html", envs[lang].get_template("event.html").render(
                **common, **pair(path, lang, root), root=root, home="../" * path.count("/"),
                canonical=f"{SITE_URL}/{home}{path}",
                title=TEXT[lang]["event_title"](ev.get(f"name_{lang}") or ev["name_en"]),
                description=event_description(ev) if lang == "en" else shown["description"],
                ev=shown, rows=ev_rows, verified=verified, pin=venue_pin(ev),
                photo=photo_info(ev, photo_car(ev, car_photos, make_pages)), og_image=og[slug],
                # The Event blocks stay on the English page: one event, described once.
                jsonld=[r["jsonld"] for r in ev_rows if lang == "en" and not r["has_page"] and r["jsonld"]]))
            sitemap.append((f"{SITE_URL}/{home}{path}", verified))
    for lang in LANGUAGES:
        for r in local_rows(rows, lang):
            if not r["has_page"]:
                continue
            ev, ed, slug = r["ev"], r["ed"], r["slug"]
            home = PREFIX[lang]
            root = "../" * (r["path"].count("/") + home.count("/"))
            # The Event block stays on the English page: one event, described once.
            event_block = r["jsonld"] if lang == "en" else None
            crumbs = build_breadcrumbs([
                (str(TEXT[lang]["crumb_home"]), f"{SITE_URL}/{home}"),
                (ev.get(f"name_{lang}") or ev["name_en"], f"{SITE_URL}/{home}events/{slug}/"), (r["label"], None)])
            write(f"{home}{r['path']}index.html", envs[lang].get_template("edition.html").render(
                **common, **pair(r["path"], lang, root), root=root, home="../" * r["path"].count("/"),
                canonical=f"{SITE_URL}/{home}{r['path']}",
                title=f"{r['full_name']}{TEXT[lang]['title_sep']}{r['parts_phrase']}",
                description=edition_description(r) if lang == "en" else r["description"],
                ev=ev, r=r, ed=ed, photo=photo_info(ev, photo_car(ev, car_photos, make_pages)), og_image=og[r["path"]], make_pages=make_pages,
                photographed=photographed.get((slug, r["id"]), []),
                jsonld=[block for block in (event_block, crumbs) if block]))
            sitemap.append((f"{SITE_URL}/{home}{r['path']}", ed["last_verified"]))

    write("about/index.html", env.get_template("about.html").render(
        **common, root="../", canonical=f"{SITE_URL}/about/", title=f"About | {SITE_NAME}",
        description=ABOUT_DESCRIPTION, og_image=og["site"], jsonld=[]))
    # The page describes the site, not the data, so no verified date stands behind it.
    sitemap.append((f"{SITE_URL}/about/", None))

    cars_verified = max((r["ed"]["last_verified"] for r in rows if r["cars"]), default=None)
    for lang in LANGUAGES:
        home = PREFIX[lang]
        t = TEXT[lang]
        # Built from the page language's rows, so each list links and names its edition in that language.
        lang_rows = local_rows(rows, lang)
        pages = [{**page, **group_text(page, lang),
                  "photo": next((car_photo_info(item, lang_rows, events) for item in car_photos.get(page["name"], [])), None)}
                 for page in group_pages(lang_rows, groups)]
        make_lines = make_index(rows, makes, groups, pages)
        root = "../" * (1 + home.count("/"))
        write(f"{home}cars/index.html", envs[lang].get_template("cars.html").render(
            **common, **pair("cars/", lang, root), root=root, home="../", canonical=f"{SITE_URL}/{home}cars/",
            title=f"{t['cars_heading']} | {SITE_NAME}",
            description=INDEX_DESCRIPTION if lang == "en" else CARS_DESCRIPTION_JA, og_image=og["site"],
            lines=make_lines, flags=index_flags(make_lines), latest=cars_verified, jsonld=[]))
        sitemap.append((f"{SITE_URL}/{home}cars/", cars_verified))
        for page in pages:
            root = "../" * (page["path"].count("/") + home.count("/"))
            plain = page.get("plain_title", page["title"])
            # No brand suffix: the title names something on its own (spec 8).
            write(f"{home}{page['path']}index.html", envs[lang].get_template("car_group.html").render(
                **common, **pair(page["path"], lang, root), root=root, home="../../",
                canonical=f"{SITE_URL}/{home}{page['path']}",
                title=page.get("page_title", f"{plain} at classic car events in Japan"), description=page["description"],
                og_image=og.get(page["path"], og["site"]), page=page, latest=page["verified"], jsonld=[build_breadcrumbs([
                    (str(t["crumb_home"]), f"{SITE_URL}/{home}"), (str(t["nav_cars"]), f"{SITE_URL}/{home}cars/"),
                    (plain, None)])]))
            sitemap.append((f"{SITE_URL}/{home}{page['path']}", page["verified"]))

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
