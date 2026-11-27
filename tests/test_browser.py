"""Past events move under "Past" on page load, judged by Japan's date.

Needs Playwright with Chromium. Skipped when Playwright isn't installed, which is
the normal case here and on GitHub (see the README's local checks).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import instance_yaml, temp_dir, write_event, write_instance  # noqa: E402
import build  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class PastEventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "past-meet", name_en="Past Meet")
        write_instance(data, "past-meet", 2026, instance_yaml("past-meet", 2026, "2026-10-19", "2026-10-19"))
        write_event(data, "next-meet", name_en="Next Meet")
        write_instance(data, "next-meet", 2026, instance_yaml("next-meet", 2026, "2026-11-01", "2026-11-01"))
        build.build(data, cls.tmp / "site")
        cls.home = (cls.tmp / "site" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def sections_at(self, utc_instant: str) -> dict:
        ctx = self.browser.new_context(timezone_id="Europe/London")
        page = ctx.new_page()
        page.clock.set_fixed_time(utc_instant)
        page.goto(self.home)
        result = {
            "upcoming": page.locator("#upcoming-list a").all_inner_texts(),
            # textContent: Past is folded, and a closed details renders none of its text.
            "past": page.locator("#past-list a").all_text_contents(),
            "past_summary": page.locator("#past-show").text_content(),
            "past_visible": page.locator("#past").is_visible(),
            "heading": page.locator("#upcoming-h").inner_text(),
        }
        ctx.close()
        return result

    def test_moves_to_past_once_the_day_has_ended_in_japan(self):
        # 16:30 on 19 Oct in London is already 00:30 on 20 Oct in Japan.
        s = self.sections_at("2026-10-19T15:30:00Z")
        self.assertEqual(s["past"], ["Past Meet"])
        self.assertEqual(s["upcoming"], ["Next Meet"])
        self.assertTrue(s["past_visible"])
        self.assertEqual(s["past_summary"], "Show 1 event")

    def test_the_sorted_list_is_headed_upcoming(self):
        # The markup says Events, for a reader whose browser never runs the script.
        self.assertEqual(self.sections_at("2026-10-19T15:30:00Z")["heading"], "Upcoming")

    def test_stays_upcoming_until_midnight_in_japan(self):
        # 23:00 on 19 Oct in Japan: the event day is not over yet.
        s = self.sections_at("2026-10-19T14:00:00Z")
        self.assertEqual(s["upcoming"], ["Past Meet", "Next Meet"])
        self.assertEqual(s["past"], [])
        self.assertFalse(s["past_visible"])


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class MonthSplitTest(unittest.TestCase):
    """A month heading follows its dates: into Past, out of Upcoming, or into both."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        for slug, day in (("early", "2026-10-04"), ("late", "2026-10-25"), ("next", "2026-11-01")):
            write_event(data, slug, name_en=slug.capitalize())
            write_instance(data, slug, 2026, instance_yaml(slug, 2026, day, day))
        build.build(data, cls.tmp / "site")
        cls.home = (cls.tmp / "site" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def headings_at(self, utc_instant: str) -> dict:
        ctx = self.browser.new_context(timezone_id="Europe/London")
        page = ctx.new_page()
        page.clock.set_fixed_time(utc_instant)
        page.goto(self.home)
        result = {where: page.locator(f"#{where}-list h3").all_text_contents() for where in ("upcoming", "past")}
        result["past_events"] = page.locator("#past-list a").all_text_contents()
        ctx.close()
        return result

    def test_a_month_with_dates_on_both_sides_of_today_is_headed_in_both(self):
        s = self.headings_at("2026-10-10T03:00:00Z")
        self.assertEqual(s["upcoming"], ["October 2026", "November 2026"])
        self.assertEqual(s["past"], ["October 2026"])

    def test_a_month_left_with_no_dates_loses_its_upcoming_heading(self):
        s = self.headings_at("2026-10-28T03:00:00Z")
        self.assertEqual(s["upcoming"], ["November 2026"])
        self.assertEqual(s["past"], ["October 2026"])

    def test_past_runs_newest_first_by_month_and_by_date(self):
        s = self.headings_at("2026-11-02T03:00:00Z")
        self.assertEqual(s["past"], ["November 2026", "October 2026"])
        self.assertEqual(s["past_events"], ["Next", "Late", "Early"])


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class WeekendAndTodayTest(unittest.TestCase):
    """The badge and the strip's Today mark, both judged by Japan's date."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        # 2026-10-17 is a Saturday.
        for slug, start, end in (("friday", "2026-10-16", "2026-10-16"), ("sunday", "2026-10-18", "2026-10-18"),
                                 ("across", "2026-10-16", "2026-10-17"), ("monday", "2026-10-19", "2026-10-19"),
                                 ("later", "2026-10-25", "2026-10-25")):
            write_event(data, slug, name_en=slug.capitalize())
            write_instance(data, slug, 2026, instance_yaml(slug, 2026, start, end))
        build.build(data, cls.tmp / "site")
        cls.home = (cls.tmp / "site" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def at(self, utc_instant: str) -> dict:
        ctx = self.browser.new_context(timezone_id="Europe/London")
        page = ctx.new_page()
        page.clock.set_fixed_time(utc_instant)
        page.goto(self.home)
        result = {
            "badged": page.locator("#upcoming-list li[data-end]:has(.weekend) a").all_text_contents(),
            "today": page.locator("#years .chart-today").evaluate_all("els => els.map(el => el.style.left)"),
            "greyed": page.locator("#years i.past").count(),
        }
        ctx.close()
        return result

    def test_on_a_weekday_the_coming_weekend_is_badged(self):
        # Wednesday 14 Oct in Japan.
        self.assertEqual(self.at("2026-10-14T03:00:00Z")["badged"], ["Across", "Sunday"])

    def test_on_a_sunday_it_is_the_weekend_in_progress(self):
        # Sunday 18 Oct, 09:00 in Japan: Saturday's events have gone to Past, Sunday's stay badged.
        self.assertEqual(self.at("2026-10-18T00:00:00Z")["badged"], ["Sunday"])

    def test_on_a_monday_it_moves_on_to_the_next_one(self):
        self.assertEqual(self.at("2026-10-19T03:00:00Z")["badged"], ["Later"])

    def test_today_is_marked_where_the_build_would_put_that_date(self):
        # 17 Oct is day 290 of 365: 289 days in, as the bars are placed.
        self.assertEqual(self.at("2026-10-17T03:00:00Z")["today"], ["79.18%"])

    def test_bars_whose_last_day_has_passed_are_greyed(self):
        self.assertEqual(self.at("2026-10-17T15:30:00Z")["greyed"], 2)


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class CalendarLinksTest(unittest.TestCase):
    """Add to calendar is offered until the edition's last day has ended in Japan."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-19", "2026-10-19"))
        build.build(data, cls.tmp / "site")
        cls.page = (cls.tmp / "site" / "events" / "meet" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def links_at(self, utc_instant: str) -> int:
        ctx = self.browser.new_context(timezone_id="Europe/London")
        page = ctx.new_page()
        page.clock.set_fixed_time(utc_instant)
        page.goto(self.page)
        count = page.locator(".calendar-links a").count()
        ctx.close()
        return count

    def test_offered_until_midnight_in_japan(self):
        self.assertEqual(self.links_at("2026-10-19T14:00:00Z"), 2)

    def test_gone_once_the_day_has_ended_in_japan(self):
        self.assertEqual(self.links_at("2026-10-19T15:30:00Z"), 0)


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class YearStripTest(unittest.TestCase):
    """The strip shows this year and the ones ahead. Past years are the list's job, not its."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "meet")
        for year in (2025, 2026, 2027):
            write_instance(data, "meet", year,
                           instance_yaml("meet", year, f"{year}-05-10", f"{year}-05-10"))
        build.build(data, cls.tmp / "site")
        cls.home = (cls.tmp / "site" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def strip_at(self, utc_instant: str) -> dict:
        ctx = self.browser.new_context(timezone_id="Europe/London")
        page = ctx.new_page()
        page.clock.set_fixed_time(utc_instant)
        page.goto(self.home)
        result = {
            "years": page.locator("#years li[data-year]:visible").evaluate_all(
                "els => els.map(el => el.dataset.year)"),
            "strip_visible": page.locator("#years").is_visible(),
        }
        ctx.close()
        return result

    def test_a_past_year_drops_off_but_this_one_stays_all_year(self):
        # 1 Dec 2026: 2026 is still current even though its only event is long gone.
        s = self.strip_at("2026-12-01T03:00:00Z")
        self.assertEqual(s["years"], ["2026", "2027"])

    def test_the_new_year_moves_the_line_on_japan_time(self):
        # 16:30 on 31 Dec in London is already 01:30 on 1 Jan in Japan.
        s = self.strip_at("2026-12-31T15:30:00Z")
        self.assertEqual(s["years"], ["2027"])

    def test_a_strip_with_nothing_left_to_show_goes_away(self):
        s = self.strip_at("2028-01-02T03:00:00Z")
        self.assertEqual(s["years"], [])
        self.assertFalse(s["strip_visible"])



@unittest.skipIf(sync_playwright is None, "playwright not installed")
class NextDateTest(unittest.TestCase):
    """A make page splits its events by whether a date is still to come in Japan (spec section 5)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        (data / "events").mkdir(parents=True)
        (data / "makes.yml").write_text("Nissan: JP\n", encoding="utf-8")
        later = {"bravo": [("2027", "2027-05-08", "2027-05-08", "confirmed")],
                 "charlie": [("2027", "2027-03-13", "2027-03-14", "confirmed")],
                 "echo": [("2027", "2027-02-01", "2027-02-01", "cancelled"),
                          ("2028", "2028-04-01", "2028-04-01", "confirmed")],
                 "foxtrot": [("2027", "2027-03-13", "2027-03-13", "confirmed")]}
        for slug in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot"):
            write_event(data, slug, name_en=slug.capitalize())
            day = "2026-03-14" if slug == "alpha" else "2026-05-10"
            write_instance(data, slug, 2026, instance_yaml(slug, 2026, day, day, extra=(
                f"list_as_of: {day[:8]}20\ncars:\n  - entry_no: \"1\"\n    make: Nissan\n    model: Skyline\n")))
            for stem, start, end, status in later.get(slug, []):
                write_instance(data, slug, stem, instance_yaml(slug, int(stem), start, end, status=status))
        build.build(data, cls.tmp / "site")
        cls.url = (cls.tmp / "site" / "cars" / "nissan" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def tables_at(self, utc_instant: str) -> dict:
        """Each heading's text and visibility, and each table's rows as (event, visible dates, cell count, last cell)."""
        ctx = self.browser.new_context(timezone_id="Europe/London")
        page = ctx.new_page()
        page.clock.set_fixed_time(utc_instant)
        page.goto(self.url)
        found = {}
        for key, box in (("next-dates", "dated-events"), ("no-date", "undated-events")):
            heading, wrap = page.locator(f"#{key}"), page.locator(f"#{box}")
            rows = [(tr.locator("a").first.inner_text(), tr.locator(".next-date:visible").all_inner_texts(),
                     tr.locator("th, td").count(), tr.locator("th, td").last.inner_text())
                    for tr in wrap.locator("tbody tr").all()]
            found[key] = (heading.inner_text() if heading.is_visible() else None, wrap.is_visible(), rows)
        ctx.close()
        return found

    def row(self, rows, name):
        return next(item for item in rows if item[0] == name)

    def test_first_table_holds_dated_events_soonest_first(self):
        heading, shown, rows = self.tables_at("2026-12-01T03:00:00Z")["next-dates"]
        self.assertEqual((heading, shown), ("Next dates", True))
        self.assertEqual([item[0] for item in rows], ["Charlie", "Foxtrot", "Bravo", "Echo"])

    def test_shows_first_date_not_ended(self):
        rows = self.tables_at("2026-12-01T03:00:00Z")["next-dates"][2]
        self.assertEqual(self.row(rows, "Bravo")[1:3], (["Sat 8 May 2027"], 3))
        self.assertEqual(self.row(rows, "Echo")[1:3], (["Sat 1 Apr 2028"], 3))

    def test_undated_events_move_to_second_table_a_to_z(self):
        heading, shown, rows = self.tables_at("2026-12-01T03:00:00Z")["no-date"]
        self.assertEqual((heading, shown), ("No date announced yet", True))
        # Their Next date cell is gone, matching the second table's two columns, and the latest list stays.
        self.assertEqual(rows, [("Alpha", [], 2, "1 in 2026"), ("Delta", [], 2, "1 in 2026")])

    def test_same_next_date_keeps_a_to_z(self):
        # Passes without the script too, since the build's order is A to Z: a guard on the final order.
        names = [item[0] for item in self.tables_at("2026-12-01T03:00:00Z")["next-dates"][2]]
        self.assertLess(names.index("Charlie"), names.index("Foxtrot"))

    def test_still_shown_on_last_day_in_japan(self):
        # 23:30 on 14 March in Japan: Charlie's second day is still running.
        rows = self.tables_at("2027-03-14T14:30:00Z")["next-dates"][2]
        self.assertEqual(self.row(rows, "Charlie")[1:3], (["Sat 13 to Sun 14 Mar 2027"], 3))

    def test_date_drops_once_ended_in_japan(self):
        # 00:30 on 15 March in Japan.
        tables = self.tables_at("2027-03-14T15:30:00Z")
        self.assertEqual([item[0] for item in tables["next-dates"][2]], ["Bravo", "Echo"])
        self.assertEqual([item[0] for item in tables["no-date"][2]], ["Alpha", "Charlie", "Delta", "Foxtrot"])

    def test_every_event_dated_leaves_second_table_hidden(self):
        # 1 March 2026: every event's 2026 date is still to come.
        tables = self.tables_at("2026-03-01T03:00:00Z")
        self.assertEqual(len(tables["next-dates"][2]), 6)
        self.assertEqual(tables["no-date"][:2], (None, False))

    def test_no_event_dated_hides_first_table(self):
        # After Echo's 2028 date, nothing is left to come.
        tables = self.tables_at("2028-05-01T03:00:00Z")
        self.assertEqual(tables["next-dates"][:2], (None, False))
        self.assertEqual(tables["no-date"][:2], ("No date announced yet", True))
        self.assertEqual(len(tables["no-date"][2]), 6)


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class CarsIndexWidthTest(unittest.TestCase):
    """The /cars/ table fits a 320px phone without sideways scrolling."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        # The real data, since its longest make names are what could overflow.
        build.build(Path(__file__).resolve().parent.parent / "data", cls.tmp / "site")
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def test_table_box_does_not_scroll_at_320px(self):
        page = self.browser.new_page(viewport={"width": 320, "height": 800})
        page.goto((self.tmp / "site" / "cars" / "index.html").as_uri())
        box = page.locator(".table-wrap").first
        rows = page.locator(".table-wrap tbody tr").count()
        scroll, client = box.evaluate("el => [el.scrollWidth, el.clientWidth]")
        page.close()
        self.assertGreater(rows, 50, "expected the real list of makes")
        self.assertLessEqual(scroll, client)


# Each status cell's word against its dot or cross: true where the word starts below the
# mark's bottom edge, which is a status split across two lines.
SPLIT_STATUSES = """() => {
  var cells = document.querySelectorAll('.dates-table .status'), split = [];
  for (var i = 0; i < cells.length; i++) {
    var mark = cells[i].firstElementChild, word = document.createRange();
    word.setStartAfter(mark);
    word.setEnd(cells[i], cells[i].childNodes.length);
    if (word.getBoundingClientRect().top >= mark.getBoundingClientRect().bottom) split.push(cells[i].textContent);
  }
  return split;
}"""

OVERFLOW = """() => {
  var wrap = document.querySelector('.dates-table').parentNode, root = document.documentElement;
  return [root.scrollWidth - root.clientWidth, wrap.scrollWidth - wrap.clientWidth];
}"""


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class DatesTableLayoutTest(unittest.TestCase):
    """Below 620px the event page's Dates table stacks each event; wider, it stays a table."""

    # SHCC's table, stacked at 390px with the status on the name's line. The sandbox measured
    # 887px with a stand-in font.
    HEIGHT_LIMIT = 950

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        # The real data: SHCC's long rows are what the layout was measured on.
        build.build(Path(__file__).resolve().parent.parent / "data", cls.tmp / "site")
        cls.shcc = (cls.tmp / "site" / "events" / "shcc" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, width: int, style: str = ""):
        page = self.browser.new_page(viewport={"width": width, "height": 800})
        page.goto(self.shcc)
        if style:
            page.add_style_tag(content=style)
        self.addCleanup(page.close)
        return page

    def test_no_status_splits_from_its_dot_on_a_phone(self):
        self.assertEqual(self.open(390).evaluate(SPLIT_STATUSES), [])

    def test_the_split_check_fires_on_a_wrapped_status(self):
        page = self.open(390, ".dates-table .status { display: block; width: 40px; white-space: normal; }")
        self.assertGreater(len(page.evaluate(SPLIT_STATUSES)), 0)

    def test_nothing_scrolls_sideways_on_a_phone(self):
        self.assertEqual(self.open(390).evaluate(OVERFLOW), [0, 0])

    def test_the_overflow_check_fires_on_a_wide_table(self):
        page = self.open(390, ".dates-table { width: 1000px; display: table; }")
        self.assertGreater(page.evaluate(OVERFLOW)[1], 0)

    def test_the_stacked_table_is_under_its_height_limit(self):
        height = self.open(390).evaluate("() => document.querySelector('.dates-table').getBoundingClientRect().height")
        self.assertLessEqual(height, self.HEIGHT_LIMIT)

    def test_each_status_sits_on_its_event_name_line_on_a_phone(self):
        tops = self.open(390).evaluate("""() => {
          var rows = document.querySelectorAll('.dates-table tbody tr:not(.calendar-links)'), tops = [];
          for (var i = 0; i < rows.length; i++) {
            tops.push([rows[i].querySelector('.edition').getBoundingClientRect().top,
                       rows[i].querySelector('.status').getBoundingClientRect().top]);
          }
          return tops;
        }""")
        self.assertGreater(len(tops), 5)
        for name, status in tops:
            self.assertLessEqual(abs(name - status), 4)

    def test_it_stays_a_table_on_a_wide_screen(self):
        shown = self.open(1280).evaluate(
            "() => Array.prototype.map.call(document.querySelectorAll('.dates-table td'),"
            " function (td) { return getComputedStyle(td).display; })")
        self.assertGreater(len(shown), 10)
        self.assertEqual(set(shown), {"table-cell"})


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class GreyWhenGoneTest(unittest.TestCase):
    """Once an event has run, its Held dot and its home-page map dot turn the muted colour."""

    BRAND = {"light": "rgb(140, 28, 36)", "dark": "rgb(208, 99, 106)"}
    MUTED = {"light": "rgb(92, 92, 92)", "dark": "rgb(168, 168, 168)"}

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "meet", name_en="Meet", extra="lat: 34.9756\nlon: 138.3828\n")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-19", "2026-10-19"))
        build.build(data, cls.tmp / "site")
        cls.site = cls.tmp / "site"
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def open(self, path: str, utc_instant: str, scheme: str):
        ctx = self.browser.new_context(timezone_id="Europe/London", color_scheme=scheme)
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        page.clock.set_fixed_time(utc_instant)
        page.goto((self.site / path).as_uri())
        return page

    def status(self, utc_instant: str, scheme: str) -> tuple:
        page = self.open("events/meet/index.html", utc_instant, scheme)
        return page.evaluate("""() => {
          var cell = document.querySelector('.dates-table .status');
          return [cell.className, getComputedStyle(cell.querySelector('.dot')).backgroundColor];
        }""")

    def test_a_held_dot_is_muted_and_a_coming_one_brand_red(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                # 00:30 on 20 Oct in Japan: the day has ended.
                self.assertEqual(self.status("2026-10-19T15:30:00Z", scheme), ["status held", self.MUTED[scheme]])
                self.assertEqual(self.status("2026-10-19T14:00:00Z", scheme), ["status", self.BRAND[scheme]])

    def test_a_past_map_dot_on_the_home_page_is_muted(self):
        for scheme in ("light", "dark"):
            with self.subTest(scheme=scheme):
                page = self.open("index.html", "2026-10-19T15:30:00Z", scheme)
                fill = page.evaluate("() => getComputedStyle(document.querySelector('#past-list .venue-map circle')).fill")
                self.assertEqual(fill, self.MUTED[scheme])
                page = self.open("index.html", "2026-10-19T14:00:00Z", scheme)
                fill = page.evaluate("() => getComputedStyle(document.querySelector('#upcoming-list .venue-map circle')).fill")
                self.assertEqual(fill, self.BRAND[scheme])


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class VideoPlayedTest(unittest.TestCase):
    """A click inside an embed never reaches the page, so the edition page counts the
    window losing focus to an embed's iframe: once per player per page load."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "meet")
        videos = ("videos:\n  - youtube_id: t3UUnZ7g5P0\n    label_en: Day 1\n"
                  "  - youtube_id: fIJCC_4IcE0\n    label_en: Day 2\n")
        write_instance(data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-18", "2025-10-18", extra=videos))
        build.build(data, cls.tmp / "site")
        cls.page = (cls.tmp / "site" / "events" / "meet" / "2025" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        ctx = self.browser.new_context()
        self.addCleanup(ctx.close)
        # No network: a blank player stands in for YouTube, and Fathom's own script never
        # loads, so the stub below is what the page reports to.
        ctx.route("**/*youtube-nocookie.com/**", lambda route: route.fulfill(body="<html><body></body></html>",
                                                                          content_type="text/html"))
        ctx.route("**/cdn.usefathom.com/**", lambda route: route.abort())
        ctx.add_init_script("window.sent = []; window.fathom = { trackEvent: function (n) { window.sent.push(n); } };")
        self.p = ctx.new_page()
        self.p.goto(self.page)

    def focus_player(self, index: int) -> list:
        self.p.locator(".video-frame iframe").nth(index).focus()
        self.p.wait_for_timeout(50)
        return self.p.evaluate("window.sent")

    def back_to_page(self):
        self.p.locator("h1").click()
        self.p.wait_for_timeout(50)

    def test_focusing_a_player_sends_video_played_once(self):
        self.assertEqual(self.focus_player(0), ["Video played"])

    def test_focusing_the_same_player_again_sends_nothing_more(self):
        self.focus_player(0)
        self.back_to_page()
        self.assertEqual(self.focus_player(0), ["Video played"])

    def test_each_player_counts_once(self):
        self.focus_player(0)
        self.back_to_page()
        self.assertEqual(self.focus_player(1), ["Video played", "Video played"])

    def test_nothing_is_sent_without_a_player_taking_focus(self):
        self.back_to_page()
        self.assertEqual(self.p.evaluate("window.sent"), [])


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class HeroFileChoiceTest(unittest.TestCase):
    """Spec 4.10: the file the browser picks, given the hero's srcset and sizes."""

    @classmethod
    def setUpClass(cls):
        from test_photos import OWN_PHOTO, write_photo
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "own", name_en="Own Meet", extra=OWN_PHOTO)
        write_photo(data, "own", size=(2000, 1000))
        build.build(data, cls.tmp / "site")
        cls.url = (cls.tmp / "site" / "events" / "own" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def chosen(self, width: int, scale: int) -> str:
        # A fresh context each time, so no file is already in the cache to sway the choice.
        ctx = self.browser.new_context(viewport={"width": width, "height": 844}, device_scale_factor=scale)
        page = ctx.new_page()
        page.goto(self.url)
        page.wait_for_function("document.querySelector('.hero img').complete")
        src = page.eval_on_selector(".hero img", "img => img.currentSrc")
        ctx.close()
        return src.rsplit("/", 1)[1]

    def test_each_screen_gets_the_smallest_webp_wide_enough(self):
        for width, scale, name in ((390, 3, "own-1080.webp"), (390, 2, "own-720.webp"),
                                   (1280, 1, "own-720.webp"), (1280, 2, "own-1440.webp")):
            with self.subTest(width=width, scale=scale):
                self.assertEqual(self.chosen(width, scale), name)


if __name__ == "__main__":
    unittest.main()
