"""The .ics files and add-to-calendar links.

An offline proxy for a phone subscribed to the feed, so a manual pass with one should be a formality.
"""

import re
import unittest
from urllib.parse import urljoin

from helpers import CARS, instance_yaml, temp_dir, write_event, write_instance
import build  # noqa: E402
import settings  # noqa: E402


class AddToCalendarTests(unittest.TestCase):
    """One edition into a visitor's own calendar: a file for most apps, a link for Google's."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "meet", name_en="Meet")
        write_instance(data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-19", "2025-10-19", status="cancelled"))
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-19", extra=CARS))
        write_instance(data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-17", "2027-10-17", status="tentative"))
        write_event(data, "show", name_en="Show")
        write_instance(data, "show", 2026, instance_yaml("show", 2026, "2026-11-03", "2026-11-03",
                                                         extra='start_time: "09:00"\nend_time: "17:00"\n'))
        write_event(data, "fair", name_en="Fair")
        write_instance(data, "fair", 2026, instance_yaml("fair", 2026, "2026-11-07", "2026-11-08",
                                                         extra='start_time: "10:00"\nend_time: "17:00"\n'))
        cls.out = cls.tmp / "site"
        build.build(data, cls.out)


    def html(self, rel: str) -> str:
        # Bytes first: read_text would turn the calendar's CRLF line ends into LF.
        return (self.out / rel).read_bytes().decode("utf-8")

    def links(self, rel: str) -> dict:
        """Each add-to-calendar link on a page, by where it points."""
        hrefs = re.findall(r'<(span|tr) class="calendar-links" data-hide-after="[^"]+"[^>]*>(.*?)</\1>', self.html(rel), re.S)
        found = {"ics": [], "google": []}
        for _, block in hrefs:
            for href in re.findall(r'href="([^"]+)"', block):
                href = href.replace("&amp;", "&")
                if href.endswith(".ics"):
                    found["ics"].append(urljoin(f"{settings.SITE_URL}/{rel}", href))
                else:
                    found["google"].append(href)
        return found

    def google(self, url: str) -> dict:
        from urllib.parse import parse_qs, urlsplit
        parts = urlsplit(url)
        self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}", "https://calendar.google.com/calendar/render")
        return {k: v[0] for k, v in parse_qs(parts.query).items()}

    def vevents(self, ics: str) -> list[str]:
        return re.findall(r"BEGIN:VEVENT\r\n.*?END:VEVENT\r\n", ics, re.S)

    def test_a_confirmed_edition_gets_a_file_beside_its_event(self):
        self.assertTrue((self.out / "events/meet/2026.ics").is_file())
        self.assertTrue((self.out / "events/show/2026.ics").is_file(), "an edition without a page gets one too")

    def test_a_date_that_could_move_or_will_not_happen_gets_none(self):
        # A saved copy never updates, so a tentative date would sit there wrong once it moved.
        self.assertFalse((self.out / "events/meet/2027.ics").exists())
        self.assertFalse((self.out / "events/meet/2025.ics").exists())

    def test_the_file_holds_the_feeds_own_entry_for_that_edition(self):
        # Same UID, so an app that also subscribes to the feed sees one event, not two.
        single = self.vevents(self.html("events/meet/2026.ics"))
        self.assertEqual(len(single), 1)
        self.assertIn(single[0], self.vevents(self.html(settings.FEED_FILE)))
        self.assertIn("UID:meet-2026@classicmotoringjapan.com\r\n", single[0])

    def test_the_file_names_no_calendar_so_the_app_adds_to_one_the_visitor_has(self):
        ics = self.html("events/meet/2026.ics")
        self.assertNotIn("X-WR-CALNAME", ics)
        self.assertNotIn("\r\nNAME:", ics)

    def test_the_edition_page_links_its_file(self):
        self.assertEqual(self.links("events/meet/2026/index.html")["ics"],
                         [f"{settings.SITE_URL}/events/meet/2026.ics"])

    def test_the_event_page_links_only_the_confirmed_editions(self):
        self.assertEqual(self.links("events/meet/index.html")["ics"], [f"{settings.SITE_URL}/events/meet/2026.ics"])
        self.assertEqual(self.links("events/show/index.html")["ics"], [f"{settings.SITE_URL}/events/show/2026.ics"])

    def test_the_event_page_offers_them_in_a_row_under_their_edition(self):
        # From the Dates column to the edge, so a phone has the width, and no label, since the row above says which.
        html = self.html("events/meet/index.html")
        row = re.search(r'<tr class="calendar-links" data-hide-after="2026-10-19" role="row">\s*'
                        r'<td class="spacer" role="cell"></td>\s*<td role="cell" colspan="3"><a ', html)
        self.assertIsNotNone(row)
        self.assertLess(html.index('<td class="edition num" role="cell">2026</td>'), row.start())
        self.assertLess(row.start(), html.index('<td class="edition num" role="cell">2025</td>'))
        self.assertNotIn("2026, Sun 18 to Mon 19 Oct", html)

    def test_the_row_spans_only_the_columns_the_table_has(self):
        # Show has no edition page, so its table has no Details column.
        self.assertIn('<td class="spacer" role="cell"></td>\n        <td role="cell" colspan="2"><a ', self.html("events/show/index.html"))

    def test_the_links_carry_the_last_day_so_the_browser_can_drop_them_once_it_has_passed(self):
        self.assertIn('<span class="calendar-links" data-hide-after="2026-10-19">',
                      self.html("events/meet/2026/index.html"))

    def test_every_page_with_links_runs_the_script_that_drops_them(self):
        for rel in ("events/meet/2026/index.html", "events/meet/index.html", "events/show/index.html"):
            self.assertIn('querySelectorAll("[data-hide-after]")', self.html(rel), rel)

    def test_google_gets_an_all_day_edition_with_the_day_after_as_its_end(self):
        q = self.google(self.links("events/meet/2026/index.html")["google"][0])
        self.assertEqual(q["action"], "TEMPLATE")
        self.assertEqual(q["text"], "Meet")
        self.assertEqual(q["dates"], "20261018/20261020")
        self.assertEqual(q["location"], "Test Park, Shizuoka, Japan")
        self.assertIn(f"{settings.SITE_URL}/events/meet/2026/", q["details"])

    def test_google_gets_a_timed_edition_in_utc(self):
        q = self.google(self.links("events/show/index.html")["google"][0])
        self.assertEqual(q["dates"], "20261103T000000Z/20261103T080000Z")
        self.assertNotIn("recur", q)

    def test_google_gets_a_timed_edition_over_several_days_as_all_day_with_its_hours_in_the_details(self):
        # Google's form documents no repeat rule, and a block from first opening to last closing runs overnight.
        q = self.google(self.links("events/fair/index.html")["google"][0])
        self.assertEqual(q["dates"], "20261107/20261109")
        self.assertNotIn("recur", q)
        self.assertIn("10:00 to 17:00 Japan time each day", q["details"])

    def test_a_one_day_timed_edition_does_not_repeat(self):
        self.assertNotIn("RRULE", self.html("events/show/2026.ics"))


if __name__ == "__main__":
    unittest.main()
