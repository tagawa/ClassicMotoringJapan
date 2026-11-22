"""The route timetable chart and the decade and make strips."""

import datetime as dt
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import cars_yaml, display_cars_yaml, instance_yaml, ROUTE, write_event, write_instance
import build  # noqa: E402
import charts  # noqa: E402


def strip_lines(strip: str) -> list[str]:
    """Each row of a strip as a screen reader hears it: its words, without the markup."""
    return [" ".join(re.sub(r"<[^>]+>", " ", li).split()) for li in re.findall(r"(?s)<li[^>]*>.*?</li>", strip)]


class RouteChartTests(unittest.TestCase):
    """The day-shape diagram: geometry is computed, not drawn, so it cannot contradict the table."""

    def setUp(self):
        self.chart = charts.route_chart([
            {"date": dt.date(2026, 10, 18), "checkpoints": [
                {"start_time": "09:00", "end_time": "09:30"},
                {"start_time": "11:00"}]},
            {"date": dt.date(2026, 10, 19), "checkpoints": [
                {"start_time": "08:00", "end_time": "08:45"}]},
        ])

    def test_no_route_means_no_chart(self):
        self.assertIsNone(charts.route_chart(None))
        self.assertIsNone(charts.route_chart([]))

    def test_axis_runs_from_the_hour_below_to_the_hour_above(self):
        # Earliest 08:00, latest 11:00, so the axis must extend past the last bar.
        self.assertEqual((self.chart["start"], self.chart["end"]), ("08:00", "12:00"))

    def test_a_bar_is_placed_and_sized_by_its_window(self):
        bar = self.chart["days"][0]["bars"][0]
        self.assertEqual((bar["left"], bar["width"]), (25.0, 12.5))

    def test_an_open_ended_stop_keeps_a_visible_minimum_width(self):
        bar = self.chart["days"][0]["bars"][1]
        self.assertEqual(bar["left"], 75.0)
        self.assertEqual(bar["width"], charts.CHART_MIN_BAR)

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

    def strip(self) -> str:
        return re.search(r'(?s)<ol class="chart decades">.*?</ol>', self.html).group(0)

    def rows(self) -> list[str]:
        return strip_lines(self.strip())

    def test_one_row_per_decade_from_the_oldest_car_to_the_newest(self):
        self.assertEqual(self.rows(), ["1920s 1 car", "1930s 0 cars", "1940s 0 cars", "1950s 3 cars"])

    def test_the_count_is_one_number_on_screen_and_says_cars_to_a_screen_reader(self):
        self.assertIn('<span class="chart-count">3<span class="visually-hidden"> cars</span></span>', self.strip())

    def test_the_busiest_decade_fills_the_track(self):
        self.assertIn("width: 100.0%", self.html)

    def test_an_empty_decade_keeps_its_place_but_draws_no_bar(self):
        empty = re.search(r'1930s</span>\s*<span class="chart-track"[^>]*>\s*</span>', self.html)
        self.assertIsNotNone(empty, "an empty decade should hold its row and draw nothing")

    def test_the_bars_are_hidden_from_screen_readers_as_a_restatement(self):
        self.assertEqual(self.strip().count('<span class="chart-track" aria-hidden="true">'), 4)

    def page(self, cars: str) -> str:
        tmp = Path(tempfile.mkdtemp())
        try:
            data = tmp / "data"
            write_event(data, "meet")
            write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=cars))
            build.build(data, tmp / "site")
            return (tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
        finally:
            shutil.rmtree(tmp)

    # An organiser's list sometimes leaves one car's year blank; the car still entered.
    UNDATED = '  - entry_no: "03"\n    make: Test\n    model: Car\n'

    def test_a_car_without_a_year_gets_a_closing_line_so_the_strip_adds_up_to_the_table(self):
        self.html = self.page(cars_yaml([1929, 1955]) + self.UNDATED)
        self.assertEqual(self.rows(), ["1920s 1 car", "1930s 0 cars", "1940s 0 cars", "1950s 1 car",
                                       "No year given: 1 car"])
        self.assertEqual(self.strip().count("chart-track"), 4, "the closing line counts, it draws no bar")

    def test_a_car_without_a_year_keeps_its_row_with_the_year_blank(self):
        html = self.page(cars_yaml([1929, 1955]) + self.UNDATED)
        self.assertIn('<tr><td class="num">03</td><td class="num"></td><td>Test</td><td>Car</td></tr>', html)

    def test_a_list_where_every_car_has_a_year_has_no_closing_line(self):
        self.assertNotIn("No year given", self.html)

    def test_a_numbered_list_with_no_years_at_all_has_no_strip(self):
        html = self.page('list_as_of: 2026-09-15\ncars:\n' + self.UNDATED)
        self.assertNotIn("chart decades", html)
        self.assertNotIn("<th scope=\"col\">Year</th>", html)

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


class MakeStripTests(unittest.TestCase):
    """Which makes turned out in numbers, counted from the same rows the table renders."""

    def page(self, cars: str) -> str:
        tmp = Path(tempfile.mkdtemp())
        try:
            data = tmp / "data"
            write_event(data, "meet")
            write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=cars))
            build.build(data, tmp / "site")
            return (tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
        finally:
            shutil.rmtree(tmp)

    def strip(self, makes: list[str]) -> str:
        html = self.page(cars_yaml([1955] * len(makes), makes=makes))
        found = re.search(r'(?s)<ol class="chart makes">.*?</ol>', html)
        self.assertIsNotNone(found, "an entry list should have a make strip")
        return found.group(0)

    def lines(self, strip: str) -> list[str]:
        return strip_lines(strip)

    def test_a_make_with_two_or_more_cars_gets_a_row_and_the_rest_share_one_line(self):
        strip = self.strip(["Fiat", "Alfa Romeo", "Bugatti", "Alfa Romeo", "Fiat", "Alfa Romeo", "Siata"])
        self.assertEqual(self.lines(strip),
                         ["Alfa Romeo 3 cars", "Fiat 2 cars", "and 2 makes with one car each"])

    def test_makes_with_the_same_count_are_in_alphabetical_order(self):
        strip = self.strip(["Porsche", "alfa", "MG", "Porsche", "alfa", "MG"])
        self.assertEqual(self.lines(strip), ["alfa 2 cars", "MG 2 cars", "Porsche 2 cars"])

    def test_the_busiest_make_fills_the_track_and_the_others_scale_to_it(self):
        strip = self.strip(["Fiat", "Alfa Romeo", "Alfa Romeo", "Fiat", "Alfa Romeo"])
        self.assertEqual(re.findall(r"width: ([\d.]+)%", strip), ["100.0", "66.67"])

    def test_the_bars_are_hidden_from_screen_readers_and_the_rest_line_has_none(self):
        strip = self.strip(["Fiat", "Fiat", "Bugatti"])
        self.assertEqual(strip.count('<span class="chart-track" aria-hidden="true">'), 1)
        self.assertEqual(strip.count('<span class="chart-track"'), 1)

    def test_a_lone_single_make_is_worded_in_the_singular(self):
        self.assertEqual(self.lines(self.strip(["Fiat", "Fiat", "Bugatti"]))[-1], "and 1 make with one car")

    def test_no_rest_line_when_every_make_has_several_cars(self):
        self.assertEqual(self.lines(self.strip(["Fiat", "Fiat"])), ["Fiat 2 cars"])

    def test_a_field_of_single_makes_is_one_line_with_nothing_to_follow_on_from(self):
        self.assertEqual(self.lines(self.strip(["Fiat", "Bugatti", "Siata"])), ["3 makes with one car each"])

    def test_it_sits_between_the_decade_strip_and_the_table(self):
        html = self.page(cars_yaml([1955, 1955], makes=["Fiat", "Fiat"]))
        self.assertLess(html.index('class="chart decades"'), html.index('class="chart makes"'))
        self.assertLess(html.index('class="chart makes"'), html.index("<table>"))

    def test_a_show_line_up_names_models_not_cars_so_it_is_not_counted(self):
        # Two Toyota models on a stand are not "Toyota: 2 cars": nobody has counted the cars.
        html = self.page(display_cars_yaml([("Toyota", "2000GT"), ("Toyota", "Sports 800")]))
        self.assertNotIn("chart makes", html)


if __name__ == "__main__":
    unittest.main()
