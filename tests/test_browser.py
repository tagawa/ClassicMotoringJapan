"""Past events move under "Past" on page load, judged by Japan's date.

Needs Playwright with Chromium. Skipped when Playwright isn't installed, which is
the normal case here and on GitHub (see the README's local checks).
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import build, instance_yaml, write_event, write_instance  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "playwright not installed")
class PastEventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
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
            shutil.rmtree(cls.tmp)
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.tmp)

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
        cls.tmp = Path(tempfile.mkdtemp())
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
            shutil.rmtree(cls.tmp)
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.tmp)

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
        cls.tmp = Path(tempfile.mkdtemp())
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
            shutil.rmtree(cls.tmp)
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.tmp)

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
        cls.tmp = Path(tempfile.mkdtemp())
        data = cls.tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-19", "2026-10-19"))
        build.build(data, cls.tmp / "site")
        cls.page = (cls.tmp / "site" / "events" / "meet" / "index.html").as_uri()
        try:
            cls.pw = sync_playwright().start()
            cls.browser = cls.pw.chromium.launch()
        except Exception as e:
            shutil.rmtree(cls.tmp)
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.tmp)

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
        cls.tmp = Path(tempfile.mkdtemp())
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
            shutil.rmtree(cls.tmp)
            raise unittest.SkipTest(f"chromium unavailable: {e}")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        shutil.rmtree(cls.tmp)

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


if __name__ == "__main__":
    unittest.main()
