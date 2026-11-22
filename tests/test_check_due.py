"""Tests for scripts/check_due.py: which editions need looking at, from the data alone.

Every case is a pure function of the loaded data and a date, so each test builds
the few events it needs and fixes "today" rather than reading the clock.
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import ROOT  # noqa: E402

import check_due  # noqa: E402  (scripts/ is on the path via helpers)
import validate  # noqa: E402

TODAY = dt.date(2026, 9, 27)


def day(offset: int) -> dt.date:
    return TODAY + dt.timedelta(days=offset)


def event(slug: str) -> dict:
    return {"slug": slug, "official_url": f"https://example.com/{slug}/", "last_verified": TODAY}


def edition(slug: str, ed_id: str, start: dt.date, end: dt.date | None = None,
            verified: dt.date = TODAY) -> dict:
    data = {"slug": slug, "start": start, "end": end or start, "last_verified": verified,
            "source_url": f"https://example.com/{slug}/{ed_id}/"}
    return {"data": data, "id": ed_id, "edition": None}


def keys(items: list[dict]) -> list[tuple[str, str]]:
    return [(i["slug"], i["id"]) for i in items]


class AfterTheEventTests(unittest.TestCase):
    """An edition that has ended but was last checked before it ended."""

    def run_due(self, ed):
        return check_due.due({"a": event("a")}, [ed], TODAY)["after"]

    def test_ended_and_checked_on_the_last_day(self):
        self.assertEqual(keys(self.run_due(edition("a", "2026", day(-3), verified=day(-3)))),
                         [("a", "2026")])

    def test_ended_and_checked_since(self):
        self.assertEqual(self.run_due(edition("a", "2026", day(-3), verified=day(-1))), [])

    def test_ends_today_has_not_ended(self):
        self.assertEqual(self.run_due(edition("a", "2026", day(-1), day(0), verified=day(-5))), [])

    def test_uses_the_end_date_not_the_start(self):
        # A four-day rally checked on its second day was checked before it ended.
        self.assertEqual(keys(self.run_due(edition("a", "2026", day(-5), day(-2), verified=day(-4)))),
                         [("a", "2026")])


class NextDateTests(unittest.TestCase):
    """An event with nothing still to come needs its next date found."""

    def test_only_past_editions(self):
        eds = [edition("a", "2024", day(-400)), edition("a", "2025", day(-30))]
        self.assertEqual([i["slug"] for i in check_due.due({"a": event("a")}, eds, TODAY)["next"]], ["a"])

    def test_an_upcoming_edition_clears_it(self):
        eds = [edition("a", "2025", day(-300)), edition("a", "2026", day(30))]
        self.assertEqual(check_due.due({"a": event("a")}, eds, TODAY)["next"], [])

    def test_an_edition_ending_today_is_still_to_come(self):
        eds = [edition("a", "2026", day(-1), day(0))]
        self.assertEqual(check_due.due({"a": event("a")}, eds, TODAY)["next"], [])

    def test_points_at_the_official_site_and_the_last_date(self):
        [item] = check_due.due({"a": event("a")}, [edition("a", "2025", day(-30))], TODAY)["next"]
        self.assertEqual(item["url"], "https://example.com/a/")
        self.assertEqual(item["date"], day(-30))


class RecheckTests(unittest.TestCase):
    """An upcoming edition not checked recently, and more often as it approaches."""

    def run_due(self, start, verified):
        return keys(check_due.due({"a": event("a")}, [edition("a", "2026", start, verified=verified)],
                            TODAY)["recheck"])

    def test_far_off_and_checked_over_four_weeks_ago(self):
        self.assertEqual(self.run_due(day(60), day(-29)), [("a", "2026")])

    def test_far_off_and_checked_four_weeks_ago(self):
        self.assertEqual(self.run_due(day(60), day(-28)), [])

    def test_within_a_fortnight_and_checked_over_a_week_ago(self):
        self.assertEqual(self.run_due(day(14), day(-8)), [("a", "2026")])

    def test_within_a_fortnight_and_checked_this_week(self):
        self.assertEqual(self.run_due(day(14), day(-7)), [])

    def test_beyond_a_fortnight_a_week_old_check_is_fine(self):
        self.assertEqual(self.run_due(day(15), day(-8)), [])

    def test_running_today_counts_as_upcoming(self):
        self.assertEqual(self.run_due(day(0), day(-8)), [("a", "2026")])

    def test_points_at_the_source(self):
        [item] = check_due.due({"a": event("a")}, [edition("a", "2026", day(60), verified=day(-40))],
                         TODAY)["recheck"]
        self.assertEqual(item["url"], "https://example.com/a/2026/")


class OrderTests(unittest.TestCase):
    def test_each_list_runs_by_date(self):
        events = {s: event(s) for s in "abc"}
        eds = [edition("a", "2026", day(50), verified=day(-40)),
               edition("b", "2026", day(10), verified=day(-40)),
               edition("c", "2026", day(30), verified=day(-40))]
        self.assertEqual([i["slug"] for i in check_due.due(events, eds, TODAY)["recheck"]], ["b", "c", "a"])


class ExitCodeTests(unittest.TestCase):
    """A failed run is what GitHub emails, so the run fails exactly when a session has work."""

    def test_fails_when_an_edition_awaits_its_post_event_check(self):
        result = check_due.due({"a": event("a")}, [edition("a", "2026", day(-3), verified=day(-3))], TODAY)
        self.assertEqual(check_due.exit_code(result), 1)

    def test_fails_when_an_upcoming_edition_needs_a_recheck(self):
        result = check_due.due({"a": event("a")}, [edition("a", "2026", day(60), verified=day(-40))], TODAY)
        self.assertEqual(check_due.exit_code(result), 1)

    def test_passes_when_an_event_only_awaits_its_next_date(self):
        # These can wait months, so failing on them would send the same email every day.
        result = check_due.due({"a": event("a")}, [edition("a", "2025", day(-30), verified=day(-1))], TODAY)
        self.assertTrue(result["next"])
        self.assertEqual(check_due.exit_code(result), 0)


class WorkflowTests(unittest.TestCase):
    def test_runs_daily_in_its_own_workflow(self):
        wf = (ROOT / ".github/workflows/due.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "0 0 * * *"', wf)
        self.assertIn("python scripts/check_due.py", wf)

    def test_build_and_deploy_does_not_run_it(self):
        # Something being due must never stop the site publishing.
        self.assertNotIn("check_due", (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8"))


class RealDataTests(unittest.TestCase):
    """The report must run over the live data and name every section."""

    def test_report_over_real_data(self):
        events, editions = validate.load_and_validate(ROOT / "data")
        report = check_due.format_report(check_due.due(events, editions, TODAY))
        for heading in ("After the event", "Next date", "Recheck before the event"):
            self.assertIn(heading, report)


if __name__ == "__main__":
    unittest.main()
