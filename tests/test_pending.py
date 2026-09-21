"""Tests for scripts/pending.py: what still needs uploading to github.com.

The network call is not exercised here. Everything that decides an answer is a
pure function over a file tree and a remote manifest, and that is what is tested.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pending  # noqa: E402


class BlobShaTests(unittest.TestCase):
    """The hashes must be git's, or every file would look changed."""

    def test_empty_file(self):
        self.assertEqual(pending.blob_sha(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")

    def test_known_content(self):
        self.assertEqual(pending.blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")


class LocalManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for rel in ("data/events/shcc.yml", "scripts/build.py", "templates/home.html",
                    "static/style.css", "tests/test_build.py", "requirements.txt",
                    ".gitignore", ".github/workflows/build.yml",
                    "site/index.html", "site/events/shcc/index.html",
                    "docs/spec_v5.md", "README.md", "CLAUDE.md",
                    ".venv/bin/python", "scripts/__pycache__/build.cpython-313.pyc",
                    "data/.DS_Store", ".DS_Store"):
            p = self.tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        self.paths = set(pending.local_manifest(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_build_inputs_are_included(self):
        for rel in ("data/events/shcc.yml", "scripts/build.py", "templates/home.html",
                    "static/style.css", "tests/test_build.py", "requirements.txt",
                    ".gitignore", ".github/workflows/build.yml"):
            self.assertIn(rel, self.paths)

    def test_build_output_is_excluded(self):
        # site/ is rebuilt by Actions on every commit; uploading it would go stale at once.
        self.assertFalse({p for p in self.paths if p.startswith("site/")}, "site/ must never be uploaded")

    def test_private_files_are_excluded(self):
        for rel in ("docs/spec_v5.md", "README.md", "CLAUDE.md"):
            self.assertNotIn(rel, self.paths)

    def test_local_junk_is_excluded(self):
        for rel in (".venv/bin/python", "scripts/__pycache__/build.cpython-313.pyc",
                    "data/.DS_Store", ".DS_Store"):
            self.assertNotIn(rel, self.paths)


class CompareTests(unittest.TestCase):
    def test_classifies_new_changed_and_remote_only(self):
        local = {"a.yml": "1", "b.yml": "2", "c.yml": "3"}
        remote = {"b.yml": "changed", "c.yml": "3", "LICENSE": "9"}
        new, changed, remote_only = pending.compare(local, remote)
        self.assertEqual(new, ["a.yml"])
        self.assertEqual(changed, ["b.yml"])
        self.assertEqual(remote_only, ["LICENSE"])

    def test_nothing_pending_when_everything_matches(self):
        manifest = {"a.yml": "1", "b.yml": "2"}
        new, changed, remote_only = pending.compare(manifest, dict(manifest))
        self.assertEqual((new, changed, remote_only), ([], [], []))


if __name__ == "__main__":
    unittest.main()
