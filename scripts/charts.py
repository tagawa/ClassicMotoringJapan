"""Bar charts (years, decades, makes) and the route timetable chart."""
from __future__ import annotations

import datetime as dt

# Percent of the axis. An open-ended checkpoint has no width of its own but still
# has to be visible, so every bar gets a floor.
CHART_MIN_BAR = 1.0


def _minutes(hhmm: str) -> int:
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def route_chart(route) -> dict | None:
    """Day shapes on one shared axis: which day starts late, which one runs long.

    Derived from the same checkpoints the tables render, so the picture cannot
    disagree with the numbers beside it.
    """
    if not route:
        return None
    points = [(p, _minutes(p["start_time"]),
               _minutes(p["end_time"]) if p.get("end_time") else _minutes(p["start_time"]))
              for day in route for p in day["checkpoints"]]
    axis_start = min(begins for _, begins, _ in points) // 60 * 60
    # One hour past the last stop, so a bar that starts on the hour still sits inside.
    axis_end = (max(finishes for _, _, finishes in points) // 60 + 1) * 60
    span = axis_end - axis_start

    days = []
    for number, day in enumerate(route, 1):
        windows = [(_minutes(p["start_time"]),
                    _minutes(p["end_time"]) if p.get("end_time") else _minutes(p["start_time"]))
                   for p in day["checkpoints"]]
        stops = len(windows)
        days.append({
            "when": f"Day {number}, {day['date']:%a} {day['date'].day} {day['date']:%b}",
            "summary": (f"{_hhmm(min(b for b, _ in windows))} to {_hhmm(max(f for _, f in windows))}, "
                        f"{stops} stop{'' if stops == 1 else 's'}"),
            "bars": [{"left": round((begins - axis_start) / span * 100, 2),
                      "width": round(max((finishes - begins) / span * 100, CHART_MIN_BAR), 2)}
                     for begins, finishes in windows],
        })
    return {"start": _hhmm(axis_start), "end": _hhmm(axis_end), "days": days}


def decade_chart(cars) -> dict | None:
    """How an entry list falls by decade, counted from the rows the table renders.

    A decade with no cars keeps its row, so a gap in the field stays visible instead of
    closing up and reading as a run. A list without years has nothing to count. Cars the
    organiser gave no year for are counted in a closing line, so the strip still adds up
    to the table it sits above.
    """
    years = [car["year"] for car in cars or [] if "year" in car]
    if not years:
        return None
    counts: dict[int, int] = {}
    for year in years:
        decade = year // 10 * 10
        counts[decade] = counts.get(decade, 0) + 1
    peak = max(counts.values())
    rows = []
    for decade in range(min(counts), max(counts) + 10, 10):
        n = counts.get(decade, 0)
        rows.append({
            "label": f"{decade}s",
            "count": n,
            "unit": "car" if n == 1 else "cars",
            "width": round(max(n / peak * 100, CHART_MIN_BAR), 2) if n else 0,
        })
    undated = len(cars) - len(years)
    return {"rows": rows,
            "rest": f"No year given: {undated} car{'' if undated == 1 else 's'}" if undated else None}


def makes_chart(cars) -> dict | None:
    """Which makes an entry list has several of, counted from the rows the table renders.

    A make with one car would only repeat its table row, so those share a single line.
    Counted only when every row has an entry number: there a row is a car, whereas a
    show's announced line-up names models, and two models are not two cars.
    """
    if not cars or not all("entry_no" in car for car in cars):
        return None
    counts: dict[str, int] = {}
    for car in cars:
        counts[car["make"]] = counts.get(car["make"], 0) + 1
    several = sorted(((make, n) for make, n in counts.items() if n > 1),
                     key=lambda pair: (-pair[1], pair[0].casefold()))
    rows = [{"label": make, "count": n, "unit": "cars",
             "width": round(max(n / several[0][1] * 100, CHART_MIN_BAR), 2)} for make, n in several]
    singles = len(counts) - len(several)
    rest = None
    if singles:
        # "and" only when there are rows above for it to follow on from.
        rest = (("and " if rows else "")
                + (f"{singles} makes with one car each" if singles > 1 else "1 make with one car"))
    return {"rows": rows, "rest": rest}


def year_chart(rows: list[dict]) -> list[dict]:
    """Where a year's editions fall across its months: which season the hobby runs in."""
    years = []
    for year in sorted({r["year"] for r in rows}):
        editions = [r["ed"] for r in rows if r["year"] == year]
        days = dt.date(year, 12, 31).timetuple().tm_yday
        first, last = min(e["start"] for e in editions), max(e["start"] for e in editions)
        when = f"{first:%b}" if first.month == last.month else f"{first:%b} to {last:%b}"
        years.append({
            "year": year,
            "label": f"{year}: {len(editions)} event{'' if len(editions) == 1 else 's'}, {when}",
            "bars": [{"left": round((e["start"].timetuple().tm_yday - 1) / days * 100, 2),
                      "width": round(max(((e["end"] - e["start"]).days + 1) / days * 100,
                                         CHART_MIN_BAR), 2),
                      "cancelled": e["status"] == "cancelled",
                      # The browser greys the bars whose last day has passed; the build never reads the clock.
                      "end": e["end"].isoformat()}
                     for e in editions],
        })
    return years
