"""Tests for scripts/indexnow.py. Offline: the live site and the endpoint are stand-ins."""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_build import ROOT, build, make_fixture  # noqa: E402

import indexnow  # noqa: E402  (scripts/ is on the path via test_build)


class KeyFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_key_file_sits_at_the_root_and_holds_only_the_key(self):
        # At the root, because a key file in a folder only covers URLs under that folder.
        self.assertEqual((self.out / f"{build.INDEXNOW_KEY}.txt").read_text(encoding="utf-8"),
                         build.INDEXNOW_KEY)

    def test_key_meets_the_protocol(self):
        self.assertRegex(build.INDEXNOW_KEY, r"^[0-9a-f]{8,128}$")

    def test_every_sitemap_url_maps_to_a_built_file(self):
        urls = indexnow.sitemap_urls(self.out)
        self.assertIn(f"{build.SITE_URL}/", urls)
        for url in urls:
            self.assertTrue(indexnow.local_path(self.out, url).is_file(), url)


class ChangedUrlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)
        cls.urls = indexnow.sitemap_urls(cls.out)
        cls.home = f"{build.SITE_URL}/"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def live(self, overrides=None):
        """A live site identical to the build, except where overrides says otherwise."""
        overrides = overrides or {}

        def fetch(url):
            if url in overrides:
                return overrides[url]
            if url == indexnow.KEY_URL:
                return build.INDEXNOW_KEY.encode("utf-8")
            return indexnow.local_path(self.out, url).read_bytes()
        return fetch

    def test_nothing_changed_sends_nothing(self):
        self.assertEqual(indexnow.changed_urls(self.out, self.live()), [])

    def test_only_the_changed_page_is_sent(self):
        fetch = self.live({self.home: b"<html>older build</html>"})
        self.assertEqual(indexnow.changed_urls(self.out, fetch), [self.home])

    def test_a_page_that_could_not_be_fetched_is_sent(self):
        # A new page 404s on the live site; a timeout looks the same.
        self.assertEqual(indexnow.changed_urls(self.out, self.live({self.home: None})), [self.home])

    def test_first_run_sends_every_page(self):
        # No key file live yet: nothing has ever been sent, so everything goes once.
        fetch = self.live({indexnow.KEY_URL: None})
        self.assertEqual(indexnow.changed_urls(self.out, fetch), self.urls)


class SubmitTests(unittest.TestCase):
    def test_payload_names_this_host_and_its_key(self):
        body = indexnow.payload([f"{build.SITE_URL}/"])
        self.assertEqual(body["host"], "classicmotoringjapan.com")
        self.assertEqual(body["key"], build.INDEXNOW_KEY)
        self.assertEqual(body["keyLocation"], f"{build.SITE_URL}/{build.INDEXNOW_KEY}.txt")
        self.assertEqual(body["urlList"], [f"{build.SITE_URL}/"])

    def test_outcomes(self):
        cases = {200: "ok", 202: "ok", 400: "fail", 403: "fail", 422: "fail",
                 429: "warn", 500: "warn", None: "warn"}
        for status, expected in cases.items():
            self.assertEqual(indexnow.outcome(status), expected, status)


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wf = yaml.safe_load((ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8"))

    def test_comparison_runs_before_deploy_and_cannot_block_it(self):
        steps = self.wf["jobs"]["build"]["steps"]
        step, = [s for s in steps if s.get("id") == "indexnow"]
        self.assertIs(step.get("continue-on-error"), True)
        self.assertIn("indexnow.py changed", step["run"])

    def test_submission_waits_for_the_deploy(self):
        job = self.wf["jobs"]["indexnow"]
        self.assertIn("deploy", job["needs"])
        self.assertTrue(any("indexnow.py submit" in s.get("run", "") for s in job["steps"]))


if __name__ == "__main__":
    unittest.main()
