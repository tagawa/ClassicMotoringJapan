"""The site's languages: each one's interface text and formatters (spec 6.6).

English is the first language and stays at the site root; every other one mirrors it
under /<code>/. A template reads its words from `t` and formats values through the
same filter names in every language. It names a language only where English pages
add the Japanese form beside a name (spec 7).
"""
from __future__ import annotations

from markupsafe import Markup, escape

import re

from formatting import (WEEKDAYS_JA, fmt_domain, fmt_fee, fmt_fee_ja, fmt_month_ja, fmt_span, fmt_span_ja, fmt_weekday,
                        mark_ja)
from settings import COUNTRIES, PREFECTURES_JA
from validate import BuildError

LANGUAGES = ("en", "ja")
PREFIX = {"en": "", "ja": "ja/"}
# Each language's name in itself, for the header link to it.
LANGUAGE_NAMES = {"en": "English", "ja": "日本語"}


def _en(text: str) -> str:
    """Latin text inside Japanese interface text, marked so a screen reader reads it as English."""
    return f'<span lang="en">{text}</span>'


class Text(dict):
    """Interface text. Jinja renders an unknown name as empty text, so a typo fails here instead."""

    def __init__(self, entries: dict):
        # The site's own words, so marked safe: escaping would turn "organiser's" into &#39;.
        super().__init__({k: Markup(v) if isinstance(v, str) else v for k, v in entries.items()})

    def __missing__(self, key: str):
        raise BuildError([f"No interface text '{key}'"])


TEXT = {
    "en": Text({
        # base.html
        "nav_cars": "Cars",
        "feed_subscribe": "Subscribe to all events in Apple Calendar or Outlook",
        "feed_after": ". Dates update automatically.",
        "feed_google": "Google Calendar",
        "feed_google_help": "Under Other calendars, choose From URL and paste",
        "link_youtube": "YouTube channel",
        "link_issues": "Report an error on GitHub",
        "link_about": "About this site",
        # icons.html
        "map": "Map",
        "add_apple": "Add to Apple Calendar or Outlook",
        "add_google": "Add to Google Calendar",
        "photo_caption": lambda year: f"Photo: {year} event",
        # An event photo that is also a make page's (spec 4.10); car arrives as markup, a link.
        "photo_car_caption": lambda car, year: Markup("Photo: {} at the {} event").format(car, year),
        "photographed_heading": "Car photos from this event",
        # A make page's photo (spec 4.12). car and where arrive as markup, the second a link or empty.
        "car_photo_caption": lambda car, where: Markup("Photo: {}").format(car)
                                                 + (Markup(" at {}").format(where) if where else ""),
        "car_year": lambda year: f"{year} ",
        "photo_year": lambda year: f"{year}",
        "photo_by": ", by ",
        "sep": ", ",
        # edition.html
        "crumb_home": "Home",
        "breadcrumb": "Breadcrumb",
        "unconfirmed_after": " does not confirm these dates yet.",
        "cancelled_note": "This event is cancelled.",
        "when": "When",
        "where": "Where",
        "cost": "Cost",
        "last_verified": "Last verified",
        "against_open": ", against ",
        "against_close": "",
        "other_events": "Other events",
        "previous_event": "Previous event: ",
        "next_event": "Next event: ",
        "cancelled_suffix": " (cancelled)",
        "unconfirmed_suffix": " (dates not confirmed)",
        "videos_of": lambda label: f"Videos of the {label} event",
        "on_this_page": "On this page",
        "route": "Route",
        "route_map_label": "Map of the route's stops in timetable order",
        "route_map_caption": "Stops in timetable order, joined by straight lines, not the roads.",
        "route_map_overnight": " Ringed stops are overnight.",
        "route_day": lambda n, date: f"Day {n}: {date}",
        "col_time": "Time",
        "col_place": "Place",
        "col_prefecture": "Prefecture",
        "as_of": lambda date: f"As of {date}.",
        "provisional": lambda caveat: f" Provisional: {caveat}.",
        "by_decade": "By decade",
        "by_make": "By make",
        "all_cars": lambda n: f"All {n} cars" if n > 1 else "1 car",
        "course_map": "Course map",
        "course_map_label": "Map of the time trial course, from start to finish",
        "course_map_caption": "Redrawn from the organiser's course map",
        "bracket_open": " (",
        "bracket_close": ")",
        "full_stop": ".",
        "videos": "Videos",
        "from_event": lambda label: f"From the {label} event",
        "title_sep": ": ",
        "colon": ": ",
        "time_to": "–",
        # event.html
        "event_title": lambda name: f"{name}: Visitor Guide",
        "dates": "Dates",
        "col_event": "Event",
        "col_status": "Status",
        "details": "Details",
        "not_confirmed": "Not confirmed",
        "cancelled": "Cancelled",
        "confirmed": "Confirmed",
        "held": "Held",
        "no_dates": "No dates announced yet.",
        "visiting": "Visiting",
        "getting_there": "Getting there",
        "nearest_station": "Nearest station: ",
        "watching": "Watching",
        "photography": "Photography",
        "what_youll_see": "What you'll see",
        "organiser": "Organiser",
        "source": "Source",
        "source_language": " (Japanese)",
        # home.html, its script's words included
        "home_title": "Classic car events in Japan",
        "home_heading": "Classic car events in Japan",
        "quarter": lambda month: ("Jan", "Apr", "Jul", "Oct")[month // 3],
        "events": "Events",
        "no_upcoming": "No upcoming dates are confirmed yet. New dates appear here and in the calendar feed as organisers announce them.",
        "date_not_confirmed": "Date not confirmed",
        "driven_route": "Driven route",
        "cars_to": lambda year: f"Cars to {year}",
        "past_events": "Past events",
        "show_past": "Show past events",
        "show_before": "Show ",
        "show_one": " event",
        "show_many": " events",
        "upcoming": "Upcoming",
        "this_weekend": "This weekend",
        "today": "Today",
        "most_recent_check": "Most recent check: ",
        # cars.html and car_group.html
        "cars_heading": "Cars by make",
        "counts_note": "Counts come only from events whose organisers publish entry lists.",
        "col_make": "Make",
        "col_cars": "Cars",
        "col_events": "Events",
        "page_note": lambda title: f"On the {title} page",
        "events_where": lambda title: f"Events where {title} cars have run",
        "next_dates": "Next dates",
        "col_event_name": "Event",
        "col_next_date": "Next date",
        "col_latest": "Cars, latest list",
        "next_not_announced": "Next date not announced",
        "no_date": "No date announced yet",
        "entry_lists": "Entry lists",
        "col_date": "Date",
        "col_count": "Count",
        "provisional_list": ", provisional list",
    }),
    # Drafted by Claude, to be reviewed by the owner before upload (spec 7).
    "ja": Text({
        "nav_cars": "車種",
        "feed_subscribe": f"全イベントを{_en('Apple')}カレンダー・{_en('Outlook')}に登録",
        "feed_after": "。日程は自動で更新されます。",
        "feed_google": f"{_en('Google')}カレンダー",
        # Google's own Japanese help writes [URL で追加], with the space (checked by the reviewer, 2026-11-24).
        "feed_google_help": f"「他のカレンダー」の「{_en('URL')} で追加」を選び、次の{_en('URL')}を貼り付けます：",
        "link_youtube": f"{_en('YouTube')}チャンネル",
        "link_issues": f"誤りを{_en('GitHub')}で報告",
        "link_about": "このサイトについて（英語）",
        "map": "地図",
        "add_apple": f"{_en('Apple')}カレンダー・{_en('Outlook')}に追加",
        "add_google": f"{_en('Google')}カレンダーに追加",
        "photo_caption": lambda year: f"写真：{year}年開催時",
        "photo_car_caption": lambda car, year: Markup("写真：{}（{}年開催時）").format(car, year),
        "photographed_heading": "この開催時に撮影された車の写真",
        "car_photo_caption": lambda car, where: Markup("写真：{}").format(car)
                                                 + (Markup("（{}開催時）").format(where) if where else ""),
        "car_year": lambda year: f"{year}年式 ",
        "photo_year": lambda year: f"{year}年",
        "photo_by": "、撮影：",
        "sep": "、",
        "crumb_home": "ホーム",
        "breadcrumb": "現在地",
        "unconfirmed_after": "では、まだ日程が確定していません。",
        "cancelled_note": "この回は中止です。",
        "when": "日時",
        "where": "会場",
        "cost": "料金",
        "last_verified": "最終確認",
        "against_open": "（情報元：",
        "against_close": "）",
        "other_events": "ほかの回",
        "previous_event": "前回：",
        "next_event": "次回：",
        "cancelled_suffix": "（中止）",
        "unconfirmed_suffix": "（日程未確定）",
        "videos_of": lambda label: f"{label}の動画",
        "on_this_page": "このページの内容",
        "route": "ルート",
        "route_map_label": "ルートの立ち寄り地点を時刻表順に結んだ地図",
        "route_map_caption": "立ち寄り地点を時刻表順に直線で結んだもので、実際の道路ではありません。",
        "route_map_overnight": "二重丸は宿泊地です。",
        "route_day": lambda n, date: f"{n}日目：{date}",
        "col_time": "時刻",
        "col_place": "場所",
        "col_prefecture": "都道府県",
        "as_of": lambda date: f"{date}時点。",
        "provisional": lambda caveat: f"暫定：{caveat}。",
        "by_decade": "年代別",
        "by_make": "メーカー別",
        "all_cars": lambda n: f"全{n}台" if n > 1 else "1台",
        "course_map": "コース図",
        "course_map_label": "タイムトライアルのコース図（スタートからゴールまで）",
        "course_map_caption": "主催者のコース図をもとに作図",
        "bracket_open": "（",
        "bracket_close": "）",
        "full_stop": "。",
        "videos": "動画",
        "from_event": lambda label: f"{label}の様子",
        "title_sep": "：",
        "colon": "：",
        "time_to": "〜",
        "event_title": lambda name: f"{name}：来場ガイド",
        "dates": "日程",
        "col_event": "開催回",
        "col_status": "状況",
        "details": "詳細",
        "not_confirmed": "日程未確定",
        "cancelled": "中止",
        "confirmed": "開催予定",
        "held": "開催済み",
        "no_dates": "日程はまだ発表されていません。",
        "visiting": "来場案内",
        "getting_there": "アクセス",
        "nearest_station": "最寄り駅：",
        "watching": "観覧",
        "photography": "撮影",
        "what_youll_see": "車両の年代",
        "organiser": "主催",
        "source": "情報元",
        # The sources are Japanese, so a Japanese page has nothing to warn of.
        "source_language": "",
        "home_title": "日本のクラシックカーイベント",
        # Break points for word-break: keep-all, or the heading splits mid-word on a phone.
        "home_heading": "日本の<wbr>クラシックカー<wbr>イベント",
        "quarter": lambda month: f"{month + 1}月",
        "events": "イベント",
        "no_upcoming": "今後の日程はまだ確定していません。主催者の発表に合わせて、このページとカレンダーに追加されます。",
        "date_not_confirmed": "日程未確定",
        "driven_route": "ルート走行",
        "cars_to": lambda year: f"{year}年式まで",
        "past_events": "過去のイベント",
        "show_past": "過去のイベントを表示",
        "show_before": "過去の",
        "show_one": "件を表示",
        "show_many": "件を表示",
        "upcoming": "今後のイベント",
        "this_weekend": "今週末",
        "today": "今日",
        "most_recent_check": "最終確認：",
        "cars_heading": "メーカー別の車両",
        "counts_note": "台数は、エントリーリストを公開しているイベントのみの集計です。",
        "col_make": "メーカー",
        "col_cars": "台数",
        "col_events": "イベント数",
        # The make cell is marked English, so the note marks itself Japanese.
        "page_note": lambda title: Markup('<span lang="ja">{}のページに掲載</span>').format(title),
        "events_where": lambda title: Markup("{}が参加したイベント").format(title),
        "next_dates": "次回の日程",
        "col_event_name": "イベント",
        "col_next_date": "次回",
        "col_latest": "台数（最新のリスト）",
        "next_not_announced": "次回日程は未発表",
        "no_date": "日程未発表",
        "entry_lists": "エントリーリスト",
        "col_date": "日程",
        "col_count": "台数",
        "provisional_list": "（暫定リスト）",
    }),
}

# Edition words as file names give them (2026-spring.yml). A word missing here fails the build.
EDITION_WORDS_JA = {"spring": "春", "autumn": "秋", "september": "9月", "new-year": "新春"}
# typical_eras values other than decades ("1950s"), which era_ja writes itself.
ERAS_JA = {"Prewar": "戦前"}
COUNTRY_NAMES_JA = {"BR": "ブラジル", "CN": "中国", "DE": "ドイツ", "FR": "フランス", "GB": "イギリス",
                    "IT": "イタリア", "JP": "日本", "SE": "スウェーデン", "US": "アメリカ"}


# A run of Latin script inside Japanese text: "in Kawajima", "SHCC", "ANA".
LATIN_RUN_RE = re.compile(r"[A-Za-z][A-Za-z0-9.'&-]*(?: [A-Za-z0-9][A-Za-z0-9.'&-]*)*")


def mark_latin(text: str) -> Markup:
    """Japanese text, escaped, with any Latin run marked lang="en" (the reverse of mark_ja)."""
    out, pos = [], 0
    for m in LATIN_RUN_RE.finditer(text):
        out += [escape(text[pos:m.start()]), Markup('<span lang="en">{}</span>').format(m.group(0))]
        pos = m.end()
    out.append(escape(text[pos:]))
    return Markup("").join(out)


def span_ja(start, end, year: bool = False) -> str:
    """fmt_span in Japanese: the year only when asked for, or when the span crosses one."""
    text = fmt_span_ja(start, end)
    return f"{start.year}年{text}" if year and start.year == end.year else text


def ymd_ja(d) -> str:
    return f"{d.year}年{d.month}月{d.day}日"


def weekday_ja(d) -> str:
    return f"{d.month}月{d.day}日({WEEKDAYS_JA[d.weekday()]})"


def address_ja(address: str):
    """The Japanese written in brackets after the romanised address, else the address marked English."""
    m = re.search(r"\(([^()]*[\u3040-\u9fff][^()]*)\)", address)
    return m.group(1) if m else Markup('<span lang="en">{}</span>').format(address)


def organiser_ja(organiser: str) -> Markup:
    """The Japanese name before the first bracket, without the English gloss and notes after it (spec 6.6)."""
    head = re.split(r"[(（]", organiser, maxsplit=1)[0].strip()
    return mark_latin(head if re.search(r"[\u3040-\u9fff]", head) else organiser)


def domain_en(url: str) -> Markup:
    return Markup('<span lang="en">{}</span>').format(fmt_domain(url))


def edition_word_ja(edition_id: str) -> str:
    """2026-spring -> 春; 2026 -> empty."""
    word = edition_id.split("-", 1)[1] if "-" in edition_id else None
    if word is None:
        return ""
    if word not in EDITION_WORDS_JA:
        raise BuildError([f"Edition word '{word}' has no Japanese form: add it to EDITION_WORDS_JA in scripts/languages.py"])
    return EDITION_WORDS_JA[word]


def label_ja(year: int, edition_id: str) -> str:
    """2026, 2026-spring -> 2026年, 2026年春."""
    return f"{year}年{edition_word_ja(edition_id)}"


def leaf_ja(start, end) -> tuple[str, str]:
    """fmt_leaf in Japanese: weekdays on the band, days beneath, months only across a month's end."""
    weekday = lambda d: WEEKDAYS_JA[d.weekday()]
    if start == end:
        return weekday(start), str(start.day)
    if (start.year, start.month) == (end.year, end.month):
        return f"{weekday(start)}〜{weekday(end)}", f"{start.day}〜{end.day}"
    return f"{weekday(start)}〜{weekday(end)}", f"{start.month}/{start.day}〜{end.month}/{end.day}"

def era_ja(era: str) -> str:
    if re.fullmatch(r"\d{3}0s", era):
        return f"{era[:-1]}年代"
    if era not in ERAS_JA:
        raise BuildError([f"Era '{era}' has no Japanese form: add it to ERAS_JA in scripts/languages.py"])
    return ERAS_JA[era]


# Filters with one name in every language, so a template never branches on it.
FILTERS = {
    "en": {"fee": fmt_fee, "pref": str, "weekday": fmt_weekday, "address": mark_ja, "span": fmt_span,
           "domain": fmt_domain, "latin": escape, "ymd": lambda d: d.isoformat(), "era": str, "organiser_name": mark_ja},
    "ja": {"fee": fmt_fee_ja, "pref": PREFECTURES_JA.__getitem__, "weekday": weekday_ja, "address": address_ja,
           "span": span_ja, "domain": domain_en, "latin": mark_latin, "ymd": ymd_ja, "era": era_ja,
           "organiser_name": organiser_ja},
}


def countries(lang: str) -> dict:
    """Each flag's (name, art), with the name in the page's language."""
    if lang == "en":
        return COUNTRIES
    return {code: (COUNTRY_NAMES_JA[code], art) for code, (name, art) in COUNTRIES.items()}


def local(lang: str, obj: dict, base: str):
    """A name in the page's language, or the English one marked as English (spec 6.6)."""
    value = obj.get(f"{base}_{lang}")
    if value:
        return value if lang == "en" else mark_latin(value)
    english = obj.get(f"{base}_en") or obj.get(base)
    if lang == "en":
        return english
    return Markup('<span lang="en">{}</span>').format(english)


# Prose and free text, which other languages leave out until phase 2 (spec 6.6).
PROSE_FIELDS = ("summary_en", "nearest_station", "access_notes_en", "spectator_notes_en",
                "photography_notes_en", "typical_scale")


def event_text(ev: dict, lang: str) -> dict:
    """What an event page says in another language, laid over the event. English has none."""
    if lang != "ja":
        return {}
    name = ev.get("name_ja") or ev["name_en"]
    return {**{field: None for field in PROSE_FIELDS},
            "description": f"{name}（{PREFECTURES_JA[ev['prefecture']]}）の日程・会場・入場料。"}


def months_text(months: list[dict], lang: str) -> list[dict]:
    """The home list's month headings and date leaves in another language."""
    if lang != "ja":
        return months
    return [{**month, "label": fmt_month_ja(month["key"]),
             "days": [{**day, "when": fmt_span_ja(day["start"], day["end"]), "leaf": leaf_ja(day["start"], day["end"])}
                      for day in month["days"]]} for month in months]


def years_text(years: list[dict], rows: list[dict], lang: str) -> list[dict]:
    """The year strip's labels in another language: 2026年：5件、3月〜11月."""
    if lang != "ja":
        return years
    out = []
    for year in years:
        starts = [r["ed"]["start"] for r in rows if r["year"] == year["year"]]
        first, last = min(starts).month, max(starts).month
        when = f"{first}月" if first == last else f"{first}月〜{last}月"
        out.append({**year, "label": f"{year['year']}年：{len(starts)}件、{when}"})
    return out


CARS_DESCRIPTION_JA = "日本のクラシックカーイベントのエントリーリストに載る全メーカーと、それぞれの台数・イベント数。"


def group_title_ja(names: list[str]) -> Markup:
    """A make page's makes, each marked English: Nissan・Datsun・Prince."""
    return Markup("・").join(Markup('<span lang="en">{}</span>').format(name) for name in names)


def group_text(page: dict, lang: str) -> dict:
    """What a make page says in another language, laid over the page built from overlaid rows."""
    if lang != "ja":
        return {}
    plain = "・".join(page["named"])
    total = sum(x["count"] for x in page["lists"])
    lines = []
    for line in page["events"]:
        r = line["row"]
        if line.get("photo_year"):
            text = f"{line['photo_year']}年に撮影"
        else:
            count = next(x["count"] for x in page["lists"] if x["row"] is r)
            text = f"{r['label']}：{count}台" + ("（暫定）" if r["list_provisional"] else "")
        lines.append({**line, "text": text,
                      "dates": [{**d, "text": span_ja(d["start"], d["end"], year=True)
                                 + ("（日程未確定）" if d["tentative"] else "")} for d in line["dates"]]})
    return {
        "title": group_title_ja(page["named"]), "plain_title": plain,
        "page_title": f"{plain}が参加した日本のクラシックカーイベント",
        "description": f"{plain}が参加した日本のクラシックカーイベントと次回日程（公開エントリーリストより）。",
        "totals": f"エントリーリスト{len(page['lists'])}件に計{total}台",
        "lists_summary": f"エントリーリスト全{len(page['lists'])}件" if len(page["lists"]) > 1 else "エントリーリスト1件",
        "lists": [{**x, "when": span_ja(x["row"]["ed"]["start"], x["row"]["ed"]["end"], year=True),
                   "text": f"{x['count']}台"} for x in page["lists"]],
        "events": lines,
    }


def row_text(r: dict, lang: str) -> dict:
    """What a row says in another language, laid over its English text. English has none."""
    if lang != "ja":
        return {}
    ev, ed = r["ev"], r["ed"]
    name = ev.get("name_ja") or ev["name_en"]
    label = label_ja(r["year"], r["id"])
    entry_list = any(c["key"] == "entry_no" for c in r["car_columns"])
    cars_label = "エントリーリスト" if entry_list else "展示車両"
    names = {"route": "ルート", "cars": cars_label, "videos": "動画", "course": "コース図"}
    cars, route, videos = ed.get("cars") or [], ed.get("route") or [], ed.get("videos") or []
    jump_text = {"course": "コース図", "videos": f"動画（{len(videos)}本）",
                 "cars": f"{cars_label}（{len(cars)}{'台' if entry_list else '車種'}）",
                 "route": (f"ルート（{len(route)}日間）" if len(route) > 1 else "ルート（1日）") if route else "ルート"}
    parts_phrase = "・".join(names[name_] for name_ in r["sections"])
    when = span_ja(ed["start"], ed["end"], year=True)
    when_full = when
    if r["is_timed"]:
        when_full += f" {ed['start_time']}〜{ed['end_time']}" + ("（各日）" if r["rrule"] else "")
    status = {"cancelled": "中止。", "tentative": "日程未確定。"}.get(ed["status"], "")
    venue = r["venue_ja"] or r["venue"]
    out = {
        "label": label, "full_name": f"{name} {label}", "when_full": when_full,
        "display_name": local("ja", ev, "name") + (f" {word}" if (word := edition_word_ja(r["id"])) else ""),
        "parts_phrase": parts_phrase, "cars_label": cars_label,
        "cars_caveat": "出走車両は変更・欠場の可能性があります" if entry_list else "展示内容は変更の可能性があります",
        "jumps": [{**jump, "text": jump_text[jump["id"]]} for jump in r["jumps"]],
        "car_columns": [{**c, "label": {"entry_no": "番号", "year": "年式", "make": "メーカー", "model": "モデル",
                                        "colour": "色"}[c["key"]]} for c in r["car_columns"]],
        "videos": [{**v, "title": f"{name} {label}、{v['label_ja'] or v['label']}"} for v in r["videos"]],
        # The event page's notes are prose, which Japanese pages leave out until phase 2.
        "event_notes": None,
        "description": f"{status}{name} {label}の{parts_phrase}。{when}、{venue}、{PREFECTURES_JA[r['prefecture']]}。",
    }
    if r["chart"]:
        days = []
        for n, (day, shown) in enumerate(zip(route, r["chart"]["days"]), 1):
            points = day["checkpoints"]
            first = min(p["start_time"] for p in points)
            last = max(p.get("end_time") or p["start_time"] for p in points)
            days.append({**shown, "when": f"{n}日目 {weekday_ja(day['date'])}",
                         "summary": f"{first}〜{last}、{len(points)}か所"})
        out["chart"] = {**r["chart"], "days": days}
    if r["decades"]:
        undated = sum(1 for car in cars if "year" not in car)
        out["decades"] = {"rows": [{**row, "label": row["label"].removesuffix("s") + "年代", "unit": "台"}
                                   for row in r["decades"]["rows"]],
                          "rest": f"年式不明：{undated}台" if undated else None}
    if r["makes"]:
        counts: dict[str, int] = {}
        for car in cars:
            counts[car["make"]] = counts.get(car["make"], 0) + 1
        singles = sum(1 for n in counts.values() if n == 1)
        rows = [{**row, "unit": "台"} for row in r["makes"]["rows"]]
        out["makes"] = {"rows": rows,
                        "rest": (("ほかに" if rows else "") + f"1台のみのメーカーが{singles}社") if singles else None}
    return out
