#!/usr/bin/env python3
"""Check every outbound link in data/ and fail if any has gone.

Run weekly by .github/workflows/links.yml, never by the build, so a dead link
cannot stop the site publishing. GitHub emails the owner when a scheduled run
fails, which is the whole point: organisers' pages move without telling anyone.

Only a link that is certainly gone fails the run (404, 410, a domain that no
longer resolves, or a video YouTube will not describe). A site that refuses a
script, rate-limits or times out is listed as unsure and leaves the run green,
since a false alarm every week would teach everyone to ignore the email.

    python scripts/check_links.py
"""
from __future__ import annotations

import re
import socket
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import LINK_RE, ROOT, VIDEO_WATCH_URL, load_and_validate  # noqa: E402

USER_AGENT = "ClassicMotoringJapan-linkcheck (+https://classicmotoringjapan.com/)"
# The watch page answers 200 even for a removed video; oEmbed does not.
OEMBED_URL = "https://www.youtube.com/oembed?format=json&url=" + VIDEO_WATCH_URL
URL_RE = re.compile(r"https?://\S+")
GONE = {404, 410}


def _walk(value, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, v in value.items():
            if key == "youtube_id":
                found.add(OEMBED_URL + v)
            else:
                _walk(v, found)
    elif isinstance(value, list):
        for v in value:
            _walk(v, found)
    elif isinstance(value, str):
        if URL_RE.fullmatch(value):
            found.add(value)
        found.update(m.group(2) for m in LINK_RE.finditer(value))


def collect_urls(data_dir: Path) -> dict[str, list[str]]:
    """Each URL, with the data files that use it."""
    events, editions = load_and_validate(data_dir)
    sources = [(f"events/{slug}.yml", ev) for slug, ev in events.items()]
    sources += [(f"events/{e['data']['slug']}/{e['id']}.yml", e["data"]) for e in editions]
    urls: dict[str, list[str]] = {}
    for rel, record in sources:
        found: set[str] = set()
        _walk(record, found)
        for url in found:
            urls.setdefault(url, []).append(rel)
    return {u: sorted(files) for u, files in urls.items()}


def verdict(url: str, status: int | None, dns_failed: bool) -> str:
    """'ok', 'dead' or 'unsure'. status is None when no answer came back."""
    if dns_failed or status in GONE:
        return "dead"
    if status is not None and status < 400:
        return "ok"
    if url.startswith(OEMBED_URL) and status is not None and 400 <= status < 500 and status != 429:
        return "dead"
    return "unsure"


def live_fetch(url: str) -> tuple[int | None, bool]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, False
    except urllib.error.HTTPError as e:
        return e.code, False
    except urllib.error.URLError as e:
        return None, isinstance(e.reason, socket.gaierror)
    except (TimeoutError, OSError):
        return None, False


def check(urls: dict[str, list[str]], fetch=live_fetch, pause: float = 30) -> dict[str, list[str]]:
    def judge(url: str) -> str:
        return verdict(url, *fetch(url))

    with ThreadPoolExecutor(max_workers=8) as pool:
        first = dict(zip(urls, pool.map(judge, urls)))
    # A second look before calling anything dead, in case the first was a passing outage.
    suspects = [u for u, v in first.items() if v == "dead"]
    if suspects:
        time.sleep(pause)
    dead = [u for u in suspects if judge(u) == "dead"]
    return {"dead": sorted(dead), "unsure": sorted(u for u, v in first.items() if v == "unsure")}


def main() -> int:
    urls = collect_urls(ROOT / "data")
    result = check(urls)
    print(f"Checked {len(urls)} links.")
    for key, heading in (("dead", "Gone: fix these in data/"), ("unsure", "No clear answer (not a failure)")):
        print(f"\n{heading} ({len(result[key])})")
        for url in result[key]:
            print(f"  {url}\n    used in {', '.join('data/' + f for f in urls[url])}")
    return 1 if result["dead"] else 0


if __name__ == "__main__":
    sys.exit(main())
