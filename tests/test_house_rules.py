"""Checks on templates and static/: spelling, em dashes, stylesheet tokens, script syntax, message pointers."""

import ast
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from markupsafe import escape

from helpers import CARS, instance_yaml, make_fixture, ROOT, ROUTE, temp_dir, write_event, write_instance
import build  # noqa: E402
import validate  # noqa: E402


class BritishSpellingTests(unittest.TestCase):
    """Page text uses British spelling; `organizer` survives only as a data field name."""

    def test_templates_say_organiser(self):
        for path in sorted((ROOT / "templates").glob("*.html")):
            # Template code names the data field; only the text around it is read by visitors.
            text = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", "", path.read_text(encoding="utf-8"))
            self.assertNotRegex(text, r"(?i)organiz", path.name)


class EventNotEditionTests(unittest.TestCase):
    """Visitors read "event", never "edition" (owner, 2026-11-23; spec section 7)."""

    @classmethod
    def setUpClass(cls):
        tmp = temp_dir(cls)
        cls.sites = {}
        # The real data reaches the step links, videos, photo captions and /cars/; the fixture,
        # a cancelled edition, which the real data may lack.
        fixture = tmp / "data"
        make_fixture(fixture)
        for name, data in (("real", ROOT / "data"), ("fixture", fixture)):
            build.build(data, tmp / name)
            # A car model is the maker's name ("Limited Edition"), not the site's wording.
            models = {car["model"] for item in validate.load_and_validate(data)[1]
                      for car in item["data"].get("cars") or []}
            cls.sites[name] = (tmp / name, models)

    @staticmethod
    def visible(html: str, models: set) -> str:
        html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S)
        # Whole cells only: Mitsubishi's model "i" would otherwise delete every letter i.
        for model in models:
            html = html.replace(f"<td>{escape(model)}</td>", "<td></td>")
        labels = re.findall(r'\b(?:aria-label|title|alt|content)="([^"]*)"', html)
        return " ".join([re.sub(r"<[^>]+>", " ", html)] + labels)

    def test_no_page_says_edition(self):
        for name, (site, models) in self.sites.items():
            pages = sorted(site.rglob("*.html"))
            self.assertGreater(len(pages), 5, name)
            found = [f"{name}: {page.relative_to(site)}: {match.group(0)!r}"
                     for page in pages
                     for match in re.finditer(r"[^.<>\n]{0,40}\beditions?\b[^.<>\n]{0,20}",
                                              self.visible(page.read_text(encoding="utf-8"), models), re.I)]
            self.assertEqual(found[:10], [], f"{len(found)} in all")

    def test_the_check_can_fire(self):
        self.assertRegex(self.visible('<nav aria-label="Other editions"><p>Next edition</p></nav>', set()),
                         r"(?i)\beditions?\b")
        self.assertNotRegex(self.visible("<td>Roadster Limited Edition</td>", {"Roadster Limited Edition", "i"}),
                            r"(?i)\bedition\b")
        self.assertRegex(self.visible("<p>Next edition</p><td>i</td>", {"i"}), r"Next edition")

# Hand-written folders. tools/, video/ and .claude/ are local only, so on Actions they are
# absent and skipped; data/ is checked by the build itself.
EM_DASH_FOLDERS = ("scripts", "tests", "templates", "static", ".github", "tools", "video", ".claude")


def em_dash_files(root):
    return [path for folder in EM_DASH_FOLDERS for path in (root / folder).rglob("*")
            if path.suffix in (".py", ".html", ".css", ".js", ".yml", ".md")
            and not {".venv", "__pycache__"} & set(path.parts)]


def em_dash_lines(root):
    return [f"{path.relative_to(root)}:{number}"
            for path in em_dash_files(root)
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if chr(0x2014) in line]


class LiteralEmDashTests(unittest.TestCase):
    """No em dash character in the code, templates or skills: a template's reaches visitors, and
    in code one reads as a hyphen. Code that needs the character writes it as an escape."""

    def test_none_in_code_templates_or_styles(self):
        self.assertTrue(em_dash_files(ROOT), "no files found, so this test would prove nothing")
        self.assertEqual(em_dash_lines(ROOT), [],
                         "write \\u2014 in code, or a comma, colon or semicolon in text")

    def test_the_sweep_finds_a_planted_dash(self):
        # Proves the sweep can report a positive, so a pass above is not a sweep matching nothing.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("tools/x.py", ".claude/skills/y/SKILL.md", "tools/.venv/z.py"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(f"one\ntwo {chr(0x2014)} three\n", encoding="utf-8")
            self.assertEqual(sorted(em_dash_lines(root)), [".claude/skills/y/SKILL.md:2", "tools/x.py:2"])


# Values the stylesheet may use. The spec's token table explains them; this is the copy
# that is enforced, because the spec is never uploaded and a test cannot read it.
COLOUR_TOKENS = {
    "#1C1C1C", "#EBEBEB", "#FFFFFF", "#141414", "#5C5C5C", "#A8A8A8", "#E0E0E0", "#333333",
    "#FFF4D6", "#5E4700", "#3A300F", "#F3D98B", "#FBE9E5", "#8E2A1B",
    "#3A1C16", "#F2A493", "#8C1C24", "#D0636A",
    # Route maps' sea, light and dark (spec 6.5).
    "#D5E3EC", "#1A2731",
}
FONT_SIZES = {"32px", "24px", "20px", "16px"}
SPACING = {"4px", "8px", "16px", "24px", "32px", "48px"}
# 16:9, the one ratio a video box is held at. Geometry, not spacing, so it is not a token.
VIDEO_RATIO = "56.25%"
RADII = {"8px"}
# An 8px radius turns the outline round a short link into a pill.
SMALL_RADII = {"4px"}
KEYWORDS = {"0", "auto", "inherit", "transparent", "currentcolor"}
COLOUR_PROPS = re.compile(r"^(color|background(-color)?|border(-(top|right|bottom|left))?-color|outline-color|fill)$")
SPACING_PROPS = re.compile(r"^(margin|padding)(-(top|right|bottom|left))?$|^gap$")


def token_violations(css: str) -> list[str]:
    found = []
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for hexval in re.findall(r"#[0-9A-Fa-f]{3,6}\b", css):
        if hexval.upper() not in COLOUR_TOKENS:
            found.append(f"colour {hexval}")
    # Inner rules only: [^{}] cannot cross into an @media block's own braces.
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            prop, value = (s.strip() for s in decl.split(":", 1))
            words = value.lower().split()
            if COLOUR_PROPS.match(prop):
                bad = [w for w in words if w not in KEYWORDS and not w.startswith("#")]
            elif prop == "font-size":
                bad = [w for w in words if w not in FONT_SIZES | KEYWORDS]
            elif SPACING_PROPS.match(prop):
                allowed = SPACING | {VIDEO_RATIO} if selector.strip() == ".video-frame" else SPACING
                # A negative margin is half of the gap that flex rows cannot use (spec 6.5), so it
                # is a spacing token negated, never a size of its own.
                if prop.startswith("margin"):
                    allowed = allowed | {f"-{w}" for w in SPACING}
                bad = [w for w in words if w not in allowed | KEYWORDS]
            elif prop == "border-radius":
                # 8px would turn a focus ring round a short link, or a 16px-high flag, into a pill.
                small = ":focus" in selector or selector.strip() == ".flag"
                allowed = RADII | SMALL_RADII if small else RADII
                bad = [w for w in words if w not in allowed | KEYWORDS]
            else:
                continue
            found += [f"{selector.strip()} {{ {prop}: {w} }}" for w in bad]
    return found


def duplicate_selectors(css: str) -> list[str]:
    """Selectors given a second rule in the same scope: the top level, or one @media block.

    A repeat is how a new rule lands on an existing class unnoticed. The thumbnails were first
    styled as .map, which the Map link already used, and the link became a block with a red pin.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    media = r"@media[^{]*\{((?:[^{}]*\{[^{}]*\})*)\s*\}"
    found = []
    for scope in [re.sub(media, "", css)] + re.findall(media, css):
        seen = set()
        for head in re.findall(r"([^{}]+)\{[^{}]*\}", scope):
            head = " ".join(head.split())
            if head in seen:
                found.append(head)
            seen.add(head)
    return found


GRID_ALLOWED = (".events", ".facts", ".dates-table")


def grid_violations(css: str) -> list[str]:
    """Grid only where it degrades to readable stacked blocks (spec 6.5).

    .events and .facts stack on their own without grid. The Dates table's rows are table rows,
    so each of its grid rules must declare display: block first, for a browser to fall back on.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = []
    for head, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        grid = re.search(r"display:\s*(?:inline-)?grid", body)
        if not grid:
            continue
        for selector in (" ".join(sel.split()) for sel in head.split(",")):
            if not selector.split(" ")[0].startswith(GRID_ALLOWED):
                found.append(f"{selector}: grid outside .events, .facts and .dates-table")
            elif selector.startswith(".dates-table") and "display: block" not in body[:grid.start()]:
                found.append(f"{selector}: no display: block before display: grid")
    return found


class GridFallbackTests(unittest.TestCase):
    def test_grid_is_used_only_where_it_falls_back(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertEqual(grid_violations(css), [])

    def test_the_check_fires_on_a_stray_grid_and_a_missing_fallback(self):
        css = (".cards { display: grid; }\n"
               "@media (max-width: 619px) {\n  .dates-table tr { display: grid; display: block; }\n"
               "  .dates-table td { display: block; display: grid; }\n}\n"
               ".events > li { display: grid; }")
        self.assertEqual(grid_violations(css), [
            ".cards: grid outside .events, .facts and .dates-table",
            ".dates-table tr: no display: block before display: grid",
        ])


class StylesheetTokenTests(unittest.TestCase):
    """Every colour, size and space in the stylesheet comes from the documented set."""

    def test_the_stylesheet_uses_only_token_values(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertEqual(token_violations(css), [])

    def test_no_selector_is_given_two_rules_in_one_scope(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertEqual(duplicate_selectors(css), [])

    def test_the_duplicate_check_catches_a_repeat(self):
        css = (".map { padding: 4px 0; }\n.map  circle { fill: red; }\n.map { display: block; }\n"
               "@media (max-width: 480px) { .map { margin: 0; } .facts { gap: 4px; } .facts { margin: 0; } }")
        # Once per scope is fine: the media block restating .map is not a repeat.
        self.assertEqual(duplicate_selectors(css), [".map", ".facts"])

    def test_the_brand_red_is_the_link_colour_in_both_themes(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"(?m)^a \{ color: #8C1C24; \}")
        self.assertRegex(css, r"(?m)^  a \{ color: #D0636A; \}")

    def test_the_check_catches_an_off_scale_value(self):
        # A zero from a check that cannot fire proves nothing, so show it firing.
        css = ("a { margin: 13px 8px; color: #123456; font-size: 15px; border-radius: 4px; }\n"
               "a:focus-visible { border-radius: 4px; }\n"
               ".flag { border-radius: 4px; }\n"
               "b { padding: 0 auto; color: currentColor; background: #fff4d6; }\n"
               "i { margin-left: -32px; margin-right: -13px; padding-left: -8px; }")
        self.assertEqual(token_violations(css), [
            "colour #123456",
            "a { margin: 13px }", "a { font-size: 15px }", "a { border-radius: 4px }",
            "i { margin-right: -13px }", "i { padding-left: -8px }",
        ])


class ScrollableTableTests(unittest.TestCase):
    """A table wider than a phone scrolls in its own box, which a keyboard can reach only if the box takes focus (WCAG 2.1.1)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        make_fixture(cls.tmp / "data")
        write_event(cls.tmp / "data", "tour")
        write_instance(cls.tmp / "data", "tour", 2026,
                       instance_yaml("tour", 2026, "2026-10-18", "2026-10-19", extra=ROUTE + CARS))
        build.build(cls.tmp / "data", cls.tmp / "site")
        cls.pages = {p.relative_to(cls.tmp / "site").as_posix(): p.read_text(encoding="utf-8")
                     for p in (cls.tmp / "site").rglob("*.html")}


    def test_every_table_box_is_a_named_focusable_region(self):
        boxes = [(name, box) for name, html in self.pages.items()
                 for box in re.findall(r'<div class="table-wrap"[^>]*>', html)]
        self.assertGreater(len(boxes), 3)
        for name, box in boxes:
            with self.subTest(page=name, box=box):
                # A script may need the box by id, and may keep it hidden until it has rows (make pages).
                self.assertRegex(box, r'^<div class="table-wrap" tabindex="0" role="region" aria-label="[^"]+"'
                                      r'( id="[a-z-]+")?( hidden)?>$')

    def test_each_box_is_named_after_what_it_holds(self):
        self.assertIn('<div class="table-wrap" tabindex="0" role="region" aria-label="Dates">',
                      self.pages["events/autumn-rally/index.html"])
        edition = self.pages["events/tour/2026/index.html"]
        self.assertRegex(edition, r'aria-label="Day 1: [^"]+"')
        self.assertIn('aria-label="Entry list"', edition)

    def test_the_focused_box_is_ringed_in_both_themes(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        # The main dark block is the first; a later one restates a breakpoint's colours.
        light, dark = css.split("@media (prefers-color-scheme: dark)", 1)
        for scope, block in (("light", light), ("dark", dark)):
            with self.subTest(theme=scope):
                self.assertRegex(block, r"\.table-wrap:focus-visible[^{]*\{[^}]*outline")


def unplaced_links(html: str) -> tuple[int, list[str]]:
    """Links in table rows that share their text with a link elsewhere going somewhere else,
    in a row with no row header to tell them apart (WCAG 2.4.4). Also the count of row links seen."""

    class Walker(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links, self.rows, self.link, self.row, self.body = [], [], None, None, 0

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "tbody":
                self.body += 1
            elif tag == "tr" and self.body:
                self.row = [False, []]
            elif tag == "th" and self.row is not None and a.get("scope") == "row":
                self.row[0] = True
            elif tag == "a":
                self.link = [a.get("aria-label") or "", a.get("href"), bool(a.get("aria-label"))]

        def handle_data(self, data):
            if self.link is not None and not self.link[2]:
                self.link[0] += data

        def handle_endtag(self, tag):
            if tag == "a" and self.link is not None:
                text = " ".join(self.link[0].split())
                self.links.append((text, self.link[1]))
                if self.row is not None:
                    self.row[1].append(text)
                self.link = None
            elif tag == "tr" and self.row is not None:
                self.rows.append(self.row)
                self.row = None
            elif tag == "tbody":
                self.body -= 1

    w = Walker()
    w.feed(html)
    targets = {}
    for text, href in w.links:
        targets.setdefault(text, set()).add(href)
    seen = sum(len(texts) for _, texts in w.rows)
    return seen, sorted({t for header, texts in w.rows if not header for t in texts if len(targets[t]) > 1})


class RowHeaderTests(unittest.TestCase):
    """A link whose text repeats with another target is told apart by its row header or its own name (WCAG 2.4.4)."""

    def test_the_checker_finds_a_repeated_link_without_a_row_header(self):
        # Proves the page test below can fail: same text, two targets, no header; the rest pass.
        html = ('<table><tbody>'
                '<tr><td>Alpha</td><td><a href="/a/2026/">1 in 2026</a></td></tr>'
                '<tr><td>Bravo</td><td><a href="/b/2026/">1 in 2026</a></td></tr>'
                '<tr><th scope="row">Charlie</th><td><a href="/c/2026/">2 in 2026</a></td></tr>'
                '<tr><td>Delta</td><td><a href="/d/2026/">2 in 2026</a></td></tr>'
                '<tr><td><a href="/cars/fiat/">Fiat</a></td><td><a href="/cars/fiat/">Fiat</a></td></tr>'
                '</tbody></table>')
        self.assertEqual(unplaced_links(html), (6, ["1 in 2026", "2 in 2026"]))

    def test_no_page_of_the_real_site_leaves_a_repeated_link_unplaced(self):
        out = temp_dir(self)
        build.build(ROOT / "data", out)
        seen = 0
        for page in sorted(out.rglob("*.html")):
            count, found = unplaced_links(page.read_text(encoding="utf-8"))
            seen += count
            with self.subTest(page=page.relative_to(out).as_posix()):
                self.assertEqual(found, [])
        # A checker that saw no links in rows would pass every page.
        self.assertGreater(seen, 1000)

    def test_a_calendar_link_names_its_edition_on_the_event_page(self):
        out = temp_dir(self)
        data = out / "data"
        write_event(data, "meet")
        write_instance(data, "meet", "2027-spring", instance_yaml("meet", 2027, "2027-04-04", "2027-04-04"))
        write_instance(data, "meet", "2027-autumn", instance_yaml("meet", 2027, "2027-10-03", "2027-10-03"))
        build.build(data, out / "site")
        html = (out / "site/events/meet/index.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'Add to Google Calendar<span class="visually-hidden"> \(Autumn 2027\)</span></a>')
        self.assertRegex(html, r'Add to Google Calendar<span class="visually-hidden"> \(Spring 2027\)</span></a>')

    def test_a_row_header_keeps_the_weight_of_a_cell(self):
        css = (ROOT / "static/style.css").read_text(encoding="utf-8")
        self.assertRegex(css, r'tbody th \{[^}]*font-weight: normal;')


def old_browser_breakers(js: str) -> list[str]:
    """Syntax and APIs that stop a script dead on the old phones and PCs the site supports."""
    js = re.sub(r"//[^\n]*", "", js)
    rules = {"arrow function": r"=>", "let or const": r"\b(let|const)\s", "class": r"\bclass\s+\w",
             "template literal": "`", "NodeList forEach": r"\.forEach\(", "dataset": r"\.dataset\b"}
    return [name for name, pattern in rules.items() if re.search(pattern, js)]


class ScriptSyntaxTests(unittest.TestCase):
    """Inline scripts are ES5 with no newer DOM methods: newer ones fail outright, taking the rest of the script with them."""

    def test_the_check_catches_each_breaker(self):
        js = "const a = 1; let b = () => `x`; class C {} els.forEach(f); el.dataset.year"
        self.assertEqual(len(old_browser_breakers(js)), 6)

    def test_no_template_script_uses_one(self):
        scripts = [(t.name, body) for t in sorted((ROOT / "templates").glob("*.html"))
                   for body in re.findall(r"<script>(.*?)</script>", t.read_text(encoding="utf-8"), re.S)]
        self.assertGreater(len(scripts), 4)
        for name, body in scripts:
            with self.subTest(template=name):
                self.assertEqual(old_browser_breakers(body), [])


def named_settings(root) -> list[tuple[str, str, str]]:
    """(file, NAME, path) for every "NAME in scripts/x.py" a message tells the reader to edit."""
    found = set()
    for folder in ("scripts", "tools", "video"):
        for path in sorted((root / folder).glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                # An f-string split over lines is one node, so a pointer broken across them is still found.
                if isinstance(node, ast.JoinedStr):
                    text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value
                else:
                    continue
                for match in re.finditer(r"\b([A-Z][A-Z0-9_]{2,}) in ((?:scripts|tools|video)/\w+\.py)", text):
                    found.add((path.relative_to(root).as_posix(), *match.groups()))
    return sorted(found)


class MessagePointerTests(unittest.TestCase):
    """A message that names where a setting lives names the file that defines it, after any move."""

    def test_the_finder_reads_a_pointer_split_across_lines(self):
        tmp = temp_dir(self)
        (tmp / "scripts").mkdir()
        (tmp / "scripts" / "x.py").write_text('m = (f"edit {a} KEY in "\n     f"scripts/y.py")\n', encoding="utf-8")
        self.assertEqual(named_settings(tmp), [("scripts/x.py", "KEY", "scripts/y.py")])

    def test_each_named_setting_is_defined_in_the_file_named(self):
        pointers = named_settings(ROOT)
        self.assertGreater(len(pointers), 0)
        for source, name, target in pointers:
            with self.subTest(f"{source}: {name} in {target}"):
                defined = re.search(rf"(?m)^{name}\b\s*(:[^=\n]*)?=", (ROOT / target).read_text(encoding="utf-8"))
                self.assertIsNotNone(defined, f"{name} is not defined in {target}")


if __name__ == "__main__":
    unittest.main()
