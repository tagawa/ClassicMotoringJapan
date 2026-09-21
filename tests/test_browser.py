"""Done check 4: past events move under "Past" on page load, judged by Japan's date.

Needs Playwright with Chromium (see the README's one-time setup).
Skipped automatically when Playwright isn't installed.
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
            "past": page.locator("#past-list a").all_inner_texts(),
            "past_visible": page.locator("#past").is_visible(),
        }
        ctx.close()
        return result

    def test_moves_to_past_once_the_day_has_ended_in_japan(self):
        # 16:30 on 19 Oct in London is already 00:30 on 20 Oct in Japan.
        s = self.sections_at("2026-10-19T15:30:00Z")
        self.assertEqual(s["past"], ["Past Meet"])
        self.assertEqual(s["upcoming"], ["Next Meet"])
        self.assertTrue(s["past_visible"])

    def test_stays_upcoming_until_midnight_in_japan(self):
        # 23:00 on 19 Oct in Japan: the event day is not over yet.
        s = self.sections_at("2026-10-19T14:00:00Z")
        self.assertEqual(s["upcoming"], ["Past Meet", "Next Meet"])
        self.assertEqual(s["past"], [])
        self.assertFalse(s["past_visible"])


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
