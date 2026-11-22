"""The home page: its rows, dates, month groups and headings."""

import datetime as dt
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import CARS, instance_yaml, make_fixture, ROOT, ROUTE, write_event, write_instance
import build  # noqa: E402
import formatting  # noqa: E402


class HomeRowFactsTests(unittest.TestCase):
    """What a reader choosing between rows wants first: do the cars move, and how old are they."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        data = cls.tmp / "data"
        write_event(data, "tour", name_en="Tour", extra="cutoff_year: 1975\n")
        write_instance(data, "tour", 2026, instance_yaml("tour", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
        write_event(data, "parade", name_en="Parade")
        write_instance(data, "parade", 2026,
                       instance_yaml("parade", 2026, "2026-11-22", "2026-11-22",
                                     extra="route_en: From the town hall along the high street.\n"))
        write_event(data, "show", name_en="Show", extra="cutoff_year: 1988\n")
        write_instance(data, "show", 2025, instance_yaml("show", 2025, "2025-11-03", "2025-11-03"))
        write_instance(data, "show", 2026,
                       instance_yaml("show", 2026, "2026-11-03", "2026-11-03", extra="cutoff_year: 1996\n"))
        write_event(data, "meet", name_en="Meet")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-11-08", "2026-11-08"))
        build.build(data, cls.tmp / "site")
        html = (cls.tmp / "site" / "index.html").read_text(encoding="utf-8")
        cls.markup = {(name, when[:4]): meta for when, name, meta in re.findall(
            r'(?s)<li data-end="([^"]+)">.*?<a href="[^"]*">([^<]+)</a>.*?<p class="meta">(.*?)</p>', html)}
        # As a screen reader hears it: the glyphs say nothing, the hidden full stops do.
        cls.rows = {key: " ".join(re.sub(r"<[^>]+>", "", meta.replace("<br>", " ")).split())
                    for key, meta in cls.markup.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_every_edition_has_a_row(self):
        # The assertions below read rows by name, so a regex that found none would pass them all.
        self.assertEqual(len(self.rows), 5)

    def test_an_edition_with_a_timetabled_route_says_the_cars_are_driven(self):
        self.assertIn("Driven route.", self.rows["Tour", "2026"])

    def test_so_does_one_whose_route_is_only_described(self):
        self.assertIn("Driven route.", self.rows["Parade", "2026"])

    def test_an_edition_without_a_route_does_not(self):
        self.assertNotIn("Driven route", self.rows["Show", "2026"])
        self.assertNotIn("Driven route", self.rows["Meet", "2026"])

    def test_the_cutoff_year_follows_the_place_and_the_fee(self):
        self.assertEqual(self.rows["Tour", "2026"],
                         "\u30c6\u30b9\u30c8\u30a4\u30d9\u30f3\u30c8 Shizuoka. Free to watch. Driven route. Cars to 1975.")

    def test_an_event_with_no_cutoff_on_record_claims_none(self):
        self.assertNotIn("Cars to", self.rows["Meet", "2026"])
        self.assertNotIn("Cars to", self.rows["Parade", "2026"])

    def test_an_edition_can_give_its_own_cutoff_and_the_others_keep_the_events(self):
        self.assertIn("Cars to 1996.", self.rows["Show", "2026"])
        self.assertIn("Cars to 1988.", self.rows["Show", "2025"])

    def test_events_json_gives_the_cutoff_year_the_row_shows_and_none_where_it_shows_none(self):
        feed = json.loads((self.tmp / "site" / "api/events.json").read_text(encoding="utf-8"))
        cutoffs = {e["id"]: e.get("cutoff_year") for e in feed["events"]}
        self.assertEqual(cutoffs, {"tour-2026": 1975, "parade-2026": None, "show-2025": 1988,
                                   "show-2026": 1996, "meet-2026": None})

    def test_each_fact_opens_with_a_glyph_of_its_own(self):
        facts = re.findall(r'<span class="fact"><svg class="icon" [^>]*aria-hidden="true"[^>]*>(.*?)</svg>'
                           r'([^<]+)<span class="visually-hidden">\. </span></span>', self.markup["Tour", "2026"])
        self.assertEqual([text for _, text in facts], ["Shizuoka", "Free to watch", "Driven route", "Cars to 1975"])
        self.assertEqual(len({glyph for glyph, _ in facts}), 4)

    def test_the_place_has_the_map_links_pin(self):
        glyph = re.search(r'<span class="fact"><svg [^>]*>(.*?)</svg>Shizuoka', self.markup["Tour", "2026"])
        self.assertIsNotNone(glyph)
        self.assertIn("M12 21s7-7.4 7-12A7 7 0 0 0 5 9c0 4.6 7 12 7 12z", glyph.group(1))


class WeekdayDateTests(unittest.TestCase):
    """Dates a visitor plans a weekend by: the weekday first, the year only where it is needed."""

    def span(self, start: str, end: str, year: bool = False) -> str:
        return formatting.fmt_span(dt.date.fromisoformat(start), dt.date.fromisoformat(end), year)

    def test_one_day(self):
        self.assertEqual(self.span("2026-10-18", "2026-10-18"), "Sun 18 Oct")
        self.assertEqual(self.span("2026-10-18", "2026-10-18", year=True), "Sun 18 Oct 2026")

    def test_days_in_one_month_name_the_month_once(self):
        self.assertEqual(self.span("2026-10-24", "2026-10-25"), "Sat 24 to Sun 25 Oct")
        self.assertEqual(self.span("2026-10-02", "2026-10-05", year=True), "Fri 2 to Mon 5 Oct 2026")

    def test_days_across_two_months_name_both(self):
        self.assertEqual(self.span("2026-10-31", "2026-11-01"), "Sat 31 Oct to Sun 1 Nov")
        self.assertEqual(self.span("2026-10-31", "2026-11-01", year=True), "Sat 31 Oct to Sun 1 Nov 2026")

    def test_days_across_new_year_always_name_both_years(self):
        # Under a December heading, "Thu 31 Dec to Fri 1 Jan" would leave the second year to guesswork.
        self.assertEqual(self.span("2026-12-31", "2027-01-01"), "Thu 31 Dec 2026 to Fri 1 Jan 2027")


class DateLeafTests(unittest.TestCase):
    """The home list's calendar leaf: weekdays on the band, days beneath, the month left to the heading."""

    def leaf(self, start: str, end: str) -> tuple[str, str]:
        return formatting.fmt_leaf(dt.date.fromisoformat(start), dt.date.fromisoformat(end))

    def test_one_day(self):
        self.assertEqual(self.leaf("2026-10-18", "2026-10-18"), ("Sun", "18"))

    def test_days_in_one_month(self):
        self.assertEqual(self.leaf("2026-10-24", "2026-10-25"), ("Sat–Sun", "24–25"))
        self.assertEqual(self.leaf("2027-04-09", "2027-04-11"), ("Fri–Sun", "9–11"))

    def test_days_across_two_months_name_both(self):
        # "31–1" under a May heading would read as a typo.
        self.assertEqual(self.leaf("2025-05-31", "2025-06-01"), ("Sat–Sun", "31 May–1 Jun"))
        self.assertEqual(self.leaf("2026-12-31", "2027-01-01"), ("Thu–Fri", "31 Dec–1 Jan"))


class EditionWhenTests(unittest.TestCase):
    """The facts block's When row carries the weekdays too."""

    def page(self, start: str, end: str, extra: str = "") -> str:
        tmp = Path(tempfile.mkdtemp())
        try:
            data = tmp / "data"
            write_event(data, "meet")
            write_instance(data, "meet", 2026, instance_yaml("meet", 2026, start, end, extra=extra + CARS))
            build.build(data, tmp / "site")
            return (tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
        finally:
            shutil.rmtree(tmp)

    def test_an_all_day_edition(self):
        # The date opens the row; the add-to-calendar links follow it.
        self.assertIn("<dd>Sun 18 to Mon 19 Oct 2026<", self.page("2026-10-18", "2026-10-19"))

    def test_a_timed_one_day_edition(self):
        html = self.page("2026-10-18", "2026-10-18", extra='start_time: "08:00"\nend_time: "16:00"\n')
        self.assertIn("<dd>Sun 18 Oct 2026, 08:00 to 16:00 Japan time<", html)

    def test_a_timed_edition_over_several_days(self):
        html = self.page("2026-10-18", "2026-10-19", extra='start_time: "08:00"\nend_time: "16:00"\n')
        self.assertIn("<dd>Sun 18 to Mon 19 Oct 2026, 08:00 to 16:00 Japan time each day<", html)


class HomeMonthGroupTests(unittest.TestCase):
    """The home list reads like a calendar: a heading per month, each date once, its events beneath."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        data = cls.tmp / "data"
        for slug, start, end in (("alpha", "2026-10-18", "2026-10-18"), ("bravo", "2026-10-18", "2026-10-18"),
                                 ("charlie", "2026-10-18", "2026-10-19"), ("delta", "2026-10-24", "2026-10-25"),
                                 ("echo", "2026-11-03", "2026-11-03"), ("foxtrot", "2027-02-20", "2027-02-21")):
            write_event(data, slug, name_en=slug.capitalize(), extra="lat: 35.6812\nlon: 139.7671\n")
            write_instance(data, slug, int(start[:4]), instance_yaml(slug, int(start[:4]), start, end))
        build.build(data, cls.tmp / "site")
        html = (cls.tmp / "site" / "index.html").read_text(encoding="utf-8")
        cls.list = re.search(r'(?s)<div id="upcoming-list">.*?</section>', html).group(0)
        cls.days = re.findall(r'(?s)<li data-end="[^"]+">\s*<div class="day-when"><time datetime="[^"]+">'
                              r'<span class="visually-hidden">(.*?)</span>.*?</time></div>(.*?)</ul>\s*</li>',
                              cls.list)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_a_heading_per_month_in_date_order(self):
        self.assertEqual(re.findall(r"<h3>(.*?)</h3>", self.list), ["October 2026", "November 2026", "February 2027"])

    def test_each_month_is_marked_for_the_script_that_splits_past_from_upcoming(self):
        self.assertEqual(re.findall(r'<div class="month" data-month="([^"]+)">', self.list),
                         ["2026-10", "2026-11", "2027-02"])

    def test_each_date_appears_once_with_the_weekday_and_without_the_year(self):
        self.assertEqual([when for when, _ in self.days],
                         ["Sun 18 Oct", "Sun 18 to Mon 19 Oct", "Sat 24 to Sun 25 Oct", "Tue 3 Nov",
                          "Sat 20 to Sun 21 Feb"])

    def test_events_on_the_same_dates_share_one_entry(self):
        names = [re.findall(r'<a href="[^"]*">([^<]+)</a>', events) for _, events in self.days]
        self.assertEqual(names[0], ["Alpha", "Bravo"])
        # Same first day, a different last one: it moves to Past on another night, so it stands alone.
        self.assertEqual(names[1], ["Charlie"])

    def test_every_event_keeps_its_own_thumbnail(self):
        self.assertEqual(self.days[0][1].count('<svg class="venue-map"'), 2)

    def test_each_date_is_drawn_as_a_leaf_that_a_screen_reader_skips(self):
        # The hidden text above it already says the whole date, month included.
        self.assertEqual(re.findall(r'<span class="leaf" aria-hidden="true"><span class="leaf-day">([^<]+)</span>'
                                    r'<span class="leaf-date">([^<]+)</span></span></time>', self.list),
                         [("Sun", "18"), ("Sun–Mon", "18–19"), ("Sat–Sun", "24–25"),
                          ("Tue", "3"), ("Sat–Sun", "20–21")])

    def test_a_past_leaf_is_grey_like_a_past_bar(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"(?m)^#past-list \.leaf-day \{ background: #5C5C5C; \}")


class HomeHeadingTests(unittest.TestCase):
    """Without JavaScript nothing sorts the list, so its heading must not call it upcoming."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.tmp / "site")
        cls.html = (cls.tmp / "site" / "index.html").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_the_list_of_every_edition_is_headed_neutrally_in_the_markup(self):
        self.assertIn('<h2 id="upcoming-h">Events</h2>', self.html)

    def test_only_the_script_that_sorts_the_list_calls_it_upcoming(self):
        markup, script = self.html.split("<script>\n  (function () {", 1)
        self.assertNotIn("Upcoming", markup)
        self.assertIn('document.getElementById("upcoming-h").textContent = "Upcoming";', script)


class HomeTimeAwareTests(unittest.TestCase):
    """What the home page decides by today's date, which only the browser knows: the markup
    carries the dates, and tests/test_browser.py runs the script against them."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.tmp / "site")
        cls.html = (cls.tmp / "site" / "index.html").read_text(encoding="utf-8")
        cls.script = cls.html[cls.html.index("<script>\n  (function () {"):]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_past_events_fold_under_a_heading_and_a_summary_the_script_counts(self):
        # A real h2, so the past months' h3s are not taken for part of Upcoming (WCAG 1.3.1).
        self.assertRegex(self.html, r'<section id="past" aria-labelledby="past-h" hidden>\s*'
                                    r'<h2 id="past-h">Past events</h2>\s*<details>\s*'
                                    r'<summary id="past-show">Show past events</summary>\s*'
                                    r'<div id="past-list"></div>')
        self.assertIn('getElementById("past-show").textContent = "Show " + count + (count === 1 ? " event" : " events");',
                      self.script)

    def test_each_strip_bar_carries_its_last_day_so_the_past_can_be_greyed(self):
        self.assertRegex(self.html, r'<i data-end="2026-04-12" style="left: [\d.]+%')
        self.assertRegex(self.html, r'<i class="off" data-end="2027-11-03" style=')

    def test_the_script_marks_today_on_the_strip(self):
        self.assertIn('"chart-today"', self.script)
        self.assertIn('"chart-today-label"', self.script)

    def test_each_date_sits_in_a_box_that_can_take_a_badge(self):
        self.assertRegex(self.html, r'<div class="day-when"><time datetime="2026-10-18">'
                                    r'<span class="visually-hidden">Sun 18 to Mon 19 Oct</span><span class="leaf"')
        self.assertIn('"This weekend"', self.script)


if __name__ == "__main__":
    unittest.main()
