"""Dates, fees and domains as the pages print them, and prose turned into text or HTML."""
from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urlparse

from markupsafe import Markup, escape

from settings import JST

# The one piece of markup prose may carry. https only: the target is fixed at build time,
# so there is no reason to link anywhere insecure, and nothing else can reach an href.
LINK_RE = re.compile(r"\[([^\[\]]+)\]\((https://[^\s()]+)\)")


def prose_blocks(v: str) -> list[tuple[str, str | list[str]]]:
    """Prose as ("p", text) and ("ul", items) blocks (spec 4.7).

    A line starting "- " begins an item, any other line continues the item or paragraph
    above it, and a blank line ends a list, so text after one needs a blank line.
    """
    blocks: list[tuple[str, str | list[str]]] = []
    for chunk in re.split(r"\n\s*\n", v.strip()):
        lead: list[str] = []
        items: list[list[str]] = []
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("- "):
                items.append([line[2:].strip()])
            elif items:
                items[-1].append(line)
            else:
                lead.append(line)
        if lead:
            blocks.append(("p", " ".join(lead)))
        if items:
            blocks.append(("ul", [" ".join(item) for item in items]))
    return blocks


def has_list(v: str) -> bool:
    return any(kind == "ul" for kind, _ in prose_blocks(v))


def prose_text(v: str) -> str:
    """Prose as a reader hears it: each link reduced to its text, a list read as one sentence."""
    if not has_list(v):
        return LINK_RE.sub(r"\1", v)
    parts = []
    for kind, body in prose_blocks(v):
        if kind == "ul":
            body = "; ".join(body)
            body += "" if body[-1] in ".!?" else "."
        parts.append(body)
    return LINK_RE.sub(r"\1", " ".join(parts))


# Kana, CJK punctuation, ideographs and full-width forms. A run keeps Latin letters, digits
# and spaces that sit between them (クラシックカーフェスティバルin桐生) and an address's
# closing number (中瀬2-1), so each name or address is one span.
_JA_CHAR = "[　-ヿ㐀-鿿＀-￯]"
JA_RUN_RE = re.compile(f"{_JA_CHAR}(?:{_JA_CHAR}|[ A-Za-z0-9-]+(?={_JA_CHAR}))*(?:[0-9](?:[0-9-]*[0-9])?)?")


def mark_ja(v: str) -> Markup:
    """Text for a page, escaped, with Japanese marked lang="ja" so a screen reader switches voice."""
    out, pos = [], 0
    for m in JA_RUN_RE.finditer(v):
        out += [escape(v[pos:m.start()]), Markup('<span lang="ja">{}</span>').format(m.group(0))]
        pos = m.end()
    out.append(escape(v[pos:]))
    return Markup("").join(out)


def prose_html(v: str) -> Markup:
    """Prose for a page: inline as before, or paragraphs and a list where it has one."""
    if not has_list(v):
        return _inline_html(v)
    out = []
    for kind, body in prose_blocks(v):
        if kind == "p":
            out.append(Markup("<p>{}</p>").format(_inline_html(body)))
        else:
            out.append(Markup("<ul>{}</ul>").format(
                Markup("").join(Markup("<li>{}</li>").format(_inline_html(item)) for item in body)))
    return Markup("").join(out)


def prose_para(v: str, cls: str = "") -> Markup:
    """Prose where the page wants a paragraph: a <div> instead once it holds a list,
    since a <ul> inside a <p> would close the paragraph."""
    attr = Markup(' class="{}"').format(cls) if cls else Markup("")
    tag = "div" if has_list(v) else "p"
    return Markup("<{0}{1}>{2}</{0}>").format(Markup(tag), attr, prose_html(v))


def _inline_html(v: str) -> Markup:
    """Escaped throughout, with each link made an anchor."""
    out, pos = [], 0
    for m in LINK_RE.finditer(v):
        out += [mark_ja(v[pos:m.start()]),
                Markup('<a href="{}">{}</a>').format(m.group(2), mark_ja(m.group(1)))]
        pos = m.end()
    out.append(mark_ja(v[pos:]))
    return Markup("").join(out)


def fmt_day(d: dt.date) -> str:
    return f"{d.day} {d:%b %Y}"


def fmt_range(start: dt.date, end: dt.date) -> str:
    if start == end:
        return fmt_day(start)
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}\u2013{end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{start.day} {start:%b} \u2013 {end.day} {end:%b %Y}"
    return f"{fmt_day(start)} \u2013 {fmt_day(end)}"


def fmt_span(start: dt.date, end: dt.date, year: bool = False) -> str:
    """A date or a run of days with weekdays, which is what a weekend is planned by.

    The year is left to a heading above it unless asked for, but a span across the new
    year always names both, since one heading cannot.
    """
    def day(d: dt.date) -> str:
        return f"{d:%a} {d.day}"
    if start.year != end.year:
        return f"{day(start)} {start:%b %Y} to {day(end)} {end:%b %Y}"
    tail = f" {end.year}" if year else ""
    if start == end:
        return f"{day(start)} {start:%b}{tail}"
    if start.month == end.month:
        return f"{day(start)} to {day(end)} {end:%b}{tail}"
    return f"{day(start)} {start:%b} to {day(end)} {end:%b}{tail}"


def fmt_leaf(start: dt.date, end: dt.date) -> tuple[str, str]:
    """A date as the home list's calendar leaf draws it: weekdays on the band, days beneath.

    The month heading above names the month, so the days name one only when they cross into the next.
    """
    if start == end:
        return f"{start:%a}", f"{start.day}"
    weekdays = f"{start:%a}\u2013{end:%a}"
    if (start.year, start.month) == (end.year, end.month):
        return weekdays, f"{start.day}\u2013{end.day}"
    return weekdays, f"{start.day} {start:%b}\u2013{end.day} {end:%b}"


def fmt_weekday(d: dt.date) -> str:
    return f"{d:%A} {d.day} {d:%B}"


def fmt_domain(url: str) -> str:
    # A source is named by where it is, since it is often a listing, a blog or a video
    # rather than the organiser's own page, and a domain is true of all of them.
    host = urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host


def fmt_fee(fee: int | None) -> str:
    # Self-describing, because the home page prints it with no label beside it.
    if fee is None:
        return "Admission not announced"
    return "Free to watch" if fee == 0 else f"\u00a5{fee:,}"


# Weekdays from a fixed string, never the locale, which differs between this Mac and the Actions runner.
WEEKDAYS_JA = "月火水木金土日"


def fmt_span_ja(start: dt.date, end: dt.date) -> str:
    """fmt_span for the /ja/ page: the month heading carries the year unless the span crosses it."""
    def day(d: dt.date) -> str:
        return f"{d.day}日({WEEKDAYS_JA[d.weekday()]})"
    if start.year != end.year:
        return f"{start.year}年{start.month}月{day(start)}〜{end.year}年{end.month}月{day(end)}"
    if start == end:
        return f"{start.month}月{day(start)}"
    if start.month == end.month:
        return f"{start.month}月{day(start)}〜{day(end)}"
    return f"{start.month}月{day(start)}〜{end.month}月{day(end)}"


def fmt_range_ja(start: dt.date, end: dt.date) -> str:
    """fmt_range in Japanese: dates without weekdays, the year always given."""
    head = f"{start.year}年{start.month}月{start.day}日"
    if start == end:
        return head
    if start.year != end.year:
        return f"{head}〜{end.year}年{end.month}月{end.day}日"
    if start.month != end.month:
        return f"{head}〜{end.month}月{end.day}日"
    return f"{head}〜{end.day}日"


def fmt_month_ja(key: str) -> str:
    year, month = key.split("-")
    return f"{year}年{int(month)}月"


def fmt_fee_ja(fee: int | None) -> str:
    if fee is None:
        return "入場料未発表"
    return "入場無料" if fee == 0 else f"入場料 {fee:,}円"


def fmt_edition(edition: str) -> str:
    return edition.replace("-", " ").capitalize()


def _local_dt(d: dt.date, hhmm: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=JST)
