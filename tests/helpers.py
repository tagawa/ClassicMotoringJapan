"""Helpers every test file shares: a site written from YAML in a temporary folder.

Importing this puts scripts/ on the path, so a test file can import build and its modules.
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def write_event(data: Path, slug: str, name_en="Test Event", name_ja="テストイベント",
                fee=0, extra="") -> None:
    """name_ja=None writes no Japanese name, as for an event that has only a Latin one.

    fee=None writes null, the state of an event whose admission is not announced yet.
    """
    p = data / "events" / f"{slug}.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"slug: {slug}\n"
        f"name_en: {name_en}\n"
        + (f"name_ja: {name_ja}\n" if name_ja is not None else "")
        + 
        f"official_url: https://example.com/{slug}/\n"
        f"prefecture: Shizuoka\n"
        f"venue_en: Test Park\n"
        f"spectator_fee_jpy: {'null' if fee is None else fee}\n"
        f"last_verified: 2026-09-20\n" + extra,
        encoding="utf-8",
    )


def instance_yaml(slug: str, year: int, start: str, end: str, status="confirmed", extra="",
                  verified="2026-09-20") -> str:
    return (
        f"slug: {slug}\n"
        f"year: {year}\n"
        f"status: {status}\n"
        f"start: {start}\n"
        f"end: {end}\n"
        f"source_url: https://example.com/{slug}/{year}/\n"
        f"last_verified: {verified}\n"
        f"sequence: 0\n" + extra
    )


def write_instance(data: Path, slug: str, stem, text: str) -> None:
    """stem is the edition file name without .yml, e.g. 2026 or "2026-spring"."""
    p = data / "events" / slug / f"{stem}.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


CARS = (
    "list_as_of: 2026-09-15\n"
    "cars:\n"
    '  - entry_no: "12"\n'
    "    year: 1929\n"
    "    make: Bentley\n"
    "    model: 4½ Litre Blower\n"
    '  - entry_no: "037"\n'
    "    year: 1934\n"
    "    make: Alfa Romeo\n"
    "    model: 6C 1750 GS\n"
)
ROUTE = (
    "route:\n"
    "  - date: 2026-10-18\n"
    "    checkpoints:\n"
    '      - start_time: "09:00"\n'
    '        end_time: "09:30"\n'
    "        place_en: Test Park, Testville\n"
    "        place_ja: \u30c6\u30b9\u30c8\u516c\u5712\n"
    "        prefecture: Shizuoka\n"
    '      - start_time: "11:00"\n'
    "        place_en: Test Harbour\n"
    "        prefecture: Shizuoka\n"
    "  - date: 2026-10-19\n"
    "    checkpoints:\n"
    '      - start_time: "08:00"\n'
    '        end_time: "08:45"\n'
    "        place_en: Test Hill\n"
    "        prefecture: Shizuoka\n"
)


ROUTE_ONE_DAY = (
    "route:\n"
    "  - date: 2026-11-22\n"
    "    checkpoints:\n"
    '      - start_time: "10:00"\n'
    "        place_en: Test Park\n"
    "        prefecture: Osaka\n"
)

RALLY_EXTRA = 'start_time: "08:00"\nend_time: "16:00"\nroute_en: Start Test Park 08:00, finish Test Harbour 16:00.\n' + CARS


def make_fixture(data: Path) -> None:
    write_event(data, "autumn-rally", name_en='"Autumn Rally, Shizuoka"',
                name_ja="オータム・クラシックカー・ラリー・イン・静岡・ヒストリック・ツーリング・ミーティング",
                extra="lat: 34.9756\nlon: 138.3828\n")
    write_instance(data, "autumn-rally", 2026,
                   instance_yaml("autumn-rally", 2026, "2026-10-18", "2026-10-19", extra=RALLY_EXTRA))
    write_event(data, "culture-day-show", fee=1500)
    write_instance(data, "culture-day-show", 2026,
                   instance_yaml("culture-day-show", 2026, "2026-11-03", "2026-11-03"))
    write_instance(data, "culture-day-show", 2027,
                   instance_yaml("culture-day-show", 2027, "2027-11-03", "2027-11-03", status="cancelled"))
    write_event(data, "hill-climb", name_en="Hill Climb",
                extra="typical_eras: [Prewar, 1950s]\ntypical_scale: About 30 cars\n")
    write_instance(data, "hill-climb", "2026-spring",
                   instance_yaml("hill-climb", 2026, "2026-04-12", "2026-04-12"))
    write_instance(data, "hill-climb", "2026-autumn",
                   instance_yaml("hill-climb", 2026, "2026-10-25", "2026-10-25", extra=CARS))


def cars_yaml(years, as_of="2026-09-15", makes=None) -> str:
    """makes, when given, names each car's make in turn; otherwise every car is a Test."""
    makes = makes or ["Test"] * len(years)
    rows = "".join(f'  - entry_no: "{i:02d}"\n    year: {y}\n    make: {make}\n    model: Car\n'
                   for i, (y, make) in enumerate(zip(years, makes), 1))
    return f"list_as_of: {as_of}\ncars:\n{rows}"


def display_cars_yaml(models, as_of="2026-09-15") -> str:
    """A show's announced line-up: the source names models, so no numbers and no years."""
    rows = "".join(f"  - make: {make}\n    model: {model}\n" for make, model in models)
    return f"list_as_of: {as_of}\ncars:\n{rows}"


def unfold(ics: str) -> list[str]:
    return ics.replace("\r\n ", "").split("\r\n")


def jsonld_blocks(html: str) -> list[dict]:
    return [json.loads(m) for m in
            re.findall(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', html, re.S)]


class HeadParser(HTMLParser):
    """The head's meta and link tags, with attribute values unescaped as a browser reads them."""

    def __init__(self, html: str):
        super().__init__()
        self.meta, self.canonical, self.title, self._in_title = {}, None, "", False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and ("name" in a or "property" in a):
            self.meta[a.get("name") or a["property"]] = a["content"]
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a["href"]
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
