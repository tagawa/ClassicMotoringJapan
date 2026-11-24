"""Meta descriptions, breadcrumbs and structured data.

These are offline proxies for Google's Rich Results Test, so a manual pass with it should be a formality.
"""

import json
import re
import unittest
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

from helpers import (CARS, display_cars_yaml, HeadParser, instance_yaml, jsonld_blocks, make_fixture, ROOT, ROUTE,
                     temp_dir, write_event, write_instance)
import build  # noqa: E402
import settings  # noqa: E402


def make_description_fixture(data: Path) -> None:
    write_event(data, "tour", name_en="Test Tour",
                extra="summary_en: >\n  A tour past [Test Park](https://example.com/park/) and the\n"
                      "  harbour. It has run every year since 1990.\n")
    write_instance(data, "tour", 2026,
                   instance_yaml("tour", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
    write_instance(data, "tour", 2027,
                   instance_yaml("tour", 2027, "2027-10-17", "2027-10-18", status="cancelled", extra=CARS))
    # Quotes and an ampersand, which have to survive the trip into an attribute value.
    write_event(data, "show", name_en="'Test \"Show\" & Meet'", fee=1000)
    write_instance(data, "show", 2026,
                   instance_yaml("show", 2026, "2026-11-03", "2026-11-03", status="tentative",
                                 extra=display_cars_yaml([("Toyota", "2000GT")])))


class PageDescriptionTests(unittest.TestCase):
    """What a search snippet or a shared link says about each page, before anyone opens it."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.out = cls.tmp / "site"
        make_description_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)


    def head(self, rel: str) -> HeadParser:
        return HeadParser((self.out / rel).read_text(encoding="utf-8"))

    def description(self, rel: str) -> str:
        return self.head(rel).meta["description"]

    def test_the_home_page_is_described_by_the_site_lede(self):
        self.assertEqual(self.description("index.html"), settings.SITE_LEDE)

    def test_an_event_page_is_described_by_the_first_sentence_of_its_summary(self):
        # A snippet shows about 155 characters, and a summary can run to 75 words.
        self.assertEqual(self.description("events/tour/index.html"), "A tour past Test Park and the harbour.")

    def test_an_event_without_a_summary_is_described_by_what_its_page_holds(self):
        self.assertEqual(self.description("events/show/index.html"),
                         'Dates, venue and admission for Test "Show" & Meet in Shizuoka.')

    def test_an_edition_is_described_by_what_its_page_holds(self):
        self.assertEqual(self.description("events/tour/2026/index.html"),
                         "Route for Test Tour 2026: 18–19 Oct 2026, Test Park, Shizuoka.")

    def test_a_cancelled_edition_says_so_before_anything_else(self):
        # A snippet that read like a normal listing would tell a searcher it is still on.
        self.assertEqual(self.description("events/tour/2027/index.html"),
                         "Cancelled. Entry list for Test Tour 2027: 17–18 Oct 2027, Test Park, Shizuoka.")

    def test_an_unconfirmed_show_says_so_and_names_its_list_as_the_page_does(self):
        self.assertEqual(self.description("events/show/2026/index.html"),
                         'Dates not confirmed. Cars on display for Test "Show" & Meet 2026: '
                         "3 Nov 2026, Test Park, Shizuoka.")

    def test_link_previews_repeat_the_title_description_and_canonical_address(self):
        pages = ["index.html", "about/index.html", "events/tour/index.html", "events/tour/2026/index.html"]
        for rel in pages:
            head = self.head(rel)
            self.assertEqual(head.meta["og:title"], head.title, rel)
            self.assertEqual(head.meta["og:description"], head.meta["description"], rel)
            self.assertEqual(head.meta["og:url"], head.canonical, rel)
            self.assertEqual(head.canonical, f"{settings.SITE_URL}/{rel.removesuffix('index.html')}", rel)
            self.assertEqual(head.meta["og:type"], "website", rel)
            self.assertEqual(head.meta["og:site_name"], settings.SITE_NAME, rel)

    def test_event_and_edition_titles_leave_the_brand_to_the_search_result(self):
        # Google shows the site name on its own line, and the suffix pushed most titles past 60 characters.
        self.assertEqual(self.head("events/tour/index.html").title, "Test Tour: Visitor Guide")
        self.assertEqual(self.head("events/tour/2026/index.html").title, "Test Tour 2026: Route")

    def test_site_level_titles_keep_the_brand(self):
        # "About" alone names nothing.
        for rel in ("index.html", "about/index.html", "ja/index.html", "404.html"):
            self.assertTrue(self.head(rel).title.endswith(f" | {settings.SITE_NAME}"), rel)

    def test_link_previews_name_the_page_language(self):
        # Left out, a preview assumes en_US.
        for rel in ("index.html", "about/index.html", "events/tour/index.html", "events/tour/2026/index.html"):
            self.assertEqual(self.head(rel).meta["og:locale"], "en_GB", rel)
        self.assertEqual(self.head("ja/index.html").meta["og:locale"], "ja_JP")

    def test_the_preview_image_is_always_the_sites_own(self):
        # Never a YouTube thumbnail: those are not the site's to put in a share card.
        for rel in ("index.html", "events/tour/2026/index.html"):
            self.assertTrue(self.head(rel).meta["og:image"].startswith(f"{settings.SITE_URL}/static/"), rel)

    def test_the_404_page_describes_nothing(self):
        head = self.head("404.html")
        self.assertNotIn("description", head.meta)
        self.assertFalse([key for key in head.meta if key.startswith("og:")])


class BreadcrumbTests(unittest.TestCase):
    """An edition page sits under its event page; the trail shows it, and says so to search engines."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)


    PAGE = "events/hill-climb/2026-autumn/index.html"

    def html(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def trail(self) -> str:
        found = re.search(r'<nav class="breadcrumbs" aria-label="Breadcrumb">(.*?)</nav>', self.html(self.PAGE), re.S)
        self.assertIsNotNone(found, "edition page has no breadcrumb trail")
        return found.group(1)

    def test_the_trail_comes_before_the_heading(self):
        html = self.html(self.PAGE)
        self.assertLess(html.index('class="breadcrumbs"'), html.index("<h1>"))

    def test_the_trail_links_home_and_the_event_and_names_the_current_page_unlinked(self):
        trail = self.trail()
        links = re.findall(r'<a href="([^"]*)">([^<]*)</a>', trail)
        resolved = [(urljoin(f"{settings.SITE_URL}/{self.PAGE}", href), text) for href, text in links]
        self.assertEqual(resolved, [(f"{settings.SITE_URL}/", "Home"),
                                    (f"{settings.SITE_URL}/events/hill-climb/", "Hill Climb")])
        self.assertIn('<span aria-current="page">Autumn 2026</span>', trail)

    def test_separators_are_hidden_from_screen_readers(self):
        trail = self.trail()
        self.assertEqual(trail.count('<span class="sep" aria-hidden="true">›</span>'), 2)

    def test_structured_data_matches_the_visible_trail(self):
        # Google expects breadcrumb markup to describe what the page shows.
        blocks = [b for b in jsonld_blocks(self.html(self.PAGE)) if b["@type"] == "BreadcrumbList"]
        self.assertEqual(len(blocks), 1)
        items = blocks[0]["itemListElement"]
        self.assertEqual([(i["position"], i["name"], i.get("item")) for i in items], [
            (1, "Home", f"{settings.SITE_URL}/"),
            (2, "Hill Climb", f"{settings.SITE_URL}/events/hill-climb/"),
            (3, "Autumn 2026", None),
        ])

    def test_pages_whose_trail_would_only_say_home_have_none(self):
        for rel in ("index.html", "events/hill-climb/index.html", "about/index.html"):
            html = self.html(rel)
            self.assertNotIn("breadcrumbs", html, rel)
            self.assertNotIn("BreadcrumbList", html, rel)


# Identifiers, codes and dates, which a page states in its own words if at all; other tests check them.
NOT_PAGE_TEXT = {"@context", "@type", "url", "item", "eventStatus", "eventAttendanceMode",
                 "startDate", "endDate", "addressCountry", "priceCurrency"}


def visible_text(html: str) -> str:
    body = re.sub(r"<script.*?</script>", " ", re.split(r"<body[^>]*>", html, maxsplit=1)[1], flags=re.S)
    # Inline tags sit mid-sentence (mark_ja's spans, a link before a full stop), so they go without a space.
    body = re.sub(r"</?(?:span|a|em|strong|abbr)\b[^>]*>", "", body)
    # An accessible name is what a screen reader announces: the logo is the site name, drawn.
    labels = re.findall(r'aria-label="([^"]*)"', body)
    return " ".join(unescape(" ".join([re.sub(r"<[^>]+>", " ", body), *labels])).split())


def text_claims(value, key=None) -> list[str]:
    """Every text value in a JSON-LD block, at any depth, apart from NOT_PAGE_TEXT."""
    if isinstance(value, dict):
        return [claim for k, v in value.items() if k not in NOT_PAGE_TEXT for claim in text_claims(v, k)]
    if isinstance(value, list):
        return [claim for v in value for claim in text_claims(v, key)]
    return [" ".join(value.split())] if isinstance(value, str) else []


def shown(claim: str, text: str, heading: str) -> bool:
    # An event page names each edition as its heading plus the label in the Dates table.
    return claim in text or (claim.startswith(f"{heading} ") and claim.removeprefix(f"{heading} ") in text)


def unshown_claims(html: str) -> tuple[int, list[str]]:
    """How many text claims the page's JSON-LD makes, and those its visible text lacks."""
    text = visible_text(html)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    heading = visible_text(f"<body>{h1.group(1)}") if h1 else ""
    claims = [claim for block in jsonld_blocks(html) for claim in text_claims(block)]
    return len(claims), [claim for claim in claims if not shown(claim, text, heading)]


class StructuredDataTruthTests(unittest.TestCase):
    """Each Event block claims only what its page shows (spec 6.2, structured-data review 2026-11-23)."""

    ADDRESS = "1-1 Test, Testville, Shizuoka (静岡県テスト市1-1)"
    FAR_ADDRESS = "2-2 Far, Fartown, Shizuoka (静岡県遠市2-2)"

    @classmethod
    def setUpClass(cls):
        tmp = temp_dir(cls)
        data = tmp / "data"
        write_event(data, "meet", extra=(
            "organizer: テスト実行委員会 (Test Committee, a club formed in 2023)\n"
            "summary_en: A meeting of old cars in the park.\n"
            f"street_address: {cls.ADDRESS}\n"))
        editions = {
            2025: instance_yaml("meet", 2025, "2025-11-03", "2025-11-03"),
            2026: instance_yaml("meet", 2026, "2026-11-03", "2026-11-03", extra=CARS),
            2027: instance_yaml("meet", 2027, "2027-11-03", "2027-11-03", extra="venue_en: Other Field\n" + CARS),
            2028: instance_yaml("meet", 2028, "2028-11-03", "2028-11-03",
                                extra=f"venue_en: Far Field\nstreet_address: {cls.FAR_ADDRESS}\n" + CARS),
            2029: instance_yaml("meet", 2029, "2029-11-03", "2029-11-03", status="tentative"),
            2030: instance_yaml("meet", 2030, "2030-11-03", "2030-11-03", status="tentative", extra=CARS),
        }
        for year, text in editions.items():
            write_instance(data, "meet", year, text)
        build.build(data, tmp / "site")
        cls.pages = {p.relative_to(tmp / "site").as_posix(): p.read_text(encoding="utf-8")
                     for p in (tmp / "site").rglob("*.html")}
        cls.api = {e["id"]: e for e in json.loads((tmp / "site/api/events.json").read_text(encoding="utf-8"))["events"]}

    def events(self, page: str) -> dict:
        return {b["name"]: b for b in jsonld_blocks(self.pages[page]) if b["@type"] == "Event"}

    def visible(self, html: str) -> str:
        return visible_text(html)

    def test_no_block_names_an_organizer(self):
        # The field describes the organiser for visitors ("a club formed in 2023"); it is not a name.
        blocks = [b for html in self.pages.values() for b in jsonld_blocks(html) if b["@type"] == "Event"]
        self.assertTrue(blocks)
        for block in blocks:
            self.assertNotIn("organizer", block, block["name"])

    def test_an_edition_page_shows_the_events_address_and_marks_it_up(self):
        page = "events/meet/2026/index.html"
        self.assertIn(self.ADDRESS, self.visible(self.pages[page]))
        self.assertEqual(self.events(page)["Test Event 2026"]["location"]["address"]["streetAddress"], self.ADDRESS)

    def test_an_edition_at_its_own_venue_does_not_take_the_events_address(self):
        page = "events/meet/2027/index.html"
        self.assertNotIn("streetAddress", self.events(page)["Test Event 2027"]["location"]["address"])
        self.assertNotIn("1-1 Test", self.visible(self.pages[page]))

    def test_the_json_feed_follows_the_pages_on_which_address_an_edition_has(self):
        # build_api once rebuilt the address itself and lent the event's to an edition
        # elsewhere (json-feed-and-agent-files review, 2026-11-24).
        self.assertEqual(self.api["meet-2026"]["street_address"], self.ADDRESS)
        self.assertNotIn("street_address", self.api["meet-2027"])
        self.assertEqual(self.api["meet-2028"]["street_address"], self.FAR_ADDRESS)

    def test_an_edition_at_its_own_venue_gives_its_own_address(self):
        page = "events/meet/2028/index.html"
        self.assertIn(self.FAR_ADDRESS, self.visible(self.pages[page]))
        self.assertEqual(self.events(page)["Test Event 2028"]["location"]["address"]["streetAddress"],
                         self.FAR_ADDRESS)

    def test_the_summary_describes_an_event_only_on_the_page_that_shows_it(self):
        self.assertEqual(self.events("events/meet/index.html")["Test Event 2025"]["description"],
                         "A meeting of old cars in the park.")
        self.assertNotIn("description", self.events("events/meet/2026/index.html")["Test Event 2026"])

    def test_an_edition_whose_dates_are_not_confirmed_has_no_block(self):
        names = {b["name"] for html in self.pages.values() for b in jsonld_blocks(html) if b["@type"] == "Event"}
        self.assertEqual(names, {"Test Event 2025", "Test Event 2026", "Test Event 2027", "Test Event 2028"})

    def test_the_checker_finds_a_claim_the_page_does_not_show(self):
        # Proves the page tests can fail: the description is marked up but not shown.
        html = ('<body><p>Test <a href="x">Park</a>.</p><script type="application/ld+json">'
                '{"@type": "Event", "url": "https://x/", "location": {"name": "Test Park"},'
                ' "description": "Not on the page"}</script></body>')
        self.assertEqual(unshown_claims(html), (2, ["Not on the page"]))

    def test_every_claim_appears_on_its_page(self):
        for page, html in self.pages.items():
            with self.subTest(page=page):
                self.assertEqual(unshown_claims(html)[1], [])


class RealSiteStructuredDataTests(unittest.TestCase):
    """The real data reaches fields and wordings no fixture does, so its pages are checked too."""

    def test_every_claim_on_every_page_of_the_real_site_appears_on_that_page(self):
        out = temp_dir(self)
        build.build(ROOT / "data", out)
        checked = 0
        for page in sorted(out.rglob("*.html")):
            html = page.read_text(encoding="utf-8")
            count, missing = unshown_claims(html)
            checked += count
            with self.subTest(page=page.relative_to(out).as_posix()):
                self.assertEqual(missing, [])
        # A checker that found no claims at all would pass every page.
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
