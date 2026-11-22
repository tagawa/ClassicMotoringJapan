"""The .ics feed, each edition's own .ics file, and add-to-calendar links."""
from __future__ import annotations

import datetime as dt
from urllib.parse import quote, urlencode

from settings import SITE_NAME

GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/render"


# iCalendar

def ics_text(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\\n").replace("\n", "\\n"))


def ics_fold(line: str) -> str:
    """Fold to 75 octets per physical line without splitting a UTF-8 character."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts, cur, limit = [], b"", 75
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > limit:
            parts.append(cur.decode("utf-8"))
            cur, limit = b"", 74
        cur += cb
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def event_location(r: dict) -> str:
    return f"{r['venue']}, {r['prefecture']}, Japan"


def event_details(r: dict) -> str:
    return "\n".join(filter(None, (r["ev"].get("name_ja"), r["abs_url"],
                                   f"Last verified {r['ed']['last_verified']}")))


def ics_event_lines(r: dict) -> list[str]:
    ed = r["ed"]
    lines = ["BEGIN:VEVENT", f"UID:{r['uid']}",
             f"DTSTAMP:{ed['last_verified']:%Y%m%d}T000000Z",
             f"SEQUENCE:{ed['sequence']}"]
    if r["is_timed"]:
        fmt = "%Y%m%dT%H%M%SZ"
        lines += [f"DTSTART:{r['start_dt'].astimezone(dt.timezone.utc):{fmt}}",
                  f"DTEND:{r['day_end_dt'].astimezone(dt.timezone.utc):{fmt}}"]
        if r["rrule"]:
            lines.append(f"RRULE:{r['rrule']}")
    else:
        lines += [f"DTSTART;VALUE=DATE:{ed['start']:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{ed['end'] + dt.timedelta(days=1):%Y%m%d}"]
    lines += [
        f"SUMMARY:{ics_text(r['display_name'])}",
        f"LOCATION:{ics_text(event_location(r))}",
    ]
    if r["pin"]:
        lines.append(f"GEO:{r['pin']['lat']};{r['pin']['lon']}")
    lines += [
        f"URL:{r['abs_url']}",
        f"DESCRIPTION:{ics_text(event_details(r))}",
        f"STATUS:{ed['status'].upper()}",
        "END:VEVENT",
    ]
    return lines


def ics_calendar(header: list[str], rows: list[dict]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{SITE_NAME}//Events//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"] + header
    for r in rows:
        lines += ics_event_lines(r)
    lines.append("END:VCALENDAR")
    return "".join(ics_fold(line) + "\r\n" for line in lines)


def google_calendar_url(r: dict) -> str:
    """Google's add-event form, filled in. Its Android app cannot open an .ics file at all."""
    details = event_details(r)
    if r["is_timed"] and not r["rrule"]:
        fmt = "%Y%m%dT%H%M%SZ"
        dates = (f"{r['start_dt'].astimezone(dt.timezone.utc):{fmt}}/"
                 f"{r['day_end_dt'].astimezone(dt.timezone.utc):{fmt}}")
    else:
        # An exclusive end, as in the feed. Google's form documents no repeat rule, so a
        # multi-day timed edition goes as all-day with its daily hours written out.
        dates = f"{r['ed']['start']:%Y%m%d}/{r['ed']['end'] + dt.timedelta(days=1):%Y%m%d}"
        if r["is_timed"]:
            details = (f"{r['ed']['start_time']} to {r['ed']['end_time']} Japan time each day\n"
                       + details)
    return GOOGLE_CALENDAR_URL + "?" + urlencode(
        {"action": "TEMPLATE", "text": r["display_name"], "dates": dates,
         "location": event_location(r), "details": details}, quote_via=quote)


def build_ics(rows: list[dict]) -> str:
    return ics_calendar([
        f"X-WR-CALNAME:{ics_text(SITE_NAME)}",
        # RFC 7986's spelling of the same thing. Neither reaches Thunderbird; see FEED_FILE.
        f"NAME:{ics_text(SITE_NAME)}",
    ], rows)
