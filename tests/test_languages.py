"""Languages (spec 6.6): the interface text, the Japanese pages, and the Latin-script guard."""

import json
import re
import shutil
import unittest
from html.parser import HTMLParser

from markupsafe import Markup

from helpers import (CARS, ROOT, ROUTE, instance_yaml, make_fixture, temp_dir, write_event, write_instance)
import build  # noqa: E402
import languages  # noqa: E402
from validate import BuildError, load_and_validate  # noqa: E402

SITE = "https://classicmotoringjapan.com"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
CHECKED_ATTRS = ("alt", "title", "aria-label")


# A whole run: "Classic Motoring Japan" is one run, not three words (plan v4, design 7).
RUN = re.compile(r"[A-Za-z]+(?:[ '&.-][A-Za-z]+)*")


def latin_runs(text: str) -> list[str]:
    """The runs of Latin script in text, a number's km or cc excepted."""
    runs = []
    for m in RUN.finditer(text):
        before = text[:m.start()]
        if m.group(0) in ("km", "cc") and re.search(r"[0-9] ?$", before):
            continue
        runs.append(m.group(0))
    return runs


class LatinGuard(HTMLParser):
    """Collects Latin text a Japanese page shows without marking it lang="en"."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str]] = [("", "ja")]
        self.unmarked: list[str] = []
        # <title> and attributes cannot carry lang, so their Latin passes when the page shows it marked.
        self.marked: set[str] = set()
        self.deferred: list[str] = []
        self.skip = 0

    def lang(self) -> str:
        return self.stack[-1][1]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        own = attrs.get("lang", self.lang())
        for name in CHECKED_ATTRS:
            if attrs.get(name):
                (self.marked.update if own == "en" else self.deferred.extend)(latin_runs(attrs[name]))
        if tag in VOID:
            return
        if tag in ("script", "style"):
            self.skip += 1
        self.stack.append((tag, own))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag in ("script", "style"):
            self.skip -= 1
        # Pop to the matching tag, so one stray end tag cannot shift every lang after it.
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.skip:
            return
        runs = latin_runs(data)
        if self.stack[-1][0] == "title" and self.lang() != "en":
            self.deferred.extend(runs)
        elif self.lang() == "en":
            self.marked.update(runs)
        else:
            self.unmarked.extend(runs)


def unmarked_latin(html: str) -> list[str]:
    guard = LatinGuard()
    guard.feed(html)
    return guard.unmarked + [run for run in guard.deferred if run not in guard.marked]


def hreflang(html: str) -> dict[str, str]:
    return dict(re.findall(r'<link rel="alternate" hreflang="([a-z-]+)" href="([^"]+)">', html))


class GuardTests(unittest.TestCase):
    """The guard is shown to fire before any page is trusted to it (reviewer's known cases)."""

    def test_text_after_a_br_is_read_in_the_right_language(self):
        self.assertEqual(unmarked_latin('<p><span lang="en">Map<br>x</span>BMW</p>'), ["BMW"])

    def test_marked_english_passes(self):
        self.assertEqual(unmarked_latin('<p>日本<span lang="en">Map</span></p>'), [])

    def test_a_unit_after_a_number_passes_and_a_bare_unit_fails(self):
        self.assertEqual(unmarked_latin("<p>120 km</p>"), [])
        self.assertEqual(unmarked_latin("<p>120km</p>"), [])
        self.assertEqual(unmarked_latin("<p>km</p>"), ["km"])

    def test_attributes_and_title_pass_only_when_the_page_marks_the_same_text(self):
        self.assertEqual(unmarked_latin('<title>Hill Climb 2026年</title><h1 lang="en">Hill Climb</h1>'), [])
        self.assertEqual(unmarked_latin('<title>Hill Climb 2026年</title>'), ["Hill Climb"])
        self.assertEqual(unmarked_latin('<img alt="A red car">'), ["A red car"])
        self.assertEqual(unmarked_latin('<img lang="en" alt="A red car">'), [])

    def test_a_title_or_attribute_run_must_match_a_whole_marked_run(self):
        self.assertEqual(unmarked_latin('<title>日本 | Classic Motoring Japan</title>'
                                        '<header><span lang="en">Classic Motoring Japan</span></header>'), [])
        self.assertEqual(unmarked_latin('<a aria-label="Map"></a><p lang="en">Map of the route</p>'), ["Map"])

    def test_script_and_style_are_skipped(self):
        self.assertEqual(unmarked_latin("<script>var x = 1;</script><style>a { color: red }</style>"), [])


class TextTests(unittest.TestCase):
    def test_every_language_has_every_key_english_has_and_no_others(self):
        for lang in languages.LANGUAGES:
            self.assertEqual(set(languages.TEXT[lang]), set(languages.TEXT["en"]), lang)

    def test_no_key_hides_a_dict_method(self):
        # Jinja reads t.items as the method, not the text.
        for key in languages.TEXT["en"]:
            self.assertFalse(hasattr(dict, key), key)

    def test_the_japanese_text_has_no_unmarked_latin(self):
        self.assertEqual(unmarked_latin("Map"), ["Map"])
        for key, value in languages.TEXT["ja"].items():
            samples = [value]
            if callable(value):
                samples = []
                # Each function is tried with every sample that fits it: a count, a label, a day.
                for args in ((1,), (2,), ("2026年",), (1, "10月18日(日)")):
                    try:
                        samples.append(value(*args))
                    except TypeError:
                        pass
                self.assertTrue(samples, key)
            for sample in samples:
                html = sample if isinstance(sample, Markup) else Markup.escape(sample)
                self.assertEqual(unmarked_latin(f"<p>{html}</p>"), [], key)

    def test_an_unknown_key_fails_the_build_with_its_name(self):
        tmp = temp_dir(self)
        templates = tmp / "templates"
        shutil.copytree(ROOT / "templates", templates)
        page = templates / "about.html"
        page.write_text(page.read_text(encoding="utf-8").replace("{% block main %}", "{% block main %}{{ t.nope }}", 1),
                        encoding="utf-8")
        data = tmp / "data"
        make_fixture(data)
        with self.assertRaises(BuildError) as caught:
            build.build(data, tmp / "site", templates_dir=templates)
        self.assertIn("nope", str(caught.exception))


class LocalTests(unittest.TestCase):
    def test_the_page_language_form_when_there_is_one(self):
        self.assertEqual(languages.local("ja", {"name_en": "Meet", "name_ja": "会"}, "name"), "会")

    def test_otherwise_english_marked_as_english(self):
        self.assertEqual(languages.local("ja", {"name_en": "Meet"}, "name"), '<span lang="en">Meet</span>')
        self.assertEqual(languages.local("ja", {"venue": "Test Park"}, "venue"), '<span lang="en">Test Park</span>')

    def test_english_pages_are_unmarked(self):
        self.assertEqual(languages.local("en", {"name_en": "Meet", "name_ja": "会"}, "name"), "Meet")


class AddressTests(unittest.TestCase):
    def test_the_japanese_in_brackets(self):
        self.assertEqual(languages.address_ja("2-1 Nakase, Mihama, Chiba (千葉県千葉市美浜区中瀬2-1)"),
                         "千葉県千葉市美浜区中瀬2-1")
        self.assertEqual(languages.address_ja("1-2-1 Takashima, Suwa, Nagano (長野県諏訪市高島1丁目2-1), the venue's entrance"),
                         "長野県諏訪市高島1丁目2-1")

    def test_without_brackets_as_stored_and_marked_english(self):
        self.assertEqual(languages.address_ja("1 Test Street"), '<span lang="en">1 Test Street</span>')


class OrganiserTests(unittest.TestCase):
    def test_the_japanese_before_the_first_bracket(self):
        self.assertEqual(languages.organiser_ja(
            "汐留町会 (Shiodome neighbourhood association), run by the Coppa di Tokyo organising committee"), "汐留町会")
        self.assertEqual(languages.organiser_ja("AUTOMOBILE COUNCIL実行委員会 (Automobile Council Committee)"),
                         '<span lang="en">AUTOMOBILE COUNCIL</span>実行委員会')

    def test_with_no_japanese_before_a_bracket_as_stored(self):
        for stored in ("Toyota Automobile Museum", "Test Club (テストクラブ)"):
            self.assertEqual(languages.organiser_ja(stored), languages.mark_latin(stored))


class JapaneseWordsTests(unittest.TestCase):
    def test_edition_labels(self):
        self.assertEqual(languages.label_ja(2026, "2026"), "2026年")
        self.assertEqual(languages.label_ja(2026, "2026-spring"), "2026年春")
        self.assertEqual(languages.label_ja(2027, "2027-new-year"), "2027年新春")

    def test_an_edition_word_with_no_japanese_fails_the_build_with_its_name(self):
        tmp = temp_dir(self)
        data = tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", "2026-winter", instance_yaml("meet", 2026, "2026-12-06", "2026-12-06", extra=CARS))
        with self.assertRaises(BuildError) as caught:
            build.build(data, tmp / "site")
        self.assertIn("winter", str(caught.exception))

    def test_eras(self):
        self.assertEqual(languages.era_ja("1950s"), "1950年代")
        self.assertEqual(languages.era_ja("Prewar"), "戦前")

    def test_an_era_with_no_japanese_fails_the_build_with_its_name(self):
        tmp = temp_dir(self)
        data = tmp / "data"
        write_event(data, "meet", extra="typical_eras:\n  - Edwardian\n")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-12-06", "2026-12-06"))
        with self.assertRaises(BuildError) as caught:
            build.build(data, tmp / "site")
        self.assertIn("Edwardian", str(caught.exception))

    def test_venue_ja_and_label_ja_are_accepted(self):
        tmp = temp_dir(self)
        data = tmp / "data"
        write_event(data, "meet", extra="venue_ja: テスト公園\n")
        write_instance(data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-18",
            extra='videos:\n  - youtube_id: "abcdefghijk"\n    label_en: Day 1\n    label_ja: 1日目\n'))
        load_and_validate(data)


# The page kinds that have a Japanese counterpart so far; each step adds its own.
KINDS = {"edition": "events/*/*/index.html", "event": "events/*/index.html",
         "cars": "cars/index.html", "car_group": "cars/*/index.html"}


class JapanesePagesTests(unittest.TestCase):
    """Built from the fixture plus a route, a video and an event with no Japanese name."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        make_fixture(data)
        write_event(data, "tour", name_en="Tour", name_ja=None, extra=(
            "venue_ja: テスト公園\nstreet_address: 1 Test Street (静岡県テスト市1-1)\n"
            "organizer: テストクラブ (Test Club), with Shiodome town\nsummary_en: A two-day tour of the coast.\n"
            "nearest_station: Test Station\ntypical_scale: About 50 cars\n"
            "typical_eras:\n  - Prewar\n  - 1960s\n"))
        write_instance(data, "tour", 2026, instance_yaml(
            "tour", 2026, "2026-10-18", "2026-10-19", status="tentative",
            extra=ROUTE + 'videos:\n  - youtube_id: "abcdefghijk"\n    label_en: Day 1\n    label_ja: 1日目\n'
                  '  - youtube_id: "bbcdefghijk"\n    label_en: The cars on show\n'))
        # A third entry list with Bentley gives it a page under /cars/.
        write_event(data, "parade", name_en="Parade", name_ja="パレード")
        write_instance(data, "parade", 2026, instance_yaml("parade", 2026, "2026-11-15", "2026-11-15", extra=CARS))
        cls.out = cls.tmp / "site"
        build.build(data, cls.out)

    def page(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def test_every_page_of_each_kind_has_a_japanese_counterpart_and_none_is_extra(self):
        for kind, pattern in KINDS.items():
            english = {p.relative_to(self.out).as_posix() for p in self.out.glob(pattern)}
            japanese = {p.relative_to(self.out / "ja").as_posix() for p in (self.out / "ja").glob(pattern)}
            self.assertTrue(english, kind)
            self.assertEqual(english, japanese, kind)

    def test_no_japanese_page_shows_unmarked_latin(self):
        pages = list((self.out / "ja").rglob("*.html"))
        self.assertGreater(len(pages), 3)
        for page in pages:
            self.assertEqual(unmarked_latin(page.read_text(encoding="utf-8")), [], page)

    def test_each_page_of_a_pair_lists_itself_its_counterpart_and_x_default(self):
        pairs = [("index.html", "ja/index.html")] + [
            (p.relative_to(self.out).as_posix(), f"ja/{p.relative_to(self.out).as_posix()}")
            for pattern in KINDS.values() for p in self.out.glob(pattern)]
        for en, ja in pairs:
            url = lambda rel: f"{SITE}/{rel.removesuffix('index.html')}"
            expected = {"en": url(en), "ja": url(ja), "x-default": url(en)}
            self.assertEqual(hreflang(self.page(en)), expected, en)
            self.assertEqual(hreflang(self.page(ja)), expected, ja)

    def test_an_edition_page_in_japanese(self):
        html = self.page("ja/events/tour/2026/index.html")
        self.assertTrue(html.startswith('<!doctype html>\n<html lang="ja">'))
        self.assertIn('<h1><span lang="en">Tour</span> 2026年</h1>', html)
        self.assertIn("2026年10月18日(日)〜19日(月)", html)
        self.assertIn("テスト公園、静岡県", html)
        self.assertIn('<a href="../../../">ホーム</a>', html)
        self.assertIn("1日目：10月18日(日)", html)
        self.assertIn("1日目 10月18日(日)：09:00〜11:00", html)
        self.assertIn("09:00〜09:30", html)
        self.assertIn("最終確認</dt>\n  <dd>2026年9月20日（情報元：", html)
        self.assertIn("ルート（2日間）", html)
        self.assertIn("テスト公園", html)
        self.assertIn('<span lang="en">Test Harbour</span>', html)
        self.assertIn(">1日目</a>", html)
        self.assertIn('<span lang="en">The cars on show</span>', html)
        self.assertIn("日程未確定", html)
        self.assertIn('<a class="language" href="../../../../events/tour/2026/" lang="en" hreflang="en">English</a>', html)

    def test_an_entry_list_in_japanese(self):
        html = self.page("ja/events/hill-climb/2026-autumn/index.html")
        self.assertIn("<title>テストイベント 2026年秋：エントリーリスト</title>", html)
        self.assertIn('<th scope="col">年式</th>', html)
        self.assertIn("1920年代", html)
        self.assertIn("2026年9月15日時点。", html)
        self.assertIn('lang="en"><a href="../../../cars/bentley/">Bentley</a>', html)

    def test_an_event_page_in_japanese(self):
        html = self.page("ja/events/tour/index.html")
        self.assertIn("<title>Tour：来場ガイド</title>", html)
        self.assertIn('<meta name="description" content="Tour（静岡県）の日程・会場・入場料。">', html)
        self.assertIn('<h1><span lang="en">Tour</span></h1>', html)
        self.assertIn('<td class="edition num" role="cell">2026年</td>\n        <td class="dates" role="cell">2026年10月18日(日)〜19日(月)</td>', html)
        self.assertIn('<th scope="col" role="columnheader">開催回</th>', html)
        self.assertIn("日程未確定", html)
        self.assertIn('<a href="../../events/tour/2026/">動画・ルート</a>', html)
        self.assertIn("テスト公園、静岡県<br>静岡県テスト市1-1", html)
        self.assertIn("<dd>入場無料</dd>", html)
        self.assertIn('<span class="chip">戦前</span><span class="chip">1960年代</span>', html)
        self.assertIn("<dd>テストクラブ</dd>", html)
        self.assertNotIn("Shiodome", html)
        self.assertIn('<dt>情報元</dt>\n  <dd><a href="https://example.com/tour/"><span lang="en">example.com</span></a></dd>', html)
        self.assertIn("<dd>2026年9月20日</dd>", html)
        self.assertIn(json.dumps("開催済み"), html)
        self.assertIn('<a class="language" href="../../../events/tour/" lang="en" hreflang="en">English</a>', html)
        # Prose and free text wait for phase 2 (spec 6.6).
        for prose in ("two-day tour", "Test Station", "About 50 cars", "最寄り駅"):
            self.assertNotIn(prose, html)

    def test_the_english_event_page_is_unchanged_but_for_its_link_to_japanese(self):
        html = self.page("events/tour/index.html")
        self.assertIn('<a class="language" href="../../ja/events/tour/" lang="ja" hreflang="ja">日本語</a>', html)
        for text in ("A two-day tour of the coast.", "Nearest station: Test Station", "About 50 cars",
                     '<span class="chip">Prewar</span>', "</a> (Japanese)</dd>", '"Held"'):
            self.assertIn(text, html)

    def test_event_blocks_stay_on_english_event_pages(self):
        english = [self.page(p.relative_to(self.out).as_posix()) for p in self.out.glob("events/*/index.html")]
        self.assertTrue(any('"@type": "Event"' in html for html in english))
        for p in (self.out / "ja").glob("events/*/index.html"):
            self.assertNotIn('"@type": "Event"', p.read_text(encoding="utf-8"), p)

    def test_the_sitemap_lists_both_event_pages(self):
        sitemap = self.page("sitemap.xml")
        self.assertIn(f"<loc>{SITE}/events/tour/</loc>", sitemap)
        self.assertIn(f"<loc>{SITE}/ja/events/tour/</loc>", sitemap)

    def test_the_cars_index_in_japanese(self):
        html = self.page("ja/cars/index.html")
        self.assertIn("<title>メーカー別の車両 | Classic Motoring Japan</title>", html)
        self.assertIn("<h1>メーカー別の車両</h1>", html)
        self.assertIn('<th>メーカー</th><th class="num">台数</th><th class="num">イベント数</th>', html)
        self.assertIn('<td class="unflagged" lang="en"><a href="bentley/">Bentley</a></td>', html)
        self.assertIn("<p>最終確認：2026年9月20日</p>", html)
        self.assertIn('<td class="unflagged"><a href="bentley/">Bentley</a></td>', self.page("cars/index.html"))

    def test_a_make_page_in_japanese(self):
        html = self.page("ja/cars/bentley/index.html")
        self.assertIn("<title>Bentleyが参加した日本のクラシックカーイベント</title>", html)
        self.assertIn('<h1><span lang="en">Bentley</span></h1>', html)
        self.assertIn('<a href="../../">ホーム</a>', html)
        self.assertIn('<a href="../../cars/">車種</a>', html)
        self.assertIn("<p>エントリーリスト3件に計3台。</p>", html)
        self.assertIn('<h2 id="next-dates"><span lang="en">Bentley</span>が参加したイベント</h2>', html)
        self.assertIn('<a href="../../events/parade/">パレード</a>', html)
        self.assertIn(">2026年11月15日(日)</span>", html)
        self.assertIn('<a href="../../events/parade/2026/">2026年：1台（暫定）</a>', html)
        self.assertIn('<a href="../../events/parade/2026/">パレード 2026年</a></td><td>2026年11月15日(日)</td><td>1台（暫定リスト）</td>', html)
        self.assertIn("<summary>エントリーリスト全3件</summary>", html)
        self.assertIn('content="Bentleyが参加した日本のクラシックカーイベントと次回日程（公開エントリーリストより）。"', html)
        self.assertIn("<p>台数は、エントリーリストを公開しているイベントのみの集計です。</p>", html)
        self.assertIn(json.dumps("次回の日程"), html)
        self.assertIn('"name": "Bentley"', html)
        self.assertIn("<p>最終確認：2026年9月20日</p>", html)

    def test_edition_pages_link_the_japanese_make_page(self):
        self.assertIn('<a href="../../../cars/bentley/">Bentley</a>', self.page("ja/events/parade/2026/index.html"))

    def test_the_page_note_marks_itself_japanese(self):
        title = Markup('<span lang="en">Nissan</span>・<span lang="en">Datsun</span>')
        self.assertEqual(languages.TEXT["ja"]["page_note"](title),
                         '<span lang="ja"><span lang="en">Nissan</span>・<span lang="en">Datsun</span>のページに掲載</span>')
        self.assertEqual(languages.group_title_ja(["Nissan", "Datsun"]), title)

    def test_the_english_page_links_its_japanese_one(self):
        html = self.page("events/tour/2026/index.html")
        self.assertIn('<a class="language" href="../../../ja/events/tour/2026/" lang="ja" hreflang="ja">日本語</a>', html)

    def test_the_japanese_home_page_links_the_japanese_edition_page(self):
        html = self.page("ja/index.html")
        self.assertIn('<a href="events/tour/2026/"><span lang="en">Tour</span></a>', html)
        self.assertIn("ルート走行", html)


class RealDataTests(unittest.TestCase):
    """The guard over every Japanese page the real data builds."""

    @classmethod
    def setUpClass(cls):
        cls.out = temp_dir(cls) / "site"
        build.build(ROOT / "data", cls.out)

    def test_no_year_is_written_twice(self):
        # A year passed in already formatted would read 2026年年.
        pages = list((self.out / "ja").rglob("*.html"))
        self.assertIn("年", (self.out / "ja/index.html").read_text(encoding="utf-8"))
        self.assertEqual([str(p) for p in pages if "年年" in p.read_text(encoding="utf-8")], [])

    def test_no_japanese_page_shows_unmarked_latin(self):
        pages = list((self.out / "ja").rglob("*.html"))
        self.assertGreater(len(pages), 10)
        failures = {str(p.relative_to(self.out)): runs for p in pages
                    if (runs := unmarked_latin(p.read_text(encoding="utf-8")))}
        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
