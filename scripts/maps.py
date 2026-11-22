"""The map of Japan, venue pins, and the animated course and route maps."""
from __future__ import annotations

import functools
import json
import math
import re
from urllib.parse import quote

from settings import ROOT

# The home page maps: the four main islands and their neighbours, not the whole range above.
# A venue outside this box fails a test rather than a dot being clipped at the edge.
MAP_LON = (128.5, 146.0)
MAP_LAT = (30.0, 45.7)
MAP_SCALE = 10
# Longitude squeezed to its length at 36N, the middle of Honshu, so the islands keep their shape.
MAP_X = math.cos(math.radians(36)) * MAP_SCALE
MAP_WIDTH = round((MAP_LON[1] - MAP_LON[0]) * MAP_X, 1)
MAP_HEIGHT = round((MAP_LAT[1] - MAP_LAT[0]) * MAP_SCALE, 1)
MAP_OUTLINE = ROOT / "data" / "japan_outline.json"
# Route maps only: finer than the outline, and with the borders between prefectures.
MAP_PREFECTURES = ROOT / "data" / "japan_prefectures.json"

# x, y, width, height of the car park area in SHCC's course template, in PDF points measured
# down from the page top. It sat at the same place in every map from 2022 to 2026.
COURSE_VIEWBOX = (84, 159, 467, 588)
# Path length between arrowheads: about 15 on the shortest course and 28 on the longest.
COURSE_ARROW_SPACING = 150
# A chevron's depth, tip to arms, in frame units; it sits inside the line, so it stays small.
COURSE_ARROW_LENGTH = 5
# Both maps' line and the casing under it, in frame units: wide enough to hold a chevron.
MAP_LINE_WIDTH = 8
MAP_CASING_WIDTH = 12
# The car's fade at each end of a lap and its wait at the finish, in seconds.
MAP_CAR_FADE = 0.4
MAP_CAR_HOLD = 1.2
# Seconds of even acceleration off each start, and braking into each stop (owner: whole-leg easing was too slow).
MAP_CAR_EASE = 0.6
# The course map's car, in frame units a second: about 26 seconds for the 2026 autumn course.
COURSE_CAR_SPEED = 80
# The route map is drawn as wide as the course map's frame, so the two share every style.
ROUTE_FRAME_WIDTH = COURSE_VIEWBOX[2]
# Frame units a second along a route map: two thirds of the first speed (owner, 2026-11-10).
ROUTE_CAR_SPEED = 67
# The most a route's corner is rounded by, in frame units, so the car turns instead of snapping.
ROUTE_CORNER = 30
# Dots closer than this, in frame units, are one dot: a cluster reads as one place.
ROUTE_STOP_MERGE = 10
# Seconds the car waits at each day's last stop, where the date changes (owner, 2026-11-10).
ROUTE_OVERNIGHT_PAUSE = 1.0


def _bezier(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1 - t
    return tuple(u * u * u * a + 3 * u * u * t * b + 3 * u * t * t * c + t * t * t * d
                 for a, b, c, d in zip(p0, p1, p2, p3))


def _arrowhead(x: float, y: float, dx: float, dy: float) -> str:
    """An open chevron centred on (x, y), arm, tip, arm, pointing along the unit vector (dx, dy)."""
    half, wide = COURSE_ARROW_LENGTH / 2, MAP_LINE_WIDTH * 0.3
    tip = (x + dx * half, y + dy * half)
    arms = [(x - dx * half + side * dy * wide, y - dy * half - side * dx * wide) for side in (1, -1)]
    return "M{:.1f} {:.1f} L{:.1f} {:.1f} L{:.1f} {:.1f}".format(*arms[0], *tip, *arms[1])


def _key(value: float) -> str:
    return ("%.4f" % value).rstrip("0").rstrip(".") or "0"


def _car_timeline(length: float, pauses: list[float], speed: float) -> dict:
    """SMIL timings for the car: fade in, drive, wait at each pause, wait, fade out.

    pauses are distances along the line. Each leg accelerates evenly for MAP_CAR_EASE, runs at
    speed, then brakes evenly over the same time. The ramps are SMIL splines for constant
    acceleration (the curve t squared), whose slope at the join matches the cruising speed, so
    the car never lurches.
    """
    speed_up, cruise, slow_down, still = "0.333 0 0.667 0.333", "0 0 1 1", "0.333 0.667 0.667 1", "0 0 1 1"
    marks, splines, clock, here = [(0.0, 0.0), (MAP_CAR_FADE, 0.0)], [still], MAP_CAR_FADE, 0.0
    for stop in sorted(pauses) + [length]:
        leg = stop - here
        # A ramp covers half the distance full speed would; a short leg shares itself between two.
        ramp = min(speed * MAP_CAR_EASE / 2, leg / 2)
        ramp_time = 2 * ramp / speed
        for distance, seconds, spline in ((ramp, ramp_time, speed_up), (leg - 2 * ramp, (leg - 2 * ramp) / speed, cruise),
                                          (ramp, ramp_time, slow_down)):
            if seconds <= 0:
                continue
            clock += seconds
            here += distance
            marks.append((clock, here))
            splines.append(spline)
        here = stop
        if stop < length:
            clock += ROUTE_OVERNIGHT_PAUSE
            marks.append((clock, stop))
            splines.append(still)
    for wait in (MAP_CAR_HOLD, MAP_CAR_FADE):
        clock += wait
        marks.append((clock, length))
        splines.append(still)
    times = [_key(at / clock) for at, _ in marks[:-1]] + ["1"]
    points = [_key(where / length) for _, where in marks[:-1]] + ["1"]
    return {"dur": f"{clock:.2f}s", "points": ";".join(points), "times": ";".join(times),
            "splines": ";".join(splines),
            "opacity": "0;1;1;0",
            "opacity_times": f"0;{_key(MAP_CAR_FADE / clock)};{_key(1 - MAP_CAR_FADE / clock)};1"}


def _course_curves(line: list) -> list:
    return [line[i:i + 4] for i in range(0, len(line) - 1, 3)]


def course_steps(line: list) -> list:
    """The drawn line as short straight steps, enough to measure along it and take a heading."""
    steps = []
    for curve in _course_curves(line):
        points = [_bezier(*curve, n / 20) for n in range(21)]
        steps += zip(points, points[1:])
    return steps


def _arrows_along(steps) -> tuple[list[str], float]:
    """Arrowheads every COURSE_ARROW_SPACING along a line of straight steps, and its length."""
    arrows, travelled, next_at = [], 0.0, COURSE_ARROW_SPACING / 2
    for (ax, ay), (bx, by) in steps:
        length = math.hypot(bx - ax, by - ay)
        while length and travelled + length >= next_at:
            share = (next_at - travelled) / length
            arrows.append(_arrowhead(ax + share * (bx - ax), ay + share * (by - ay),
                                     (bx - ax) / length, (by - ay) / length))
            next_at += COURSE_ARROW_SPACING
        travelled += length
    return arrows, travelled


def course_map(course: dict) -> dict:
    """The course line as SVG, with arrowheads spaced by path length (spec 4.8).

    Drawn from course.line alone, so the same PDF always gives the same map, and the
    direction shown never depends on where the organiser happened to put theirs.
    """
    line = course["line"]
    d = f"M{line[0][0]:.1f} {line[0][1]:.1f} " + " ".join(
        "C" + " ".join(f"{x:.1f} {y:.1f}" for x, y in curve[1:]) for curve in _course_curves(line))
    arrows, travelled = _arrows_along(course_steps(line))
    return {"d": d, "start": [f"{n:.1f}" for n in line[0]], "finish": [f"{n:.1f}" for n in line[-1]],
            "cones": [[f"{n:.1f}" for n in cone] for cone in course.get("cones") or []],
            "arrows": arrows, "viewbox": " ".join(str(n) for n in COURSE_VIEWBOX),
            "car": _car_timeline(travelled, [], COURSE_CAR_SPEED),
            "line_width": MAP_LINE_WIDTH, "casing_width": MAP_CASING_WIDTH,
            # Height as a share of width, for the frame's padding.
            "shape": f"{COURSE_VIEWBOX[3] / COURSE_VIEWBOX[2] * 100:.2f}"}


@functools.cache
def _prefectures() -> dict:
    return json.loads(MAP_PREFECTURES.read_text(encoding="utf-8"))


def _rounded(points: list) -> tuple[str, list, list[float]]:
    """A polyline with each corner rounded: SVG, short straight steps, and how far along
    the line each point is passed (a corner's point is passed at the middle of its curve).

    The car follows the drawn path, so rounding the corners is what turns its heading
    smoothly instead of snapping it round at every stop.
    """
    d, steps, here = [f"M{points[0][0]:.1f} {points[0][1]:.1f}"], [], points[0]
    passed, travelled = [0.0], 0.0
    for before, corner, after in zip(points, points[1:], points[2:]):
        len_in, len_out = math.dist(before, corner), math.dist(corner, after)
        cut = min(ROUTE_CORNER, len_in / 2, len_out / 2)
        enter = tuple(c - (c - b) / len_in * cut for b, c in zip(before, corner))
        leave = tuple(c + (a - c) / len_out * cut for c, a in zip(corner, after))
        curve = [_quadratic(enter, corner, leave, n / 8) for n in range(9)]
        d.append(f"L{enter[0]:.1f} {enter[1]:.1f} Q{corner[0]:.1f} {corner[1]:.1f} {leave[0]:.1f} {leave[1]:.1f}")
        travelled += math.dist(here, enter)
        half = sum(math.dist(a, b) for a, b in zip(curve[:5], curve[1:5]))
        passed.append(travelled + half)
        travelled += sum(math.dist(a, b) for a, b in zip(curve, curve[1:]))
        steps += [(here, enter)] + list(zip(curve, curve[1:]))
        here = leave
    d.append(f"L{points[-1][0]:.1f} {points[-1][1]:.1f}")
    steps.append((here, points[-1]))
    passed.append(travelled + math.dist(here, points[-1]))
    return " ".join(d), steps, passed


def _quadratic(p0, p1, p2, t: float) -> tuple[float, float]:
    u = 1 - t
    return tuple(u * u * a + 2 * u * t * b + t * t * c for a, b, c in zip(p0, p1, p2))


def route_map(route) -> dict | None:
    """The stops in timetable order on the coastline, framed on the stops (spec 4.8)."""
    stops, day_ends = [], []
    for day in route:
        for point in day["checkpoints"]:
            spot = map_point(point["lat"], point["lon"])
            # An overnight stop ends one day and starts the next: one dot, not two.
            if not stops or stops[-1] != spot:
                stops.append(spot)
        day_ends.append(len(stops) - 1)
    # One or two places: a straight line from A to B, which the table already says (spec 4.8).
    if len(set(stops)) < 3:
        return None
    first, last = route[0]["checkpoints"][0], route[-1]["checkpoints"][-1]
    xs, ys = [x for x, _ in stops], [y for _, y in stops]
    margin = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.12 + 1
    x0, x1, y0, y1 = min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin
    # Keep the frame between 3:4 and 4:3, so a route running north to south is not a sliver.
    if (y1 - y0) > (x1 - x0) * 4 / 3:
        grow = ((y1 - y0) * 3 / 4 - (x1 - x0)) / 2
        x0, x1 = x0 - grow, x1 + grow
    elif (x1 - x0) > (y1 - y0) * 4 / 3:
        grow = ((x1 - x0) * 3 / 4 - (y1 - y0)) / 2
        y0, y1 = y0 - grow, y1 + grow
    scale = ROUTE_FRAME_WIDTH / (x1 - x0)
    width, height = ROUTE_FRAME_WIDTH, round((y1 - y0) * scale, 1)

    def frame(x: float, y: float) -> tuple[float, float]:
        return round((x - x0) * scale, 1), round((y - y0) * scale, 1)

    placed = [frame(*spot) for spot in stops]
    land = []
    for rings in _prefectures().values():
        for ring in rings:
            points = [frame(*map_point(lat, lon)) for lon, lat in ring]
            # Only what reaches into the frame, at the detail its scale can show: about a pixel.
            # By bounding box, so a frame lying wholly inside one prefecture still gets its land.
            xs, ys = [x for x, _ in points], [y for _, y in points]
            if min(xs) <= width and max(xs) >= 0 and min(ys) <= height and max(ys) >= 0:
                land.append("M" + " ".join("%.1f,%.1f" % p for p in simplify(points, 1.0)) + "Z")
    d, steps, passed = _rounded(placed)
    arrows, travelled = _arrows_along(steps)
    # Overnight stops first, since they are never merged away; then small dots, leaving out any
    # that would sit on another dot, an overnight or an end marker.
    overnights = [placed[i] for i in day_ends[:-1] if 0 < i < len(placed) - 1]
    dots = []
    for spot in placed[1:-1]:
        if spot not in overnights and all(math.dist(spot, other) > ROUTE_STOP_MERGE
                                          for other in dots + overnights + [placed[0], placed[-1]]):
            dots.append(spot)

    markers = placed[:1] + dots + overnights + placed[-1:]

    def label(spot, point, taken: list) -> dict:
        """The first of right, left, above, below that covers no marker, stays on the card
        and keeps clear of names already placed; failing that, the one covering least."""
        # The place itself: no town after the comma, no organiser's note in brackets.
        text = re.sub(r"\s*\(.*?\)", "", point.get("place_en", "")).split(",")[0].strip()
        reach = len(text) * 9  # Roughly, at 16px semibold.
        x, y = spot
        tries = [(x + 14, y + 5, "start", (x + 14, y - 11, x + 14 + reach, y + 5)),
                 (x - 14, y + 5, "end", (x - 14 - reach, y - 11, x - 14, y + 5))]
        # Above, then below, centred on the marker, then slid a quarter of the name either way,
        # each kept on the card, so a long name can step round a cluster of stops.
        for baseline in (y - 14, y + 24):
            for slide in (0, -reach / 4, reach / 4):
                middle = min(max(x + slide, reach / 2), width - reach / 2)
                tries.append((middle, baseline, "middle",
                              (middle - reach / 2, baseline - 16, middle + reach / 2, baseline)))

        def cost(box) -> int:
            left, top, right, bottom = box
            covered = sum(left - 4 < mx < right + 4 and top - 4 < my < bottom + 4 for mx, my in markers)
            clash = sum(left < o[2] and o[0] < right and top < o[3] and o[1] < bottom for o in taken)
            off = left < 0 or right > width or top < 0 or bottom > height
            return covered + 10 * clash + 100 * off

        lx, ly, anchor, box = min(tries, key=lambda t: cost(t[3]))
        taken.append(box)
        return {"text": text, "x": f"{lx:.1f}", "y": f"{ly:.1f}", "anchor": anchor,
                "box": [f"{n:.1f}" for n in box]}

    overnight = [passed[i] for i in day_ends[:-1] if 0 < i < len(placed) - 1]
    return {"stops": [[f"{n:.1f}" for n in spot] for spot in placed],
            "dots": [[f"{n:.1f}" for n in spot] for spot in dots],
            "overnights": [[f"{n:.1f}" for n in spot] for spot in overnights],
            # A route back to where it began is named once.
            "labels": ([label(placed[0], first, taken := [])]
                       + ([label(placed[-1], last, taken)] if placed[-1] != placed[0] else [])),
            "car": _car_timeline(travelled, overnight, ROUTE_CAR_SPEED),
            "line_width": MAP_LINE_WIDTH, "casing_width": MAP_CASING_WIDTH,
            "start": [f"{n:.1f}" for n in placed[0]], "finish": [f"{n:.1f}" for n in placed[-1]],
            "d": d, "arrows": arrows, "land": " ".join(land), "viewbox": f"0 0 {width} {height}",
            "width": width, "height": height,
            "shape": f"{height / width * 100:.2f}"}


# Map links

def venue_pin(ev: dict, ed: dict | None = None) -> dict | None:
    """Where a map link points, or None when no coordinates have been recorded.

    Coordinates belong to the venue they were taken at, so an edition that names a venue of
    its own does not inherit the event's pin: no link beats a link to the wrong field.
    """
    if ed and "lat" in ed:
        source = ed
    elif ed and ed.get("venue_en"):
        return None
    else:
        source = ev
    if "lat" not in source:
        return None
    # ll fixes the point and q only labels the pin, so the label cannot move it.
    label = (ed or {}).get("venue_en") or ev["venue_en"]
    return {"lat": source["lat"], "lon": source["lon"],
            "url": f"https://maps.apple.com/?ll={source['lat']},{source['lon']}&q={quote(label)}"}


# The map of Japan

def _line_distance(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return math.hypot(x - x1, y - y1)
    return abs((x2 - x1) * (y1 - y) - (x1 - x) * (y2 - y1)) / length


def simplify(points: list, tolerance: float) -> list:
    """Douglas-Peucker: drop points closer than tolerance to the line they sit on.

    With a stack rather than recursion, since a prefecture's coast runs to thousands of points.
    """
    if len(points) < 3:
        return points
    keep, stack = {0, len(points) - 1}, [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        far, index = max((_line_distance(points[i], points[first], points[last]), i)
                         for i in range(first + 1, last))
        if far > tolerance:
            keep.add(index)
            stack += [(first, index), (index, last)]
    return [points[i] for i in sorted(keep)]


def map_point(lat: float, lon: float) -> tuple[float, float]:
    """The one projection: the coastline and every dot go through it, so they cannot disagree."""
    return round((lon - MAP_LON[0]) * MAP_X, 1), round((MAP_LAT[1] - lat) * MAP_SCALE, 1)


def japan_path() -> str:
    rings = json.loads(MAP_OUTLINE.read_text(encoding="utf-8"))
    return " ".join("M" + " ".join("%g,%g" % map_point(lat, lon) for lon, lat in ring) + "Z"
                    for ring in rings)
