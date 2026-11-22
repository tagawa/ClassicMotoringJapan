#!/usr/bin/env python3
"""Report which editions need looking at, from the data alone.

No fetching: every answer follows from the edition dates and when each was last
checked, so the report works for sources a script cannot read (Instagram,
flyers, pages drawn by JavaScript) as well as for those it can. tools/due.py
adds the local-only reminders on top.

    python scripts/check_due.py

Run daily by .github/workflows/due.yml. It fails when a post-event check or a recheck
is due, so GitHub emails the owner to open a session.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import validate  # noqa: E402

STALE_DAYS = 28
# Cancellations and late changes cluster in the run-up, so checks tighten then.
SOON_DAYS = 14
SOON_STALE_DAYS = 7


def due(events: dict, editions: list[dict], today: dt.date) -> dict[str, list[dict]]:
    after, recheck = [], []
    latest_end: dict[str, dt.date] = {}
    for item in editions:
        ed = item["data"]
        slug, start, end, checked = ed["slug"], ed["start"], ed["end"], ed["last_verified"]
        latest_end[slug] = max(end, latest_end.get(slug, end))
        entry = {"slug": slug, "id": item["id"], "last_verified": checked, "url": ed["source_url"]}
        if end < today:
            # Checked on or before the last day means nothing seen since it ran.
            if checked <= end:
                after.append({**entry, "date": end})
        else:
            limit = SOON_STALE_DAYS if (start - today).days <= SOON_DAYS else STALE_DAYS
            if (today - checked).days > limit:
                recheck.append({**entry, "date": start})
    nxt = [{"slug": slug, "id": None, "date": end, "last_verified": events[slug]["last_verified"],
            "url": events[slug]["official_url"]}
           for slug, end in latest_end.items() if end < today]
    by_date = lambda i: (i["date"], i["slug"])  # noqa: E731
    return {"after": sorted(after, key=by_date), "next": sorted(nxt, key=by_date),
            "recheck": sorted(recheck, key=by_date)}


SECTIONS = (
    ("after", "After the event", "ended", "videos, a cancellation, the final entry list"),
    ("next", "Next date", "last ran", "nothing still to come"),
    ("recheck", "Recheck before the event", "starts", "not checked recently"),
)


def format_report(result: dict[str, list[dict]]) -> str:
    lines = []
    for key, heading, verb, why in SECTIONS:
        items = result[key]
        lines.append(f"{heading} ({len(items)}): {why}")
        for i in items:
            name = f"{i['slug']}/{i['id']}" if i["id"] else i["slug"]
            lines.append(f"  {name}: {verb} {i['date']}, checked {i['last_verified']}")
            lines.append(f"    {i['url']}")
        lines.append("")
    return "\n".join(lines)


def exit_code(result: dict[str, list[dict]]) -> int:
    # "next" is left out: an event can wait months for its next date, and a failure
    # every day for it would teach the owner to ignore the email.
    return 1 if result["after"] or result["recheck"] else 0


def main() -> int:
    # Japan's date, since every edition date in the data is a Japanese one.
    today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).date()
    events, editions = validate.load_and_validate(ROOT / "data")
    result = due(events, editions, today)
    print(format_report(result), end="")
    return exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
