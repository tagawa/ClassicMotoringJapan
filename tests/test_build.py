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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402


def write_event(data: Path, slug: str, name_en="Test Event", name_ja="テストイベント",
                fee=0, extra="") -> None:
    p = data / "events" / f"{slug}.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"slug: {slug}\n"
        f"name_en: {name_en}\n"
        f"name_ja: {name_ja}\n"
        f"official_url: https://example.com/{slug}/\n"
        f"prefecture: Shizuoka\n"
        f"venue_en: Test Park\n"
        f"spectator_fee_jpy: {fee}\n"
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
    write_event(data, "hill-climb", name_en="Hill Climb")
    write_instance(data, "hill-climb", "2026-spring",
                   instance_yaml("hill-climb", 2026, "2026-04-12", "2026-04-12"))
    write_instance(data, "hill-climb", "2026-autumn",
                   instance_yaml("hill-climb", 2026, "2026-10-25", "2026-10-25", extra=CARS))


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
        cls.pages = {p.relative_to(cls.out).as_posix(): p.read_text(encoding="utf-8")
                     for p in cls.out.rglob("*.html")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def jsonld_by_name(self) -> dict:
        found = {}
        for page, html in self.pages.items():
            for block in jsonld_blocks(html):
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
        self.assertIn("Entry list as of 2026-09-15.", html)
        self.assertIn("Provisional", html)
        self.assertIn(">037<", html)

    def test_every_page_shows_last_verified(self):
        for page, html in self.pages.items():
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
        self.assertEqual(self.html.count('class="daychart-track"'), 2)

    def test_the_summary_is_real_text_not_only_a_bar(self):
        self.assertIn("Day 1, Sun 18 Oct: 09:00 to 11:00, 2 stops", self.html)

    def test_the_bars_are_hidden_from_screen_readers_as_a_restatement(self):
        self.assertIn('class="daychart-track" aria-hidden="true"', self.html)

    def test_the_axis_ends_are_labelled(self):
        self.assertIn(">08:00<", self.html)
        self.assertIn(">12:00<", self.html)


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
