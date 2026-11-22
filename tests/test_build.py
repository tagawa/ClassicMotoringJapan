"""The built site as a whole: every page and file, the 404 and about pages, the deploy
workflow, site copy, analytics events, the footer and the output folder.

Run every test file: .venv/bin/python -B -m unittest discover -s tests -v
Shared helpers are in helpers.py.
"""

import json
import re
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin

import yaml

from helpers import (CARS, instance_yaml, jsonld_blocks, make_fixture, ROOT, unfold, write_event,
                     write_instance)
import build  # noqa: E402
import settings  # noqa: E402
import validate  # noqa: E402


class BuildOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        make_fixture(cls.data)
        build.build(cls.data, cls.out)
        cls.ics_raw = (cls.out / settings.FEED_FILE).read_bytes().decode("utf-8")
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

    # Structured data (offline proxy for the Rich Results Test)

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

    def test_offer_carries_the_fee_in_yen(self):
        found = self.jsonld_by_name()
        self.assertEqual(found["Autumn Rally, Shizuoka 2026"][0][1]["offers"],
                         {"@type": "Offer", "price": 0, "priceCurrency": "JPY"})
        self.assertEqual(found["Test Event 2026"][0][1]["offers"],
                         {"@type": "Offer", "price": 1500, "priceCurrency": "JPY"})

    def test_home_page_alone_names_the_site(self):
        # Google reads the site name in its results from WebSite data on the home page.
        self.assertEqual(jsonld_blocks(self.pages["index.html"]),
                         [{"@context": "https://schema.org", "@type": "WebSite",
                           "name": "Classic Motoring Japan", "url": "https://classicmotoringjapan.com/"}])
        for page, html in self.pages.items():
            if page != "index.html":
                self.assertNotIn("WebSite", [b["@type"] for b in jsonld_blocks(html)], page)

    # Calendar feed (offline proxy for the phone subscription)

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
        self.assertIn("DTEND:20261018T070000Z", self.ics)
        self.assertFalse(any(line.startswith("BEGIN:VTIMEZONE") for line in self.ics))

    def test_ics_timed_edition_over_several_days_repeats_its_hours_daily(self):
        # The times are each day's hours: one 32-hour block would claim the rally runs overnight.
        self.assertIn("RRULE:FREQ=DAILY;COUNT=2", self.ics)
        self.assertNotIn("DTEND:20261019T070000Z", self.ics)

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

    def header_logos(self) -> list[str]:
        found = [re.search(r'<a class="brand".*?</a>', html, re.S).group(0)
                 for html in self.pages.values()]
        self.assertTrue(found)
        return [link[link.index("<svg"):link.index("</svg>")] for link in found]

    def test_the_header_logo_is_named_for_screen_readers(self):
        for svg in self.header_logos():
            self.assertIn('role="img"', svg)
            self.assertIn('aria-label="Classic Motoring Japan"', svg)

    def test_the_header_logo_takes_its_colours_from_the_stylesheet(self):
        # The swoosh gets a lighter red in dark mode and the wordmark follows the ink.
        for svg in self.header_logos():
            self.assertNotIn("#", svg, "a baked-in colour would ignore dark mode")
            self.assertIn('class="roof"', svg)
            self.assertIn('fill="currentColor"', svg)

    def test_the_header_logo_carries_no_background_or_metadata(self):
        for svg in self.header_logos():
            self.assertNotIn("<rect", svg)
            self.assertNotIn("<metadata", svg)

    def test_the_header_logo_is_sized_in_the_markup_so_it_survives_a_missing_stylesheet(self):
        for svg in self.header_logos():
            self.assertRegex(svg, r'<svg[^>]* width="\d+" height="\d+"')

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
        self.assertIn('<span class="dot" aria-hidden="true"></span><span data-last-day="2026-11-03">Confirmed</span>', html)

    def test_cancelled_is_a_cross_so_its_shape_differs_from_the_confirmed_dot(self):
        # Both are red, so shape is what tells them apart, even in greyscale.
        html = self.pages["events/culture-day-show/index.html"]
        self.assertNotIn("dot cancelled", html)
        svg = re.search(r'<svg class="cross"[^>]*>.*?</svg>(?=Cancelled)', html, re.S).group(0)
        for attr in ('aria-hidden="true"', 'focusable="false"', 'stroke="currentColor"',
                     'width="8"', 'height="8"'):
            self.assertIn(attr, svg)
        self.assertNotIn("#", svg, "a baked-in colour would ignore dark mode")

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

    # Every row carries its end date for the browser script (tests/test_browser.py has the other half)

    def test_home_rows_carry_end_dates_in_date_order(self):
        ends = re.findall(r'<li data-end="(\d{4}-\d{2}-\d{2})"', self.pages["index.html"])
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

    def test_home_title_is_fixed_text(self):
        self.assertIn("<title>Classic car events in Japan | Classic Motoring Japan</title>",
                      self.pages["index.html"])

    # Crawler and browser files

    def test_llms_txt_links_every_sitemap_page(self):
        # So a new kind of page cannot reach the sitemap and miss the index. The root is the
        # site llms.txt itself describes, so it is the one page not linked from it.
        llms = self.out_text("llms.txt")
        urls = re.findall(r"<loc>([^<]+)</loc>", self.out_text("sitemap.xml"))
        self.assertGreater(len(urls), 5)
        for url in urls:
            if url != f"{settings.SITE_URL}/":
                self.assertIn(f"({url})", llms)

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
        self.assertIn('<h2 id="cars">Entry list</h2>', html)
        self.assertNotIn("Entry list as of", html, "the heading already says what the list is")
        self.assertIn("<p>As of 2026-09-15.", html)
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
            self.assertRegex(html, r"(Last verified</dt>\s*<dd>|Most recent check: )2026-09-20", page)

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

    def test_robots_txt_states_the_same_preferences_in_the_ietf_vocabulary(self):
        # draft-ietf-aipref-attach's Content-Usage rule, in the same group as Content-Signal.
        group = self.out_text("robots.txt").split("\n\n", 1)[0].splitlines()
        self.assertIn("Content-Usage: search=y, ai-use=y, train-ai=n", group)

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
            rel = e["url"].removeprefix(settings.SITE_URL + "/") + "index.html"
            self.assertIn(rel, self.pages, e["id"])

    def test_llms_txt_links_every_event_page_and_both_feeds(self):
        llms = self.out_text("llms.txt")
        linked = [page for page in self.pages if page.startswith("events/")]
        self.assertGreaterEqual(len(linked), 4)
        for page in linked:
            self.assertIn(f"{settings.SITE_URL}/{page.removesuffix('index.html')})", llms, page)
        self.assertIn(f"{settings.SITE_URL}/api/events.json", llms)
        self.assertIn(f"{settings.SITE_URL}/{settings.FEED_FILE}", llms)

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
        self.assertIn(f"Agentmap: {settings.SITE_URL}/.well-known/ard.json",
                      self.out_text("robots.txt"))

    def test_every_page_advertises_the_manifest_under_both_relations(self):
        want = {"ard": ".well-known/ard.json", "ai-catalog": ".well-known/ai-catalog.json"}
        for page, html in self.pages.items():
            for rel, target in want.items():
                found = re.search(rf'<link rel="{rel}" href="([^"]*)"', html)
                self.assertIsNotNone(found, f"{page}: no rel={rel} link")
                self.assertEqual(urljoin(f"{settings.SITE_URL}/{page}", found.group(1)),
                                 f"{settings.SITE_URL}/{target}", page)

    def test_ard_manifest_matches_the_published_catalog_schema(self):
        catalog = self.out_json(".well-known/ai-catalog.json")
        self.assertEqual(set(catalog), {"specVersion", "host", "entries"})
        self.assertEqual(catalog["specVersion"], "1.0")
        self.assertEqual(catalog["host"]["displayName"], settings.SITE_NAME)
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
                         [f"{settings.SITE_URL}/api/events.json", f"{settings.SITE_URL}/{settings.FEED_FILE}"])
        for entry in linkset:
            self.assertEqual(entry["service-doc"][0]["type"], "text/html")

    def test_api_catalog_service_doc_is_a_page_that_links_the_feed(self):
        # service-doc is the feed's documentation: a page that never mentions it is not that.
        for entry in self.out_json(".well-known/api-catalog")["linkset"]:
            href = entry["service-doc"][0]["href"]
            page = href.removeprefix(settings.SITE_URL + "/") + "index.html"
            links = [urljoin(href, h) for h in re.findall(r'<a href="([^"]*)"', self.pages[page])]
            self.assertIn(entry["anchor"], links, href)

    def test_every_url_the_catalogs_advertise_is_a_file_the_build_wrote(self):
        linkset = self.out_json(".well-known/api-catalog")["linkset"]
        urls = [e["url"] for e in self.out_json(".well-known/ai-catalog.json")["entries"]]
        urls += [e["anchor"] for e in linkset]
        urls += [link["href"] for e in linkset for link in e["service-doc"]]
        self.assertEqual(len(urls), 7, "an advertised link that was never collected proves nothing")
        for url in urls:
            rel = url.removeprefix(settings.SITE_URL + "/")
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

    def test_links_to_the_sites_own_youtube_channel(self):
        self.assertIn('href="https://www.youtube.com/@ClassicMotoringJapan"', self.html)

    def test_every_page_links_to_it(self):
        pages = [p for p in self.out.rglob("*.html") if p.name != "404.html"]
        self.assertGreater(len(pages), 4)
        for p in pages:
            rel = p.relative_to(self.out).as_posix()
            hrefs = re.findall(r'href="([^"]*about/)"', p.read_text(encoding="utf-8"))
            self.assertIn(f"{settings.SITE_URL}/about/",
                          [urljoin(f"{settings.SITE_URL}/{rel}", h) for h in hrefs], rel)

    def test_the_404_page_links_to_it_from_the_root(self):
        self.assertIn('href="/about/"', (self.out / "404.html").read_text(encoding="utf-8"))

    def test_is_listed_in_the_sitemap_and_llms_txt(self):
        self.assertIn(f"<loc>{settings.SITE_URL}/about/</loc>", (self.out / "sitemap.xml").read_text(encoding="utf-8"))
        self.assertIn(f"({settings.SITE_URL}/about/)", (self.out / "llms.txt").read_text(encoding="utf-8"))


class SiteCopyTests(unittest.TestCase):
    """Fixed wording that states facts, not advice, and keeps visitors' pages free of machine furniture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        write_instance(cls.tmp / "data", "hill-climb", "2027-spring",
                       instance_yaml("hill-climb", 2027, "2027-04-11", "2027-04-11", status="tentative",
                                     extra=CARS))
        build.build(cls.tmp / "data", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def html(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def test_a_tentative_edition_says_so_without_advising(self):
        html = self.html("events/hill-climb/2027-spring/index.html")
        self.assertIn('<a href="https://example.com/hill-climb/2027/">example.com</a> '
                      "does not confirm these dates yet.", html)
        self.assertNotIn("booking", html)

    def test_the_lede_stands_alone_as_a_description(self):
        # It is also the search snippet, the share text and the llms.txt summary, where no
        # heading sits above it to say what the site covers.
        for phrase in ("classic cars", "Japan", "Japanese and imported"):
            self.assertIn(phrase, settings.SITE_LEDE)

    def test_the_about_page_says_both_japanese_and_imported_cars(self):
        # "Classic" alone does not tell an imported-car reader the site covers their cars.
        self.assertIn("Japanese and imported", self.html("about/index.html"))

    def test_the_about_page_does_not_list_the_language_model_index(self):
        self.assertNotIn("llms.txt", self.html("about/index.html"))

    def test_google_calendar_steps_are_folded_away(self):
        self.assertRegex(self.html("index.html"),
                         r"(?s)<details[^>]*>\s*<summary>Google Calendar</summary>.*Other calendars.*</details>")

    def test_the_404_page_does_not_guess_why(self):
        self.assertNotIn("typo", self.html("404.html"))


class FathomEventTests(unittest.TestCase):
    """Fathom counts only what the page reports, and an event's name can never be changed:
    a renamed one starts a new count. So the names are pinned here, and each sits on the
    element whose use it counts."""

    NAMES = {"Calendar file downloaded", "Google Calendar form opened",
             "Calendar feed subscribe clicked", "Google Calendar feed help opened"}

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        make_fixture(cls.tmp / "data")
        out = cls.tmp / "site"
        build.build(cls.tmp / "data", out)
        cls.pages = {str(p.relative_to(out)): p.read_text(encoding="utf-8") for p in out.rglob("*.html")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def counted(self, html: str) -> list[tuple[str, str]]:
        """Each counted element's opening tag, with the event it reports."""
        return [(tag, name) for tag, name in re.findall(r'(<(?:a|details)\b[^>]*data-fathom="([^"]+)"[^>]*>)', html)]

    def test_no_name_but_the_pinned_ones_is_reported(self):
        found = {name for html in self.pages.values() for _, name in self.counted(html)}
        self.assertEqual(found, self.NAMES)

    def test_each_name_is_on_the_element_it_counts(self):
        html = self.pages["events/autumn-rally/2026/index.html"]
        expected = {
            "Calendar file downloaded": r'<a href="[^"]+\.ics"',
            "Google Calendar form opened": r'<a href="https://calendar\.google\.com/',
            "Calendar feed subscribe clicked": r'<a href="webcal://',
            "Google Calendar feed help opened": r"<details\b",
        }
        for tag, name in self.counted(html):
            self.assertRegex(tag, expected[name], name)
        self.assertEqual({name for _, name in self.counted(html)}, self.NAMES)

    def test_the_footer_counts_on_every_page(self):
        for rel, html in self.pages.items():
            names = {name for _, name in self.counted(html)}
            self.assertIn("Calendar feed subscribe clicked", names, rel)
            self.assertIn("Google Calendar feed help opened", names, rel)

    def test_every_page_reports_them_and_survives_fathom_being_blocked(self):
        for rel, html in self.pages.items():
            self.assertIn('querySelectorAll("[data-fathom]")', html, rel)
            self.assertIn("if (window.fathom) window.fathom.trackEvent(", html, rel)

    def test_the_help_counts_when_opened_not_when_closed(self):
        script = self.pages["index.html"]
        self.assertIn('addEventListener("toggle", function (e) { if (e.target.open) report(e.target); })', script)


class SiteFooterLinkTests(unittest.TestCase):
    """The channel and the way to report an error, on every page and not only on About."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        make_fixture(cls.tmp / "data")
        out = cls.tmp / "site"
        build.build(cls.tmp / "data", out)
        cls.pages = {str(p.relative_to(out)): p.read_text(encoding="utf-8") for p in out.rglob("*.html")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_every_footer_links_the_channel_the_issues_and_about(self):
        for rel, html in self.pages.items():
            footer = html[html.index('<footer class="site-footer"'):]
            links = re.search(r'(?s)<p class="site-links">(.*?)</p>', footer)
            self.assertIsNotNone(links, rel)
            self.assertEqual([text for _, text in re.findall(r'<a href="([^"]+)">([^<]+)</a>', links.group(1))],
                             ["YouTube channel", "Report an error on GitHub", "About this site"], rel)
            self.assertIn(f'<a href="{settings.YOUTUBE_CHANNEL_URL}">', links.group(1))
            self.assertIn(f'<a href="{settings.ISSUES_URL}">', links.group(1))


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
        with self.assertRaises(validate.BuildError):
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
