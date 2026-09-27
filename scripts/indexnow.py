#!/usr/bin/env python3
"""Tell IndexNow search engines (Bing and others) which pages a deploy changed.

Two steps, run by .github/workflows/build.yml:
  changed  In the build job, before deploy. Compares each page in site/sitemap.xml with the
           live copy and prints the URLs that differ, space-separated. The live site is the
           record of what was last sent, so nothing else has to be stored.
  submit   In the indexnow job, after deploy. Sends those URLs to api.indexnow.org.

IndexNow asks for changed pages only, so an unchanged page is never sent. If the live site
does not serve the key file yet, this is the first run and every page is sent once.
Neither step can stop a deploy: see the workflow for how.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import INDEXNOW_KEY, ROOT, SITE_URL  # noqa: E402

ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_URL = f"{SITE_URL}/{INDEXNOW_KEY}.txt"
USER_AGENT = "ClassicMotoringJapan-deploy"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
# Our mistakes: the run should go red so they get fixed.
CONFIG_ERRORS = {400, 403, 422}


def sitemap_urls(site_dir: Path) -> list[str]:
    tree = ET.parse(site_dir / "sitemap.xml")
    return [loc.text for loc in tree.getroot().findall("sm:url/sm:loc", SITEMAP_NS)]


def local_path(site_dir: Path, url: str) -> Path:
    rel = url.removeprefix(SITE_URL + "/")
    return site_dir / (rel + "index.html" if rel == "" or rel.endswith("/") else rel)


def changed_urls(site_dir: Path, fetch) -> list[str]:
    """fetch(url) returns the live bytes, or None for a 404, a timeout or any other failure.

    A page that could not be fetched counts as changed: sending one page too many costs
    nothing, while missing a change leaves it unindexed.
    """
    urls = sitemap_urls(site_dir)
    if fetch(KEY_URL) != INDEXNOW_KEY.encode("utf-8"):
        return urls
    return [u for u in urls if fetch(u) != local_path(site_dir, u).read_bytes()]


def payload(urls: list[str]) -> dict:
    return {"host": SITE_URL.split("://", 1)[1], "key": INDEXNOW_KEY,
            "keyLocation": KEY_URL, "urlList": urls}


def outcome(status: int | None) -> str:
    """'ok', 'fail' (our mistake: go red) or 'warn' (theirs, or the network's: stay green)."""
    if status in (200, 202):
        return "ok"
    if status in CONFIG_ERRORS:
        return "fail"
    return "warn"


def live_fetch(url: str) -> bytes | None:
    # Pages sits behind a CDN that caches for minutes; a unique query string skips that cache.
    req = urllib.request.Request(f"{url}?indexnow={time.time_ns()}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def post(body: dict) -> int | None:
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8",
                                          "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def main(argv: list[str]) -> int:
    if argv[1:] == ["changed"]:
        urls = changed_urls(ROOT / "site", live_fetch)
        print(" ".join(urls))
        print(f"{len(urls)} changed page(s)", file=sys.stderr)
        return 0
    if argv[1:] == ["submit"]:
        urls = os.environ.get("URLS", "").split()
        if not urls:
            print("No changed pages to submit.")
            return 0
        status = post(payload(urls))
        result = outcome(status)
        print(f"IndexNow answered {status} for {len(urls)} page(s): {result}")
        if result == "fail":
            print(f"::error::IndexNow rejected the request ({status}). Check INDEXNOW_KEY in "
                  f"scripts/build.py and that {KEY_URL} is live.")
            return 1
        if result == "warn":
            print(f"::warning::IndexNow did not accept the pages ({status}). They go again "
                  f"only if they change again; the site itself deployed normally.")
        return 0
    print("usage: indexnow.py changed | submit", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
