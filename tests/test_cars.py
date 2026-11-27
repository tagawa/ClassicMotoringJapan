"""The cars section: /cars/ and one page per make group (spec 4.11 and section 5)."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import (GROUPS, MAKES, NISSAN_LISTS, cars_yaml, display_cars_yaml, instance_yaml, make_fixture,
                     temp_dir, write_event, write_instance, write_site)
import build  # noqa: E402
import validate  # noqa: E402

def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


class CarsSiteCase(unittest.TestCase):
    LISTS = NISSAN_LISTS

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        write_site(cls.data, cls.LISTS)
        build.build(cls.data, cls.out)


    def page(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def index_rows(self) -> list[str]:
        """The /cars/ table's body rows, as markup."""
        body = self.page("cars/index.html").split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        return re.findall(r"<tr>.*?</tr>", body, re.S)

    def index_line(self, make: str) -> str:
        """The /cars/ table row for one make, as markup."""
        found = [row for row in self.index_rows() if re.search(rf">{re.escape(make)}<", row)]
        self.assertEqual(len(found), 1, f"{make}: expected one row, found {len(found)}")
        return found[0]

    @staticmethod
    def cells(row: str) -> list[str]:
        return re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)

    def page_note(self, make: str):
        found = re.search(r'<span class="make-page">(.*?)</span>', self.index_line(make))
        return found and found.group(1)


class GroupPageTests(CarsSiteCase):
    def test_three_editions_get_a_page(self):
        self.assertTrue((self.out / "cars/nissan/index.html").is_file())

    def test_one_edition_line_no_page(self):
        self.assertFalse((self.out / "cars/lotus").exists())
        self.assertNotIn("<a ", self.index_line("Lotus"))

    def test_unknown_gets_no_line(self):
        index = text_of(self.page("cars/index.html"))
        self.assertIn("Lotus", index)
        self.assertNotIn("Unknown", index)

    def test_title_names_members_with_two_or_more(self):
        html = self.page("cars/nissan/index.html")
        self.assertIn("<title>Nissan and Datsun at classic car events in Japan</title>", html)
        self.assertRegex(html, r"<h1>Nissan and Datsun</h1>")

    def test_trail_home_cars_title(self):
        nav = re.search(r'(?s)<nav class="breadcrumbs" aria-label="Breadcrumb">(.*?)</nav>',
                        self.page("cars/nissan/index.html")).group(1)
        items = re.findall(r"<li>(.*?)</li>", nav, re.S)
        self.assertEqual(len(items), 3)
        self.assertIn('<a href="../../">Home</a>', items[0])
        self.assertIn('<a href="../../cars/">Cars</a>', items[1])
        self.assertIn('<span aria-current="page">Nissan and Datsun</span>', items[2])
        self.assertNotIn("<a ", items[2])

    def test_trail_comes_before_the_heading(self):
        html = self.page("cars/nissan/index.html")
        self.assertLess(html.index('class="breadcrumbs"'), html.index("<h1>"))

    def test_breadcrumb_jsonld_matches_the_trail(self):
        html = self.page("cars/nissan/index.html")
        blocks = [json.loads(b) for b in re.findall(r'(?s)<script type="application/ld\+json">(.*?)</script>', html)]
        crumbs = [b for b in blocks if b.get("@type") == "BreadcrumbList"]
        self.assertEqual(len(crumbs), 1)
        self.assertEqual(crumbs[0]["itemListElement"], [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://classicmotoringjapan.com/"},
            {"@type": "ListItem", "position": 2, "name": "Cars", "item": "https://classicmotoringjapan.com/cars/"},
            {"@type": "ListItem", "position": 3, "name": "Nissan and Datsun"}])

    def test_cars_index_has_no_trail(self):
        html = self.page("cars/index.html")
        self.assertNotIn('class="breadcrumbs"', html)
        self.assertNotIn("BreadcrumbList", html)

    def test_lede_gives_cars_and_entry_lists(self):
        # 2 Nissan at meet-a, 3 Datsun at meet-b, 1 Nissan Diesel at meet-c.
        self.assertRegex(self.page("cars/nissan/index.html"),
                         r"<h1>Nissan and Datsun</h1>\s*<p>6 cars on 3 entry lists\.</p>")

    def test_single_car_member_left_out_of_title(self):
        html = self.page("cars/nissan/index.html")
        title = re.search(r"<title>(.*?)</title>", html).group(1)
        h1 = re.search(r"<h1>(.*?)</h1>", html).group(1)
        self.assertNotIn("Nissan Diesel", title + h1)
        self.assertIn('href="nissan/"', self.index_line("Nissan Diesel"))

    def test_grouped_member_line_points_to_page(self):
        self.assertIn('href="nissan/"', self.index_line("Datsun"))
        self.assertEqual(self.page_note("Datsun"), "On the Nissan and Datsun page")

    def test_single_car_member_still_names_the_page(self):
        self.assertEqual(self.page_note("Nissan Diesel"), "On the Nissan and Datsun page")

    def test_no_second_line_for_first_named_member_or_make_without_page(self):
        self.assertIsNone(self.page_note("Nissan"))
        self.assertIsNone(self.page_note("Lotus"))

    def test_index_is_a_to_z(self):
        makes = [re.sub(r"<[^>]+>", "", re.sub(r"<svg.*?</svg>|<span.*?</span>", "", self.cells(row)[0]))
                 for row in self.index_rows()]
        self.assertEqual(makes, ["Datsun", "Lotus", "Nissan", "Nissan Diesel"])

    def test_index_is_a_table_with_no_list_or_sentences(self):
        html = self.page("cars/index.html")
        self.assertIn('<div class="table-wrap" tabindex="0" role="region" aria-label="Cars by make">', html)
        self.assertNotIn("<ul", html.split("<main", 1)[1])
        body = text_of(html.split("<tbody>", 1)[1])
        self.assertNotIn("See", body)
        self.assertNotIn("cars at", body)

    def test_counts_are_numbers_only(self):
        # Nissan: 2 cars at meet-a; Datsun: 3 at meet-b; Lotus: 2 at meet-a.
        self.assertEqual(self.cells(self.index_line("Nissan"))[1:], ["2", "1"])
        self.assertEqual(self.cells(self.index_line("Datsun"))[1:], ["3", "1"])
        self.assertEqual(self.cells(self.index_line("Lotus"))[1:], ["2", "1"])
        self.assertIn('<td class="num">2</td>', self.index_line("Lotus"))

    def test_cars_pages_are_byte_identical(self):
        out2 = self.tmp / "site2"
        build.build(self.data, out2)
        files = sorted(p.relative_to(self.out) for p in (self.out / "cars").rglob("*") if p.is_file())
        self.assertEqual(len(files), 2, "expected /cars/ and /cars/nissan/")
        for rel in files:
            self.assertEqual((self.out / rel).read_bytes(), (out2 / rel).read_bytes(), str(rel))

    def test_group_page_check_date_is_its_own_lists_latest(self):
        self.assertIn("Most recent check: 2026-09-25", self.page("cars/nissan/index.html"))

    def test_index_check_date_is_the_latest_list(self):
        self.assertIn("Most recent check: 2026-10-05", self.page("cars/index.html"))

    def test_sitemap_lists_cars_pages(self):
        sitemap = self.page("sitemap.xml")
        self.assertIn("<loc>https://classicmotoringjapan.com/cars/</loc><lastmod>2026-10-05</lastmod>", sitemap)
        self.assertIn("<loc>https://classicmotoringjapan.com/cars/nissan/</loc><lastmod>2026-09-25</lastmod>",
                      sitemap)
        self.assertNotIn("/cars/lotus/", sitemap)

    def test_entry_table_make_links_to_group_page(self):
        self.assertIn('<a href="../../../cars/nissan/">Datsun</a></td>', self.page("events/meet-b/2026/index.html"))

    def test_make_without_page_is_not_linked(self):
        html = self.page("events/meet-c/2026/index.html")
        self.assertIn('<a href="../../../cars/nissan/">Nissan Diesel</a></td>', html)
        self.assertIn(">Unknown</td>", html)
        self.assertRegex(self.page("events/meet-a/2025/index.html"), r"</svg>Lotus</td>")

    def test_api_has_no_cars_pages(self):
        api = self.page("api/events.json")
        self.assertIn("events/meet-b/2026/", api)
        self.assertNotIn("/cars/", api)

    def test_llms_txt_lists_cars_pages(self):
        llms = self.page("llms.txt")
        self.assertIn("## Cars\n\n- [Cars by make](https://classicmotoringjapan.com/cars/): "
                      "every make on a published entry list, with its counts.\n"
                      "  - [Nissan and Datsun](https://classicmotoringjapan.com/cars/nissan/): "
                      "events where these cars have run, and every list including them.\n", llms)
        self.assertNotIn("/cars/lotus/", llms)
        self.assertLess(llms.index("## Events"), llms.index("## Cars"))


class MakeStripLinkTests(CarsSiteCase):
    # meet-b's make strip: Nissan (has a page), Datsun (grouped under Nissan), Lotus (no page),
    # then a closing line for Ford.
    LISTS = (("meet-a", 2025, ["Nissan", "Nissan"]),
             ("meet-b", 2026, ["Nissan", "Nissan", "Datsun", "Datsun", "Lotus", "Lotus", "Ford"]),
             ("meet-c", 2026, ["Nissan"]))

    def strip(self, kind: str) -> str:
        html = self.page("events/meet-b/2026/index.html")
        return re.search(rf'<ol class="chart {kind}">(.*?)</ol>', html, re.S).group(1)

    def label(self, make: str) -> str:
        found = [span for span in re.findall(r'<span class="chart-when">(.*?)</span>', self.strip("makes"), re.S)
                 if re.sub(r"<[^>]+>", "", span) == make]
        self.assertEqual(len(found), 1, f"{make}: expected one strip row")
        return found[0]

    def assert_links_as_the_table_does(self, make: str) -> None:
        html = self.page("events/meet-b/2026/index.html")
        table_link = re.search(rf'<a href="([^"]+)">{make}</a></td>', html).group(1)
        self.assertEqual(self.label(make), f'<a href="{table_link}">{make}</a>')
        self.assertEqual(table_link, "../../../cars/nissan/")

    def test_make_with_page_links_as_the_table_does(self):
        self.assert_links_as_the_table_does("Nissan")

    def test_grouped_member_links_to_its_group_page(self):
        self.assert_links_as_the_table_does("Datsun")

    def test_make_without_page_is_plain_text(self):
        self.assertNotIn("<a", self.label("Lotus"))

    def test_closing_line_is_not_a_link(self):
        rest = re.search(r'<li class="chart-rest">(.*?)</li>', self.strip("makes"), re.S).group(1)
        self.assertIn("with one car", rest)
        self.assertNotIn("<a", rest)

    def test_decade_strip_has_no_links(self):
        self.assertIn("1970s", self.strip("decades"))
        self.assertNotIn("<a", self.strip("decades"))


class CountsTests(CarsSiteCase):
    """A display list's models count as cars, one each, on /cars/ (spec section 5)."""
    LISTS = (("rally-a", 2025, ["Lotus", "Lotus", "Nissan", "Nissan", "Nissan"]),
             ("show-b", 2026, [("Lotus", "Elan"), ("Lotus", "Europa"), ("Lotus", "Seven"), ("Ford", "Model A"),
                               ("Ford", "Model T"), ("Ford", "Anglia"), ("Datsun", "Fairlady")]),
             # Checked before the event, so its list is provisional.
             ("rally-c", 2026, ["Nissan", "Datsun"],
              {"day": "2026-06-14", "as_of": "2026-05-01", "verified": "2026-05-01"}))

    def test_index_counts_models_as_cars(self):
        # 2 cars at rally-a and 3 models at show-b.
        row = self.index_line("Lotus")
        self.assertEqual(self.cells(row)[1:], ["5", "2"])
        self.assertNotIn("model", text_of(row))

    def test_index_display_only_make(self):
        self.assertEqual(self.cells(self.index_line("Ford"))[1:], ["3", "1"])

    def test_index_flag_from_makes_yml(self):
        self.assertIn('<td class="flagged">', self.index_line("Lotus"))
        self.assertIn('xlink:href="#flag-gb"', self.index_line("Lotus"))
        self.assertIn('<td class="unflagged">', self.index_line("Ford"))
        self.assertNotIn("<svg", self.index_line("Ford"))
        self.assertEqual(self.page("cars/index.html").count('<g id="flag-gb">'), 1)

    def test_a_display_list_counts_towards_the_bar(self):
        # Lotus is on rally-a's entry list and show-b's display list only.
        self.assertTrue((self.out / "cars/lotus/index.html").is_file())

    def test_group_totals_count_models_as_cars(self):
        text = text_of(self.page("cars/nissan/index.html"))
        self.assertIn("6 cars on 3 entry lists.", text)
        self.assertNotIn("model", text)

    def test_two_members_at_one_edition_count_once(self):
        # rally-c has both Nissan and Datsun: counted twice, the totals would say 4 editions.
        text = text_of(self.page("cars/nissan/index.html"))
        self.assertIn("6 cars on 3 entry lists", text)
        self.assertNotIn("on 4 entry lists", text)

    def entry_rows(self) -> dict:
        html = self.page("cars/nissan/index.html")
        folded = re.search(r'(?s)<details class="all-cars">\s*<summary>(.*?)</summary>(.*?)</details>', html)
        rows = re.findall(r"<tr>.*?</tr>", folded.group(2), re.S)
        return {re.search(r">(Rally A|Show B|Rally C) ", row).group(1): text_of(row) for row in rows[1:]}

    def test_entry_lists_table_marks_provisional(self):
        rows = self.entry_rows()
        self.assertEqual(sorted(rows), ["Rally A", "Rally C", "Show B"])
        self.assertIn("provisional", rows["Rally C"])
        self.assertNotIn("provisional", rows["Rally A"])
        self.assertNotIn("provisional", rows["Show B"])

    def test_entry_lists_folded_under_a_count(self):
        html = self.page("cars/nissan/index.html")
        self.assertRegex(html, r'<details class="all-cars">\s*<summary>All 3 entry lists</summary>')
        self.assertNotIn('id="entry-lists"', html)
        self.assertEqual(html.count('<details class="all-cars">'), 1)

    def test_entry_lists_newest_first_with_counts(self):
        rows = self.entry_rows()
        self.assertEqual(list(rows), ["Rally C", "Show B", "Rally A"])
        self.assertIn("3 cars", rows["Rally A"])
        self.assertIn("1 car", rows["Show B"])

    def test_entry_lists_dated_without_weekdays(self):
        # A past list is looked up by its date, not planned by its weekday (owner, 2026-11-28).
        self.assertIn("14 Jun 2026", self.entry_rows()["Rally C"])
        for rel, weekday in (("cars/nissan/index.html", r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b"),
                             ("ja/cars/nissan/index.html", r"\([月火水木金土日]\)")):
            folded = re.search(r'(?s)<details class="all-cars">(.*?)</details>', self.page(rel)).group(1)
            self.assertRegex(folded, r"14 Jun 2026|2026年6月14日")
            self.assertNotRegex(folded, weekday)

    def test_display_table_make_links_too(self):
        self.assertIn('<a href="../../../cars/nissan/">Datsun</a></td>', self.page("events/show-b/2026/index.html"))

    def test_entry_list_links_to_the_edition(self):
        self.assertIn('href="../../events/rally-a/2025/"', self.page("cars/nissan/index.html"))

    def test_caveat_on_both_pages_as_plain_text(self):
        caveat = "Counts come only from events whose organisers publish entry lists.</p>"
        self.assertIn("<p>" + caveat, self.page("cars/nissan/index.html"))
        # On /cars/ it sits under the heading, ahead of the table it qualifies.
        index = self.page("cars/index.html")
        self.assertRegex(index, r"<h1>Cars by make</h1>\s*<p class=\"index-note\">" + re.escape(caveat))
        self.assertLess(index.index(caveat), index.index("<table"))


def write_edition(data: Path, slug: str, stem, day: str, status="confirmed", cars=None,
                  as_of=None, verified="2026-09-20") -> None:
    """One edition; cars as in write_site, listed as of the day after unless as_of is given."""
    extra = ""
    if cars:
        as_of = as_of or day[:8] + f"{int(day[8:]) + 1:02d}"
        extra = (display_cars_yaml(cars, as_of=as_of) if isinstance(cars[0], tuple)
                 else cars_yaml([1970] * len(cars), as_of=as_of, makes=cars))
    write_instance(data, slug, stem, instance_yaml(slug, int(str(stem)[:4]), day, day, status=status,
                                                   extra=extra, verified=verified))


class EventsSectionTests(unittest.TestCase):
    """"Events where <group> cars have run", as the build renders it, before any script."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        data = cls.tmp / "data"
        (data / "events").mkdir(parents=True)
        (data / "makes.yml").write_text(MAKES, encoding="utf-8")
        (data / "make_groups.yml").write_text(GROUPS, encoding="utf-8")
        events = {
            "own-date": [("2026", "2026-05-10", "confirmed", ["Nissan", "Nissan"], None, "2026-09-20"),
                         # Checked before its own day, so the list is provisional.
                         ("2027", "2027-05-09", "confirmed", ["Nissan", "Nissan", "Datsun"], "2027-01-10",
                          "2027-01-10")],
            "cancelled-later": [("2026", "2026-05-10", "confirmed", ["Nissan"], None, "2026-09-20"),
                                ("2027", "2027-05-09", "cancelled", None, None, "2026-09-20"),
                                ("2028", "2028-05-14", "confirmed", None, None, "2026-09-20")],
            "tentative-next": [("2026", "2026-05-10", "confirmed", ["Datsun"], None, "2026-09-20"),
                               ("2027", "2027-05-09", "tentative", None, None, "2026-09-20"),
                               ("2028", "2028-05-14", "confirmed", None, None, "2026-09-20")],
            "only-cancelled": [("2026", "2026-05-10", "cancelled", ["Nissan"], None, "2026-09-20")],
            "older-list": [("2025", "2025-05-11", "confirmed", ["Nissan"], None, "2026-09-20"),
                           ("2026", "2026-05-10", "confirmed", ["Lotus"], None, "2026-09-20")],
            "show-event": [("2026-spring", "2026-05-10", "confirmed",
                            [("Datsun", "Fairlady"), ("Nissan", "Skyline"), ("Prince", "Gloria")], None,
                            "2026-09-20")],
        }
        for slug, editions in events.items():
            write_event(data, slug, name_en=slug.replace("-", " ").title())
            for stem, day, status, cars, as_of, verified in editions:
                write_edition(data, slug, stem, day, status=status, cars=cars, as_of=as_of, verified=verified)
        build.build(data, cls.tmp / "site")
        cls.html = (cls.tmp / "site/cars/nissan/index.html").read_text(encoding="utf-8")
        section = cls.html.split('<h2 id="next-dates">', 1)[1].split("</table>", 1)[0]
        cls.head = re.search(r"(?s)<thead>(.*?)</thead>", section).group(1)
        cls.lines = {re.search(r'events/([a-z-]+)/"', row).group(1): row
                     for row in re.findall(r"<tr>.*?</tr>", section.split("<tbody>", 1)[1], re.S)}


    def dates(self, slug: str) -> list[tuple]:
        return re.findall(r'<span class="next-date" data-start="([\d-]+)" data-ends="([\d-]+)">([^<]*)</span>',
                          self.lines[slug])

    def cells(self, slug: str) -> list[str]:
        return [text_of(cell).strip() for cell in re.findall(r'<(?:td|th scope="row")>(.*?)</t[dh]>', self.lines[slug], re.S)]

    def test_heading_names_the_group(self):
        self.assertRegex(self.html, r'<h2 id="next-dates">Events where Nissan and Datsun cars have run</h2>')

    def test_first_table_columns(self):
        self.assertEqual(re.findall(r'<th scope="col">(.*?)</th>', self.head), ["Event", "Next date", "Cars, latest list"])

    def test_second_table_hidden_and_empty_without_script(self):
        self.assertIn('<h2 id="no-date" hidden>No date announced yet</h2>', self.html)
        rest = self.html.split('<h2 id="no-date" hidden>', 1)[1].split("</table>", 1)[0]
        self.assertRegex(rest, r'^No date announced yet</h2>\s*<div class="table-wrap"[^>]* id="undated-events" hidden>')
        self.assertEqual(re.findall(r'<th scope="col">(.*?)</th>', rest), ["Event", "Cars, latest list"])
        self.assertNotIn("<td", rest)

    def test_one_table_holds_every_event_and_date(self):
        self.assertEqual(len(self.lines), 6)
        # own-date 1, cancelled-later 2, tentative-next 3, older-list 2 (from its 2025 list on), show-event 1.
        self.assertEqual(self.html.count('class="next-date"'), 9)

    def test_upcoming_list_shows_its_own_date(self):
        self.assertEqual(self.cells("own-date")[2], "3 in 2027, provisional")
        self.assertEqual([d[1] for d in self.dates("own-date")], ["2027-05-09"])

    def test_cancelled_later_edition_is_skipped(self):
        self.assertEqual([d[1] for d in self.dates("cancelled-later")], ["2026-05-10", "2028-05-14"])

    def test_tentative_edition_is_marked(self):
        dates = {d[1]: d[2] for d in self.dates("tentative-next")}
        self.assertEqual(sorted(dates), ["2026-05-10", "2027-05-09", "2028-05-14"])
        self.assertTrue(dates["2027-05-09"].endswith("(dates not confirmed)"), dates["2027-05-09"])
        self.assertNotIn("not confirmed", dates["2026-05-10"] + dates["2028-05-14"])

    def test_no_date_rendered_shows_placeholder_without_script(self):
        self.assertEqual(self.dates("only-cancelled"), [])
        self.assertIn('<span class="no-next">Next date not announced</span>', self.lines["only-cancelled"])

    def test_placeholder_hidden_when_dates_exist(self):
        self.assertIn('<span class="no-next" hidden>Next date not announced</span>', self.lines["cancelled-later"])

    def test_build_orders_events_a_to_z(self):
        self.assertEqual(list(self.lines), ["cancelled-later", "older-list", "only-cancelled", "own-date",
                                            "show-event", "tentative-next"])

    def test_count_from_latest_list_including_group(self):
        self.assertEqual(self.cells("older-list")[2], "1 in 2025")
        self.assertIn('href="../../events/older-list/2025/"', self.lines["older-list"])

    def test_display_count_text(self):
        self.assertEqual(self.cells("show-event")[2], "3 in Spring 2026")
        self.assertEqual(self.cells("cancelled-later")[2], "1 in 2026")
        self.assertNotIn("model", text_of(self.lines["show-event"]))

    def test_dates_carry_their_first_and_last_day(self):
        self.assertEqual(self.dates("cancelled-later")[0][:2], ("2026-05-10", "2026-05-10"))


class TwoEditionsTests(CarsSiteCase):
    """Two lists are enough for a page (owner, 2026-11-27: Bristol)."""
    LISTS = (("meet-a", 2025, ["Lotus"]), ("meet-b", 2026, ["Lotus"]))

    def test_two_editions_get_a_page(self):
        self.assertTrue((self.out / "cars/lotus/index.html").is_file())
        self.assertIn('href="lotus/"', self.index_line("Lotus"))


class UnknownOnThreeEditionsTests(CarsSiteCase):
    LISTS = (("meet-a", 2025, ["Unknown", "Lotus"]), ("meet-b", 2026, ["Unknown"]), ("meet-c", 2026, ["Unknown"]))

    def test_unknown_gets_no_page_even_at_three_editions(self):
        self.assertTrue((self.out / "cars/index.html").is_file())
        self.assertFalse((self.out / "cars/unknown").exists())
        self.assertNotIn("Unknown", text_of(self.page("cars/index.html")))


class ThreeNamedMembersTests(CarsSiteCase):
    LISTS = (("meet-a", 2025, ["Nissan", "Nissan"]), ("meet-b", 2026, ["Datsun", "Datsun"]),
             ("meet-c", 2026, ["Prince", "Prince"]))

    def test_three_named_members_joined_with_and(self):
        self.assertIn("<h1>Nissan, Datsun and Prince</h1>", self.page("cars/nissan/index.html"))


class KeyWithoutCarsTests(CarsSiteCase):
    LISTS = (("meet-a", 2025, ["Healey", "Healey"]), ("meet-b", 2026, ["Healey"]), ("meet-c", 2026, ["Healey"]))

    def test_title_skips_key_without_cars(self):
        self.assertIn("<h1>Healey</h1>", self.page("cars/austin-healey/index.html"))


class TitleIsTheMakeTests(CarsSiteCase):
    """Healey's single car leaves the page titled Austin-Healey alone."""
    LISTS = (("meet-a", 2025, ["Austin-Healey", "Healey"]), ("meet-b", 2026, ["Austin-Healey"]),
             ("meet-c", 2026, ["Austin-Healey"]))

    def test_no_second_line_where_the_page_is_titled_by_the_make(self):
        self.assertIsNone(self.page_note("Austin-Healey"))
        self.assertEqual(self.page_note("Healey"), "On the Austin-Healey page")


class LoneMakePageTests(CarsSiteCase):
    """A make in no group, with a page of its own."""
    LISTS = (("meet-a", 2025, ["Lotus"]), ("meet-b", 2026, ["Lotus"]), ("meet-c", 2026, ["Lotus", "Unknown"]))

    def test_make_alone_has_link_and_no_second_line(self):
        self.assertIn('href="lotus/"', self.index_line("Lotus"))
        self.assertIsNone(self.page_note("Lotus"))

    def test_one_row_per_make_and_none_for_unknown(self):
        self.assertEqual(len(self.index_rows()), 1)


class CollidingSlugsTests(unittest.TestCase):
    def test_colliding_slugs_fail_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            write_site(data, (("meet-a", 2026, ["Lotus"]),), makes="Citroën: FR\nCitroen: FR\nLotus: GB\n",
                       groups=None)
            with self.assertRaises(validate.BuildError) as caught:
                build.build(data, Path(tmp) / "site")
            self.assertIn("cars/citroen/", "\n".join(caught.exception.errors))


class HeaderLinkTests(unittest.TestCase):
    """Every page's header links Cars, resolved from that page's own depth."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.out = cls.tmp / "site"
        make_fixture(cls.tmp / "data")
        build.build(cls.tmp / "data", cls.out)


    def nav(self, rel: str) -> str:
        found = re.findall(r'<a class="site-nav"([^>]*)>(?:Cars|車種)</a>', (self.out / rel).read_text(encoding="utf-8"))
        self.assertEqual(len(found), 1, rel)
        return found[0]

    def test_header_links_cars_on_every_page(self):
        pages = [p for p in self.out.rglob("*.html") if p.name != "404.html"]
        self.assertGreater(len(pages), 5)
        for page in pages:
            rel = page.relative_to(self.out)
            with self.subTest(page=str(rel)):
                href = re.search(r'href="([^"]*)"', self.nav(str(rel))).group(1)
                # Each language's pages link its own cars page.
                target = self.out / ("ja/" if rel.parts[0] == "ja" else "") / "cars/index.html"
                self.assertEqual((page.parent / href / "index.html").resolve(), target.resolve())
                self.assertTrue(target.is_file())

    def test_japanese_page_names_the_link_in_japanese(self):
        self.assertIn('<a class="site-nav" href="./cars/">車種</a>', (self.out / "ja/index.html").read_text(encoding="utf-8"))

    def test_404_link_is_root_absolute(self):
        self.assertIn('href="/cars/"', self.nav("404.html"))


if __name__ == "__main__":
    unittest.main()
