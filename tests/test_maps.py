"""The map of Japan and the course and route maps."""

import json
import re
import unittest

import yaml

from helpers import CARS, instance_yaml, ROOT, ROUTE, temp_dir, write_event, write_instance
import build  # noqa: E402
import maps  # noqa: E402
import rows  # noqa: E402
import validate  # noqa: E402


class RouteTests(unittest.TestCase):
    """A route is structured data, so a skimmer can find a time and a place."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
        build.build(self.data, self.tmp / "site")
        self.html = (self.tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8")


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


class JapanMapTests(unittest.TestCase):
    """The home page maps: one coastline and one projection, so a dot cannot drift off its venue."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "tokyo-meet", name_en="Tokyo Meet", extra="lat: 35.6812\nlon: 139.7671\n")
        write_instance(data, "tokyo-meet", 2026, instance_yaml("tokyo-meet", 2026, "2026-10-18", "2026-10-18"))
        write_instance(data, "tokyo-meet", 2027, instance_yaml("tokyo-meet", 2027, "2027-10-17", "2027-10-17",
                                                               status="cancelled"))
        write_event(data, "unmapped-meet", name_en="Unmapped Meet")
        write_instance(data, "unmapped-meet", 2026,
                       instance_yaml("unmapped-meet", 2026, "2026-11-01", "2026-11-01"))
        build.build(data, cls.tmp / "site")
        cls.html = (cls.tmp / "site" / "index.html").read_text(encoding="utf-8")
        cls.entries = re.findall(r'<li data-end="[^"]*">.*?</li>', cls.html, re.S)


    def test_the_map_corners_are_the_projection_limits(self):
        self.assertEqual(maps.map_point(maps.MAP_LAT[1], maps.MAP_LON[0]), (0, 0))
        self.assertEqual(maps.map_point(maps.MAP_LAT[0], maps.MAP_LON[1]),
                         (maps.MAP_WIDTH, maps.MAP_HEIGHT))

    def test_east_is_right_and_north_is_up(self):
        tokyo, osaka = maps.map_point(35.68, 139.77), maps.map_point(34.69, 135.50)
        self.assertGreater(tokyo[0], osaka[0])
        self.assertLess(tokyo[1], osaka[1])

    def test_a_mapped_entry_has_a_thumbnail_with_its_dot_where_the_projection_puts_it(self):
        entry = next(e for e in self.entries if "Tokyo Meet" in e and "2026-10-18" in e)
        x, y = maps.map_point(35.6812, 139.7671)
        self.assertEqual(entry.count('<svg class="venue-map"'), 1)
        self.assertIn(f'cx="{x}" cy="{y}"', entry)

    def test_an_entry_without_coordinates_has_no_thumbnail(self):
        entry = next(e for e in self.entries if "Unmapped Meet" in e)
        self.assertNotIn('<svg class="venue-map"', entry)

    def test_no_overview_map_tops_the_page(self):
        # Tried and dropped: at a readable size it pushed the Upcoming list off the first screen.
        top = self.html[:self.html.index('<section id="upcoming"')]
        self.assertNotIn("<use", top)

    def test_a_cancelled_edition_has_a_grey_dot(self):
        confirmed = next(e for e in self.entries if "2026-10-18" in e)
        cancelled = next(e for e in self.entries if "2027-10-17" in e)
        self.assertNotIn('class="off"', confirmed)
        self.assertIn('class="off"', cancelled)

    def test_the_maps_restate_the_prefecture_so_screen_readers_skip_them(self):
        maps = re.findall(r'<svg class="venue-map"[^>]*>', self.html)
        self.assertEqual(len(maps), 2)
        for svg in maps:
            self.assertIn('aria-hidden="true"', svg)

    def test_the_thumbnail_styles_leave_the_map_link_alone(self):
        # Once named .map, the thumbnail rules turned the Map link into a block and filled its pin red.
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?m)^\s*\.map\b(?!-)[^{]*", css), [".map "])

    def test_the_coastline_is_sent_once_and_reused(self):
        self.assertEqual(self.html.count('id="japan"'), 1)
        self.assertEqual(self.html.count('<use xlink:href="#japan"'), 2)

    def test_no_coordinates_anywhere_means_no_maps(self):
        tmp = temp_dir(self)
        write_event(tmp / "data", "meet")
        write_instance(tmp / "data", "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(tmp / "data", tmp / "site")
        self.assertNotIn("<svg class=\"venue-map", (tmp / "site" / "index.html").read_text(encoding="utf-8"))

    def test_every_real_venue_falls_inside_the_map(self):
        # An Okinawa or Hokkaido venue past the edge fails here, before the dot is clipped.
        events, editions = validate.load_and_validate(ROOT / "data")
        dotted = [r for r in rows.make_rows(events, editions) if r["dot"]]
        self.assertTrue(dotted)
        for r in dotted:
            x, y = r["dot"]
            self.assertTrue(0 < x < maps.MAP_WIDTH and 0 < y < maps.MAP_HEIGHT, r["full_name"])


# A straight 500-unit run up the frame, written as the tool writes a straight segment:
# one curve whose control points are its ends.
STRAIGHT_LINE = [[300.0, 700.0], [300.0, 700.0], [300.0, 200.0], [300.0, 200.0]]


def course_yaml(line=STRAIGHT_LINE, map_url=None, cones=None) -> str:
    return ("course:\n"
            + (f"  map_url: {map_url}\n" if map_url else "")
            + "  line:\n" + "".join(f"    - [{x}, {y}]\n" for x, y in line)
            + ("  cones:\n" + "".join(f"    - [{x}, {y}]\n" for x, y in cones) if cones else ""))


class CourseMapTests(unittest.TestCase):
    """A time-trial course read from the organiser's PDF, drawn on the edition page (spec 4.8)."""

    def page(self, extra: str, status="confirmed") -> str:
        tmp = temp_dir(self)
        write_event(tmp / "data", "meet")
        write_instance(tmp / "data", "meet", 2026,
                       instance_yaml("meet", 2026, "2026-11-08", "2026-11-08", status=status, extra=extra))
        build.build(tmp / "data", tmp / "site")
        return (tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8")

    def errors(self, extra: str) -> str:
        tmp = temp_dir(self)
        write_event(tmp / "data", "meet")
        write_instance(tmp / "data", "meet", 2026,
                       instance_yaml("meet", 2026, "2026-11-08", "2026-11-08", extra=extra))
        with self.assertRaises(validate.BuildError) as caught:
            validate.load_and_validate(tmp / "data")
        return str(caught.exception)

    def test_a_course_alone_makes_an_edition_page(self):
        html = self.page(course_yaml())
        self.assertIn('<h2 id="course">Course map</h2>', html)
        self.assertIn("<title>Test Event 2026: Course map", html)

    def test_the_line_is_drawn_from_the_data(self):
        html = self.page(course_yaml())
        self.assertIn('d="M300.0 700.0 C300.0 700.0 300.0 200.0 300.0 200.0"', html)

    def test_start_is_open_and_finish_filled(self):
        html = self.page(course_yaml())
        self.assertIn('<circle class="course-start" cx="300.0" cy="700.0"', html)
        self.assertIn('<circle class="course-finish" cx="300.0" cy="200.0"', html)

    def test_the_caption_does_not_explain_what_the_drawing_shows(self):
        # Owner, 2026-11-10: no reader thinks a course runs against its arrows.
        figure = self.page(course_yaml()).split('id="course"')[1].split("</figure>")[0]
        for obvious in ("open circle", "filled circle", "arrows"):
            self.assertNotIn(obvious, figure)

    def test_cones_are_drawn_where_the_data_puts_them(self):
        html = self.page(course_yaml(cones=[[250.0, 400.0], [350.5, 450.0]]))
        self.assertIn('<circle class="course-cone" cx="250.0" cy="400.0"', html)
        self.assertIn('<circle class="course-cone" cx="350.5" cy="450.0"', html)

    def test_a_car_drives_the_line_on_a_loop(self):
        html = self.page(course_yaml())
        self.assertIn('<path id="course-path" class="course-line"', html)
        self.assertRegex(html, r'<g class="course-car">.*?<animateMotion dur="[0-9.]+s" '
                               r'repeatCount="indefinite" rotate="auto" calcMode="spline" keyPoints="[0-9.;]+" '
                               r'keyTimes="[0-9.;]+" keySplines="[0-9. ;]+"><mpath xlink:href="#course-path"/>')
        self.assertRegex(html, r'<animate attributeName="opacity" dur="[0-9.]+s" repeatCount="indefinite" '
                               r'values="[0-9;]+" keyTimes="[0-9.;]+"/>')

    def test_the_line_has_a_casing_under_it(self):
        html = self.page(course_yaml())
        self.assertLess(html.index('class="course-casing"'), html.index('class="course-line"'))

    def test_the_car_stays_still_for_reduced_motion(self):
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"@media \(prefers-reduced-motion: reduce\) \{\s*\.course-car \{ display: none; \}")

    def test_a_course_without_cones_draws_none(self):
        self.assertNotIn("course-cone", self.page(course_yaml()))

    def test_a_cone_outside_the_frame_is_refused(self):
        self.assertIn("course: cones", self.errors(course_yaml(cones=[[900.0, 400.0]])))

    def test_the_map_has_an_accessible_name(self):
        self.assertRegex(self.page(course_yaml()), r'<svg class="course-map"[^>]* role="img" aria-label="[^"]+"')

    def test_course_comes_after_videos_and_first_without_them(self):
        videos = "videos:\n  - youtube_id: gDq-2nEG3Y8\n    label_en: Film\n"
        with_videos = self.page(videos + course_yaml() + CARS)
        self.assertLess(with_videos.index('id="videos"'), with_videos.index('id="course"'))
        self.assertLess(with_videos.index('id="course"'), with_videos.index('id="cars"'))
        without = self.page(course_yaml() + CARS)
        self.assertLess(without.index('id="course"'), without.index('id="cars"'))

    def test_the_pdf_link_goes_once_the_edition_has_ended(self):
        # Tentative: no calendar links, so the removing script must come from the map alone.
        html = self.page(course_yaml(map_url="https://example.com/course.pdf"), status="tentative")
        self.assertRegex(html, r'<span data-hide-after="2026-11-08">[^<]*<a href="https://example.com/course.pdf">')
        self.assertIn('querySelectorAll("[data-hide-after]")', html)

    def test_the_credit_stays_without_a_link(self):
        html = self.page(course_yaml())
        self.assertIn("Redrawn from the organiser's course map", html)
        figure = html.split('id="course"')[1].split("</figure>")[0]
        self.assertNotIn("<a ", figure)

    def test_a_line_must_be_a_start_point_and_whole_curves(self):
        self.assertIn("course: line", self.errors(course_yaml(line=STRAIGHT_LINE[:3])))

    def test_a_line_outside_the_frame_is_refused(self):
        self.assertIn("course: line", self.errors(course_yaml(line=[[900.0, 700.0]] + STRAIGHT_LINE[1:])))

    def test_unknown_course_fields_are_refused(self):
        self.assertIn("unknown field 'barriers'", self.errors(course_yaml() + "  barriers: []\n"))


class CourseArrowTests(unittest.TestCase):
    """Chevrons inside the line at a fixed spacing of path length, pointing the way it runs."""

    def numbers(self, chevron):
        return [float(n) for n in re.findall(r"-?\d+\.\d", chevron)]

    def test_one_chevron_per_spacing_starting_half_a_spacing_in(self):
        spacing = maps.COURSE_ARROW_SPACING
        expected = int((500 - spacing / 2) // spacing) + 1
        self.assertEqual(len(maps.course_map({"line": STRAIGHT_LINE})["arrows"]), expected)

    def test_chevrons_are_open_and_the_set_depth(self):
        # Arm, tip, arm: an open V, not a filled triangle. The line runs straight up, so the
        # depth is how far the tip sits above the arms.
        chevron = maps.course_map({"line": STRAIGHT_LINE})["arrows"][0]
        self.assertNotIn("Z", chevron)
        arm_y, tip_y = self.numbers(chevron)[1], self.numbers(chevron)[3]
        self.assertAlmostEqual(arm_y - tip_y, maps.COURSE_ARROW_LENGTH, places=1)

    def test_chevrons_point_along_the_line(self):
        # The line runs up the page, so every tip is above (smaller y than) both arms.
        for chevron in maps.course_map({"line": STRAIGHT_LINE})["arrows"]:
            n = self.numbers(chevron)
            self.assertTrue(n[3] < n[1] and n[3] < n[5], chevron)

    def test_chevrons_fit_inside_the_line(self):
        n = self.numbers(maps.course_map({"line": STRAIGHT_LINE})["arrows"][0])
        self.assertLess(abs(n[4] - n[0]), maps.MAP_LINE_WIDTH)


class MapCarTimingTests(unittest.TestCase):
    """The car fades in, eases off, pauses where the date changes, waits at the finish, fades out."""

    def test_a_course_lap_adds_the_fades_the_hold_and_the_ramps_to_the_drive(self):
        # Even acceleration over a ramp covers half the distance full speed would, so the
        # two ramps add half a ramp's time each to the drive.
        car = maps.course_map({"line": STRAIGHT_LINE})["car"]
        expected = (2 * maps.MAP_CAR_FADE + 500 / maps.COURSE_CAR_SPEED + maps.MAP_CAR_HOLD
                    + maps.MAP_CAR_EASE)
        self.assertAlmostEqual(float(car["dur"].rstrip("s")), expected, places=1)

    def test_the_car_gets_up_to_speed_in_the_ramp_time(self):
        car = maps.course_map({"line": STRAIGHT_LINE})["car"]
        times = [float(t) for t in car["times"].split(";")]
        dur = float(car["dur"].rstrip("s"))
        # After the fade in, the next interval is the acceleration.
        self.assertAlmostEqual((times[2] - times[1]) * dur, maps.MAP_CAR_EASE, places=2)

    def test_a_leg_too_short_for_full_ramps_shares_it_between_them(self):
        short = [[300.0, 700.0], [300.0, 700.0], [300.0, 690.0], [300.0, 690.0]]
        car = maps.course_map({"line": short})["car"]
        times = [float(t) for t in car["times"].split(";")]
        dur = float(car["dur"].rstrip("s"))
        self.assertLess((times[2] - times[1]) * dur, maps.MAP_CAR_EASE)

    def test_the_lists_line_up_for_smil(self):
        for car in (maps.course_map({"line": STRAIGHT_LINE})["car"],
                    maps.route_map(yaml.safe_load(located_route())["route"])["car"]):
            points, times = car["points"].split(";"), car["times"].split(";")
            self.assertEqual(len(points), len(times))
            self.assertEqual(len(car["splines"].split(";")), len(times) - 1)
            self.assertEqual((times[0], times[-1]), ("0", "1"))
            self.assertEqual([float(t) for t in times], sorted(float(t) for t in times))

    def test_the_car_starts_and_ends_unseen(self):
        car = maps.course_map({"line": STRAIGHT_LINE})["car"]
        self.assertEqual(car["opacity"].split(";")[0], "0")
        self.assertEqual(car["opacity"].split(";")[-1], "0")

    def test_a_route_pauses_once_where_the_date_changes(self):
        # Two days, so one change of date: the car holds one point for a while there.
        car = maps.route_map(yaml.safe_load(located_route())["route"])["car"]
        points = car["points"].split(";")
        holds = [a for a, b in zip(points, points[1:]) if a == b and a not in ("0", "1")]
        self.assertEqual(len(holds), 1)



def located_route(overnight=False, drop_one=False) -> str:
    """ROUTE's three stops with coordinates; overnight makes day 2 start where day 1 ended."""
    hill = ("35.0", "138.5") if overnight else ("35.2", "138.6")
    coords = [("34.9756", "138.3828"), ("35.0", "138.5"), hill]
    lines, n = [], 0
    for line in ROUTE.splitlines(keepends=True):
        lines.append(line)
        if line.strip().startswith("prefecture:"):
            if not (drop_one and n == 1):
                lines.append(f"        lat: {coords[n][0]}\n        lon: {coords[n][1]}\n")
            n += 1
    return "".join(lines)


class RouteMapTests(unittest.TestCase):
    """A rally's stops on the coastline, joined in order by straight lines (spec 4.8)."""

    def page(self, extra: str) -> str:
        tmp = temp_dir(self)
        write_event(tmp / "data", "rally")
        write_instance(tmp / "data", "rally", 2026,
                       instance_yaml("rally", 2026, "2026-10-18", "2026-10-19", extra=extra))
        build.build(tmp / "data", tmp / "site")
        return (tmp / "site/events/rally/2026/index.html").read_text(encoding="utf-8")

    def errors(self, extra: str) -> str:
        tmp = temp_dir(self)
        write_event(tmp / "data", "rally")
        write_instance(tmp / "data", "rally", 2026,
                       instance_yaml("rally", 2026, "2026-10-18", "2026-10-19", extra=extra))
        with self.assertRaises(validate.BuildError) as caught:
            validate.load_and_validate(tmp / "data")
        return str(caught.exception)

    def test_the_map_sits_above_the_day_chart(self):
        html = self.page(located_route())
        self.assertIn('<svg class="route-map"', html)
        self.assertLess(html.index('class="route-map"'), html.index('<ol class="chart">'))

    def test_no_map_without_coordinates(self):
        self.assertNotIn("route-map", self.page(ROUTE))

    def test_coordinates_are_all_or_none(self):
        self.assertIn("all of its checkpoints or none", self.errors(located_route(drop_one=True)))

    def test_a_checkpoint_needs_both_halves(self):
        broken = located_route().replace("        lon: 138.5\n", "", 1)
        self.assertIn("give lat and lon together", self.errors(broken))

    def test_start_and_finish_are_the_first_and_last_stops(self):
        drawn = maps.route_map(yaml.safe_load(located_route())["route"])
        self.assertEqual((drawn["start"], drawn["finish"]), (drawn["stops"][0], drawn["stops"][-1]))
        # The first stop is south-west of the last, so it sits left of and below it.
        (sx, sy), (fx, fy) = ([float(n) for n in drawn[k]] for k in ("start", "finish"))
        self.assertLess(sx, fx)
        self.assertGreater(sy, fy)
        html = self.page(located_route())
        self.assertIn(f'<circle class="course-start" cx="{drawn["start"][0]}" cy="{drawn["start"][1]}"', html)
        self.assertIn(f'<circle class="course-finish" cx="{drawn["finish"][0]}" cy="{drawn["finish"][1]}"', html)

    def test_an_overnight_stop_is_one_dot(self):
        def stop(lat, lon):
            return {"lat": lat, "lon": lon}
        # Day 2 starting where day 1 ended is one stop; starting somewhere else is two.
        same = [{"checkpoints": [stop(34.9, 138.3), stop(35.0, 138.5)]},
                {"checkpoints": [stop(35.0, 138.5), stop(35.2, 138.6)]}]
        moved = [{"checkpoints": [stop(34.9, 138.3), stop(35.0, 138.5)]},
                 {"checkpoints": [stop(35.1, 138.4), stop(35.2, 138.6)]}]
        self.assertEqual((len(maps.route_map(same)["stops"]), len(maps.route_map(moved)["stops"])), (3, 4))

    def test_the_car_drives_the_route(self):
        html = self.page(located_route())
        self.assertIn('<path id="route-path" class="course-line"', html)
        self.assertIn('<mpath xlink:href="#route-path"/>', html)

    def test_each_corner_is_rounded_so_the_car_turns(self):
        drawn = maps.route_map(yaml.safe_load(located_route())["route"])
        # Three stops, so one corner, drawn as one curve the car follows.
        self.assertEqual(drawn["d"].count("Q"), 1)

    def test_the_land_is_the_prefectures_in_the_frame(self):
        html = self.page(located_route())
        land = re.search(r'<path class="route-land" d="([^"]+)"', html)
        self.assertIsNotNone(land)
        # More than one prefecture, so there is a border, and far fewer than all 47 hold.
        rings = land.group(1).count("M")
        self.assertGreater(rings, 1)
        everything = json.loads((ROOT / "data" / "japan_prefectures.json").read_text(encoding="utf-8"))
        self.assertLess(rings, sum(len(r) for r in everything.values()))

    def test_a_route_inside_one_prefecture_still_has_land(self):
        # No border point of Shizuoka falls in a frame this small, yet the frame is all land.
        tiny = [{"checkpoints": [{"lat": 34.98, "lon": 138.39}, {"lat": 34.985, "lon": 138.395},
                                 {"lat": 34.99, "lon": 138.38}]}]
        self.assertGreater(maps.route_map(tiny)["land"].count("M"), 0)

    def test_the_map_stays_light(self):
        figure = self.page(located_route()).split('class="route-map"')[1].split("</svg>")[0]
        self.assertLess(len(figure), 30000)

    def test_close_stops_share_one_dot(self):
        def day(*spots):
            return [{"checkpoints": [{"lat": lat, "lon": lon} for lat, lon in spots]}]
        apart = maps.route_map(day((34.9, 138.3), (35.0, 138.4), (35.1, 138.5), (35.3, 138.7)))
        close = maps.route_map(day((34.9, 138.3), (35.0, 138.4), (35.0001, 138.4001), (35.3, 138.7)))
        self.assertEqual((len(apart["dots"]), len(close["dots"])), (2, 1))

    def test_an_overnight_stop_is_ringed_and_never_merged_away(self):
        route = yaml.safe_load(located_route())["route"]
        drawn = maps.route_map(route)
        # Two days: day 1's last stop is the one overnight, and it is not an ordinary dot.
        self.assertEqual(len(drawn["overnights"]), 1)
        self.assertNotIn(drawn["overnights"][0], drawn["dots"])
        html = self.page(located_route())
        self.assertIn('class="route-overnight"', html)
        self.assertIn("overnight", html.split('class="route-map"')[1].split("</figure>")[0].split("<figcaption>")[1])

    def test_the_start_and_finish_are_named(self):
        html = self.page(located_route())
        self.assertIn(">Test Park</text>", html)
        self.assertIn(">Test Hill</text>", html)

    def test_close_ends_name_themselves_on_opposite_sides(self):
        # La Festa 2026 starts in Harajuku and finishes in Makuhari: close, and the names collided.
        route = yaml.safe_load(located_route())["route"]
        route[1]["checkpoints"][-1].update(lat=34.99, lon=138.40)
        start, finish = maps.route_map(route)["labels"]
        # Different sides, or different lines a font height apart: either way, no overlap.
        apart = abs(float(start["y"]) - float(finish["y"])) >= 16
        self.assertTrue(apart or {start["anchor"], finish["anchor"]} == {"start", "end"})

    def test_names_cover_no_marker_on_the_real_la_festa_map(self):
        # La Festa 2026's start label once hid the Narita overnight ring beneath it.
        edition = yaml.safe_load((ROOT / "data/events/la-festa-autunno/2026.yml").read_text(encoding="utf-8"))
        drawn = maps.route_map(edition["route"])
        markers = [[float(n) for n in spot] for spot in drawn["dots"] + drawn["overnights"]
                   + [drawn["start"], drawn["finish"]]]
        for label in drawn["labels"]:
            left, top, right, bottom = (float(n) for n in label["box"])
            for x, y in markers:
                self.assertFalse(left - 4 < x < right + 4 and top - 4 < y < bottom + 4, (label["text"], x, y))

    def test_a_route_between_two_places_draws_no_map(self):
        # Japan Classic Car Day: Daikanyama to the Tokyo Prince Hotel, an hour's drive between.
        two = [{"checkpoints": [{"lat": 35.6493, "lon": 139.6998}, {"lat": 35.6589, "lon": 139.7488}]}]
        self.assertIsNone(maps.route_map(two))

    def test_a_route_at_one_place_draws_no_map(self):
        # Coppa di Tokyo checks in, starts and finishes at one park: nothing to draw.
        one = [{"checkpoints": [{"lat": 35.66, "lon": 139.76}, {"lat": 35.66, "lon": 139.76}]}]
        self.assertIsNone(maps.route_map(one))

    def test_a_name_drops_the_organisers_note_in_brackets(self):
        # ROUTE's first stop is "Test Park, Testville"; Coppa di Kyoto's is
        # "Kyoto Prefectural Office (cars check in)".
        route = yaml.safe_load(located_route())["route"]
        route[0]["checkpoints"][0]["place_en"] = "Kyoto Prefectural Office (cars check in)"
        self.assertEqual(maps.route_map(route)["labels"][0]["text"], "Kyoto Prefectural Office")

    def test_a_route_back_to_its_start_is_named_once(self):
        # Coppa di Koumi starts and finishes at Gateaux Kingdom Koumi.
        route = yaml.safe_load(located_route())["route"]
        route[1]["checkpoints"].append(dict(route[1]["checkpoints"][0], lat=34.9756, lon=138.3828,
                                            start_time="09:00", place_en="Test Park (finish)"))
        self.assertEqual(len(maps.route_map(route)["labels"]), 1)

    def test_the_sea_is_drawn_under_the_land(self):
        html = self.page(located_route())
        self.assertLess(html.index('class="route-sea"'), html.index('class="route-land"'))

    def test_the_caption_says_the_lines_are_not_the_roads(self):
        figure = self.page(located_route()).split('class="route-map"')[1].split("</figure>")[0]
        self.assertIn("not the roads", figure)


if __name__ == "__main__":
    unittest.main()
