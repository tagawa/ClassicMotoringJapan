"""Event and edition pages: entry lists, videos, fees, notes and page sections."""

import json
import re
import shutil
import unittest

from helpers import (CARS, cars_yaml, display_cars_yaml, instance_yaml, jsonld_blocks, make_fixture, ROOT,
                     ROUTE, ROUTE_ONE_DAY, temp_dir, unfold, write_event, write_instance)
import build  # noqa: E402
import settings  # noqa: E402
import validate  # noqa: E402


class VerifiedPlacementTests(unittest.TestCase):
    """The check date and its source sit with the facts they vouch for, not under the lists."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)
        cls.edition = (cls.out / "events/autumn-rally/2026/index.html").read_text(encoding="utf-8")
        cls.event = (cls.out / "events/autumn-rally/index.html").read_text(encoding="utf-8")


    def facts(self, html: str) -> str:
        return re.search(r'(?s)<dl class="facts">.*?</dl>', html).group(0)

    def test_an_edition_page_gives_the_date_and_links_the_source_among_its_facts(self):
        # Named by its domain: a source is often a listing, a blog or a video, not the organiser.
        self.assertRegex(self.facts(self.edition),
                         r'<dt>Last verified</dt>\s*<dd>2026-09-20, against '
                         r'<a href="https://example.com/autumn-rally/2026/">example.com</a></dd>')

    def test_on_an_edition_page_it_comes_before_the_entry_list_and_route(self):
        self.assertLess(self.edition.index("Last verified"), self.edition.index("<h2"))

    def test_an_event_page_gives_the_date_beside_the_source(self):
        # The date is the latest check of the event or any edition, so it names no one source.
        self.assertRegex(self.facts(self.event),
                         r'<dt>Source</dt>\s*<dd><a href="https://example.com/autumn-rally/">example.com</a> '
                         r'\(Japanese\)</dd>\s*<dt>Last verified</dt>\s*<dd>2026-09-20</dd>')

    def test_no_page_calls_a_source_the_organisers(self):
        # official_url and source_url are often a tourism listing, a blog post or a video.
        for path in self.out.rglob("*"):
            if path.suffix in (".html", ".json", ".txt"):
                text = path.read_text(encoding="utf-8")
                for claim in ("organiser's announcement", "official site", "organiser's page"):
                    self.assertNotIn(claim, text.lower(), path)

    def page(self, event_extra="", url="https://example.com/meet/", status="confirmed") -> tuple[str, str]:
        tmp = temp_dir(self)
        write_event(tmp / "data", "meet", extra=event_extra)
        text = instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", status=status, extra=CARS)
        write_instance(tmp / "data", "meet", 2026, text.replace("https://example.com/meet/2026/", url))
        build.build(tmp / "data", tmp / "site")
        return ((tmp / "site/events/meet/index.html").read_text(encoding="utf-8"),
                (tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8"))

    def test_the_organiser_is_plain_text_not_the_source_link(self):
        event, _ = self.page("organizer: Test Club\n")
        self.assertRegex(self.facts(event), r'<dt>Organiser</dt>\s*<dd>Test Club</dd>\s*<dt>Source</dt>')
        self.assertNotIn(">Test Club</a>", event)

    def test_no_organiser_row_without_an_organiser(self):
        event, _ = self.page()
        self.assertNotIn("<dt>Organiser</dt>", event)

    def test_the_domain_drops_www(self):
        _, edition = self.page(url="https://www.listing.example.org/events/123")
        self.assertIn('against <a href="https://www.listing.example.org/events/123">listing.example.org</a>', edition)

    def test_a_tentative_edition_names_its_source_by_domain(self):
        _, edition = self.page(url="https://listing.example.org/1", status="tentative")
        self.assertIn('<p class="note"><a href="https://listing.example.org/1">listing.example.org</a> '
                      'does not confirm these dates yet.</p>', edition)

    def test_the_footer_no_longer_repeats_it(self):
        for html in (self.edition, self.event):
            self.assertNotIn("Last verified", html[html.index('<footer class="site-footer">'):])


class EntryListProvisionalTests(unittest.TestCase):
    """An entry list published before the event only warns while we have not re-checked."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"
        write_event(self.data, "meet")


    def edition_page(self, verified: str) -> str:
        write_instance(self.data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                                     extra=CARS, verified=verified))
        out = self.tmp / "site"
        shutil.rmtree(out, ignore_errors=True)
        build.build(self.data, out)
        return (out / "events/meet/2026/index.html").read_text(encoding="utf-8")

    def test_list_is_provisional_while_the_event_is_still_ahead_of_our_last_check(self):
        html = self.edition_page("2026-09-20")
        self.assertIn("<p>As of 2026-09-15.", html)
        self.assertIn("cars may withdraw or change", html)

    def test_list_is_still_provisional_when_we_only_checked_on_the_closing_day(self):
        # Cars can withdraw during the event, so a same-day check does not settle the list.
        self.assertIn("cars may withdraw or change", self.edition_page("2026-10-18"))

    def test_list_is_settled_once_we_have_checked_after_the_event_ended(self):
        html = self.edition_page("2026-10-19")
        self.assertIn("<p>As of 2026-09-15.", html)
        self.assertNotIn("cars may withdraw or change", html)


VIDEOS = (
    "videos:\n"
    "  - youtube_id: t3UUnZ7g5P0\n"
    "    label_en: Day 1\n"
    "  - youtube_id: fIJCC_4IcE0\n"
    "    label_en: Day 2\n"
)


class VideoTests(unittest.TestCase):
    """A past edition embeds its videos; later editions link back to the latest of them."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2024, instance_yaml("meet", 2024, "2024-10-18", "2024-10-18",
                                                              extra=VIDEOS.replace("t3UUnZ7g5P0", "AAAAAAAAAAA")))
        write_instance(self.data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-18", "2025-10-18",
                                                              extra=VIDEOS))
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-19",
                                                              extra=ROUTE))


    def page(self, stem) -> str:
        build.build(self.data, self.tmp / "site")
        return (self.tmp / f"site/events/meet/{stem}/index.html").read_text(encoding="utf-8")

    def test_videos_alone_earn_the_edition_its_own_page(self):
        self.assertIn("<h1>Test Event 2025</h1>", self.page(2025))

    def test_every_embed_uses_the_no_cookie_domain(self):
        srcs = re.findall(r'<iframe[^>]*\ssrc="([^"]+)"', self.page(2025))
        self.assertEqual(srcs, ["https://www.youtube-nocookie.com/embed/t3UUnZ7g5P0",
                                "https://www.youtube-nocookie.com/embed/fIJCC_4IcE0"])

    def test_every_embed_is_titled_and_lazy(self):
        frames = re.findall(r"<iframe[^>]*>", self.page(2025))
        self.assertEqual(len(frames), 2)
        self.assertIn('title="Test Event 2025, Day 1"', frames[0])
        for frame in frames:
            self.assertIn('loading="lazy"', frame)

    def test_each_video_links_to_youtube_by_its_label_alone(self):
        html = self.page(2025)
        self.assertIn('<a href="https://www.youtube.com/watch?v=fIJCC_4IcE0">Day 2</a>', html)
        self.assertNotIn("on YouTube", html)

    def test_a_later_edition_links_to_the_latest_earlier_videos(self):
        link = re.search(r'<a href="../../../events/meet/2025/#videos">(.*?)</a>', self.page(2026)).group(1)
        self.assertTrue(link.endswith("</svg>Videos of the 2025 event"), link)

    def test_the_videos_link_is_drawn_with_a_play_glyph_like_the_map_pin(self):
        link = re.search(r'<a href="[^"]*#videos">(.*?)</a>', self.page(2026)).group(1)
        svg = link[link.index("<svg"):link.index("</svg>")]
        for attr in ('class="icon"', 'aria-hidden="true"', 'focusable="false"',
                     'width="16"', 'height="16"', 'currentColor'):
            self.assertIn(attr, svg)
        self.assertNotIn("#", svg, "a baked-in colour would ignore dark mode")

    def test_an_edition_with_videos_links_to_the_one_before(self):
        self.assertIn("Videos of the 2024 event", self.page(2025))
        self.assertNotIn("Videos of the", self.page(2024))

    def test_an_edition_without_videos_embeds_the_first_earlier_one(self):
        srcs = re.findall(r'<iframe[^>]*\ssrc="([^"]+)"', self.page(2026))
        self.assertEqual(srcs, ["https://www.youtube-nocookie.com/embed/t3UUnZ7g5P0"])

    def test_the_borrowed_video_comes_last_under_a_heading_naming_its_edition(self):
        html = self.page(2026)
        heading = html.index(">From the 2025 event</h2>")
        self.assertGreater(heading, html.index('<h2 id="route">Route</h2>'))
        self.assertGreater(html.index("<iframe"), heading)

    def test_the_borrowed_video_is_titled_lazy_and_linked_like_an_own_one(self):
        html = self.page(2026)
        frame = re.search(r"<iframe[^>]*>", html).group(0)
        self.assertIn('title="Test Event 2025, Day 1"', frame)
        self.assertIn('loading="lazy"', frame)
        self.assertIn('<a href="https://www.youtube.com/watch?v=t3UUnZ7g5P0">Day 1</a>', html)

    def test_an_edition_with_its_own_videos_borrows_none(self):
        html = self.page(2025)
        self.assertNotIn("From the", html)
        self.assertNotIn("AAAAAAAAAAA", html)

    def test_the_borrowed_video_is_not_a_section_of_the_edition(self):
        html = self.page(2026)
        self.assertNotIn('id="videos"', html)
        title = re.search(r"<title>(.*?)</title>", html).group(1)
        self.assertNotIn("video", title.lower())
        event_page = (self.tmp / "site/events/meet/index.html").read_text(encoding="utf-8")
        self.assertIn('href="../../events/meet/2026/">Route</a>', event_page)

    def test_a_borrowed_video_alone_does_not_earn_an_edition_page(self):
        write_instance(self.data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-18", "2027-10-18"))
        build.build(self.data, self.tmp / "site")
        self.assertFalse((self.tmp / "site/events/meet/2027").exists())

    def test_a_twice_yearly_event_names_the_season_as_well_as_the_year(self):
        write_instance(self.data, "meet", "2026-spring", instance_yaml(
            "meet", 2026, "2026-04-18", "2026-04-18", extra=VIDEOS))
        write_instance(self.data, "meet", "2026-autumn", instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-19", extra=ROUTE))
        (self.data / "events/meet/2026.yml").unlink()
        html = self.page("2026-autumn")
        self.assertIn("Videos of the Spring 2026 event", html)
        self.assertIn(">From the Spring 2026 event</h2>", html)

    def test_the_event_page_names_videos_among_the_edition_contents(self):
        build.build(self.data, self.tmp / "site")
        html = (self.tmp / "site/events/meet/index.html").read_text(encoding="utf-8")
        self.assertIn('href="../../events/meet/2025/">Videos</a>', html)

    def test_the_json_feed_carries_the_videos(self):
        build.build(self.data, self.tmp / "site")
        feed = json.loads((self.tmp / "site/api/events.json").read_text(encoding="utf-8"))
        by_year = {e["year"]: e for e in feed["events"]}
        self.assertEqual(by_year[2025]["videos"][1], {"youtube_id": "fIJCC_4IcE0", "label_en": "Day 2"})
        self.assertNotIn("videos", by_year[2026])

    def test_a_full_url_in_place_of_the_id_is_rejected(self):
        write_instance(self.data, "meet", 2025, instance_yaml(
            "meet", 2025, "2025-10-18", "2025-10-18",
            extra=VIDEOS.replace("t3UUnZ7g5P0", "https://www.youtube.com/watch?v=t3UUnZ7g5P0")))
        with self.assertRaises(validate.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn("videos item 1: youtube_id", str(ctx.exception))

    def test_a_video_without_a_label_is_rejected(self):
        write_instance(self.data, "meet", 2025, instance_yaml(
            "meet", 2025, "2025-10-18", "2025-10-18", extra=VIDEOS.replace("    label_en: Day 1\n", "")))
        with self.assertRaises(validate.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn("videos item 1: missing required field 'label_en'", str(ctx.exception))


class PastEditionTests(unittest.TestCase):
    """Videos exist only once an edition has run, so they mark the page as a look back."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-19",
                                                              extra=ROUTE + CARS + VIDEOS))
        write_instance(self.data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-18", "2027-10-19",
                                                              extra=ROUTE.replace("2026-10-1", "2027-10-1")
                                                              + CARS))


    def page(self, stem) -> str:
        build.build(self.data, self.tmp / "site")
        return (self.tmp / f"site/events/meet/{stem}/index.html").read_text(encoding="utf-8")

    def test_an_edition_with_videos_leads_with_them_then_the_cars(self):
        self.assertEqual(re.findall(r"<h2[^>]*>(.*?)</h2>", self.page(2026)), ["Videos", "Entry list", "Route"])

    def test_an_edition_without_videos_keeps_the_route_first(self):
        self.assertEqual(re.findall(r"<h2[^>]*>(.*?)</h2>", self.page(2027)),
                         ["Route", "Entry list", "From the 2026 event"])

    def test_the_title_names_the_sections_in_page_order(self):
        self.assertIn("<title>Test Event 2026: Videos, entry list and route</title>", self.page(2026))

    def nav(self, stem) -> str:
        found = re.search(r'<nav class="edition-steps" aria-label="Other events">(.*?)</nav>', self.page(stem), re.S)
        return re.sub(r"\s+", " ", found.group(1)).strip() if found else ""

    def test_an_edition_links_forward_to_the_next_one_by_its_label(self):
        self.assertIn('<a href="../../../events/meet/2027/">Next event: 2027'
                      '<span aria-hidden="true"> →</span></a>', self.nav(2026))

    def test_an_edition_links_back_to_the_previous_one_by_its_label(self):
        self.assertIn('<a href="../../../events/meet/2026/"><span aria-hidden="true">← </span>'
                      'Previous event: 2026</a>', self.nav(2027))

    def test_both_links_share_one_line_back_first_with_a_bar_screen_readers_skip(self):
        write_instance(self.data, "meet", 2028, instance_yaml("meet", 2028, "2028-10-15", "2028-10-15"))
        nav = self.nav(2027)
        self.assertLess(nav.index("Previous event"), nav.index("Next event"))
        self.assertIn('<span class="bar" aria-hidden="true">|</span>', nav)

    def test_the_latest_edition_has_no_forward_link_and_no_bar(self):
        nav = self.nav(2027)
        self.assertNotIn("Next event", nav)
        self.assertNotIn('class="bar"', nav)

    def test_the_earliest_edition_has_no_back_link(self):
        self.assertNotIn("Previous event", self.nav(2026))

    def test_a_lone_edition_has_no_nav_at_all(self):
        shutil.rmtree(self.data / "events" / "meet")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-19",
                                                              extra=CARS))
        self.assertNotIn("edition-steps", self.page(2026))

    def test_a_neighbour_without_a_page_links_to_the_event_page(self):
        write_instance(self.data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-19", "2025-10-19"))
        write_instance(self.data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-17", "2027-10-17"))
        nav = self.nav(2026)
        self.assertIn('<a href="../../../events/meet/"><span aria-hidden="true">← </span>Previous event: 2025</a>', nav)
        self.assertIn('<a href="../../../events/meet/">Next event: 2027', nav)

    def test_the_links_carry_their_edition_status(self):
        write_instance(self.data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-17", "2027-10-17",
                                                              status="tentative"))
        self.assertIn("</a> (dates not confirmed)", self.nav(2026))
        write_instance(self.data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-17", "2027-10-17",
                                                              status="cancelled"))
        self.assertIn("</a> (cancelled)", self.nav(2026))
        write_instance(self.data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-19", "2025-10-19",
                                                              status="cancelled"))
        self.assertIn("Previous event: 2025</a> (cancelled)", self.nav(2026))

    def test_each_link_is_kept_whole_and_a_phone_stacks_them_without_the_bar(self):
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.edition-steps \.step \{[^}]*display: inline-block")
        narrow = re.search(r"@media \(max-width: 480px\) \{(.*?)\n\}", css, re.S).group(1)
        self.assertRegex(narrow, r"\.edition-steps \.step \{[^}]*display: block")
        self.assertRegex(narrow, r"\.edition-steps \.bar \{[^}]*display: none")


class EventNotesLinkTests(unittest.TestCase):
    """The edition page's link to the event page names only the notes that page has."""

    def page(self, extra: str) -> str:
        tmp = temp_dir(self)
        write_event(tmp / "data", "meet", extra=extra)
        write_instance(tmp / "data", "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=CARS))
        build.build(tmp / "data", tmp / "site")
        return (tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8")

    def test_every_kind_of_note_is_named(self):
        html = self.page("nearest_station: Test\nspectator_notes_en: Free.\nphotography_notes_en: Allowed.\n")
        self.assertIn('<a href="../../../events/meet/">Access, spectator and photography notes</a>', html)

    def test_access_notes_alone_count_as_access(self):
        self.assertIn(">Access notes</a>", self.page("access_notes_en: Walk.\n"))

    def test_notes_the_event_lacks_are_not_promised(self):
        html = self.page("spectator_notes_en: Free.\n")
        self.assertIn('<a href="../../../events/meet/">Spectator notes</a>', html)
        self.assertNotIn("photography", html.lower())
        self.assertNotIn("viewing spots", html)

    def test_no_link_when_the_event_has_no_notes(self):
        # The breadcrumb still leads there.
        self.assertNotIn(" notes</a>", self.page(""))


class EntryListHeadingTests(unittest.TestCase):
    """The two strips look alike, so each part of an entry list says what it counts."""

    def page(self, cars: str) -> str:
        tmp = temp_dir(self)
        data = tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=cars))
        build.build(data, tmp / "site")
        return (tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")

    def subheadings(self, html: str) -> list[str]:
        return re.findall(r"<h3>(.*?)</h3>", html)

    def test_each_strip_has_its_own_heading_and_the_table_its_own_summary_in_page_order(self):
        html = self.page(cars_yaml([1929, 1955, 1955]))
        self.assertEqual(self.subheadings(html), ["By decade", "By make"])
        order = [html.index(mark) for mark in ("<h3>By decade</h3>", '<ol class="chart decades">',
                                               "<h3>By make</h3>", '<ol class="chart makes">',
                                               "<summary>All 3 cars</summary>", "<table>")]
        self.assertEqual(order, sorted(order), "each heading should sit directly above what it names")

    def test_the_two_strips_share_one_row_so_wide_screens_can_set_them_side_by_side(self):
        html = self.page(cars_yaml([1929, 1955, 1955]))
        row = re.search(r'(?s)<div class="strips">(.*?)<details', html)
        self.assertIsNotNone(row)
        self.assertIn('class="chart decades"', row.group(1))
        self.assertIn('class="chart makes"', row.group(1))

    def test_the_table_folds_away_under_the_strips_that_summarise_it(self):
        html = self.page(cars_yaml([1929, 1955, 1955]))
        folded = re.search(r'(?s)<details class="all-cars">\s*<summary>All 3 cars</summary>.*?</details>', html)
        self.assertIsNotNone(folded)
        self.assertIn("<table>", folded.group(0))

    def test_a_list_of_one_car_is_not_called_all_of_them(self):
        self.assertIn("<summary>1 car</summary>", self.page(cars_yaml([1955])))

    def test_a_numbered_list_without_years_has_no_decade_heading(self):
        html = self.page('list_as_of: 2026-09-15\ncars:\n  - entry_no: "01"\n    make: Test\n    model: Car\n')
        self.assertEqual(self.subheadings(html), ["By make"])
        self.assertIn('<details class="all-cars">', html)

    def test_a_line_up_with_no_strips_shows_its_table_open(self):
        # Nothing above it says what is in it, so folding it would hide the whole list.
        html = self.page(display_cars_yaml([("Toyota", "2000GT"), ("Honda", "S500")]))
        self.assertEqual(self.subheadings(html), [])
        self.assertIn("<table>", html)
        self.assertNotIn('class="all-cars"', html)
        self.assertNotIn('class="strips"', html)


class EntryListFlagTests(unittest.TestCase):
    """A car's country, where the organiser's list gives one, as a small flag beside its make."""

    FLAGGED = ('list_as_of: 2026-09-15\ncars:\n'
               '  - entry_no: "01"\n    year: 1955\n    make: Alfa Romeo\n    model: Car\n    country: IT\n'
               '  - entry_no: "02"\n    year: 1956\n    make: MG\n    model: Car\n    country: GB\n'
               '  - entry_no: "03"\n    year: 1957\n    make: Lancia\n    model: Car\n    country: IT\n'
               '  - entry_no: "04"\n    year: 1958\n    make: Test\n    model: Car\n')

    def site(self, cars: str, makes: str = "") -> dict:
        """makes, when given, is the text of data/makes.yml: each make's home country."""
        tmp = temp_dir(self)
        data = tmp / "data"
        write_event(data, "meet")
        if makes:
            (data / "makes.yml").write_text(makes, encoding="utf-8")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=cars))
        build.build(data, tmp / "site")
        return {"page": (tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8"),
                "json": (tmp / "site" / "api" / "events.json").read_text(encoding="utf-8")}

    def test_the_flag_sits_before_the_make_and_names_its_country_for_those_who_cannot_see_it(self):
        html = self.site(self.FLAGGED)["page"]
        self.assertRegex(html, r'<td class="flagged"><svg class="flag"[^>]* role="img" aria-label="Italy"[^>]*><title>Italy</title>'
                               r'<use xlink:href="#flag-it"/></svg>Alfa Romeo</td>')
        self.assertRegex(html, r'aria-label="Britain"[^>]*><title>Britain</title><use xlink:href="#flag-gb"/></svg>MG</td>')

    def test_each_flag_on_the_page_is_drawn_once_and_no_others_are_shipped(self):
        html = self.site(self.FLAGGED)["page"]
        self.assertEqual(html.count('id="flag-it"'), 1)
        self.assertEqual(html.count('id="flag-gb"'), 1)
        self.assertNotIn('id="flag-de"', html)
        self.assertLess(html.index('id="flag-it"'), html.index('xlink:href="#flag-it"'),
                        "the drawings should be defined before the rows that use them")

    def test_a_car_without_a_country_keeps_the_indent_so_the_makes_still_line_up(self):
        # The cell is indented by the flag's width either way, so a make that wraps hangs clear of it.
        self.assertIn('<td class="unflagged">Test</td>', self.site(self.FLAGGED)["page"])

    def test_a_list_with_no_countries_has_no_flags_and_no_slots(self):
        html = self.site(cars_yaml([1955, 1956]))["page"]
        self.assertNotIn("flag", html)
        self.assertIn("<td>Test</td>", html)

    def test_the_json_carries_the_country_code(self):
        self.assertIn('"country": "IT"', self.site(self.FLAGGED)["json"])

    def numbered(self, *cars: str) -> str:
        return "list_as_of: 2026-09-15\ncars:\n" + "".join(
            f'  - entry_no: "{i:02d}"\n    year: 1960\n    model: Car\n{car}' for i, car in enumerate(cars, 1))

    def test_a_list_that_prints_no_country_takes_each_flag_from_the_make(self):
        site = self.site(self.numbered("    make: Lancia\n", "    make: Honda\n"), makes="Honda: JP\nLancia: IT\n")
        self.assertRegex(site["page"], r'aria-label="Italy"[^>]*><title>Italy</title><use xlink:href="#flag-it"/></svg>Lancia</td>')
        self.assertRegex(site["page"], r'aria-label="Japan"[^>]*><title>Japan</title><use xlink:href="#flag-jp"/></svg>Honda</td>')
        self.assertIn('"country": "IT"', site["json"], "the JSON should say what the page shows")

    def test_a_cars_own_country_beats_its_makes(self):
        # A BMW Isetta built at Brighton: the organiser's list says Britain, the make says Germany.
        page = self.site(self.numbered("    make: BMW\n    country: GB\n"), makes="BMW: DE\n")["page"]
        self.assertRegex(page, r'aria-label="Britain"[^>]*><title>Britain</title><use xlink:href="#flag-gb"/></svg>BMW</td>')
        self.assertNotIn('id="flag-de"', page)

    def test_a_make_with_no_single_country_has_no_flag_until_a_car_is_given_one(self):
        # Ford built Mustangs in America and Anglias in Britain, so the make alone settles nothing.
        page = self.site(self.numbered("    make: Ford\n", "    make: Ford\n    country: US\n", "    make: Lancia\n"),
                         makes="Ford: null  # Mustangs in America, Anglias in Britain\nLancia: IT\n")["page"]
        self.assertIn('<td class="unflagged">Ford</td>', page)
        self.assertRegex(page, r'<use xlink:href="#flag-us"/></svg>Ford</td>')

    def test_a_make_the_table_does_not_know_has_no_flag(self):
        page = self.site(self.numbered("    make: Lancia\n", "    make: Honda\n"), makes="Honda: JP\n")["page"]
        self.assertIn('<td class="unflagged">Lancia</td>', page)

    def test_a_site_with_no_make_table_still_builds(self):
        self.assertNotIn("flag", self.site(self.numbered("    make: Lancia\n"))["page"])

    def assert_makes_rejected(self, makes: str, expected: str):
        with self.assertRaises(validate.ValidationError) as caught:
            self.site(self.numbered("    make: Lancia\n"), makes=makes)
        self.assertIn(expected, str(caught.exception))

    def test_a_make_with_a_country_the_site_cannot_draw_is_rejected(self):
        self.assert_makes_rejected("Lancia: Italy\n", "makes.yml: Lancia: must be one of")

    def test_a_make_listed_twice_is_rejected_rather_than_the_last_one_winning(self):
        self.assert_makes_rejected("Lancia: IT\nHonda: JP\nLancia: FR\n", "makes.yml: Lancia is listed twice")

    def test_a_table_that_is_not_make_then_country_is_rejected(self):
        self.assert_makes_rejected("- Lancia\n- Honda\n", "makes.yml: must be a list of makes, each with a country")

    def test_the_real_table_is_valid_and_carries_both_kinds_of_decision(self):
        makes = validate.load_makes(ROOT / "data")
        self.assertEqual(makes["Alfa Romeo"], "IT")
        self.assertIsNone(makes["Ford"], "Ford is in the table as a make with no single country")

    def test_brazil_has_a_flag_for_the_beetle_built_there(self):
        # Volkswagen's table entry is DE, so without its own code a Fusca would show Germany's flag.
        self.assertEqual(settings.COUNTRIES["BR"][0], "Brazil")

    def test_china_has_a_flag_for_the_byd_on_the_2026_coppa_di_tokyo_list(self):
        name, art = settings.COUNTRIES["CN"]
        self.assertEqual(name, "China")
        self.assertEqual(art.count("#FFDE00"), 5, "one large star and four small ones")

    def test_every_country_has_a_name_and_a_drawing_with_ids_of_its_own(self):
        ids = []
        for code, (name, art) in settings.COUNTRIES.items():
            self.assertRegex(code, r"^[A-Z]{2}$")
            self.assertTrue(name and art.startswith("<"), code)
            ids += re.findall(r'id="([^"]+)"', art)
        self.assertEqual(len(ids), len(set(ids)), "an id repeated across drawings would clash on a page with both")
        self.assertTrue(all(i.startswith("flag-") for i in ids), ids)


class LatinOnlyNameTests(unittest.TestCase):
    """Plenty of Japanese car events are named only in Latin script, so name_ja is optional.

    An empty line in its place would print the name twice and tag Latin text lang="ja",
    which tells a screen reader to read it with Japanese pronunciation rules.
    """

    def setUp(self):
        self.tmp = temp_dir(self)
        data = self.tmp / "data"
        write_event(data, "latin-fes", name_en="Latin Fes", name_ja=None)
        write_instance(data, "latin-fes", 2026,
                       instance_yaml("latin-fes", 2026, "2026-11-22", "2026-11-22", extra=ROUTE_ONE_DAY))
        build.build(data, self.tmp / "site")
        out = self.tmp / "site"
        self.event_html = (out / "events" / "latin-fes" / "index.html").read_text(encoding="utf-8")
        self.edition_html = (out / "events" / "latin-fes" / "2026" / "index.html").read_text(encoding="utf-8")
        self.home_html = (out / "index.html").read_text(encoding="utf-8")
        self.ics = unfold((out / settings.FEED_FILE).read_bytes().decode("utf-8"))


    def test_no_page_carries_an_empty_japanese_line(self):
        for name, html in (("event", self.event_html), ("edition", self.edition_html),
                           ("home", self.home_html)):
            with self.subTest(page=name):
                # Whitespace first, so the home page's hreflang="ja" link is not taken for one.
                self.assertNotRegex(html, r'\slang="ja"[^>]*>\s*<')

    def test_the_name_is_not_printed_twice_in_the_body(self):
        main = re.search(r"<main.*?</main>", self.event_html, re.S).group(0)
        self.assertEqual(main.count("Latin Fes"), 1, main)

    def test_the_calendar_description_does_not_open_with_a_blank_line(self):
        line = next(l for l in self.ics if l.startswith("DESCRIPTION:"))
        self.assertTrue(line.startswith("DESCRIPTION:https://"), line)

    def test_a_japanese_name_is_still_shown_when_there_is_one(self):
        self.assertIn('lang="ja">テストイベント', self.pages_with_ja())

    def pages_with_ja(self) -> str:
        tmp = temp_dir(self)
        data = tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-11-22", "2026-11-22"))
        build.build(data, tmp / "site")
        return (tmp / "site" / "events" / "meet" / "index.html").read_text(encoding="utf-8")


class UnannouncedFeeTests(unittest.TestCase):
    """An admission the organizer has not published yet is absent, not zero.

    Writing 0 would tell a visitor the day is free and a guess would be worse, so the
    field takes null and every surface says only that the number is not known.
    """

    def setUp(self):
        self.tmp = temp_dir(self)
        data = self.tmp / "data"
        write_event(data, "fee-pending", name_en="Fee Pending", fee=None)
        write_instance(data, "fee-pending", 2026,
                       instance_yaml("fee-pending", 2026, "2026-11-03", "2026-11-03"))
        build.build(data, self.tmp / "site")
        self.out = self.tmp / "site"
        self.event_html = (self.out / "events/fee-pending/index.html").read_text(encoding="utf-8")
        self.home_html = (self.out / "index.html").read_text(encoding="utf-8")


    def test_the_pages_say_the_admission_is_unannounced_rather_than_free(self):
        for name, html in (("event", self.event_html), ("home", self.home_html)):
            with self.subTest(page=name):
                self.assertIn("Admission not announced", html)
                self.assertNotIn("Free to watch", html)

    # Once the day has passed, "not announced" says nothing useful, so past entries drop it.
    # The build never reads the clock: the home page hides it under Past events in CSS, and an
    # edition page removes it in the browser once the edition has ended in Japan.

    def test_the_past_list_on_the_home_page_hides_it(self):
        self.assertRegex(self.home_html, r'<span class="fact fee-unannounced"><svg [^>]*>.*?</svg>Admission not announced<')
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"(?m)^#past-list \.fee-unannounced \{ display: none; \}")

    def pages_with_entry_list(self, fee) -> dict:
        tmp = temp_dir(self)
        write_event(tmp / "data", "meet", fee=fee)
        write_instance(tmp / "data", "meet", 2026,
                       instance_yaml("meet", 2026, "2026-11-03", "2026-11-03", extra=CARS))
        build.build(tmp / "data", tmp / "site")
        return {rel: (tmp / "site" / rel).read_text(encoding="utf-8")
                for rel in ("index.html", "events/meet/2026/index.html")}

    def test_an_edition_page_drops_the_cost_once_the_edition_has_ended(self):
        html = self.pages_with_entry_list(None)["events/meet/2026/index.html"]
        self.assertIn('<dt class="fee-unannounced">Cost</dt>', html)
        self.assertIn('<dd class="fee-unannounced">Admission not announced</dd>', html)
        self.assertIn('if ("2026-11-03" < todayInJapan)', html)

    def test_a_published_fee_stays_on_past_entries(self):
        for rel, html in self.pages_with_entry_list(1500).items():
            with self.subTest(page=rel):
                self.assertIn("\u00a51,500", html)
                self.assertNotIn("fee-unannounced", html)

    def test_the_json_feed_leaves_the_fee_out_rather_than_calling_it_zero(self):
        feed = json.loads((self.out / "api/events.json").read_text(encoding="utf-8"))
        self.assertNotIn("spectator_fee_jpy", feed["events"][0])

    def test_the_structured_data_claims_neither_free_nor_paid(self):
        block = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',
                                     self.event_html, re.S).group(1))
        self.assertNotIn("isAccessibleForFree", block)
        self.assertNotIn("offers", block)


class HeldEditionTests(unittest.TestCase):
    """A confirmed edition that has run reads "Held" in the event page's Dates table.

    The build never reads the clock, so the page carries each confirmed edition's last day
    and the browser swaps the word once that day has ended in Japan. Without the script the
    cell still says Confirmed, which stays true.
    """

    def setUp(self):
        self.tmp = temp_dir(self)
        data = self.tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2025, instance_yaml("meet", 2025, "2025-10-18", "2025-10-19"))
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                                                         status="cancelled"))
        write_instance(data, "meet", 2027, instance_yaml("meet", 2027, "2027-10-17", "2027-10-17",
                                                         status="tentative"))
        build.build(data, self.tmp / "site")
        self.html = (self.tmp / "site/events/meet/index.html").read_text(encoding="utf-8")


    def test_a_confirmed_edition_carries_its_last_day(self):
        self.assertIn('<span data-last-day="2025-10-19">Confirmed</span>', self.html)

    def test_cancelled_and_tentative_editions_keep_their_words(self):
        self.assertEqual(self.html.count("data-last-day="), 1)
        self.assertIn("Cancelled</td>", self.html)
        self.assertIn("Not confirmed</td>", self.html)

    def test_the_browser_relabels_it_once_the_last_day_has_ended_in_japan(self):
        script = next(s for s in re.findall(r"<script>(.*?)</script>", self.html, re.S) if "data-last-day" in s)
        self.assertIn("new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10)", script)
        self.assertIn('getAttribute("data-last-day") < todayInJapan', script)
        self.assertIn('textContent = "Held"', script)


class DisplayListTests(unittest.TestCase):
    """A show that names the models it will have on the floor, not the cars that will fill them.

    There are no entry numbers to give, and a model's production span is not the age of the
    car standing on the stand, so neither column can be filled without inventing the contents.
    """

    def setUp(self):
        self.tmp = temp_dir(self)
        data = self.tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                                     extra=display_cars_yaml([("Toyota", "2000GT"), ("Honda", "S500")])))
        build.build(data, self.tmp / "site")
        self.html = (self.tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
        self.event_html = (self.tmp / "site" / "events" / "meet" / "index.html").read_text(encoding="utf-8")


    def headers(self) -> list[str]:
        return re.findall(r'<th scope="col">(.*?)</th>', self.html)

    def test_columns_nothing_can_fill_are_dropped_rather_than_left_blank(self):
        self.assertEqual(self.headers(), ["Make", "Model"])

    def test_the_rows_still_render(self):
        self.assertIn("<td>Toyota</td><td>2000GT</td>", self.html)

    def test_it_is_not_called_an_entry_list(self):
        self.assertIn('<h2 id="cars">Cars on display</h2>', self.html)
        self.assertNotIn("Entry list", self.html)

    def test_the_as_of_line_does_not_repeat_the_heading_above_it(self):
        self.assertIn("<p>As of 2026-09-15.", self.html)
        self.assertNotIn("Cars on display as of", self.html)

    def test_a_list_that_can_still_change_says_so_without_calling_them_entrants(self):
        self.assertIn("Provisional: the line-up may change.", self.html)
        self.assertNotIn("withdraw", self.html)

    def test_the_link_to_it_is_labelled_for_what_it_holds(self):
        self.assertIn("Cars on display", self.event_html)
        self.assertNotIn("Entry list", self.event_html)

    def test_no_decade_strip_without_years_to_count(self):
        self.assertNotIn("chart decades", self.html)


class EditionPrefectureTests(unittest.TestCase):
    """An event that moves between prefectures: each edition is printed with the one it ran in."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.out = self.tmp / "site"

    def build_with(self, edition_extra: str) -> None:
        # write_event puts the event at Test Park, Shizuoka.
        write_event(self.tmp / "data", "meet")
        write_instance(self.tmp / "data", "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=edition_extra))
        build.build(self.tmp / "data", self.out)

    def page(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def test_the_edition_page_names_the_edition_s_prefecture(self):
        self.build_with("venue_en: Another Field\nprefecture: Gifu\n" + CARS)
        html = self.page("events/meet/2026/index.html")
        self.assertIn("<dd>Another Field, Gifu</dd>", html)
        self.assertIn("Another Field, Gifu.", re.search(r'<meta name="description" content="([^"]*)"', html).group(1))
        self.assertNotIn("Shizuoka", html)

    def test_the_event_page_keeps_the_event_s_prefecture(self):
        self.build_with("venue_en: Another Field\nprefecture: Gifu\n" + CARS)
        self.assertIn("Test Park, Shizuoka", self.page("events/meet/index.html"))

    def test_the_home_page_lists_the_edition_under_its_own_prefecture(self):
        self.build_with("venue_en: Another Field\nprefecture: Gifu\n" + CARS)
        html = self.page("index.html")
        self.assertIn("</svg>Gifu<", html)
        self.assertNotIn("Shizuoka", html)

    def test_the_calendar_structured_data_and_feed_agree_with_the_page(self):
        self.build_with("venue_en: Another Field\nprefecture: Gifu\n" + CARS)
        self.assertIn("LOCATION:Another Field\\, Gifu\\, Japan", self.page("classic-car-events.ics"))
        events = [b for b in jsonld_blocks(self.page("events/meet/2026/index.html")) if b["@type"] == "Event"]
        self.assertEqual([b["location"]["address"]["addressRegion"] for b in events], ["Gifu"])
        self.assertEqual([e["prefecture"] for e in json.loads(self.page("api/events.json"))["events"]], ["Gifu"])

    def test_llms_txt_names_the_prefecture_beside_an_edition_held_elsewhere(self):
        self.build_with("venue_en: Another Field\nprefecture: Gifu\n" + CARS)
        self.assertIn("): Shizuoka. 18 Oct 2026 (Gifu).", self.page("llms.txt"))

    def test_without_one_the_edition_takes_the_event_s(self):
        self.build_with(CARS)
        self.assertIn("<dd>Test Park, Shizuoka</dd>", self.page("events/meet/2026/index.html"))
        self.assertEqual([e["prefecture"] for e in json.loads(self.page("api/events.json"))["events"]], ["Shizuoka"])

    def test_a_prefecture_without_a_venue_is_refused(self):
        # It would print the event's venue in a prefecture it is not in.
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with("prefecture: Gifu\n" + CARS)
        self.assertIn("venue_en", str(ctx.exception))


class OnThisPageTests(unittest.TestCase):
    """A jump to each section of a long edition page, counted from what the section shows."""

    def page(self, extra: str) -> str:
        tmp = temp_dir(self)
        data = tmp / "data"
        write_event(data, "meet")
        write_instance(data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-19", extra=extra))
        build.build(data, tmp / "site")
        return (tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")

    def jumps(self, html: str) -> list[tuple[str, str]]:
        nav = re.search(r'(?s)<nav class="on-this-page" aria-label="On this page">(.*?)</nav>', html)
        return re.findall(r'<a href="(#[^"]+)">([^<]+)</a>', nav.group(1)) if nav else []

    def test_each_section_in_page_order_with_what_it_holds(self):
        html = self.page(VIDEOS + CARS + ROUTE)
        self.assertEqual(self.jumps(html), [("#videos", "Videos (2)"), ("#cars", "Entry list (2 cars)"),
                                            ("#route", "Route (2 days)")])

    def test_every_jump_lands_on_a_heading(self):
        html = self.page(VIDEOS + CARS + ROUTE)
        for href, _ in self.jumps(html):
            self.assertRegex(html, rf'<h2 id="{href[1:]}">')

    def test_a_show_line_up_counts_models_and_a_described_route_counts_nothing(self):
        html = self.page(display_cars_yaml([("Toyota", "2000GT"), ("Honda", "S500")])
                         + "route_en: From the town hall along the high street.\n")
        self.assertEqual(self.jumps(html), [("#route", "Route"), ("#cars", "Cars on display (2 models)")])

    def test_a_page_with_one_section_needs_no_jumps(self):
        self.assertEqual(self.jumps(self.page(CARS)), [])
        self.assertNotIn('class="on-this-page"', self.page(CARS))

    def test_several_videos_share_a_row_that_wide_screens_can_split(self):
        html = self.page(VIDEOS + CARS)
        row = re.search(r'(?s)<div class="videos">(.*?)</div>\s*(?:<h2|$)', html)
        self.assertIsNotNone(row)
        self.assertEqual(row.group(1).count('<figure class="video">'), 2)


if __name__ == "__main__":
    unittest.main()
