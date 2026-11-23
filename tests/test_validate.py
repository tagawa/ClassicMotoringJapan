"""Validation of data/: fields, prose limits, house style, links and coordinates."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CARS, HeadParser, instance_yaml, jsonld_blocks, ROOT, temp_dir, write_event, write_instance
import build  # noqa: E402
import validate  # noqa: E402


class ProseLengthTests(unittest.TestCase):
    """Long prose hides its own facts, so the build refuses it."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"


    def build_with_summary(self, words: int):
        # One word per sentence, so the first sentence stays inside the description cap.
        write_event(self.data, "meet", extra=f"summary_en:{' Word.' * words}\n")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def test_prose_at_the_cap_is_accepted(self):
        self.build_with_summary(validate.PROSE_MAX_WORDS)

    def test_prose_over_the_cap_is_rejected(self):
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with_summary(validate.PROSE_MAX_WORDS + 1)
        self.assertIn("summary_en", str(ctx.exception))

    def test_the_message_offers_more_than_one_way_out(self):
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with_summary(validate.PROSE_MAX_WORDS + 1)
        message = str(ctx.exception)
        for way in ("bullet", "table", "diagram"):
            self.assertIn(way, message.lower(), f"the fix hint should mention {way}s")


class DescriptionLengthTests(unittest.TestCase):
    """An event page's snippet is its summary's first sentence, so that sentence has to fit one."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"


    def build_with_first_sentence(self, chars: int):
        sentence = "A" + "a" * (chars - 2) + "."
        write_event(self.data, "meet", extra=f"summary_en: {sentence} Then a second sentence.\n")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def test_a_first_sentence_at_the_cap_is_accepted(self):
        self.build_with_first_sentence(validate.DESCRIPTION_MAX_CHARS)

    def test_a_first_sentence_over_the_cap_is_rejected_by_event_and_field(self):
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with_first_sentence(validate.DESCRIPTION_MAX_CHARS + 1)
        message = str(ctx.exception)
        self.assertIn("events/meet.yml", message)
        self.assertIn("summary_en", message)

    def test_an_edition_description_is_never_capped(self):
        # Built only from facts: shortening one would mean shortening a venue name.
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-18", status="tentative",
            extra=f"venue_en: {'Long Venue Name ' * 10}\n" + CARS))
        build.build(self.data, self.tmp / "site")
        html = (self.tmp / "site/events/meet/2026/index.html").read_text(encoding="utf-8")
        description = HeadParser(html).meta["description"]
        self.assertGreater(len(description), validate.DESCRIPTION_MAX_CHARS)


class CombinedProseTests(unittest.TestCase):
    """Fields that land in one block on the page are capped on what the reader sees."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"


    def build_with(self, **fields):
        extra = "".join(f"{k}: {' '.join(['word'] * n)}\n" for k, n in fields.items())
        write_event(self.data, "meet", extra=extra)
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def refusal(self, **fields) -> str:
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with(**fields)
        return str(ctx.exception)

    def test_nearest_station_is_prose_and_capped_on_its_own(self):
        # It reads as a sentence and sits in the same block as access_notes_en.
        self.assertIn("nearest_station", self.refusal(nearest_station=validate.PROSE_MAX_WORDS + 1))

    def test_two_legal_fields_that_share_a_block_can_still_be_too_long_together(self):
        half = validate.PROSE_MAX_WORDS // 2 + 1
        message = self.refusal(nearest_station=half, access_notes_en=half)
        self.assertIn("nearest_station", message)
        self.assertIn("access_notes_en", message)
        self.assertIn("one block", message)

    def test_the_combined_cap_is_the_same_number(self):
        half = validate.PROSE_MAX_WORDS // 2
        self.build_with(nearest_station=half, access_notes_en=validate.PROSE_MAX_WORDS - half)

    def test_one_field_alone_is_untouched_by_the_combined_rule(self):
        self.build_with(access_notes_en=validate.PROSE_MAX_WORDS)


class EditorialProseTests(unittest.TestCase):
    """The pages are a reference, not a recommendation, so advice fails the build."""

    # The clause that shipped on la-festa-autunno and prompted the rule.
    SHIPPED = ("About two weeks beforehand the organiser publishes a timetable giving an "
               "arrival window for every checkpoint, which is the practical way to plan a "
               "day around it.")
    CUT = ("About two weeks beforehand the organiser publishes a timetable giving an "
           "arrival window for every checkpoint.")

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"


    def build_with_prose(self, text: str, field="summary_en"):
        write_event(self.data, "meet", extra=f"{field}: {json.dumps(text)}\n")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def refusal(self, text: str, field="summary_en") -> str:
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with_prose(text, field)
        return str(ctx.exception)

    def test_the_clause_that_shipped_is_rejected(self):
        message = self.refusal(self.SHIPPED)
        self.assertIn("summary_en", message)
        self.assertIn("the practical way to", message)

    def test_the_same_sentence_without_the_clause_is_accepted(self):
        # The gate has to fault the advice, not the sentence carrying it.
        self.build_with_prose(self.CUT)

    def test_the_message_says_what_to_do_about_it(self):
        message = self.refusal(self.SHIPPED).lower()
        self.assertIn("cut", message)
        self.assertIn("fact", message)

    def test_every_listed_phrase_is_actually_caught(self):
        # An absence check proves nothing until the pattern is shown to produce a positive.
        for phrase in validate.EDITORIAL_PHRASES:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.refusal(f"The meeting is {phrase} something."))

    def test_a_curly_apostrophe_is_caught_like_a_straight_one(self):
        self.assertIn("don't miss", self.refusal("The swap meet, and don\u2019t miss the time trial."))

    def test_a_phrase_broken_over_a_folded_line_is_still_caught(self):
        self.assertIn("worth a look", self.refusal("The paddock is worth\n  a look."))

    def test_editions_are_held_to_the_same_rule(self):
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-18",
            extra=f"route_en: {json.dumps(self.SHIPPED)}\n"))
        with self.assertRaises(validate.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn("route_en", str(ctx.exception))

    def test_facts_that_merely_look_like_advice_are_left_alone(self):
        for text in (
            "Cars must be built before 1968 and replicas are not accepted.",
            "A Mustang and two Jaguars ran in 2025.",
            "The best-preserved of the three is the 1927 car.",
            "Entry is free for spectators and the car park is free with it.",
        ):
            with self.subTest(text=text):
                self.build_with_prose(text)


class HouseStyleTests(unittest.TestCase):
    """English text in the data uses no em dashes and British spelling (spec 4.7)."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"


    def build_event(self, **event):
        write_event(self.data, "meet", **event)
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def refusal(self, **event) -> str:
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_event(**event)
        return str(ctx.exception)

    def summary(self, text: str) -> dict:
        return {"extra": f"summary_en: {json.dumps(text)}\n"}

    def test_an_em_dash_in_prose_is_refused_with_the_way_out(self):
        message = self.refusal(**self.summary("Entry is free \u2014 parking is not."))
        self.assertIn("summary_en", message)
        self.assertIn("em dash", message)
        self.assertIn("comma", message)

    def test_an_em_dash_in_a_short_text_field_is_refused(self):
        self.assertIn("name_en", self.refusal(name_en="Meeting \u2014 Autumn"))

    def test_an_em_dash_in_a_list_of_text_is_refused(self):
        message = self.refusal(extra='typical_eras: ["1950s", "1960s \u2014 1970s"]\n')
        self.assertIn("typical_eras", message)

    def test_japanese_text_may_carry_one(self):
        self.build_event(name_ja="テスト\u2014ミーティング")

    def test_every_listed_american_spelling_is_caught_with_its_british_form(self):
        # An absence check proves nothing until the pattern is shown to produce a positive.
        for american, british in validate.AMERICAN_SPELLINGS.items():
            with self.subTest(word=american):
                message = self.refusal(**self.summary(f"The {american} is near the gate."))
                self.assertIn(repr(american), message)
                self.assertIn(british, message)

    def test_capitals_do_not_hide_one(self):
        self.assertIn("'Color'", self.refusal(name_en="Color Meeting"))

    def test_only_whole_words_count(self):
        self.build_event(**self.summary("Colorado's programme starts at the centre; the organiser has tyres."))

    def test_a_listed_proper_name_is_left_alone(self):
        self.build_event(**self.summary("Day 2 at Hiruzen Kogen Center."))

    def test_the_message_points_proper_names_at_the_exception_list(self):
        self.assertIn("AMERICAN_SPELLING_NAMES", self.refusal(name_en="Fuji Center Meeting"))

    def test_edition_is_refused_with_event_as_the_way_out(self):
        # Enthusiasts say "event" (owner, 2026-11-23; spec section 7).
        for text in ("The 2026 edition is the fifth.", "Both Editions left Okayama."):
            with self.subTest(text=text):
                message = self.refusal(**self.summary(text))
                self.assertIn("summary_en", message)
                self.assertIn("'event'", message)

    def test_edition_in_a_short_text_field_is_refused(self):
        self.assertIn("name_en", self.refusal(name_en="Meeting, Autumn Edition"))

    def test_a_car_model_may_carry_edition(self):
        # A model is the maker's name for it ("Limited Edition"), not the site's wording.
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-18",
            extra="list_as_of: 2026-10-01\ncars:\n  - make: Mazda\n    model: Roadster Limited Edition\n"))
        build.build(self.data, self.tmp / "site")


class ProseLinkTests(unittest.TestCase):
    """Prose may carry [text](https://...) links: anchors on the page, plain text elsewhere."""

    LINKED = "It fills a car park inside [Fuji Speedway](https://en.fujispeedway.jp/) on the day."

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"


    def build_with_prose(self, text: str, field="summary_en") -> str:
        write_event(self.data, "meet", extra=f"{field}: {json.dumps(text)}\n")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")
        return (self.tmp / "site" / "events" / "meet" / "index.html").read_text(encoding="utf-8")

    def refusal(self, text: str) -> str:
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with_prose(text)
        return str(ctx.exception)

    def test_a_link_renders_as_an_anchor(self):
        html = self.build_with_prose(self.LINKED)
        self.assertIn('inside <a href="https://en.fujispeedway.jp/">Fuji Speedway</a> on the day', html)
        self.assertNotIn("](", html)

    def test_every_prose_field_on_the_event_page_renders_links(self):
        for field in ("summary_en", "nearest_station", "access_notes_en",
                      "spectator_notes_en", "photography_notes_en"):
            with self.subTest(field=field):
                html = self.build_with_prose(self.LINKED, field)
                self.assertIn('<a href="https://en.fujispeedway.jp/">Fuji Speedway</a>', html)
                shutil.rmtree(self.data)

    def test_route_en_renders_links(self):
        write_event(self.data, "meet")
        write_instance(self.data, "meet", 2026, instance_yaml(
            "meet", 2026, "2026-10-18", "2026-10-18", extra=f"route_en: {json.dumps(self.LINKED)}\n"))
        build.build(self.data, self.tmp / "site")
        html = (self.tmp / "site" / "events" / "meet" / "2026" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<a href="https://en.fujispeedway.jp/">Fuji Speedway</a>', html)
        api = json.loads((self.tmp / "site" / "api" / "events.json").read_text(encoding="utf-8"))
        self.assertEqual(api["events"][0]["route_en"],
                         "It fills a car park inside Fuji Speedway on the day.")

    def test_the_rest_of_the_prose_is_still_escaped(self):
        html = self.build_with_prose('Bring <b>cash</b> & see [A & B](https://example.com/?a=1&b="2").')
        self.assertIn("Bring &lt;b&gt;cash&lt;/b&gt; &amp; see", html)
        self.assertIn('<a href="https://example.com/?a=1&amp;b=&#34;2&#34;">A &amp; B</a>', html)

    def test_jsonld_gets_the_link_text_only(self):
        html = self.build_with_prose(self.LINKED)
        block, = jsonld_blocks(html)
        self.assertEqual(block["description"], "It fills a car park inside Fuji Speedway on the day.")

    def test_urls_do_not_count_towards_the_word_cap(self):
        words = " ".join(["Word."] * (validate.PROSE_MAX_WORDS - 2))
        self.build_with_prose(f"{words} [Fuji Speedway](https://en.fujispeedway.jp/a-very/long/path)")

    def test_advice_inside_link_text_is_still_caught(self):
        self.assertIn("worth a look", self.refusal("The [museum is worth a look](https://example.com/)."))

    def test_a_plain_http_link_is_rejected(self):
        message = self.refusal("See [the circuit](http://example.com/).")
        self.assertIn("summary_en", message)
        self.assertIn("https://", message)

    def test_a_javascript_link_is_rejected(self):
        self.assertIn("summary_en", self.refusal("See [the circuit](javascript:alert(1))."))

    def test_a_malformed_link_is_rejected(self):
        for text in ("See [the circuit] (https://example.com/).",
                     "See [the circuit](https://example.com/.",
                     "See the circuit](https://example.com/)."):
            with self.subTest(text=text):
                self.assertIn("summary_en", self.refusal(text))

    def test_an_html_link_is_rejected_with_the_markdown_form_named(self):
        message = self.refusal('See <a href="https://example.com/">the circuit</a>.')
        self.assertIn("[text](https://", message)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"
        write_event(self.data, "meet")


    def assert_build_fails(self, expected: str):
        with self.assertRaises(validate.ValidationError) as ctx:
            build.build(self.data, self.tmp / "site")
        self.assertIn(expected, str(ctx.exception))

    def assert_rejected(self, instance_text: str, expected: str, stem="2026"):
        write_instance(self.data, "meet", stem, instance_text)
        self.assert_build_fails(expected)

    def test_valid_instance_builds(self):
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        build.build(self.data, self.tmp / "site")

    def test_repo_sample_data_builds(self):
        build.build(ROOT / "data", self.tmp / "sample-site")

    def test_a_fee_that_is_neither_a_number_nor_null_is_rejected(self):
        write_event(self.data, "meet", fee='"free"')
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("spectator_fee_jpy")

    def test_a_negative_fee_is_rejected(self):
        write_event(self.data, "meet", fee=-500)
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("spectator_fee_jpy")

    def test_unquoted_time_is_rejected_with_the_fix(self):
        self.assert_rejected(
            instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                          extra='start_time: 10:30\nend_time: "16:00"\n'),
            '"10:30"')

    def test_hours_ending_before_they_start_are_rejected_on_a_multi_day_edition(self):
        # The times are each day's hours, so 16:00 to 10:00 is never a day.
        self.assert_rejected(
            instance_yaml("meet", 2026, "2026-10-18", "2026-10-19",
                          extra='start_time: "16:00"\nend_time: "10:00"\n'),
            "end_time must be after start_time")

    def test_an_unknown_event_prefecture_is_rejected(self):
        # write_event hard-codes Shizuoka; a second prefecture key via extra would be a YAML duplicate.
        ev = self.data / "events" / "meet.yml"
        ev.write_text(ev.read_text(encoding="utf-8").replace("prefecture: Shizuoka", "prefecture: Shizuokaa"),
                      encoding="utf-8")
        write_instance(self.data, "meet", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("Shizuokaa")

    def test_an_unknown_edition_prefecture_is_rejected(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18",
                                           extra="venue_en: Other Park\nprefecture: Tokio\n"), "Tokio")

    def test_bare_no_key_is_rejected(self):
        extra = "list_as_of: 2026-09-15\ncars:\n  - no: 12\n    year: 1929\n    make: Bentley\n    model: Blower\n"
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra), "entry_no")

    def test_numeric_entry_no_is_rejected(self):
        extra = 'list_as_of: 2026-09-15\ncars:\n  - entry_no: 12\n    year: 1929\n    make: Bentley\n    model: Blower\n'
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "entry_no: must be non-empty text")

    def test_personal_fields_are_rejected(self):
        extra = ('list_as_of: 2026-09-15\ncars:\n  - entry_no: "12"\n    year: 1929\n'
                 '    make: Bentley\n    model: Blower\n    driver: Somebody\n')
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "unknown field 'driver'")

    def test_end_before_start_is_rejected(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-17"), "is before start")

    def test_quoted_date_is_rejected(self):
        self.assert_rejected(instance_yaml("meet", 2026, '"2026-10-18"', "2026-10-18"), "unquoted date")

    def test_times_must_come_in_pairs(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra='start_time: "08:00"\n'),
                             "together")

    def test_entry_numbers_must_be_given_for_every_car_or_none(self):
        extra = ('list_as_of: 2026-09-15\ncars:\n  - entry_no: "12"\n    make: Bentley\n    model: Blower\n'
                 '  - make: Alfa Romeo\n    model: 6C 1750 GS\n')
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "entry_no on every car or on none")

    def test_a_car_country_must_be_one_the_site_can_draw(self):
        extra = ('list_as_of: 2026-09-15\ncars:\n  - entry_no: "12"\n    year: 1929\n    make: Bentley\n'
                 '    model: Blower\n    country: England\n')
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "country: must be one of")

    def test_a_cutoff_year_must_be_a_whole_number(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra="cutoff_year: about 2000\n"),
                             "cutoff_year: must be a whole number")

    def test_a_car_still_needs_a_make_and_a_model(self):
        extra = "list_as_of: 2026-09-15\ncars:\n  - make: Bentley\n"
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "missing required field 'model'")

    def test_cars_need_list_as_of(self):
        extra = 'cars:\n  - entry_no: "12"\n    year: 1929\n    make: Bentley\n    model: Blower\n'
        self.assert_rejected(instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=extra),
                             "cars and list_as_of")

    def test_slug_must_match_folder(self):
        self.assert_rejected(instance_yaml("other", 2026, "2026-10-18", "2026-10-18"), "must match the folder")

    def test_unsafe_event_file_name_is_rejected(self):
        write_event(self.data, "tom & jerry")
        self.assert_build_fails("lowercase letters, digits and single hyphens")

    def test_unsafe_folder_name_is_rejected(self):
        write_instance(self.data, "Meet 2", 2026, instance_yaml("meet", 2026, "2026-10-18", "2026-10-18"))
        self.assert_build_fails("lowercase letters, digits and single hyphens")

    def test_edition_file_names_must_start_with_the_year(self):
        for stem in ("spring-2026", "2026_spring", "2026-Spring", "26-spring"):
            with self.subTest(stem=stem):
                shutil.rmtree(self.data / "events" / "meet", ignore_errors=True)
                self.assert_rejected(instance_yaml("meet", 2026, "2026-04-12", "2026-04-12"),
                                     "file name must be the year", stem=stem)

    def test_edition_year_must_match_file_name(self):
        self.assert_rejected(instance_yaml("meet", 2026, "2026-04-12", "2026-04-12"),
                             "must match the file name", stem="2027-spring")


class CoordinateTests(unittest.TestCase):
    """A pin is data like any other: checked, or absent. Never approximated."""

    def setUp(self):
        self.tmp = temp_dir(self)
        self.data = self.tmp / "data"


    def build_with(self, event_extra="", edition_extra=""):
        write_event(self.data, "meet", extra=event_extra)
        write_instance(self.data, "meet", 2026,
                       instance_yaml("meet", 2026, "2026-10-18", "2026-10-18", extra=edition_extra))
        build.build(self.data, self.tmp / "site")

    def refusal(self, **kwargs) -> str:
        with self.assertRaises(validate.ValidationError) as ctx:
            self.build_with(**kwargs)
        return str(ctx.exception)

    def page(self, rel: str) -> str:
        return (self.tmp / "site" / rel).read_text(encoding="utf-8")

    def test_an_event_with_no_coordinates_builds_and_says_nothing(self):
        self.build_with()
        self.assertNotIn("maps.apple.com", self.page("events/meet/index.html"))

    def test_a_lone_latitude_is_refused(self):
        message = self.refusal(event_extra="lat: 34.9756\n")
        self.assertIn("lat", message)
        self.assertIn("lon", message)

    def test_a_lone_longitude_is_refused(self):
        self.assertIn("lon", self.refusal(event_extra="lon: 138.3828\n"))

    def test_a_swapped_pair_falls_outside_japan_and_is_refused(self):
        self.assertIn("Japan", self.refusal(event_extra="lat: 138.3828\nlon: 34.9756\n"))

    def test_text_where_a_number_belongs_is_refused(self):
        self.assertIn("lat", self.refusal(event_extra='lat: "34.9756"\nlon: 138.3828\n'))

    def test_a_whole_number_is_still_a_coordinate(self):
        self.build_with(event_extra="lat: 35\nlon: 139\n")
        self.assertIn("ll=35,139", self.page("events/meet/index.html"))

    def test_an_edition_that_names_its_own_venue_does_not_inherit_the_pin(self):
        # The coordinates were recorded at the event's venue, not at this one.
        self.build_with(event_extra="lat: 34.9756\nlon: 138.3828\n",
                        edition_extra="venue_en: Another Field\n" + CARS)
        self.assertIn("maps.apple.com", self.page("events/meet/index.html"))
        self.assertNotIn("maps.apple.com", self.page("events/meet/2026/index.html"))

    def test_an_edition_can_carry_its_own_pin(self):
        self.build_with(event_extra="lat: 34.9756\nlon: 138.3828\n",
                        edition_extra="venue_en: Another Field\nlat: 35.1\nlon: 138.9\n" + CARS)
        html = self.page("events/meet/2026/index.html")
        self.assertIn("ll=35.1,138.9", html)
        self.assertIn("q=Another%20Field", html)


class MakeGroupsFileTests(unittest.TestCase):
    """data/make_groups.yml (spec 4.11): checked against makes.yml, one group per make."""

    MAKES = {"Nissan": "JP", "Datsun": "JP", "Prince": "JP", "Lotus": "GB"}

    def setUp(self):
        self.tmp = temp_dir(self)


    def load(self, text: str, makes=None):
        (self.tmp / "make_groups.yml").write_text(text, encoding="utf-8")
        return validate.load_make_groups(self.tmp, self.MAKES if makes is None else makes)

    def errors(self, text: str, makes=None) -> str:
        with self.assertRaises(validate.ValidationError) as caught:
            self.load(text, makes)
        return "\n".join(caught.exception.errors)

    def test_groups_come_back_in_file_order_with_the_rest_as_groups_of_one(self):
        self.assertEqual(self.load("Nissan: [Nissan, Datsun, Prince]\n"),
                         {"Nissan": ["Nissan", "Datsun", "Prince"], "Lotus": ["Lotus"]})

    def test_member_missing_from_makes_fails(self):
        msg = self.errors("Nissan: [Nissan, Datsun]\n", makes={"Nissan": "JP"})
        self.assertIn("Datsun", msg)
        self.assertIn("makes.yml", msg)

    def test_make_in_two_groups_fails(self):
        msg = self.errors("Nissan: [Nissan, Datsun]\nPrince: [Prince, Datsun]\n")
        self.assertRegex(msg, r"Datsun.*Nissan.*Prince")

    def test_first_member_must_be_the_key(self):
        self.assertIn("Nissan", self.errors("Nissan: [Datsun, Nissan]\n"))

    def test_value_must_be_a_list(self):
        self.assertIn("Nissan", self.errors("Nissan: Datsun\n"))

    def test_group_listed_twice_fails(self):
        self.assertIn("listed twice", self.errors("Nissan: [Nissan]\nNissan: [Nissan, Datsun]\n"))

    def test_no_groups_file_gives_groups_of_one(self):
        self.assertEqual(validate.load_make_groups(self.tmp, {"A": None, "B": "GB"}), {"A": ["A"], "B": ["B"]})

    def test_make_slug(self):
        for name, slug in (("Citroën", "citroen"), ("TOM'S", "toms"), ("Mercedes-Benz", "mercedes-benz"),
                           ("Alfa Romeo", "alfa-romeo")):
            with self.subTest(name=name):
                self.assertEqual(validate.make_slug(name), slug)

    def test_colliding_slugs_fail(self):
        # Neither make is on a list: a group that crosses the page bar later must not collide.
        (self.tmp / "makes.yml").write_text("Citroën: FR\nCitroen: FR\n", encoding="utf-8")
        msg = self.errors("", makes=validate.load_makes(self.tmp))
        self.assertIn("citroen", msg)
        self.assertIn("Citroën", msg)
        self.assertIn("Citroen", msg)


class StandaloneValidateTests(unittest.TestCase):
    def test_duplicate_make_is_refused_without_importing_build(self):
        # tools/cars.py and check_links.py import validate alone, so its YAML loader must not
        # depend on a side effect in build.py. A fresh process, since this one has imported build.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "makes.yml").write_text("Lancia: IT\nLancia: GB\n", encoding="utf-8")
            code = ("import sys; sys.path.insert(0, sys.argv[1]); import validate\n"
                    "try:\n    validate.load_makes(__import__('pathlib').Path(sys.argv[2]))\n"
                    "except validate.ValidationError as e:\n    print(e.errors[0])\n"
                    "assert 'build' not in sys.modules")
            out = subprocess.run([sys.executable, "-B", "-c", code, str(ROOT / "scripts"), tmp],
                                 capture_output=True, text=True, check=True).stdout
        self.assertIn("Lancia is listed twice", out)


if __name__ == "__main__":
    unittest.main()
