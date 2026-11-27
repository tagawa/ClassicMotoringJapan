"""The Japanese page, Japanese formats, and marking Japanese runs in English pages."""

import datetime as dt
import json
import re
import unittest
from html.parser import HTMLParser

from helpers import instance_yaml, ROOT, ROUTE_ONE_DAY, temp_dir, write_event, write_instance
import build  # noqa: E402
import formatting  # noqa: E402
import settings  # noqa: E402


class JapaneseFormatTests(unittest.TestCase):
    """The /ja/ page's wording, made in code so no event ever needs a translation."""

    def test_one_day(self):
        self.assertEqual(formatting.fmt_span_ja(dt.date(2026, 10, 18), dt.date(2026, 10, 18)), "10月18日(日)")

    def test_days_in_one_month(self):
        self.assertEqual(formatting.fmt_span_ja(dt.date(2026, 10, 24), dt.date(2026, 10, 25)), "10月24日(土)〜25日(日)")

    def test_days_across_a_month_name_both_months(self):
        self.assertEqual(formatting.fmt_span_ja(dt.date(2026, 10, 31), dt.date(2026, 11, 1)), "10月31日(土)〜11月1日(日)")

    def test_days_across_the_new_year_name_both_years(self):
        # The month heading carries one year only, as in fmt_span.
        self.assertEqual(formatting.fmt_span_ja(dt.date(2026, 12, 31), dt.date(2027, 1, 1)),
                         "2026年12月31日(木)〜2027年1月1日(金)")

    def test_range_without_weekdays(self):
        # A past date, as a make page's folded list gives it (spec, /cars/<group>/).
        cases = [((2026, 10, 18), (2026, 10, 18), "2026年10月18日"),
                 ((2026, 10, 24), (2026, 10, 25), "2026年10月24日〜25日"),
                 ((2026, 10, 31), (2026, 11, 1), "2026年10月31日〜11月1日"),
                 ((2026, 12, 31), (2027, 1, 1), "2026年12月31日〜2027年1月1日")]
        for start, end, want in cases:
            self.assertEqual(formatting.fmt_range_ja(dt.date(*start), dt.date(*end)), want)

    def test_month_heading(self):
        self.assertEqual(formatting.fmt_month_ja("2026-10"), "2026年10月")

    def test_fees(self):
        self.assertEqual(formatting.fmt_fee_ja(0), "入場無料")
        self.assertEqual(formatting.fmt_fee_ja(1000), "入場料 1,000円")
        self.assertEqual(formatting.fmt_fee_ja(None), "入場料未発表")

    def test_every_prefecture_has_its_suffix(self):
        self.assertEqual(len(settings.PREFECTURES_JA), 47)
        self.assertEqual(len(set(settings.PREFECTURES_JA.values())), 47)
        self.assertEqual(settings.PREFECTURES_JA["Tokyo"], "東京都")
        self.assertEqual(settings.PREFECTURES_JA["Hokkaido"], "北海道")
        self.assertEqual(settings.PREFECTURES_JA["Osaka"], "大阪府")
        self.assertEqual(settings.PREFECTURES_JA["Kyoto"], "京都府")
        self.assertEqual(settings.PREFECTURES_JA["Shizuoka"], "静岡県")
        for name in settings.PREFECTURES_JA.values():
            self.assertRegex(name, r"^.+[都道府県]$")


class JapanesePageTests(unittest.TestCase):
    """/ja/: the home page in Japanese (spec 6.6)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "meet", name_en="Meet")
        write_instance(data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-19", "2025-10-19", status="cancelled"))
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-19"))
        write_instance(data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-17", "2027-10-17", status="tentative"))
        write_event(data, "show", name_en="Show", name_ja=None, fee=None)
        write_instance(data, "show", "2026-autumn", instance_yaml("show", 2026, "2026-10-31", "2026-11-01"))
        write_event(data, "fair", name_en="Fair", fee=1000)
        write_instance(data, "fair", 2026, instance_yaml("fair", 2026, "2026-11-03", "2026-11-03",
                                                         extra="cutoff_year: 1975\n"))
        cls.out = cls.tmp / "site"
        build.build(data, cls.out)
        cls.html = (cls.out / "ja" / "index.html").read_text(encoding="utf-8")
        cls.home = (cls.out / "index.html").read_text(encoding="utf-8")

    def row(self, start: str) -> str:
        """The list item for the date starting that day."""
        return re.search(r'<li data-end="[^"]+">\s*<div class="day-when"><time datetime="%s">.*?</ul>\s*</li>' % start,
                         self.html, re.S).group(0)

    def test_the_page_is_japanese_and_its_english_parts_say_so(self):
        self.assertTrue(self.html.startswith('<!doctype html>\n<html lang="ja">'))
        self.assertIn('<span lang="en">YouTube</span>チャンネル', self.html)
        # The logo goes to this language's home; its accessible name is the English site name.
        self.assertIn('<a class="brand" href="./" lang="en">', self.html)
        # English pages add the Japanese name beside each event; a Japanese page has no need.
        self.assertNotIn('<span lang="ja">', self.html)

    def test_title_heading_and_lede(self):
        self.assertIn("<title>日本のクラシックカーイベント | Classic Motoring Japan</title>", self.html)
        # Break points for word-break: keep-all, or the heading splits mid-word on a phone.
        self.assertIn("<h1>日本の<wbr>クラシックカー<wbr>イベント</h1>", self.html)
        lede = settings.JA_LEDE
        self.assertNotIn("英語", lede)
        self.assertIn(f'<p class="lede">{lede}</p>', self.html)
        self.assertIn(f'<meta name="description" content="{lede}">', self.html)

    def test_a_japanese_name_is_shown_and_a_latin_one_is_marked_english(self):
        self.assertIn('<a href="events/meet/">テストイベント</a>', self.row("2026-10-18"))
        self.assertIn('<a href="events/show/"><span lang="en">Show</span> 秋</a>', self.row("2026-10-31"))

    def test_months_dates_and_leaves(self):
        self.assertIn("<h3>2026年10月</h3>", self.html)
        row = self.row("2026-10-18")
        self.assertIn('<span class="visually-hidden">10月18日(日)〜19日(月)</span>', row)
        self.assertIn('<span class="leaf-day">日〜月</span><span class="leaf-date">18〜19</span>', row)
        self.assertIn('<span class="leaf-date">10/31〜11/1</span>', self.row("2026-10-31"))
        self.assertIn('<span class="leaf-day">火</span><span class="leaf-date">3</span>', self.row("2026-11-03"))

    def test_prefecture_admission_and_cutoff(self):
        self.assertIn("静岡県", self.row("2026-10-18"))
        self.assertIn("入場無料", self.row("2026-10-18"))
        self.assertIn("入場料 1,000円", self.row("2026-11-03"))
        self.assertIn("入場料未発表", self.row("2026-10-31"))
        self.assertIn("1975年式まで", self.row("2026-11-03"))

    def test_status_badges_and_a_cancelled_edition_stays_listed(self):
        self.assertIn('<span class="badge cancelled">中止</span>', self.row("2025-10-19"))
        self.assertIn('<span class="badge">日程未確定</span>', self.row("2027-10-17"))
        self.assertNotIn("中止", self.row("2026-10-18"))

    def test_year_strip(self):
        self.assertIn('<span class="chart-when">2026年：3件、10月〜11月</span>', self.html)
        self.assertIn('<span class="chart-when">2027年：1件、10月</span>', self.html)
        self.assertIn("<span>1月</span><span>4月</span><span>7月</span><span>10月</span>", self.html)

    def test_the_script_writes_japanese(self):
        for text in ("今後のイベント", "今週末", "今日", "過去の"):
            self.assertIn(json.dumps(text), self.html)
        for text in ("Upcoming", "This weekend", "Today", "Show "):
            self.assertIn(json.dumps(text), self.home)

    def test_footer_date(self):
        self.assertIn("<p>最終確認：2026年9月20日</p>", self.html)

    def test_home_and_ja_name_each_other_themselves_and_the_default(self):
        # Every other pair is checked in test_languages.
        pair = ('<link rel="alternate" hreflang="en" href="https://classicmotoringjapan.com/">\n'
                '<link rel="alternate" hreflang="ja" href="https://classicmotoringjapan.com/ja/">\n'
                '<link rel="alternate" hreflang="x-default" href="https://classicmotoringjapan.com/">')
        self.assertIn(pair, self.html)
        self.assertIn(pair, self.home)

    def test_the_header_links_each_language(self):
        self.assertIn('<a class="language" href="ja/" lang="ja" hreflang="ja">日本語</a>', self.home)
        self.assertIn('<a class="language" href="../" lang="en" hreflang="en">English</a>', self.html)

    def test_listed_in_the_sitemap_and_llms_txt(self):
        self.assertIn("<loc>https://classicmotoringjapan.com/ja/</loc>",
                      (self.out / "sitemap.xml").read_text(encoding="utf-8"))
        self.assertIn("(https://classicmotoringjapan.com/ja/)", (self.out / "llms.txt").read_text(encoding="utf-8"))


# Hiragana, katakana, CJK punctuation and ideographs, and full-width forms.
JAPANESE_CHAR = re.compile("[　-ヿ㐀-鿿＀-￯]")


def unmarked_japanese(html: str) -> list[str]:
    """Text holding Japanese whose nearest lang is not ja, so a screen reader voices it as English."""

    class Walker(HTMLParser):
        VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
                "source", "track", "wbr"}

        def __init__(self):
            super().__init__()
            self.stack, self.found = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in self.VOID:
                self.stack.append((tag, dict(attrs)))

        def handle_startendtag(self, tag, attrs):
            pass

        def handle_endtag(self, tag):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

        def handle_data(self, data):
            if any(tag in ("script", "style", "title") or a.get("aria-hidden") == "true"
                   for tag, a in self.stack):
                return
            lang = next((a["lang"] for _, a in reversed(self.stack) if "lang" in a), "")
            if JAPANESE_CHAR.search(data) and not lang.startswith("ja"):
                self.found.append(data.strip())

    walker = Walker()
    walker.feed(html)
    return walker.found


class JapaneseRunTests(unittest.TestCase):
    """Japanese inside an English field is marked lang="ja", so a screen reader switches voice (WCAG 3.1.2)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        write_event(data, "meet", extra=(
            "organizer: テスト実行委員会 (Test Committee)\n"
            "street_address: 1-1 Test, Shizuoka (静岡県テスト市1-1)\n"
            "summary_en: Held at [テスト公園](https://example.com/park/), with times given as planned (予定).\n"))
        write_instance(data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-11-22", "2026-11-22",
            extra="route_en: From the park to the harbour, times as planned (予定).\n" + ROUTE_ONE_DAY))
        build.build(data, cls.tmp / "site")
        cls.event = (cls.tmp / "site/events/meet/index.html").read_text(encoding="utf-8")
        cls.edition = (cls.tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8")


    def test_the_checker_finds_japanese_left_unmarked(self):
        # Proves the page tests below can fail.
        html = '<html lang="en"><p>テスト <span lang="ja">公園</span></p><p aria-hidden="true">日</p></html>'
        self.assertEqual(unmarked_japanese(html), ["テスト"])

    def test_event_and_edition_pages_leave_no_japanese_unmarked(self):
        for name, html in (("event", self.event), ("edition", self.edition)):
            with self.subTest(page=name):
                self.assertEqual(unmarked_japanese(html), [])

    def test_a_mixed_field_marks_only_its_japanese(self):
        self.assertIn('<span lang="ja">テスト実行委員会</span> (Test Committee)', self.event)
        self.assertIn('(<span lang="ja">静岡県テスト市1-1</span>)', self.event)
        self.assertIn('<a href="https://example.com/park/"><span lang="ja">テスト公園</span></a>', self.event)

    def test_latin_letters_between_japanese_stay_in_one_run(self):
        self.assertEqual(str(formatting.mark_ja("クラシックカーフェスティバルin桐生実行委員会 (Committee)")),
                         '<span lang="ja">クラシックカーフェスティバルin桐生実行委員会</span> (Committee)')
        self.assertEqual(str(formatting.mark_ja("Fujioka オールディーズ実行委員会")),
                         'Fujioka <span lang="ja">オールディーズ実行委員会</span>')
        self.assertEqual(str(formatting.mark_ja("コッパ ディ 小海 実行委員会")),
                         '<span lang="ja">コッパ ディ 小海 実行委員会</span>')

    def test_everything_else_is_still_escaped(self):
        self.assertEqual(str(formatting.mark_ja("A & <b> 公園")), 'A &amp; &lt;b&gt; <span lang="ja">公園</span>')

    def test_no_page_of_the_real_site_leaves_japanese_unmarked(self):
        out = self.tmp / "real-site"
        build.build(ROOT / "data", out)
        pages = sorted(out.rglob("*.html"))
        self.assertGreater(len(pages), 10)
        for page in pages:
            with self.subTest(page=str(page.relative_to(out))):
                self.assertEqual(unmarked_japanese(page.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()
