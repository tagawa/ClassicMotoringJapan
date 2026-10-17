"""Tests for scripts/check_links.py. Offline: every fetch is a stand-in."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import ROOT, instance_yaml, write_event, write_instance  # noqa: E402

import check_links  # noqa: E402  (scripts/ is on the path via test_build)

OEMBED = check_links.OEMBED_URL + "gDq-2nEG3Y8"


class CollectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        data = cls.tmp / "data"
        write_event(data, "meet", extra="summary_en: Run by [the club](https://club.example.com/).\n")
        write_instance(data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-11-03", "2026-11-03",
            extra="videos:\n  - youtube_id: gDq-2nEG3Y8\n    label_en: Film\n"))
        write_instance(data, "meet", 2027, instance_yaml(
            "meet", 2027, "2027-11-03", "2027-11-03",
            extra="route_en: Same as [the club page](https://club.example.com/).\n"))
        cls.urls = check_links.collect_urls(data)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_finds_every_kind_of_link_and_where_it_is_used(self):
        self.assertEqual(self.urls, {
            "https://example.com/meet/": ["events/meet.yml"],
            "https://example.com/meet/2026/": ["events/meet/2026.yml"],
            "https://example.com/meet/2027/": ["events/meet/2027.yml"],
            "https://club.example.com/": ["events/meet.yml", "events/meet/2027.yml"],
            OEMBED: ["events/meet/2026.yml"],
        })

    def test_finds_links_in_the_real_data(self):
        self.assertGreater(len(check_links.collect_urls(ROOT / "data")), 0)


class VerdictTests(unittest.TestCase):
    def test_gone_or_unresolvable_is_dead(self):
        for status, dns in ((404, False), (410, False), (None, True)):
            self.assertEqual(check_links.verdict("https://a.example/", status, dns), "dead")

    def test_working_is_ok(self):
        self.assertEqual(check_links.verdict("https://a.example/", 200, False), "ok")

    def test_blocked_busy_or_timed_out_is_unsure(self):
        # A site that refuses a script, or is down for an hour, has not gone.
        for status in (401, 403, 429, 500, 503, None):
            self.assertEqual(check_links.verdict("https://a.example/", status, False), "unsure", status)

    def test_a_video_youtube_will_not_describe_is_dead(self):
        # oEmbed answers 4xx for a removed, private or unembeddable video, all of which break the page.
        for status in (400, 401, 403, 404):
            self.assertEqual(check_links.verdict(OEMBED, status, False), "dead", status)
        self.assertEqual(check_links.verdict(OEMBED, 429, False), "unsure")


class CheckTests(unittest.TestCase):
    def run_check(self, answers: dict):
        calls = {}

        def fetch(url):
            calls[url] = calls.get(url, 0) + 1
            return answers[url][min(calls[url], len(answers[url])) - 1]

        return check_links.check({u: ["events/x.yml"] for u in answers}, fetch, pause=0)

    def test_dead_twice_is_reported(self):
        self.assertEqual(self.run_check({"https://a.example/": [(404, False)]}),
                         {"dead": ["https://a.example/"], "unsure": []})

    def test_dead_once_then_working_is_not(self):
        self.assertEqual(self.run_check({"https://a.example/": [(None, True), (200, False)]}),
                         {"dead": [], "unsure": []})

    def test_unsure_is_listed_apart(self):
        self.assertEqual(self.run_check({"https://a.example/": [(403, False)], "https://b.example/": [(200, False)]}),
                         {"dead": [], "unsure": ["https://a.example/"]})


class WorkflowTests(unittest.TestCase):
    """A dead link must never stop the site publishing, so the check runs on its own timetable."""

    def test_runs_weekly_in_its_own_workflow(self):
        wf = (ROOT / ".github/workflows/links.yml").read_text(encoding="utf-8")
        self.assertIn("schedule:", wf)
        self.assertIn("python scripts/check_links.py", wf)

    def test_build_and_deploy_does_not_run_it(self):
        self.assertNotIn("check_links", (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
