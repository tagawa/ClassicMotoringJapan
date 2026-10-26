# Japanese Timetable Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One page at `/ja/` listing every edition in Japanese, generated entirely from fields `data/` already has, so that Fathom can show whether Japanese readers want it.

**Architecture:** `build()` renders a new `templates/ja.html` from the same `rows` and `month_groups(rows)` the home page uses. Japanese wording comes from three small formatting helpers and a prefecture table in `scripts/build.py`, registered as Jinja filters. Past editions drop out in the browser through the existing `drop_passed()` macro, because the build never reads the clock.

**Tech Stack:** Python 3, Jinja2, `unittest`, plain CSS, ES5.

**Spec:** `docs/spec_v6.md`, plus the design agreed in conversation on 2026-10-18 (summarised under "Design" below, and written into the spec in Task 2).

## Design

The page is an experiment with a fixed end. Keep it if it gets 20 or more visits a month from outside referrers (search engines or other sites) in its third month, the month to 2027-01-18; otherwise delete it. Raw `/ja/` visits overstate demand, because English readers click 日本語 out of curiosity, so the measure is Fathom filtered to Page = `/ja/`, read by Referrers. Deleting it removes the template, the helpers and their tests.

| On the page | From | Example |
|---|---|---|
| Event name | `name_ja`, or `display_name` under `lang="en"` when the event has no `name_ja` | 昭和レトロカーミート; `<span lang="en">Nostalgic 2days</span>` |
| Dates | `ed.start`, `ed.end` | 10月18日(日); 10月24日(土)〜25日(日) |
| Hours | `start_time`, `end_time`, only on a timed edition | 10:00〜16:00; 10:00〜17:00（各日） |
| Prefecture | `prefecture`, through `PREFECTURES_JA` | 東京都 |
| Admission | `spectator_fee_jpy` | 入場無料; 入場料 1,000円; 入場料未発表 |
| Source link | `official_url`, link text from the `domain` filter | 情報元：retrocar.yaesu-net.co.jp |
| Details link | the edition's existing English page (`r.path`) | 詳細（英語） |
| Status | `ed.status` | 日程未確定 (tentative); 中止 (cancelled) |

Left out, on purpose: venues (the data holds English names only, and a `venue_ja` field would need a lookup for every event), routes, entry lists, videos, prose. "情報元", not "公式サイト": `official_url` is often a tourism listing or a blog, the same reason `event.html` labels it "Source".

Hand-written Japanese, for the owner to check before Task 2 is done:

| Where | Text |
|---|---|
| `<title>` | 日本のクラシックカーイベント \| Classic Motoring Japan |
| `<h1>` | 日本のクラシックカーイベント |
| Lede and meta description | 日本各地のクラシックカーイベントの日程です。ルート、エントリーリスト、動画などの詳細は英語のページにあります。 |
| Month heading | 2026年10月 |
| Home page header link | 日本語 |
| `/ja/` header link | English |

## Global Constraints

- Scripts are ES5; CSS has no custom properties and no flex `gap` (guard test).
- `static/style.css` uses only the values in `FONT_SIZES`, `SPACING` and `RADII` in `tests/test_build.py` (`StylesheetTokenTests`).
- Prose states facts, never advice (`EDITORIAL_PHRASES`); English text in British spelling.
- Search the whole project before introducing any new name (CSS class, id, filter, function, file).
- No local git: there are no commit steps. Files go up by hand, in one drag of `scripts`, `static`, `templates` and `tests`, because the new tests fail without the builder and templates. `.venv/bin/python -B tools/pending.py` lists them.
- Run tests with `.venv/bin/python -B -m unittest discover -s tests`.

## Review Focus

1. **An event with no `name_ja`** (Nostalgic 2days, Nostalgic Car Fes Kashiwara): the Latin name is printed inside `lang="en"`, so a screen reader doesn't read it with Japanese rules (`build.py` explains this next to `EVENT_OPTIONAL`). Test in Task 2.
2. **A span crossing a month or a year end:** both months, or both years, are named, as `fmt_span` does in English. Test in Task 1.
3. **A prefecture missing from the table** (a typo, or a first event in a new prefecture): the build fails with a validation error naming the file and the value, never a `KeyError` at render time. Test in Task 1.
4. **A month whose editions have all passed:** its heading goes with them, so the page never shows an empty month. Test in Task 2 (the month carries `data-hide-after` = its latest `end`).
5. **A cancelled edition:** it stays listed with 中止 until its date passes, as on the home page, rather than being dropped. Test in Task 2.

---

### Task 1: Japanese formatting helpers and prefecture validation

**Files:**
- Modify: `scripts/build.py` (constants near `COUNTRIES`; helpers beside `fmt_span` and `fmt_fee`; check in `load_and_validate`)
- Test: `tests/test_build.py` (new class `JapaneseFormatTests`; one test added to `ValidationTests`)

**Interfaces:**
- Produces: `PREFECTURES_JA: dict[str, str]`, all 47, keyed by the romanised forms the data uses (`"Tokyo"`, `"Hyogo"`, `"Hokkaido"`, no macrons), values with their suffix (`"東京都"`, `"北海道"`, `"大阪府"`, `"京都府"`, `"静岡県"`).
- Produces: `fmt_span_ja(start: dt.date, end: dt.date) -> str`, `fmt_month_ja(key: str) -> str` (takes `month_groups`' `"2026-10"`), `fmt_fee_ja(fee: int | None) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
class JapaneseFormatTests(unittest.TestCase):
    def test_one_day(self):
        self.assertEqual(build.fmt_span_ja(dt.date(2026, 10, 18), dt.date(2026, 10, 18)), "10月18日(日)")

    def test_days_in_one_month(self):
        self.assertEqual(build.fmt_span_ja(dt.date(2026, 10, 24), dt.date(2026, 10, 25)), "10月24日(土)〜25日(日)")

    def test_days_across_a_month_name_both_months(self):
        self.assertEqual(build.fmt_span_ja(dt.date(2026, 10, 31), dt.date(2026, 11, 1)), "10月31日(土)〜11月1日(日)")

    def test_days_across_the_new_year_name_both_years(self):
        # The month heading carries one year only, as in fmt_span.
        self.assertEqual(build.fmt_span_ja(dt.date(2026, 12, 31), dt.date(2027, 1, 1)),
                         "2026年12月31日(木)〜2027年1月1日(金)")

    def test_month_heading(self):
        self.assertEqual(build.fmt_month_ja("2026-10"), "2026年10月")

    def test_fees(self):
        self.assertEqual(build.fmt_fee_ja(0), "入場無料")
        self.assertEqual(build.fmt_fee_ja(1000), "入場料 1,000円")
        self.assertEqual(build.fmt_fee_ja(None), "入場料未発表")

    def test_every_prefecture_has_its_suffix(self):
        self.assertEqual(len(build.PREFECTURES_JA), 47)
        self.assertEqual(build.PREFECTURES_JA["Tokyo"], "東京都")
        self.assertEqual(build.PREFECTURES_JA["Hokkaido"], "北海道")
        self.assertEqual(build.PREFECTURES_JA["Osaka"], "大阪府")
        self.assertEqual(build.PREFECTURES_JA["Kyoto"], "京都府")
        self.assertEqual(build.PREFECTURES_JA["Shizuoka"], "静岡県")
```

In `ValidationTests`:

```python
    def test_an_unknown_prefecture_is_rejected(self):
        # write_event hard-codes Shizuoka; a second prefecture key via extra would be a YAML duplicate.
        ev = self.data / "events" / "meet.yml"
        ev.write_text(ev.read_text(encoding="utf-8").replace("prefecture: Shizuoka", "prefecture: Shizuokaa"),
                      encoding="utf-8")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("Shizuokaa")
```

Add the same test for an edition's own `prefecture`, passed through `instance_yaml`'s `extra` with `venue_en` beside it.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/bin/python -B -m unittest tests.test_build.JapaneseFormatTests tests.test_build.ValidationTests`
Expected: `AttributeError` for the missing helpers; the validation tests fail because the build succeeds.

- [ ] **Step 3: Implement**

Weekday kanji come from a fixed string indexed by `date.weekday()` (`"月火水木金土日"`), never from the locale, which differs between this Mac and the Actions runner. In `load_and_validate`, reject an event or edition `prefecture` that is not a key of `PREFECTURES_JA`, with the file and the value in the message. Checkpoint prefectures are not rendered on `/ja/` and stay unchecked.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -B -m unittest discover -s tests`
Expected: OK. `test_repo_sample_data_builds` proves every prefecture in `data/` is in the table.

---

### Task 2: The `/ja/` page, its links and the spec

**Files:**
- Create: `templates/ja.html`
- Modify: `templates/base.html` (`lang`, footer `lang`, a header block, `hreflang` links)
- Modify: `templates/home.html` (fills the header block with the 日本語 link)
- Modify: `scripts/build.py` (`build()`: register filters, render `ja/index.html`, add it to the sitemap)
- Modify: `static/style.css` (only what the screenshots in Step 6 show is needed)
- Modify: `docs/spec_v6.md` (a new subsection after 6.4, and the page list wherever the spec enumerates pages)
- Modify: `tools/reviews.yml` (the experiment's deadline)
- Test: `tests/test_build.py` (new class `JapanesePageTests`)

**Interfaces:**
- Consumes: Task 1's helpers, registered as filters `span_ja`, `month_ja`, `fee_ja`, `pref_ja` (search `templates/` and `scripts/` for each name first).
- Consumes: `month_groups(rows)`, `drop_passed()` from `templates/icons.html`, the `domain` filter.
- Produces: `base.html` variables `lang` (default `"en"`) and `hreflang` (truthy on `/` and `/ja/` only), and `{% block header_extra %}`.

- [ ] **Step 1: Write the failing tests**

Build the site once in `setUpClass` from its own small set, in the style of `AddToCalendarTests`: an event with `name_ja` (the `write_event` default), one with `name_ja=None`, a cancelled edition, a tentative one, an all-day edition and a two-day timed one. `make_fixture` has no tentative edition, so it is not enough on its own. Pin these assertions:

- `ja/index.html` starts `<html lang="ja">`, its `<footer` carries `lang="en"`, and so does the logo link (`<a class="brand" href="../" lang="en">`), whose accessible name is the English site name. `base.html` puts `lang="en"` on the logo link on every page.
- `<title>日本のクラシックカーイベント | Classic Motoring Japan</title>` and the `<h1>` and lede from the Design table.
- The fixture's `name_ja` appears; the event without one appears as `<span lang="en">` + its `display_name`.
- The two-day timed edition shows `10:00〜17:00（各日）`; an all-day edition shows no `〜` time.
- Each edition's row carries `data-hide-after="<end>"`; each month `<div>` carries `data-hide-after` equal to the latest `end` among its days; the page includes `drop_passed()`'s script (`querySelectorAll("[data-hide-after]")`).
- The cancelled edition is listed with 中止, the tentative one with 日程未確定.
- `情報元：` precedes a link whose `href` is the event's `official_url`; `詳細（英語）` links `../` + `r.path`.
- Both `index.html` and `ja/index.html` carry `<link rel="alternate" hreflang="en" href="https://classicmotoringjapan.com/">` and `<link rel="alternate" hreflang="ja" href="https://classicmotoringjapan.com/ja/">`; no other page carries `hreflang`.
- The home page header has `<a href="ja/" lang="ja" hreflang="ja">日本語</a>`; `/ja/`'s has `<a href="../" lang="en" hreflang="en">English</a>`.

The existing `test_sitemap_is_well_formed_and_lists_every_page` covers the sitemap once the page exists; check that it really enumerates `ja/index.html` rather than assuming.

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/bin/python -B -m unittest tests.test_build.JapanesePageTests`
Expected: fails on the missing `ja/index.html`.

- [ ] **Step 3: Implement**

Render with `root="../"`, `canonical=f"{SITE_URL}/ja/"`, `lang="ja"`, `hreflang=True`, `jsonld=[]` (the `WebSite` block stays on the home page only, per spec 6.2). Add `(f"{SITE_URL}/ja/", latest)` to the sitemap. The month's latest end in the template: `month.days | map(attribute="end") | max`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -B -m unittest discover -s tests`
Expected: OK, including `BritishSpellingTests`, `StylesheetTokenTests` and `FathomEventTests` unchanged.

- [ ] **Step 5: Write the spec subsection**

What the page shows and leaves out (the Design table, in prose or a table), why "情報元", the experiment's rule exactly as in the Design section (20 or more outside-referrer visits in the month to 2027-01-18, measured in Fathom filtered to Page = `/ja/` and read by Referrers, otherwise delete), and that a new prefecture needs a line in `PREFECTURES_JA`.

Add to `tools/reviews.yml`, so the SessionStart hook raises it on 2027-01-18 (`due.py` raises an area more than 91 days after `last_reviewed`):

```yaml
# Not a review: the Japanese page's deadline. Dated the day the experiment was set, so
# due.py raises it on 2027-01-18. On that day apply the rule and delete this entry.
ja-page-experiment:
  last_reviewed: 2026-10-18
  check: Fathom, Page = /ja/, Referrers, the month to 2027-01-18. 20 or more visits from outside referrers keeps the page (spec, Japanese page); fewer deletes it.
```

Then run `.venv/bin/python -B tools/due.py` and `.venv/bin/python -B -m unittest discover -s tools` to confirm the entry parses and is not yet listed as due. Add that last point to the project `CLAUDE.md`'s "Editing data" list too, beside the `data/makes.yml` rule.

- [ ] **Step 6: Look at it**

Run: `.venv/bin/python -B tools/shoot.py ja/ / --theme both --width 390 1000`
Check: the header links sit clear of the logo at 390px, Japanese text wraps without overflow, both themes. Fix in `static/style.css` with token values only, rerun the suite, then delete `docs/shots/`.

- [ ] **Step 7: Owner check**

Show the owner the 390px light screenshot of `/ja/` and the hand-written strings in the Design table. Upload only after they approve the wording.
