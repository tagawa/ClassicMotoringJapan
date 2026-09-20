"""Tests for scripts/build.py. Run: .venv/bin/python -m unittest discover -s tests -v

Done checks 1 and 2 need a final manual pass (Google Rich Results Test, calendar subscription on a phone).
These tests cover everything that can be checked offline, so the manual pass should be a formality.
"""
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


def instance_yaml(slug: str, year: int, start: str, end: str, status="confirmed", extra="") -> str:
    return (
        f"slug: {slug}\n"
        f"year: {year}\n"
        f"status: {status}\n"
        f"start: {start}\n"
        f"end: {end}\n"
        f"source_url: https://example.com/{slug}/{year}/\n"
        f"last_verified: 2026-09-20\n"
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
RALLY_EXTRA = 'start_time: "08:00"\nend_time: "16:00"\nroute_en: Start Test Park 08:00, finish Test Harbour 16:00.\n' + CARS


def make_fixture(data: Path) -> None:
    write_event(data, "autumn-rally", name_en='"Autumn Rally, Shizuoka"',
                name_ja="オータム・クラシックカー・ラリー・イン・静岡・ヒストリック・ツーリング・ミーティング")
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
        cls.ics_raw = (cls.out / "events.ics").read_bytes().decode("utf-8")
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
            self.assertIn('href="webcal://classicmotoringjapan.com/events.ics"', html, page)
            self.assertIn("https://classicmotoringjapan.com/events.ics", html, page)

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

    def test_rebuilds_over_a_previous_build(self):
        out = self.tmp / "site"
        build.build(self.data, out)
        (out / "stale.html").write_text("old", encoding="utf-8")
        build.build(self.data, out)
        self.assertFalse((out / "stale.html").exists())


if __name__ == "__main__":
    unittest.main()
