"""Meta descriptions, breadcrumbs and structured data.

These are offline proxies for Google's Rich Results Test, so a manual pass with it should be a formality.
"""

import re
import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urljoin

from helpers import (CARS, display_cars_yaml, HeadParser, instance_yaml, jsonld_blocks, make_fixture, ROUTE,
                     write_event, write_instance)
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
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_description_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

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
        cls.tmp = Path(tempfile.mkdtemp())
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

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


class StructuredDataOrganizerTests(unittest.TestCase):
    """The organiser is named but given no URL: `official_url` is often a tourism listing,
    a blog post or an Instagram account, which would be a false claim about its website."""

    def test_organizer_has_a_name_and_no_url(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        write_event(tmp / "data", "meet", extra="organizer: Test Club\n")
        write_instance(tmp / "data", "meet", 2026, instance_yaml("meet", 2026, "2026-11-03", "2026-11-03"))
        build.build(tmp / "data", tmp / "site")
        block, = jsonld_blocks((tmp / "site/events/meet/index.html").read_text(encoding="utf-8"))
        self.assertEqual(block["organizer"], {"@type": "Organization", "name": "Test Club"})


if __name__ == "__main__":
    unittest.main()
