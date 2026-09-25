"""Tests for scripts/build.py. Run: .venv/bin/python -m unittest discover -s tests -v

Done checks 1 and 2 need a final manual pass (Google Rich Results Test, calendar subscription on a phone).
These tests cover everything that can be checked offline, so the manual pass should be a formality.
"""
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402


def write_event(data: Path, slug: str, name_en="Test Event", name_ja="テストイベント",
                fee=0, extra="") -> None:
    """name_ja=None writes no Japanese name, as for an event that has only a Latin one.

    fee=None writes null, the state of an event whose admission is not announced yet.
    """
    p = data / "events" / f"{slug}.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"slug: {slug}\n"
        f"name_en: {name_en}\n"
        + (f"name_ja: {name_ja}\n" if name_ja is not None else "")
        + 
        f"official_url: https://example.com/{slug}/\n"
        f"prefecture: Shizuoka\n"
        f"venue_en: Test Park\n"
        f"spectator_fee_jpy: {'null' if fee is None else fee}\n"
        f"last_verified: 2026-09-20\n" + extra,
        encoding="utf-8",
    )


def instance_yaml(slug: str, year: int, start: str, end: str, status="confirmed", extra="",
                  verified="2026-09-20") -> str:
    return (
        f"slug: {slug}\n"
        f"year: {year}\n"
        f"status: {status}\n"
        f"start: {start}\n"
        f"end: {end}\n"
        f"source_url: https://example.com/{slug}/{year}/\n"
        f"last_verified: {verified}\n"
        f"sequence: 0\n" + extra
    )


def write_instance(data: Path, slug: str, stem, text: str) -> None:
    """stem is the edition file name without .yml, e.g. 2026 or "2026-spring"."""
    p = data / "events" / slug / f"{stem}.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


CARS = (
    "list_as_of: 2026-09-15\n"
    "cars:\n"
    '  - entry_no: "12"\n'
    "    year: 1929\n"
    "    make: Bentley\n"
    "    model: 4½ Litre Blower\n"
    '  - entry_no: "037"\n'
    "    year: 1934\n"
    "    make: Alfa Romeo\n"
    "    model: 6C 1750 GS\n"
)
ROUTE = (
    "route:\n"
    "  - date: 2026-10-18\n"
    "    checkpoints:\n"
    '      - start_time: "09:00"\n'
    '        end_time: "09:30"\n'
    "        place_en: Test Park, Testville\n"
    "        place_ja: \u30c6\u30b9\u30c8\u516c\u5712\n"
    "        prefecture: Shizuoka\n"
    '      - start_time: "11:00"\n'
    "        place_en: Test Harbour\n"
    "        prefecture: Shizuoka\n"
    "  - date: 2026-10-19\n"
    "    checkpoints:\n"
    '      - start_time: "08:00"\n'
    '        end_time: "08:45"\n'
    "        place_en: Test Hill\n"
    "        prefecture: Shizuoka\n"
)


ROUTE_ONE_DAY = (
    "route:\n"
    "  - date: 2026-11-22\n"
    "    checkpoints:\n"
    '      - start_time: "10:00"\n'
    "        place_en: Test Park\n"
    "        prefecture: Osaka\n"
)

RALLY_EXTRA = 'start_time: "08:00"\nend_time: "16:00"\nroute_en: Start Test Park 08:00, finish Test Harbour 16:00.\n' + CARS


def make_fixture(data: Path) -> None:
    write_event(data, "autumn-rally", name_en='"Autumn Rally, Shizuoka"',
                name_ja="オータム・クラシックカー・ラリー・イン・静岡・ヒストリック・ツーリング・ミーティング",
                extra="lat: 34.9756\nlon: 138.3828\n")
    write_instance(data, "autumn-rally", 2026,
                   instance_yaml("autumn-rally", 2026, "2026-10-18", "2026-10-19", extra=RALLY_EXTRA))
    write_event(data, "culture-day-show", fee=1500)
    write_instance(data, "culture-day-show", 2026,
                   instance_yaml("culture-day-show", 2026, "2026-11-03", "2026-11-03"))
    write_instance(data, "culture-day-show", 2027,
                   instance_yaml("culture-day-show", 2027, "2027-11-03", "2027-11-03", status="cancelled"))
    write_event(data, "hill-climb", name_en="Hill Climb",
                extra="typical_eras: [Prewar, 1950s]\ntypical_scale: About 30 cars\n")
    write_instance(data, "hill-climb", "2026-spring",
                   instance_yaml("hill-climb", 2026, "2026-04-12", "2026-04-12"))
    write_instance(data, "hill-climb", "2026-autumn",
                   instance_yaml("hill-climb", 2026, "2026-10-25", "2026-10-25", extra=CARS))


def cars_yaml(years, as_of="2026-09-15") -> str:
    rows = "".join(f'  - entry_no: "{i:02d}"\n    year: {y}\n    make: Test\n    model: Car\n'
                   for i, y in enumerate(years, 1))
    return f"list_as_of: {as_of}\ncars:\n{rows}"


def display_cars_yaml(models, as_of="2026-09-15") -> str:
    """A show's announced line-up: the source names models, so no numbers and no years."""
    rows = "".join(f"  - make: {make}\n    model: {model}\n" for make, model in models)
    return f"list_as_of: {as_of}\ncars:\n{rows}"


def unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


def jsonld_blocks(html: str) -> list[dict]:
    return [json.loads(m) for m in
            re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


class BuildOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        make_fixture(cls.data)
        build.build(cls.data, cls.out)
        cls.ics_raw = (cls.out / build.FEED_FILE).read_bytes().decode("utf-8")
        cls.ics = unfold(cls.ics_raw)
        # The 404 page is not a page of the site (no sitemap entry, served at any depth),
        # so the "every page" checks leave it out and NotFoundPageTests covers it.
        cls.pages = {p.relative_to(cls.out).as_posix(): p.read_text(encoding="utf-8")
                     for p in cls.out.rglob("*.html") if p.name != "404.html"}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def jsonld_by_name(self) -> dict:
        """Event blocks only: a page's breadcrumb trail is structured data too, but not an edition."""
        found = {}
        for page, html in self.pages.items():
            for block in jsonld_blocks(html):
                if block["@type"] == "Event":
                    found.setdefault(block["name"], []).append((page, block))
        return found

    # Done check 1: structured data (offline proxy for the Rich Results Test)

    def test_timed_event_jsonld_uses_japan_offset(self):
        (page, block), = self.jsonld_by_name()["Autumn Rally, Shizuoka 2026"]
        self.assertEqual(block["startDate"], "2026-10-18T08:00:00+09:00")
        self.assertEqual(block["endDate"], "2026-10-19T16:00:00+09:00")

    def test_all_day_event_jsonld_is_date_only(self):
        (page, block), = self.jsonld_by_name()["Test Event 2026"]
        self.assertEqual((block["startDate"], block["endDate"]), ("2026-11-03", "2026-11-03"))

    def test_each_edition_has_exactly_one_jsonld_block_on_the_right_page(self):
        found = self.jsonld_by_name()
        self.assertEqual(set(found), {"Autumn Rally, Shizuoka 2026", "Test Event 2026", "Test Event 2027",
                                      "Hill Climb Spring 2026", "Hill Climb Autumn 2026"})
        for name, hits in found.items():
            self.assertEqual(len(hits), 1, f"{name} appears on {[p for p, _ in hits]}")
        self.assertEqual(found["Autumn Rally, Shizuoka 2026"][0][0], "events/autumn-rally/2026/index.html")
        self.assertEqual(found["Test Event 2026"][0][0], "events/culture-day-show/index.html")
        self.assertEqual(found["Hill Climb Spring 2026"][0][0], "events/hill-climb/index.html")
        self.assertEqual(found["Hill Climb Autumn 2026"][0][0], "events/hill-climb/2026-autumn/index.html")

    def test_jsonld_has_required_fields(self):
        for hits in self.jsonld_by_name().values():
            for _, b in hits:
                self.assertEqual(b["@type"], "Event")
                for key in ("name", "startDate", "location", "eventStatus", "url"):
                    self.assertIn(key, b)
                self.assertEqual(b["location"]["name"], "Test Park")
                self.assertEqual(b["location"]["address"]["addressCountry"], "JP")
                self.assertTrue(b["url"].startswith("https://classicmotoringjapan.com/"))

    def test_cancelled_maps_to_event_cancelled(self):
        (_, block), = self.jsonld_by_name()["Test Event 2027"]
        self.assertEqual(block["eventStatus"], "https://schema.org/EventCancelled")

    def test_free_flag_follows_fee(self):
        found = self.jsonld_by_name()
        self.assertTrue(found["Autumn Rally, Shizuoka 2026"][0][1]["isAccessibleForFree"])
        self.assertFalse(found["Test Event 2026"][0][1]["isAccessibleForFree"])

    # Done check 2: calendar feed (offline proxy for the phone subscription)

    def test_ics_uses_crlf_and_folds_at_75_octets(self):
        self.assertTrue(self.ics_raw.endswith("\r\n"))
        self.assertNotIn("\n", self.ics_raw.replace("\r\n", ""))
        for line in self.ics_raw.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, line)
        self.assertIn("\r\n ", self.ics_raw, "fixture should exercise folding")

    def test_ics_all_day_end_is_exclusive_and_never_utc(self):
        self.assertIn("DTSTART;VALUE=DATE:20261103", self.ics)
        self.assertIn("DTEND;VALUE=DATE:20261104", self.ics)

    def test_ics_timed_event_is_utc(self):
        self.assertIn("DTSTART:20261017T230000Z", self.ics)
        self.assertIn("DTEND:20261019T070000Z", self.ics)
        self.assertFalse(any(line.startswith("BEGIN:VTIMEZONE") for line in self.ics))

    def test_ics_uid_dtstamp_sequence_status(self):
        self.assertIn("UID:autumn-rally-2026@classicmotoringjapan.com", self.ics)
        self.assertIn("DTSTAMP:20260920T000000Z", self.ics)
        self.assertIn("SEQUENCE:0", self.ics)
        self.assertIn("STATUS:CANCELLED", self.ics)
        self.assertEqual(self.ics.count("BEGIN:VEVENT"), 5)

    def test_ics_escapes_commas(self):
        self.assertIn("SUMMARY:Autumn Rally\\, Shizuoka", self.ics)

    def test_every_page_offers_a_live_subscription(self):
        for page, html in self.pages.items():
            self.assertIn('href="webcal://classicmotoringjapan.com/classic-car-events.ics"', html, page)
            self.assertIn("https://classicmotoringjapan.com/classic-car-events.ics", html, page)

    def test_the_feed_file_name_is_the_name_thunderbird_will_show(self):
        # Thunderbird has never read X-WR-CALNAME (bugzilla 168176, open since 2002). It
        # names a calendar after the last path segment, so the file name is the name.
        self.assertTrue((self.out / "classic-car-events.ics").is_file())
        self.assertFalse((self.out / "events.ics").exists())

    def test_the_calendar_names_itself_for_clients_that_do_read_it(self):
        self.assertIn("X-WR-CALNAME:Classic Motoring Japan", self.ics)
        self.assertIn("NAME:Classic Motoring Japan", self.ics)

    # Map links

    def test_a_venue_with_coordinates_gets_a_map_link(self):
        html = self.pages["events/autumn-rally/index.html"]
        self.assertIn('href="https://maps.apple.com/?ll=34.9756,138.3828&amp;q=Test%20Park"', html)
        self.assertIn(">Map</a>", html)

    def test_the_edition_page_pins_the_same_venue(self):
        html = self.pages["events/autumn-rally/2026/index.html"]
        self.assertIn("https://maps.apple.com/?ll=34.9756,138.3828&amp;q=Test%20Park", html)

    def test_a_venue_without_coordinates_shows_no_map_link(self):
        for page in ("events/hill-climb/index.html", "events/culture-day-show/index.html",
                     "index.html"):
            self.assertNotIn("maps.apple.com", self.pages[page], page)
            self.assertNotIn('class="map"', self.pages[page], page)

    def map_links(self) -> list[str]:
        found = [m for html in self.pages.values()
                 for m in re.findall(r'<a class="map".*?</a>', html, re.S)]
        self.assertTrue(found, "fixture should have map links to check")
        return found

    def test_every_map_link_is_drawn_with_a_pin_and_still_reads_as_text(self):
        for link in self.map_links():
            self.assertIn("<svg", link)
            self.assertTrue(link.endswith(">Map</a>"), link)

    def test_the_pin_is_decorative_and_never_reaches_a_screen_reader(self):
        for link in self.map_links():
            self.assertIn('aria-hidden="true"', link)
            self.assertIn('focusable="false"', link)

    def test_the_pin_follows_the_link_colour_instead_of_carrying_its_own(self):
        # currentColor is what makes one icon work in both themes.
        for link in self.map_links():
            svg = link[link.index("<svg"):link.index("</svg>")]
            self.assertIn('stroke="currentColor"', svg)
            self.assertNotIn("#", svg, "a baked-in colour would ignore dark mode")

    def test_the_pin_is_sized_in_the_markup_so_it_survives_a_missing_stylesheet(self):
        for link in self.map_links():
            svg = link[link.index("<svg"):link.index("</svg>")]
            self.assertIn('width="16"', svg)
            self.assertIn('height="16"', svg)

    def test_the_calendar_entry_carries_the_pin(self):
        self.assertIn("GEO:34.9756;138.3828", self.ics)
        self.assertEqual(sum(line.startswith("GEO:") for line in self.ics), 1,
                         "only the venue with coordinates should carry one")

    def test_structured_data_carries_the_pin_only_where_there_is_one(self):
        found = self.jsonld_by_name()
        pinned = found["Autumn Rally, Shizuoka 2026"][0][1]["location"]
        self.assertEqual(pinned["geo"], {"@type": "GeoCoordinates",
                                         "latitude": 34.9756, "longitude": 138.3828})
        self.assertNotIn("geo", found["Test Event 2026"][0][1]["location"])

    # The year at a glance

    def test_the_home_page_opens_with_a_strip_per_year(self):
        html = self.pages["index.html"]
        self.assertIn(">2026: 4 events, Apr to Nov<", html)
        self.assertIn(">2027: 1 event, Nov<", html)

    def test_each_year_is_labelled_so_the_browser_can_drop_the_past_ones(self):
        # The build never reads the clock, so which years are past is decided in the browser,
        # the same way upcoming and past are. See tests/test_browser.py.
        html = self.pages["index.html"]
        self.assertIn('<li data-year="2026">', html)
        self.assertIn('<li data-year="2027">', html)
        self.assertIn('<div id="years">', html)

    def test_an_edition_sits_where_its_date_falls_in_the_year(self):
        # 12 Apr 2026 is day 102 of 365, so the bar starts 101 days in.
        self.assertIn("left: 27.67%", self.pages["index.html"])

    def test_a_one_day_edition_still_gets_a_visible_bar(self):
        self.assertIn("width: 1.0%", self.pages["index.html"])

    def test_a_cancelled_edition_is_drawn_apart_from_the_rest(self):
        self.assertEqual(self.pages["index.html"].count('<i class="off"'), 1)

    def test_the_year_strip_restates_the_list_and_stays_out_of_the_way(self):
        html = self.pages["index.html"]
        self.assertIn('<span class="chart-track" aria-hidden="true">', html)
        self.assertIn(">Jan<", html)
        self.assertIn(">Oct<", html)

    # Chips, dots and the column that earns its place

    def test_eras_render_as_chips(self):
        html = self.pages["events/hill-climb/index.html"]
        self.assertIn('<span class="chip">Prewar</span>', html)
        self.assertIn('<span class="chip">1950s</span>', html)
        self.assertIn("About 30 cars", html)

    def test_status_keeps_its_word_and_gains_a_dot(self):
        html = self.pages["events/culture-day-show/index.html"]
        self.assertIn('<span class="dot" aria-hidden="true"></span>Confirmed', html)
        self.assertIn('<span class="dot cancelled" aria-hidden="true"></span>Cancelled', html)

    def test_the_details_column_goes_when_no_edition_has_a_page(self):
        no_pages = self.pages["events/culture-day-show/index.html"]
        self.assertEqual(no_pages.count("<th scope=\"col\">"), 3)
        self.assertNotIn("visually-hidden", no_pages)
        with_pages = self.pages["events/autumn-rally/index.html"]
        self.assertEqual(with_pages.count("<th scope=\"col\">"), 4)

    # Several editions in one year

    def test_editions_get_their_own_uid_and_calendar_name(self):
        self.assertIn("UID:hill-climb-2026-spring@classicmotoringjapan.com", self.ics)
        self.assertIn("UID:hill-climb-2026-autumn@classicmotoringjapan.com", self.ics)
        self.assertIn("SUMMARY:Hill Climb Spring", self.ics)
        self.assertIn("SUMMARY:Hill Climb Autumn", self.ics)

    def test_editions_share_one_evergreen_page(self):
        html = self.pages["events/hill-climb/index.html"]
        self.assertIn("Spring 2026", html)
        self.assertIn("Autumn 2026", html)
        self.assertIn('href="../../events/hill-climb/2026-autumn/">Entry list</a>', html)

    def test_home_lists_each_edition_by_name(self):
        html = self.pages["index.html"]
        self.assertIn(">Hill Climb Spring</a>", html)
        self.assertIn(">Hill Climb Autumn</a>", html)

    # Done check 4 (static half): every row carries its end date for the browser script

    def test_home_rows_carry_end_dates_in_date_order(self):
        ends = re.findall(r'data-end="(\d{4}-\d{2}-\d{2})"', self.pages["index.html"])
        self.assertEqual(ends, ["2026-04-12", "2026-10-19", "2026-10-25", "2026-11-03", "2027-11-03"])

    # Old and budget devices: plain CSS only (see ~/.claude/DESIGN.md)

    def css(self) -> str:
        return (self.out / "static/style.css").read_text(encoding="utf-8")

    def test_stylesheet_declares_no_custom_properties(self):
        # var() is unsupported on IE and on Android browsers still in use.
        self.assertNotIn("var(--", self.css())
        self.assertIsNone(re.search(r"^\s*--[\w-]+\s*:", self.css(), re.M),
                          "custom property declared")

    def test_flex_containers_use_margins_not_gap(self):
        # Flex `gap` resolves to nothing on IE and Safari before 14.1: no fallback.
        for rule in re.findall(r"\{[^}]*display:\s*(?:inline-)?flex[^}]*\}", self.css()):
            self.assertNotIn("gap", rule, f"flex rule uses gap: {rule}")

    def test_dark_mode_is_defined_by_duplicating_colours(self):
        self.assertIn("@media (prefers-color-scheme: dark)", self.css())

    # Reproducibility and the home-page title

    def test_same_data_gives_identical_files(self):
        out2 = self.tmp / "site2"
        build.build(self.data, out2)
        files1 = sorted(p.relative_to(self.out) for p in self.out.rglob("*") if p.is_file())
        files2 = sorted(p.relative_to(out2) for p in out2.rglob("*") if p.is_file())
        self.assertEqual(files1, files2)
        for rel in files1:
            self.assertEqual((self.out / rel).read_bytes(), (out2 / rel).read_bytes(), str(rel))

    def test_home_title_year_comes_from_data(self):
        self.assertIn("<title>Classic Car Events in Japan 2027 | Classic Motoring Japan</title>",
                      self.pages["index.html"])

    # Crawler and browser files

    def test_robots_txt_allows_everything_and_points_at_the_sitemap(self):
        robots = (self.out / "robots.txt").read_text(encoding="utf-8")
        self.assertIn("User-agent: *", robots)
        self.assertIn("Allow: /", robots)
        self.assertIn("Sitemap: https://classicmotoringjapan.com/sitemap.xml", robots)

    def test_favicon_ico_sits_at_the_site_root_where_browsers_ask_for_it(self):
        ico = self.out / "favicon.ico"
        self.assertTrue(ico.is_file(), "browsers request /favicon.ico with no link tag")
        self.assertEqual(ico.read_bytes()[:4], b"\x00\x00\x01\x00", "not an ICO file")
        self.assertFalse((self.out / "static" / "favicon.ico").exists(),
                         "the .ico belongs at the root only, not copied into static/ as well")

    def test_every_page_offers_both_icon_formats(self):
        for page, html in self.pages.items():
            self.assertRegex(html, r'<link rel="icon" href="[^"]*favicon\.ico"', page)
            self.assertRegex(html, r'<link rel="icon" href="[^"]*static/favicon\.svg" type="image/svg\+xml">', page)

    # Content rules

    def test_edition_page_only_when_route_or_cars(self):
        self.assertIn("events/autumn-rally/2026/index.html", self.pages)
        self.assertNotIn("events/culture-day-show/2026/index.html", self.pages)
        self.assertNotIn("events/hill-climb/2026-spring/index.html", self.pages)

    def test_entry_list_labels_and_keeps_leading_zeros(self):
        html = self.pages["events/autumn-rally/2026/index.html"]
        self.assertIn("<h2>Entry list</h2>", html)
        self.assertIn("Entry list as of 2026-09-15.", html)
        self.assertIn("Provisional: cars may withdraw or change.", html)
        self.assertIn(">037<", html)
        self.assertEqual(re.findall(r'<th scope="col">(.*?)</th>', html)[-4:],
                         ["No.", "Year", "Make", "Model"])

    def test_an_admission_fee_renders_as_yen(self):
        self.assertIn("\u00a51,500", self.pages["events/culture-day-show/index.html"])

    def test_every_page_shows_last_verified(self):
        # The About page describes the site and holds no event data to have checked.
        for page, html in self.pages.items():
            if page == "about/index.html":
                continue
            self.assertRegex(html, r"(Last verified|Most recent check:) 2026-09-20", page)

    def test_internal_links_are_relative(self):
        for page, html in self.pages.items():
            self.assertNotRegex(html, r'(href|src)="/(?!/)', page)

    def test_sitemap_is_well_formed_and_lists_every_page(self):
        sitemap = (self.out / "sitemap.xml").read_text(encoding="utf-8")
        ET.fromstring(sitemap)
        for page in self.pages:
            url = "https://classicmotoringjapan.com/" + page.removesuffix("index.html")
            self.assertIn(f"<loc>{url}</loc>", sitemap)


    # Agent discovery files. GitHub Pages serves static files and nothing else, so the
    # checks that need response headers or content negotiation are out of reach; these
    # are the ones a file on disk can answer.

    def out_text(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def out_json(self, rel: str) -> dict:
        return json.loads(self.out_text(rel))

    def api_event(self, ident: str) -> dict:
        return next(e for e in self.out_json("api/events.json")["events"] if e["id"] == ident)

    def test_robots_txt_declares_content_signals_inside_the_wildcard_group(self):
        group = self.out_text("robots.txt").split("\n\n", 1)[0].splitlines()
        self.assertIn("User-agent: *", group)
        self.assertIn("Content-Signal: search=yes, ai-input=yes, ai-train=no", group)

    def test_events_json_carries_one_record_per_edition_in_date_order(self):
        self.assertEqual([e["id"] for e in self.out_json("api/events.json")["events"]],
                         ["hill-climb-2026-spring", "autumn-rally-2026", "hill-climb-2026-autumn",
                          "culture-day-show-2026", "culture-day-show-2027"])

    def test_events_json_dates_are_strings_a_parser_can_read(self):
        rally = self.api_event("autumn-rally-2026")
        self.assertEqual(rally["start"], "2026-10-18")
        self.assertEqual(rally["end"], "2026-10-19")
        self.assertEqual(rally["start_time"], "08:00")
        self.assertEqual(rally["last_verified"], "2026-09-20")
        self.assertEqual(rally["status"], "confirmed")

    def test_events_json_keeps_a_free_event_distinct_from_one_with_no_fee_recorded(self):
        self.assertEqual(self.api_event("autumn-rally-2026")["spectator_fee_jpy"], 0)
        self.assertEqual(self.api_event("culture-day-show-2026")["spectator_fee_jpy"], 1500)

    def test_events_json_repeats_the_entry_list_the_page_tabulates(self):
        self.assertEqual(self.api_event("autumn-rally-2026")["cars"][1],
                         {"entry_no": "037", "year": 1934, "make": "Alfa Romeo", "model": "6C 1750 GS"})
        self.assertNotIn("cars", self.api_event("culture-day-show-2026"))

    def test_events_json_carries_a_prose_route_where_that_is_all_the_source_gave(self):
        rally = self.api_event("autumn-rally-2026")
        self.assertEqual(rally["route_en"], "Start Test Park 08:00, finish Test Harbour 16:00.")
        self.assertNotIn("route", rally)

    def test_events_json_gives_coordinates_only_where_the_pages_have_a_map_link(self):
        self.assertEqual(self.api_event("autumn-rally-2026")["lat"], 34.9756)
        self.assertNotIn("lat", self.api_event("culture-day-show-2026"))

    def test_events_json_points_at_the_page_a_reader_would_open(self):
        for e in self.out_json("api/events.json")["events"]:
            rel = e["url"].removeprefix(build.SITE_URL + "/") + "index.html"
            self.assertIn(rel, self.pages, e["id"])

    def test_llms_txt_links_every_event_page_and_both_feeds(self):
        llms = self.out_text("llms.txt")
        linked = [page for page in self.pages if page.startswith("events/")]
        self.assertGreaterEqual(len(linked), 4)
        for page in linked:
            self.assertIn(f"{build.SITE_URL}/{page.removesuffix('index.html')})", llms, page)
        self.assertIn(f"{build.SITE_URL}/api/events.json", llms)
        self.assertIn(f"{build.SITE_URL}/{build.FEED_FILE}", llms)

    def test_llms_txt_names_an_edition_without_repeating_its_year(self):
        self.assertIn("): Shizuoka. Spring: 12 Apr 2026; Autumn: 25 Oct 2026.", self.out_text("llms.txt"))

    def test_llms_txt_marks_an_edition_that_is_not_going_ahead(self):
        self.assertIn("): Shizuoka. 3 Nov 2026; 3 Nov 2027 (cancelled).", self.out_text("llms.txt"))

    def test_the_manifest_is_served_from_the_current_and_the_predecessor_path(self):
        """ARD moved to /.well-known/ard.json; the scanner and older consumers still read
        the predecessor path, and the document is the same either way."""
        current = self.out_text(".well-known/ard.json")
        self.assertEqual(current, self.out_text(".well-known/ai-catalog.json"))
        self.assertEqual(json.loads(current)["specVersion"], "1.0")

    def test_robots_txt_names_the_manifest_as_an_entry_source(self):
        self.assertIn(f"Agentmap: {build.SITE_URL}/.well-known/ard.json",
                      self.out_text("robots.txt"))

    def test_every_page_advertises_the_manifest_under_both_relations(self):
        want = {"ard": ".well-known/ard.json", "ai-catalog": ".well-known/ai-catalog.json"}
        for page, html in self.pages.items():
            for rel, target in want.items():
                found = re.search(rf'<link rel="{rel}" href="([^"]*)"', html)
                self.assertIsNotNone(found, f"{page}: no rel={rel} link")
                self.assertEqual(urljoin(f"{build.SITE_URL}/{page}", found.group(1)),
                                 f"{build.SITE_URL}/{target}", page)

    def test_ard_manifest_matches_the_published_catalog_schema(self):
        catalog = self.out_json(".well-known/ai-catalog.json")
        self.assertEqual(set(catalog), {"specVersion", "host", "entries"})
        self.assertEqual(catalog["specVersion"], "1.0")
        self.assertEqual(catalog["host"]["displayName"], build.SITE_NAME)
        self.assertEqual(len(catalog["entries"]), 3)
        for entry in catalog["entries"]:
            where = entry["identifier"]
            self.assertRegex(where, r"^urn:air:classicmotoringjapan\.com(:[a-zA-Z0-9._-]+){2}$")
            self.assertTrue(entry["displayName"], where)
            self.assertRegex(entry["type"], r"^[a-z]+/[\w.+-]+$", where)
            self.assertNotIn("data", entry, "an entry carries url or data, never both")
            self.assertTrue(2 <= len(entry["representativeQueries"]) <= 5, where)

    def test_api_catalog_is_a_linkset_anchored_on_the_feeds(self):
        linkset = self.out_json(".well-known/api-catalog")["linkset"]
        self.assertEqual([e["anchor"] for e in linkset],
                         [f"{build.SITE_URL}/api/events.json", f"{build.SITE_URL}/{build.FEED_FILE}"])
        for entry in linkset:
            self.assertEqual(entry["service-doc"][0]["type"], "text/html")

    def test_every_url_the_catalogs_advertise_is_a_file_the_build_wrote(self):
        linkset = self.out_json(".well-known/api-catalog")["linkset"]
        urls = [e["url"] for e in self.out_json(".well-known/ai-catalog.json")["entries"]]
        urls += [e["anchor"] for e in linkset]
        urls += [link["href"] for e in linkset for link in e["service-doc"]]
        self.assertEqual(len(urls), 7, "an advertised link that was never collected proves nothing")
        for url in urls:
            rel = url.removeprefix(build.SITE_URL + "/")
            rel = rel + "index.html" if rel == "" or rel.endswith("/") else rel
            self.assertTrue((self.out / rel).is_file(), url)


class NotFoundPageTests(unittest.TestCase):
    """Pages serves /404.html for any missing path, at whatever depth was asked for."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)
        cls.html = (cls.out / "404.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_every_internal_link_is_root_absolute(self):
        # A relative link would resolve against the broken URL and 404 in turn.
        links = re.findall(r'(?:href|src)="([^"]*)"', self.html)
        internal = [u for u in links if not re.match(r"(https?:|webcal:)", u)]
        self.assertTrue(internal)
        for url in internal:
            self.assertTrue(url.startswith("/") and not url.startswith("//"), url)

    def test_links_every_event_page(self):
        slugs = sorted(p.name for p in (self.out / "events").iterdir() if p.is_dir())
        self.assertTrue(slugs)
        for slug in slugs:
            self.assertIn(f'href="/events/{slug}/"', self.html)

    def test_is_kept_out_of_search_results(self):
        self.assertIn('<meta name="robots" content="noindex">', self.html)
        self.assertNotIn('rel="canonical"', self.html)
        self.assertNotIn("application/ld+json", self.html)
        self.assertNotIn("404", (self.out / "sitemap.xml").read_text(encoding="utf-8"))

    def test_records_a_fathom_event(self):
        # Fathom event names cannot be renamed once created: a new name starts a new count.
        self.assertIn("fathom.trackEvent('404 page shown')", self.html)
        self.assertIn("if (window.fathom)", self.html)


class DeployWorkflowTests(unittest.TestCase):
    """The build writes site/.well-known/; the workflow has to carry it as far as Pages."""

    def test_the_artifact_step_keeps_dot_directories(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8"))
        steps = workflow["jobs"]["build"]["steps"]
        step, = [s for s in steps if "upload-pages-artifact" in s.get("uses", "")]
        self.assertIs(step["with"].get("include-hidden-files"), True,
                      "v4 and v5 of the action exclude every dot-path unless told otherwise, "
                      "which drops site/.well-known/ and 404s the agent catalogs")


class HeadParser(HTMLParser):
    """The head's meta and link tags, with attribute values unescaped as a browser reads them."""

    def __init__(self, html: str):
        super().__init__()
        self.meta, self.canonical, self.title, self._in_title = {}, None, "", False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and ("name" in a or "property" in a):
            self.meta[a.get("name") or a["property"]] = a["content"]
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a["href"]
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def make_description_fixture(data: Path) -> None:
    write_event(data, "tour", name_en="Test Tour",
                extra="summary_en: >\n  A tour past [Test Park](https://example.com/park/) and the\n"
                      "  harbour. It has run every year since 1990.\n")
    write_instance(data, "tour", 2026,
                   instance_yaml("tour", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
    write_instance(data, "tour", 2027,
                   instance_yaml("tour", 2027, "2027-10-17", "2027-10-18", status="cancelled", extra=CARS))
    # Quotes and an ampersand, which have to survive the trip into an attribute value.
    write_event(data, "show", name_en="'Test \"Show\" & Meet'", fee=1000)
    write_instance(data, "show", 2026,
                   instance_yaml("show", 2026, "2026-11-03", "2026-11-03", status="tentative",
                                 extra=display_cars_yaml([("Toyota", "2000GT")])))


class PageDescriptionTests(unittest.TestCase):
    """What a search snippet or a shared link says about each page, before anyone opens it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_description_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def head(self, rel: str) -> HeadParser:
        return HeadParser((self.out / rel).read_text(encoding="utf-8"))

    def description(self, rel: str) -> str:
        return self.head(rel).meta["description"]

    def test_the_home_page_is_described_by_the_site_lede(self):
        self.assertEqual(self.description("index.html"), build.SITE_LEDE)

    def test_an_event_page_is_described_by_the_first_sentence_of_its_summary(self):
        # A snippet shows about 155 characters, and a summary can run to 75 words.
        self.assertEqual(self.description("events/tour/index.html"), "A tour past Test Park and the harbour.")

    def test_an_event_without_a_summary_is_described_by_what_its_page_holds(self):
        self.assertEqual(self.description("events/show/index.html"),
                         'Dates, venue and admission for Test "Show" & Meet in Shizuoka.')

    def test_an_edition_is_described_by_what_its_page_holds(self):
        self.assertEqual(self.description("events/tour/2026/index.html"),
                         "Route for Test Tour 2026: 18–19 Oct 2026, Test Park, Shizuoka.")

    def test_a_cancelled_edition_says_so_before_anything_else(self):
        # A snippet that read like a normal listing would tell a searcher it is still on.
        self.assertEqual(self.description("events/tour/2027/index.html"),
                         "Cancelled. Entry list for Test Tour 2027: 17–18 Oct 2027, Test Park, Shizuoka.")

    def test_an_unconfirmed_show_says_so_and_names_its_list_as_the_page_does(self):
        self.assertEqual(self.description("events/show/2026/index.html"),
                         'Dates not confirmed. Cars on display for Test "Show" & Meet 2026: '
                         "3 Nov 2026, Test Park, Shizuoka.")

    def test_link_previews_repeat_the_title_description_and_canonical_address(self):
        pages = ["index.html", "about/index.html", "events/tour/index.html", "events/tour/2026/index.html"]
        for rel in pages:
            head = self.head(rel)
            self.assertEqual(head.meta["og:title"], head.title, rel)
            self.assertEqual(head.meta["og:description"], head.meta["description"], rel)
            self.assertEqual(head.meta["og:url"], head.canonical, rel)
            self.assertEqual(head.canonical, f"{build.SITE_URL}/{rel.removesuffix('index.html')}", rel)
            self.assertEqual(head.meta["og:type"], "website", rel)
            self.assertEqual(head.meta["og:site_name"], build.SITE_NAME, rel)

    def test_the_site_has_no_images_so_no_preview_image_is_claimed(self):
        for rel in ("index.html", "events/tour/2026/index.html"):
            self.assertNotIn("og:image", self.head(rel).meta, rel)

    def test_the_404_page_describes_nothing(self):
        head = self.head("404.html")
        self.assertNotIn("description", head.meta)
        self.assertFalse([key for key in head.meta if key.startswith("og:")])


class BreadcrumbTests(unittest.TestCase):
    """An edition page sits under its event page; the trail shows it, and says so to search engines."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    PAGE = "events/hill-climb/2026-autumn/index.html"

    def html(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def trail(self) -> str:
        found = re.search(r'<nav class="breadcrumbs" aria-label="Breadcrumb">(.*?)</nav>', self.html(self.PAGE), re.S)
        self.assertIsNotNone(found, "edition page has no breadcrumb trail")
        return found.group(1)

    def test_the_trail_comes_before_the_heading(self):
        html = self.html(self.PAGE)
        self.assertLess(html.index('class="breadcrumbs"'), html.index("<h1>"))

    def test_the_trail_links_home_and_the_event_and_names_the_current_page_unlinked(self):
        trail = self.trail()
        links = re.findall(r'<a href="([^"]*)">([^<]*)</a>', trail)
        resolved = [(urljoin(f"{build.SITE_URL}/{self.PAGE}", href), text) for href, text in links]
        self.assertEqual(resolved, [(f"{build.SITE_URL}/", "Home"),
                                    (f"{build.SITE_URL}/events/hill-climb/", "Hill Climb")])
        self.assertIn('<span aria-current="page">Autumn 2026</span>', trail)

    def test_separators_are_hidden_from_screen_readers(self):
        trail = self.trail()
        self.assertEqual(trail.count('<span class="sep" aria-hidden="true">›</span>'), 2)

    def test_structured_data_matches_the_visible_trail(self):
        # Google expects breadcrumb markup to describe what the page shows.
        blocks = [b for b in jsonld_blocks(self.html(self.PAGE)) if b["@type"] == "BreadcrumbList"]
        self.assertEqual(len(blocks), 1)
        items = blocks[0]["itemListElement"]
        self.assertEqual([(i["position"], i["name"], i.get("item")) for i in items], [
            (1, "Home", f"{build.SITE_URL}/"),
            (2, "Hill Climb", f"{build.SITE_URL}/events/hill-climb/"),
            (3, "Autumn 2026", None),
        ])

    def test_pages_whose_trail_would_only_say_home_have_none(self):
        for rel in ("index.html", "events/hill-climb/index.html", "about/index.html"):
            html = self.html(rel)
            self.assertNotIn("breadcrumbs", html, rel)
            self.assertNotIn("BreadcrumbList", html, rel)


class AboutPageTests(unittest.TestCase):
    """Where the facts come from, what the site is not, and where to report a mistake."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)
        cls.html = (cls.out / "about/index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_has_one_heading_and_a_brand_suffixed_title(self):
        self.assertEqual(self.html.count("<h1>"), 1)
        self.assertIn("<title>About | Classic Motoring Japan</title>", self.html)

    def test_says_the_site_is_not_the_official_channel(self):
        # Wording is left free; the one claim a visitor must not miss is pinned.
        self.assertIn("Not affiliated with any event or organiser.", self.html)

    def test_says_where_to_report_an_error(self):
        self.assertIn('href="https://github.com/tagawa/ClassicMotoringJapan/issues"', self.html)

    def test_every_page_links_to_it(self):
        pages = [p for p in self.out.rglob("*.html") if p.name != "404.html"]
        self.assertGreater(len(pages), 4)
        for p in pages:
            rel = p.relative_to(self.out).as_posix()
            hrefs = re.findall(r'href="([^"]*about/)"', p.read_text(encoding="utf-8"))
            self.assertIn(f"{build.SITE_URL}/about/",
                          [urljoin(f"{build.SITE_URL}/{rel}", h) for h in hrefs], rel)

    def test_the_404_page_links_to_it_from_the_root(self):
        self.assertIn('href="/about/"', (self.out / "404.html").read_text(encoding="utf-8"))

    def test_is_listed_in_the_sitemap_and_llms_txt(self):
        self.assertIn(f"<loc>{build.SITE_URL}/about/</loc>", (self.out / "sitemap.xml").read_text(encoding="utf-8"))
        self.assertIn(f"({build.SITE_URL}/about/)", (self.out / "llms.txt").read_text(encoding="utf-8"))


class BritishSpellingTests(unittest.TestCase):
    """Page text uses British spelling; `organizer` survives only as a data field name."""

    def test_templates_say_organiser(self):
        for path in sorted((ROOT / "templates").glob("*.html")):
            # Template code names the data field; only the text around it is read by visitors.
            text = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", path.read_text(encoding="utf-8"))
            self.assertNotRegex(text, r"(?i)organiz", path.name)


# Values the stylesheet may use. The spec's token table explains them; this is the copy
# that is enforced, because the spec is never uploaded and a test cannot read it.
COLOUR_TOKENS = {
    "#1C1C1C", "#EBEBEB", "#FFFFFF", "#141414", "#5C5C5C", "#A8A8A8", "#E0E0E0", "#333333",
    "#165E83", "#8CC4E0", "#FFF4D6", "#5E4700", "#3A300F", "#F3D98B", "#FBE9E5", "#8E2A1B",
    "#3A1C16", "#F2A493",
}
FONT_SIZES = {"32px", "24px", "20px", "16px"}
SPACING = {"4px", "8px", "16px", "24px", "32px", "48px"}
# 16:9, the one ratio a video box is held at. Geometry, not spacing, so it is not a token.
VIDEO_RATIO = "56.25%"
RADII = {"8px"}
# An 8px radius turns the outline round a short link into a pill.
FOCUS_RADII = {"4px"}
KEYWORDS = {"0", "auto", "inherit", "transparent", "currentcolor"}
COLOUR_PROPS = re.compile(r"^(color|background(-color)?|border(-(top|right|bottom|left))?-color|outline-color|fill)$")
SPACING_PROPS = re.compile(r"^(margin|padding)(-(top|right|bottom|left))?$|^gap$")


def token_violations(css: str) -> list[str]:
    found = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for hexval in re.findall(r"#[0-9A-Fa-f]{3,6}\b", css):
        if hexval.upper() not in COLOUR_TOKENS:
            found.append(f"colour {hexval}")
    # Inner rules only: [^{}] cannot cross into an @media block's own braces.
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            prop, value = (s.strip() for s in decl.split(":", 1))
            words = value.lower().split()
            if COLOUR_PROPS.match(prop):
                bad = [w for w in words if w not in KEYWORDS and not w.startswith("#")]
            elif prop == "font-size":
                bad = [w for w in words if w not in FONT_SIZES | KEYWORDS]
            elif SPACING_PROPS.match(prop):
                allowed = SPACING | {VIDEO_RATIO} if selector.strip() == ".video-frame" else SPACING
                bad = [w for w in words if w not in allowed | KEYWORDS]
            elif prop == "border-radius":
                allowed = RADII | FOCUS_RADII if ":focus" in selector else RADII
                bad = [w for w in words if w not in allowed | KEYWORDS]
            else:
                continue
            found += [f"{selector.strip()} {{ {prop}: {w} }}" for w in bad]
    return found


class StylesheetTokenTests(unittest.TestCase):
    """Every colour, size and space in the stylesheet comes from the documented set."""

    def test_the_stylesheet_uses_only_token_values(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertEqual(token_violations(css), [])

    def test_the_check_catches_an_off_scale_value(self):
        # A zero from a check that cannot fire proves nothing, so show it firing.
        css = ("a { margin: 13px 8px; color: #123456; font-size: 15px; border-radius: 4px; }\n"
               "a:focus-visible { border-radius: 4px; }\n"
               "b { padding: 0 auto; color: currentColor; background: #fff4d6; }")
        self.assertEqual(token_violations(css), [
            "colour #123456",
            "a { margin: 13px }", "a { font-size: 15px }", "a { border-radius: 4px }",
        ])


class EntryListProvisionalTests(unittest.TestCase):
    """An entry list published before the event only warns while we have not re-checked."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"
        write_event(self.data, "meet")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edition_page(self, verified: str) -> str:
        write_instance(self.data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                                     extra=CARS, verified=verified))
        out = self.tmp / "site"
        shutil.rmtree(out, ignore_errors=True)
        build.build(self.data, out)
        return (out / "events/meet/2026/index.html").read_text(encoding="utf-8")

    def test_list_is_provisional_while_the_event_is_still_ahead_of_our_last_check(self):
        html = self.edition_page("2026-09-20")
        self.assertIn("Entry list as of 2026-09-15.", html)
        self.assertIn("cars may withdraw or change", html)

    def test_list_is_still_provisional_when_we_only_checked_on_the_closing_day(self):
        # Cars can withdraw during the event, so a same-day check does not settle the list.
        self.assertIn("cars may withdraw or change", self.edition_page("2026-10-18"))

    def test_list_is_settled_once_we_have_checked_after_the_event_ended(self):
        html = self.edition_page("2026-10-19")
        self.assertIn("Entry list as of 2026-09-15.", html)
        self.assertNotIn("cars may withdraw or change", html)


class RouteTests(unittest.TestCase):
    """A route is structured data, so a skimmer can find a time and a place."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
        build.build(self.data, self.tmp / "site")
        self.html = (self.tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_the_json_feed_repeats_the_route_the_page_tabulates(self):
        feed = json.loads((self.tmp / "site/api/events.json").read_text(encoding="utf-8"))
        route = feed["events"][0]["route"]
        self.assertEqual([day["date"] for day in route], ["2026-10-18", "2026-10-19"])
        self.assertEqual(route[0]["checkpoints"][1],
                         {"start_time": "11:00", "place_en": "Test Harbour", "prefecture": "Shizuoka"})

    def test_a_route_alone_earns_the_edition_its_own_page(self):
        self.assertIn("<h1>Test Event 2026</h1>", self.html)

    def test_one_table_per_day(self):
        self.assertEqual(self.html.count("<table>"), 2)

    def test_days_are_headed_by_date_and_weekday(self):
        self.assertIn("Day 1", self.html)
        self.assertIn("Sunday 18 October", self.html)
        self.assertIn("Day 2", self.html)
        self.assertIn("Monday 19 October", self.html)

    def test_a_checkpoint_shows_its_window_place_and_prefecture(self):
        self.assertIn("09:00\u201309:30", self.html)
        self.assertIn("Test Park, Testville", self.html)
        self.assertIn('lang="ja">\u30c6\u30b9\u30c8\u516c\u5712', self.html)

    def test_an_open_ended_window_shows_only_its_start(self):
        # The organizer leaves some checkpoints open, e.g. "16:40~".
        self.assertIn(">11:00</td>", self.html)


class RouteChartTests(unittest.TestCase):
    """The day-shape diagram: geometry is computed, not drawn, so it cannot contradict the table."""

    def setUp(self):
        self.chart = build.route_chart([
            {"date": dt.date(2026, 10, 18), "checkpoints": [
                {"start_time": "09:00", "end_time": "09:30"},
                {"start_time": "11:00"}]},
            {"date": dt.date(2026, 10, 19), "checkpoints": [
                {"start_time": "08:00", "end_time": "08:45"}]},
        ])

    def test_no_route_means_no_chart(self):
        self.assertIsNone(build.route_chart(None))
        self.assertIsNone(build.route_chart([]))

    def test_axis_runs_from_the_hour_below_to_the_hour_above(self):
        # Earliest 08:00, latest 11:00, so the axis must extend past the last bar.
        self.assertEqual((self.chart["start"], self.chart["end"]), ("08:00", "12:00"))

    def test_a_bar_is_placed_and_sized_by_its_window(self):
        bar = self.chart["days"][0]["bars"][0]
        self.assertEqual((bar["left"], bar["width"]), (25.0, 12.5))

    def test_an_open_ended_stop_keeps_a_visible_minimum_width(self):
        bar = self.chart["days"][0]["bars"][1]
        self.assertEqual(bar["left"], 75.0)
        self.assertEqual(bar["width"], build.CHART_MIN_BAR)

    def test_no_bar_can_run_past_the_axis(self):
        for day in self.chart["days"]:
            for bar in day["bars"]:
                self.assertLessEqual(bar["left"] + bar["width"], 100.0)

    def test_each_day_carries_its_span_and_count_as_text(self):
        self.assertEqual(self.chart["days"][0]["summary"], "09:00 to 11:00, 2 stops")
        self.assertEqual(self.chart["days"][1]["summary"], "08:00 to 08:45, 1 stop")

    def test_each_day_is_named_and_dated(self):
        self.assertEqual(self.chart["days"][0]["when"], "Day 1, Sun 18 Oct")


class RouteChartRenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
        build.build(data, self.tmp / "site")
        self.html = (self.tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_one_chart_row_per_day(self):
        self.assertEqual(self.html.count('class="chart-track"'), 2)

    def test_the_summary_is_real_text_not_only_a_bar(self):
        self.assertIn("Day 1, Sun 18 Oct: 09:00 to 11:00, 2 stops", self.html)

    def test_the_bars_are_hidden_from_screen_readers_as_a_restatement(self):
        self.assertIn('class="chart-track" aria-hidden="true"', self.html)

    def test_the_axis_ends_are_labelled(self):
        self.assertIn(">08:00<", self.html)
        self.assertIn(">12:00<", self.html)


VIDEOS = (
    "videos:\n"
    "  - youtube_id: t3UUnZ7g5P0\n"
    "    label_en: Day 1\n"
    "  - youtube_id: fIJCC_4IcE0\n"
    "    label_en: Day 2\n"
)


class VideoTests(unittest.TestCase):
    """A past edition embeds its videos; later editions link back to the latest of them."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2024, instance_yaml("meet", 2024, "2024-10-18", "2024-10-18",
                                                              extra=VIDEOS.replace("t3UUnZ7g5P0", "AAAAAAAAAAA")))
        write_instance(self.data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-18", "2025-10-18",
                                                              extra=VIDEOS))
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-19",
                                                              extra=ROUTE))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def page(self, stem) -> str:
        build.build(self.data, self.tmp / "site")
        return (self.tmp / f"site/events/meet/{stem}/index.html").read_text(encoding="utf-8")

    def test_videos_alone_earn_the_edition_its_own_page(self):
        self.assertIn("<h1>Test Event 2025</h1>", self.page(2025))

    def test_every_embed_uses_the_no_cookie_domain(self):
        srcs = re.findall(r'<iframe[^>]*\ssrc="([^"]+)"', self.page(2025))
        self.assertEqual(srcs, ["https://www.youtube-nocookie.com/embed/t3UUnZ7g5P0",
                                "https://www.youtube-nocookie.com/embed/fIJCC_4IcE0"])

    def test_every_embed_is_titled_and_lazy(self):
        frames = re.findall(r"<iframe[^>]*>", self.page(2025))
        self.assertEqual(len(frames), 2)
        self.assertIn('title="Test Event 2025, Day 1"', frames[0])
        for frame in frames:
            self.assertIn('loading="lazy"', frame)

    def test_each_video_links_to_youtube_by_its_label(self):
        self.assertIn('<a href="https://www.youtube.com/watch?v=fIJCC_4IcE0">Day 2 on YouTube</a>',
                      self.page(2025))

    def test_a_later_edition_links_to_the_latest_earlier_videos(self):
        self.assertIn('<a href="../../../events/meet/2025/#videos">Videos of the 2025 edition</a>',
                      self.page(2026))

    def test_an_edition_with_videos_links_to_the_one_before(self):
        self.assertIn("Videos of the 2024 edition", self.page(2025))
        self.assertNotIn("Videos of the", self.page(2024))

    def test_the_event_page_names_videos_among_the_edition_contents(self):
        build.build(self.data, self.tmp / "site")
        html = (self.tmp / "site/events/meet/index.html").read_text(encoding="utf-8")
        self.assertIn('href="../../events/meet/2025/">Videos</a>', html)

    def test_the_json_feed_carries_the_videos(self):
        build.build(self.data, self.tmp / "site")
        feed = json.loads((self.tmp / "site/api/events.json").read_text(encoding="utf-8"))
        by_year = {e["year"]: e for e in feed["events"]}
        self.assertEqual(by_year[2025]["videos"][1], {"youtube_id": "fIJCC_4IcE0", "label_en": "Day 2"})
        self.assertNotIn("videos", by_year[2026])

    def test_a_full_url_in_place_of_the_id_is_rejected(self):
        write_instance(self.data, "meet", 2025, instance_yaml(
            "meet", 2025, "2025-10-18", "2025-10-18",
            extra=VIDEOS.replace("t3UUnZ7g5P0", "https://www.youtube.com/watch?v=t3UUnZ7g5P0")))
        with self.assertRaises(build.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn("videos item 1: youtube_id", str(ctx.exception))

    def test_a_video_without_a_label_is_rejected(self):
        write_instance(self.data, "meet", 2025, instance_yaml(
            "meet", 2025, "2025-10-18", "2025-10-18", extra=VIDEOS.replace("    label_en: Day 1\n", "")))
        with self.assertRaises(build.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn("videos item 1: missing required field 'label_en'", str(ctx.exception))


class ProseLengthTests(unittest.TestCase):
    """Long prose hides its own facts, so the build refuses it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build_with_summary(self, words: int):
        write_event(self.data, "meet", extra=f"summary_en: {' word' * words}\n".replace("  ", " "))
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def test_prose_at_the_cap_is_accepted(self):
        self.build_with_summary(build.PROSE_MAX_WORDS)

    def test_prose_over_the_cap_is_rejected(self):
        with self.assertRaises(build.ValidationError) as ctx:
            self.build_with_summary(build.PROSE_MAX_WORDS + 1)
        self.assertIn("summary_en", str(ctx.exception))

    def test_the_message_offers_more_than_one_way_out(self):
        with self.assertRaises(build.ValidationError) as ctx:
            self.build_with_summary(build.PROSE_MAX_WORDS + 1)
        message = str(ctx.exception)
        for way in ("bullet", "table", "diagram"):
            self.assertIn(way, message.lower(), f"the fix hint should mention {way}s")


class CombinedProseTests(unittest.TestCase):
    """Fields that land in one block on the page are capped on what the reader sees."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build_with(self, **fields):
        extra = "".join(f"{k}: {' '.join(['word'] * n)}\n" for k, n in fields.items())
        write_event(self.data, "meet", extra=extra)
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def refusal(self, **fields) -> str:
        with self.assertRaises(build.ValidationError) as ctx:
            self.build_with(**fields)
        return str(ctx.exception)

    def test_nearest_station_is_prose_and_capped_on_its_own(self):
        # It reads as a sentence and sits in the same block as access_notes_en.
        self.assertIn("nearest_station", self.refusal(nearest_station=build.PROSE_MAX_WORDS + 1))

    def test_two_legal_fields_that_share_a_block_can_still_be_too_long_together(self):
        half = build.PROSE_MAX_WORDS // 2 + 1
        message = self.refusal(nearest_station=half, access_notes_en=half)
        self.assertIn("nearest_station", message)
        self.assertIn("access_notes_en", message)
        self.assertIn("one block", message)

    def test_the_combined_cap_is_the_same_number(self):
        half = build.PROSE_MAX_WORDS // 2
        self.build_with(nearest_station=half, access_notes_en=build.PROSE_MAX_WORDS - half)

    def test_one_field_alone_is_untouched_by_the_combined_rule(self):
        self.build_with(access_notes_en=build.PROSE_MAX_WORDS)


class EditorialProseTests(unittest.TestCase):
    """The pages are a reference, not a recommendation, so advice fails the build."""

    # The clause that shipped on la-festa-autunno and prompted the rule.
    SHIPPED = ("About two weeks beforehand the organizer publishes a timetable giving an "
               "arrival window for every checkpoint, which is the practical way to plan a "
               "day around it.")
    CUT = ("About two weeks beforehand the organizer publishes a timetable giving an "
           "arrival window for every checkpoint.")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build_with_prose(self, text: str, field="summary_en"):
        write_event(self.data, "meet", extra=f"{field}: {json.dumps(text)}\n")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def refusal(self, text: str, field="summary_en") -> str:
        with self.assertRaises(build.ValidationError) as ctx:
            self.build_with_prose(text, field)
        return str(ctx.exception)

    def test_the_clause_that_shipped_is_rejected(self):
        message = self.refusal(self.SHIPPED)
        self.assertIn("summary_en", message)
        self.assertIn("the practical way to", message)

    def test_the_same_sentence_without_the_clause_is_accepted(self):
        # The gate has to fault the advice, not the sentence carrying it.
        self.build_with_prose(self.CUT)

    def test_the_message_says_what_to_do_about_it(self):
        message = self.refusal(self.SHIPPED).lower()
        self.assertIn("cut", message)
        self.assertIn("fact", message)

    def test_every_listed_phrase_is_actually_caught(self):
        # An absence check proves nothing until the pattern is shown to produce a positive.
        for phrase in build.EDITORIAL_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.refusal(f"The meeting is {phrase} something."))

    def test_a_curly_apostrophe_is_caught_like_a_straight_one(self):
        self.assertIn("don't miss", self.refusal("The swap meet, and don\u2019t miss the time trial."))

    def test_a_phrase_broken_over_a_folded_line_is_still_caught(self):
        self.assertIn("worth a look", self.refusal("The paddock is worth\n  a look."))

    def test_editions_are_held_to_the_same_rule(self):
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-18",
            extra=f"route_en: {json.dumps(self.SHIPPED)}\n"))
        with self.assertRaises(build.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn("route_en", str(ctx.exception))

    def test_facts_that_merely_look_like_advice_are_left_alone(self):
        for text in (
            "Cars must be built before 1968 and replicas are not accepted.",
            "A Mustang and two Jaguars ran in 2025.",
            "The best-preserved of the three is the 1927 car.",
            "Entry is free for spectators and the car park is free with it.",
        ):
            with self.subTest(text=text):
                self.build_with_prose(text)


class ProseLinkTests(unittest.TestCase):
    """Prose may carry [text](https://...) links: anchors on the page, plain text elsewhere."""

    LINKED = "It fills a car park inside [Fuji Speedway](https://en.fujispeedway.jp/) on the day."

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build_with_prose(self, text: str, field="summary_en") -> str:
        write_event(self.data, "meet", extra=f"{field}: {json.dumps(text)}\n")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")
        return (self.tmp / "site" / "events" / "meet" / "index.html").read_text(encoding="utf-8")

    def refusal(self, text: str) -> str:
        with self.assertRaises(build.ValidationError) as ctx:
            self.build_with_prose(text)
        return str(ctx.exception)

    def test_a_link_renders_as_an_anchor(self):
        html = self.build_with_prose(self.LINKED)
        self.assertIn('inside <a href="https://en.fujispeedway.jp/">Fuji Speedway</a> on the day', html)
        self.assertNotIn("](", html)

    def test_every_prose_field_on_the_event_page_renders_links(self):
        for field in ("summary_en", "nearest_station", "access_notes_en",
                      "spectator_notes_en", "photography_notes_en"):
            with self.subTest(field=field):
                html = self.build_with_prose(self.LINKED, field)
                self.assertIn('<a href="https://en.fujispeedway.jp/">Fuji Speedway</a>', html)
                shutil.rmtree(self.data)

    def test_route_en_renders_links(self):
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-18", extra=f"route_en: {json.dumps(self.LINKED)}\n"))
        build.build(self.data, self.tmp / "site")
        html = (self.tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<a href="https://en.fujispeedway.jp/">Fuji Speedway</a>', html)
        api = json.loads((self.tmp / "site" / "api" / "events.json").read_text(encoding="utf-8"))
        self.assertEqual(api["events"][0]["route_en"],
                         "It fills a car park inside Fuji Speedway on the day.")

    def test_the_rest_of_the_prose_is_still_escaped(self):
        html = self.build_with_prose('Bring <b>cash</b> & see [A & B](https://example.com/?a=1&b="2").')
        self.assertIn("Bring &lt;b&gt;cash&lt;/b&gt; &amp; see", html)
        self.assertIn('<a href="https://example.com/?a=1&amp;b=&#34;2&#34;">A &amp; B</a>', html)

    def test_jsonld_gets_the_link_text_only(self):
        html = self.build_with_prose(self.LINKED)
        block, = jsonld_blocks(html)
        self.assertEqual(block["description"], "It fills a car park inside Fuji Speedway on the day.")

    def test_urls_do_not_count_towards_the_word_cap(self):
        words = " ".join(["word"] * (build.PROSE_MAX_WORDS - 2))
        self.build_with_prose(f"{words} [Fuji Speedway](https://en.fujispeedway.jp/a-very/long/path)")

    def test_advice_inside_link_text_is_still_caught(self):
        self.assertIn("worth a look", self.refusal("The [museum is worth a look](https://example.com/)."))

    def test_a_plain_http_link_is_rejected(self):
        message = self.refusal("See [the circuit](http://example.com/).")
        self.assertIn("summary_en", message)
        self.assertIn("https://", message)

    def test_a_javascript_link_is_rejected(self):
        self.assertIn("summary_en", self.refusal("See [the circuit](javascript:alert(1))."))

    def test_a_malformed_link_is_rejected(self):
        for text in ("See [the circuit] (https://example.com/).",
                     "See [the circuit](https://example.com/.",
                     "See the circuit](https://example.com/)."):
            with self.subTest(text=text):
                self.assertIn("summary_en", self.refusal(text))

    def test_an_html_link_is_rejected_with_the_markdown_form_named(self):
        message = self.refusal('See <a href="https://example.com/">the circuit</a>.')
        self.assertIn("[text](https://", message)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"
        write_event(self.data, "meet")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def assert_build_fails(self, expected: str):
        with self.assertRaises(build.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn(expected, str(ctx.exception))

    def assert_rejected(self, instance_text: str, expected: str, stem="2026"):
        write_instance(self.data, "meet", stem, instance_text)
        self.assert_build_fails(expected)

    def test_valid_instance_builds(self):
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def test_repo_sample_data_builds(self):
        build.build(ROOT / "data", self.tmp / "sample-site")

    def test_a_fee_that_is_neither_a_number_nor_null_is_rejected(self):
        write_event(self.data, "meet", fee='"free"')
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("spectator_fee_jpy")

    def test_a_negative_fee_is_rejected(self):
        write_event(self.data, "meet", fee=-500)
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("spectator_fee_jpy")

    def test_unquoted_time_is_rejected_with_the_fix(self):
        self.assert_rejected(
            instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                          extra='start_time: 10:30\nend_time: "16:00"\n'),
            '"10:30"')

    def test_bare_no_key_is_rejected(self):
        extra = "list_as_of: 2026-09-15\ncars:\n  - no: 12\n    year: 1929\n    make: Bentley\n    model: Blower\n"
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra), "entry_no")

    def test_numeric_entry_no_is_rejected(self):
        extra = 'list_as_of: 2026-09-15\ncars:\n  - entry_no: 12\n    year: 1929\n    make: Bentley\n    model: Blower\n'
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "entry_no: must be non-empty text")

    def test_personal_fields_are_rejected(self):
        extra = ('list_as_of: 2026-09-15\ncars:\n  - entry_no: "12"\n    year: 1929\n'
                 '    make: Bentley\n    model: Blower\n    driver: Somebody\n')
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "unknown field 'driver'")

    def test_end_before_start_is_rejected(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-17"), "is before start")

    def test_quoted_date_is_rejected(self):
        self.assert_rejected(instance_yaml("meet", 2026, '"2026-10-18"', "2026-10-18"), "unquoted date")

    def test_times_must_come_in_pairs(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra='start_time: "08:00"\n'),
                             "together")

    def test_entry_numbers_must_be_given_for_every_car_or_none(self):
        extra = ('list_as_of: 2026-09-15\ncars:\n  - entry_no: "12"\n    make: Bentley\n    model: Blower\n'
                 '  - make: Alfa Romeo\n    model: 6C 1750 GS\n')
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "entry_no on every car or on none")

    def test_years_must_be_given_for_every_car_or_none(self):
        extra = ('list_as_of: 2026-09-15\ncars:\n  - year: 1929\n    make: Bentley\n    model: Blower\n'
                 '  - make: Alfa Romeo\n    model: 6C 1750 GS\n')
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "year on every car or on none")

    def test_a_car_still_needs_a_make_and_a_model(self):
        extra = "list_as_of: 2026-09-15\ncars:\n  - make: Bentley\n"
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "missing required field 'model'")

    def test_cars_need_list_as_of(self):
        extra = 'cars:\n  - entry_no: "12"\n    year: 1929\n    make: Bentley\n    model: Blower\n'
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "cars and list_as_of")

    def test_slug_must_match_folder(self):
        self.assert_rejected(instance_yaml("other", 2026, "2026-10-18", "2026-10-18"), "must match the folder")

    def test_unsafe_event_file_name_is_rejected(self):
        write_event(self.data, "tom & jerry")
        self.assert_build_fails("lowercase letters, digits and single hyphens")

    def test_unsafe_folder_name_is_rejected(self):
        write_instance(self.data, "Meet 2", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("lowercase letters, digits and single hyphens")

    def test_edition_file_names_must_start_with_the_year(self):
        for stem in ("spring-2026", "2026_spring", "2026-Spring", "26-spring"):
            with self.subTest(stem=stem):
                shutil.rmtree(self.data / "events" / "meet", ignore_errors=True)
                self.assert_rejected(instance_yaml("meet", 2026, "2026-04-12", "2026-04-12"),
                                     "file name must be the year", stem=stem)

    def test_edition_year_must_match_file_name(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-04-12", "2026-04-12"),
                             "must match the file name", stem="2027-spring")


class DecadeStripTests(unittest.TestCase):
    """The entry list's shape, drawn from the same rows the table renders."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                                     extra=cars_yaml([1929, 1959, 1955, 1955])))
        build.build(data, self.tmp / "site")
        self.html = (self.tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def rows(self) -> list[str]:
        return re.findall(r'<span class="chart-when">(.*?)</span>', self.html)

    def test_one_row_per_decade_from_the_oldest_car_to_the_newest(self):
        self.assertEqual(self.rows(), ["1920s: 1 car", "1930s: none", "1940s: none", "1950s: 3 cars"])

    def test_the_busiest_decade_fills_the_track(self):
        self.assertIn("width: 100.0%", self.html)

    def test_an_empty_decade_keeps_its_place_but_draws_no_bar(self):
        empty = re.search(r'1930s: none</span>\s*<span class="chart-track"[^>]*>\s*</span>', self.html)
        self.assertIsNotNone(empty, "an empty decade should hold its row and draw nothing")

    def test_the_bars_are_hidden_from_screen_readers_as_a_restatement(self):
        self.assertEqual(self.html.count('<span class="chart-track" aria-hidden="true">'), 4)

    def test_an_edition_without_an_entry_list_has_no_strip(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            data = tmp / "data"
            write_event(data, "meet")
            write_instance(data, "meet", 2026,
                           instance_yaml("meet", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
            build.build(data, tmp / "site")
            html = (tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("chart decades", html)
        finally:
            shutil.rmtree(tmp)


class LatinOnlyNameTests(unittest.TestCase):
    """Plenty of Japanese car events are named only in Latin script, so name_ja is optional.

    An empty line in its place would print the name twice and tag Latin text lang="ja",
    which tells a screen reader to read it with Japanese pronunciation rules.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / "data"
        write_event(data, "latin-fes", name_en="Latin Fes", name_ja=None)
        write_instance(data, "latin-fes", 2026,
                       instance_yaml("latin-fes", 2026, "2026-11-22", "2026-11-22", extra=ROUTE_ONE_DAY))
        build.build(data, self.tmp / "site")
        out = self.tmp / "site"
        self.event_html = (out / "events" / "latin-fes" / "index.html").read_text(encoding="utf-8")
        self.edition_html = (out / "events" / "latin-fes" / "2026" / "index.html").read_text(encoding="utf-8")
        self.home_html = (out / "index.html").read_text(encoding="utf-8")
        self.ics = unfold((out / build.FEED_FILE).read_bytes().decode("utf-8"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_no_page_carries_an_empty_japanese_line(self):
        for name, html in (("event", self.event_html), ("edition", self.edition_html),
                           ("home", self.home_html)):
            with self.subTest(page=name):
                self.assertNotRegex(html, r'lang="ja"[^>]*>\s*<')

    def test_the_name_is_not_printed_twice_in_the_body(self):
        main = re.search(r"<main.*?</main>", self.event_html, re.S).group(0)
        self.assertEqual(main.count("Latin Fes"), 1, main)

    def test_the_calendar_description_does_not_open_with_a_blank_line(self):
        line = next(l for l in self.ics if l.startswith("DESCRIPTION:"))
        self.assertTrue(line.startswith("DESCRIPTION:https://"), line)

    def test_a_japanese_name_is_still_shown_when_there_is_one(self):
        self.assertIn('lang="ja">テストイベント', self.pages_with_ja())

    def pages_with_ja(self) -> str:
        tmp = Path(tempfile.mkdtemp())
        try:
            data = tmp / "data"
            write_event(data, "meet")
            write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-11-22", "2026-11-22"))
            build.build(data, tmp / "site")
            return (tmp / "site" / "events" / "meet" / "index.html").read_text(encoding="utf-8")
        finally:
            shutil.rmtree(tmp)


class UnannouncedFeeTests(unittest.TestCase):
    """An admission the organizer has not published yet is absent, not zero.

    Writing 0 would tell a visitor the day is free and a guess would be worse, so the
    field takes null and every surface says only that the number is not known.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / "data"
        write_event(data, "fee-pending", name_en="Fee Pending", fee=None)
        write_instance(data, "fee-pending", 2026,
                       instance_yaml("fee-pending", 2026, "2026-11-03", "2026-11-03"))
        build.build(data, self.tmp / "site")
        self.out = self.tmp / "site"
        self.event_html = (self.out / "events/fee-pending/index.html").read_text(encoding="utf-8")
        self.home_html = (self.out / "index.html").read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_the_pages_say_the_admission_is_unannounced_rather_than_free(self):
        for name, html in (("event", self.event_html), ("home", self.home_html)):
            with self.subTest(page=name):
                self.assertIn("Admission not announced", html)
                self.assertNotIn("Free to watch", html)

    def test_the_json_feed_leaves_the_fee_out_rather_than_calling_it_zero(self):
        feed = json.loads((self.out / "api/events.json").read_text(encoding="utf-8"))
        self.assertNotIn("spectator_fee_jpy", feed["events"][0])

    def test_the_structured_data_claims_neither_free_nor_paid(self):
        block = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',
                                     self.event_html, re.S).group(1))
        self.assertNotIn("isAccessibleForFree", block)


class DisplayListTests(unittest.TestCase):
    """A show that names the models it will have on the floor, not the cars that will fill them.

    There are no entry numbers to give, and a model's production span is not the age of the
    car standing on the stand, so neither column can be filled without inventing the contents.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                                     extra=display_cars_yaml([("Toyota", "2000GT"), ("Honda", "S500")])))
        build.build(data, self.tmp / "site")
        self.html = (self.tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
        self.event_html = (self.tmp / "site" / "events" / "meet" / "index.html").read_text(encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def headers(self) -> list[str]:
        return re.findall(r'<th scope="col">(.*?)</th>', self.html)

    def test_columns_nothing_can_fill_are_dropped_rather_than_left_blank(self):
        self.assertEqual(self.headers(), ["Make", "Model"])

    def test_the_rows_still_render(self):
        self.assertIn("<td>Toyota</td><td>2000GT</td>", self.html)

    def test_it_is_not_called_an_entry_list(self):
        self.assertIn("<h2>Cars on display</h2>", self.html)
        self.assertNotIn("Entry list", self.html)

    def test_the_as_of_line_names_what_the_list_is(self):
        self.assertIn("Cars on display as of 2026-09-15.", self.html)

    def test_a_list_that_can_still_change_says_so_without_calling_them_entrants(self):
        self.assertIn("Provisional: the line-up may change.", self.html)
        self.assertNotIn("withdraw", self.html)

    def test_the_link_to_it_is_labelled_for_what_it_holds(self):
        self.assertIn("Cars on display", self.event_html)
        self.assertNotIn("Entry list", self.event_html)

    def test_no_decade_strip_without_years_to_count(self):
        self.assertNotIn("chart decades", self.html)


class CoordinateTests(unittest.TestCase):
    """A pin is data like any other: checked, or absent. Never approximated."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build_with(self, event_extra="", edition_extra=""):
        write_event(self.data, "meet", extra=event_extra)
        write_instance(self.data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=edition_extra))
        build.build(self.data, self.tmp / "site")

    def refusal(self, **kwargs) -> str:
        with self.assertRaises(build.ValidationError) as ctx:
            self.build_with(**kwargs)
        return str(ctx.exception)

    def page(self, rel: str) -> str:
        return (self.tmp / "site" / rel).read_text(encoding="utf-8")

    def test_an_event_with_no_coordinates_builds_and_says_nothing(self):
        self.build_with()
        self.assertNotIn("maps.apple.com", self.page("events/meet/index.html"))

    def test_a_lone_latitude_is_refused(self):
        message = self.refusal(event_extra="lat: 34.9756\n")
        self.assertIn("lat", message)
        self.assertIn("lon", message)

    def test_a_lone_longitude_is_refused(self):
        self.assertIn("lon", self.refusal(event_extra="lon: 138.3828\n"))

    def test_a_swapped_pair_falls_outside_japan_and_is_refused(self):
        self.assertIn("Japan", self.refusal(event_extra="lat: 138.3828\nlon: 34.9756\n"))

    def test_text_where_a_number_belongs_is_refused(self):
        self.assertIn("lat", self.refusal(event_extra='lat: "34.9756"\nlon: 138.3828\n'))

    def test_a_whole_number_is_still_a_coordinate(self):
        self.build_with(event_extra="lat: 35\nlon: 139\n")
        self.assertIn("ll=35,139", self.page("events/meet/index.html"))

    def test_an_edition_that_names_its_own_venue_does_not_inherit_the_pin(self):
        # The coordinates were recorded at the event's venue, not at this one.
        self.build_with(event_extra="lat: 34.9756\nlon: 138.3828\n",
                        edition_extra="venue_en: Another Field\n" + CARS)
        self.assertIn("maps.apple.com", self.page("events/meet/index.html"))
        self.assertNotIn("maps.apple.com", self.page("events/meet/2026/index.html"))

    def test_an_edition_can_carry_its_own_pin(self):
        self.build_with(event_extra="lat: 34.9756\nlon: 138.3828\n",
                        edition_extra="venue_en: Another Field\nlat: 35.1\nlon: 138.9\n" + CARS)
        html = self.page("events/meet/2026/index.html")
        self.assertIn("ll=35.1,138.9", html)
        self.assertIn("q=Another%20Field", html)


class OutputFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"
        write_event(self.data, "meet")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_refuses_to_delete_a_folder_that_is_not_a_build(self):
        precious = self.tmp / "precious"
        precious.mkdir()
        (precious / "notes.txt").write_text("keep me", encoding="utf-8")
        with self.assertRaises(build.BuildError):
            build.build(self.data, precious)
        self.assertEqual((precious / "notes.txt").read_text(encoding="utf-8"), "keep me")

    def test_rebuilds_over_a_build_that_used_an_older_feed_name(self):
        out = self.tmp / "site"
        out.mkdir()
        (out / "index.html").write_text("old", encoding="utf-8")
        (out / "events.ics").write_text("old", encoding="utf-8")
        build.build(self.data, out)
        self.assertFalse((out / "events.ics").exists())

    def test_rebuilds_over_a_previous_build(self):
        out = self.tmp / "site"
        build.build(self.data, out)
        (out / "stale.html").write_text("old", encoding="utf-8")
        build.build(self.data, out)
        self.assertFalse((out / "stale.html").exists())


if __name__ == "__main__":
    unittest.main()
