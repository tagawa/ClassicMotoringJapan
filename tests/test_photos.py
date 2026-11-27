"""Event photos and share cards (spec 4.11 and 8.3). Run: python -m unittest discover -s tests -v"""
import hashlib
import re
import shutil
import struct
import sys
import unittest
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
import photos  # noqa: E402
import car_pages  # noqa: E402
import settings  # noqa: E402
import validate  # noqa: E402
from helpers import (HeadParser, instance_yaml, make_fixture, temp_dir, write_event,  # noqa: E402
                     write_instance, write_site, CARS, NISSAN_LISTS)

OWN_PHOTO = "photo:\n  alt_en: A red coupe on the start line\n  year: 2025\n"
CC_PHOTO = ("photo:\n  alt_en: Two roadsters parked by a fountain\n  year: 2024\n"
            "  credit: Test Author\n  license: CC BY-SA 4.0\n"
            "  source_url: https://commons.wikimedia.org/wiki/File:Test.jpg\n")


def iptc_segment(by_line: str) -> bytes:
    """An APP13 block as Photoshop writes it, holding one IPTC field: the photographer's name."""
    dataset = b"\x1c\x02\x50" + struct.pack(">H", len(by_line)) + by_line.encode()
    if len(dataset) % 2:
        dataset += b"\x00"
    resource = b"8BIM" + struct.pack(">H", 0x0404) + b"\x00\x00" + struct.pack(">I", len(dataset)) + dataset
    body = b"Photoshop 3.0\x00" + resource
    return b"\xff\xed" + struct.pack(">H", len(body) + 2) + body


def save_jpeg(path: Path, size=(1600, 900), meta=(), orientation=None, icc=None) -> None:
    """A test JPEG, clean unless meta names what a camera or editor would have left in it."""
    img = Image.new("RGB", size, (140, 28, 36))
    img.paste((240, 240, 240), (0, 0, size[0] // 2, size[1] // 2))
    extra = {}
    if "exif" in meta or orientation:
        exif = Image.Exif()
        exif[0x010F] = "TestCam"
        if orientation:
            exif[0x0112] = orientation
        extra["exif"] = exif
    if "xmp" in meta:
        extra["xmp"] = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF/></x:xmpmeta>'
    if "comment" in meta:
        extra["comment"] = b"Taken by A. Person, Oiso"
    if icc:
        extra["icc_profile"] = icc
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=90, **extra)
    if "iptc" in meta:
        raw = path.read_bytes()
        path.write_bytes(raw[:2] + iptc_segment("Test Photographer") + raw[2:])


def write_photo(data: Path, slug: str, size=(1600, 900), meta=()) -> None:
    save_jpeg(data / "photos" / f"{slug}.jpg", size, meta)


SIZES = 'sizes="(max-width: 720px) calc(100vw - 32px), 688px"'


def assert_picture(case: unittest.TestCase, html: str, stem: str, height: int) -> None:
    """The hero's <picture>: a WebP source and a JPEG img, both at the three widths (spec 4.10)."""
    pic = re.search(r'(?s)<figure class="hero">\s*<picture>(.*?)</picture>', html).group(1)
    source = re.search(r"<source [^>]+>", pic).group(0)
    img = re.search(r"<img [^>]+>", pic).group(0)
    case.assertIn('type="image/webp"', source)
    for tag, ext in ((source, "webp"), (img, "jpg")):
        case.assertRegex(tag, 'srcset="' + ", ".join(rf"(?:\.\./)*{re.escape(stem)}-{w}\.{ext} {w}w"
                                                    for w in (720, 1080, 1440)) + '"')
        case.assertIn(SIZES, tag)
    case.assertRegex(img, rf'src="[^"]*{re.escape(stem)}-720\.jpg"')
    case.assertIn(f'width="720" height="{height}"', img)
    case.assertNotIn("loading", img, "it is the first thing on the page")


def assert_files(case: unittest.TestCase, folder: Path, stem: str, heights: dict) -> None:
    for w, h in heights.items():
        for ext, fmt in (("jpg", "JPEG"), ("webp", "WEBP")):
            with Image.open(folder / f"{stem}-{w}.{ext}") as im:
                case.assertEqual((im.size, im.format), ((w, h), fmt), f"{stem}-{w}.{ext}")


def share_path(out: Path, url: str) -> Path:
    return out / url.removeprefix(f"{settings.SITE_URL}/").split("?")[0]


def errors_for(data: Path, out: Path) -> str:
    with unittest.TestCase().assertRaises(validate.BuildError) as caught:
        build.build(data, out)
    return "\n".join(caught.exception.errors)


class PhotoValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir(self)
        self.data, self.out = self.tmp / "data", self.tmp / "site"


    def test_a_photo_field_needs_its_file(self):
        write_event(self.data, "meet", extra=OWN_PHOTO)
        self.assertIn("photos/meet.jpg", errors_for(self.data, self.out))

    def test_a_photo_file_needs_its_field(self):
        # Otherwise a photo could go live with no alt text and no credit.
        write_event(self.data, "meet")
        write_photo(self.data, "meet")
        self.assertIn("photos/meet.jpg has no photo field", errors_for(self.data, self.out))

    def test_a_photo_for_no_event_is_rejected(self):
        write_event(self.data, "meet")
        write_photo(self.data, "meat")
        self.assertIn("photos/meat.jpg", errors_for(self.data, self.out))

    def test_credit_licence_and_source_come_together(self):
        write_event(self.data, "meet", extra=OWN_PHOTO + "  credit: Someone\n")
        write_photo(self.data, "meet")
        self.assertIn("credit, license and source_url", errors_for(self.data, self.out))

    def test_a_licence_that_forbids_cropping_is_rejected(self):
        write_event(self.data, "meet", extra=CC_PHOTO.replace("CC BY-SA 4.0", "CC BY-ND 4.0"))
        write_photo(self.data, "meet")
        self.assertIn("license", errors_for(self.data, self.out))

    def test_a_photo_too_small_for_a_sharp_page_is_rejected(self):
        write_event(self.data, "meet", extra=OWN_PHOTO)
        write_photo(self.data, "meet", size=(1200, 800))
        self.assertIn("1440", errors_for(self.data, self.out))

    def test_a_photo_still_carrying_metadata_is_refused_by_name(self):
        # By then it is public in the repository, so the message says what to do about it.
        for kind in ("exif", "xmp", "iptc", "comment"):
            with self.subTest(kind):
                shutil.rmtree(self.tmp)
                write_event(self.data, "meet", extra=OWN_PHOTO)
                write_photo(self.data, "meet", meta=(kind,))
                msg = errors_for(self.data, self.out)
                self.assertIn("photos/meet.jpg", msg)
                self.assertIn(kind.upper() if kind != "comment" else "comment", msg)
                self.assertIn("already public", msg)
                self.assertIn("tools/photo.py", msg)
                self.assertNotIn("history", msg, "removing a file from history is not practical here")

    def test_pending_can_list_every_photo_still_carrying_metadata(self):
        # tools/pending.py lists nothing for upload while this is not empty (spec 4.10).
        write_photo(self.data, "clean")
        write_photo(self.data, "dirty", meta=("xmp",))
        self.assertEqual(photos.photos_with_metadata(self.data),
                         ["photos/dirty.jpg carries XMP: run it through tools/photo.py"])
        self.assertEqual(photos.photos_with_metadata(self.tmp / "empty"), [])

    def test_the_metadata_check_names_each_kind_and_passes_a_clean_file(self):
        p = self.tmp / "x.jpg"
        save_jpeg(p, meta=("exif", "xmp", "iptc", "comment"))
        self.assertEqual(photos.photo_metadata(p), ["EXIF", "XMP", "IPTC", "comment"])
        save_jpeg(p, icc=b"not checked")
        self.assertEqual(photos.photo_metadata(p), [])


class PhotoOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        write_event(cls.data, "own", name_en="Own Meet", extra=OWN_PHOTO)
        write_photo(cls.data, "own")
        write_instance(cls.data, "own", 2026, instance_yaml("own", 2026, "2026-10-18", "2026-10-18", extra=CARS))
        write_event(cls.data, "commons", name_en="Commons Meet", extra=CC_PHOTO)
        write_photo(cls.data, "commons", size=(2000, 1500))
        write_event(cls.data, "bare", name_en="Bare Meet")
        build.build(cls.data, cls.out)


    def page(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def test_each_photo_is_written_at_three_widths_in_both_formats_in_two_to_one(self):
        for slug in ("own", "commons"):
            assert_files(self, self.out / "static/photos", slug, {720: 360, 1080: 540, 1440: 720})

    def test_no_camera_data_reaches_the_site(self):
        # GPS lives in EXIF, so no EXIF at all means no location either.
        for p in (self.out / "static/photos").iterdir():
            with Image.open(p) as img:
                self.assertEqual(dict(img.getexif()), {}, p.name)
                self.assertNotIn("exif", img.info, p.name)

    def test_the_photo_sits_under_the_heading_on_event_and_edition_pages(self):
        for rel in ("events/own/index.html", "events/own/2026/index.html"):
            html = self.page(rel)
            self.assertRegex(html, r'(?s)</h1>.*?<figure class="hero">.*?<dl class="facts">', rel)

    def test_the_image_has_size_alt_and_three_widths_in_both_formats(self):
        for rel in ("events/own/index.html", "events/own/2026/index.html"):
            html = self.page(rel)
            assert_picture(self, html, "static/photos/own", 360)
            self.assertIn('alt="A red coupe on the start line"', re.search(r"<img [^>]+>", html).group(0))

    def test_an_own_photo_names_its_edition_and_no_one(self):
        cap = re.search(r"(?s)<figcaption>(.*?)</figcaption>", self.page("events/own/index.html")).group(1)
        self.assertEqual(" ".join(cap.split()), "Photo: 2025 event")

    # Never "edited": the owner asks for it when a photo needs it (2026-11-27).
    def test_someone_elses_photo_carries_credit_source_and_licence_only(self):
        cap = re.search(r"(?s)<figcaption>(.*?)</figcaption>", self.page("events/commons/index.html")).group(1)
        self.assertIn('<a href="https://commons.wikimedia.org/wiki/File:Test.jpg">Test Author</a>', cap)
        self.assertIn('<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>', cap)
        self.assertTrue(cap.rstrip().endswith("CC BY-SA 4.0</a>"), cap)
        self.assertIn("2024 event", cap)
        ja = re.search(r"(?s)<figcaption>(.*?)</figcaption>", self.page("ja/events/commons/index.html")).group(1)
        self.assertTrue(ja.rstrip().endswith("CC BY-SA 4.0</a>"), ja)

    def test_the_same_photo_gives_the_same_bytes(self):
        again = self.tmp / "again"
        build.build(self.data, again)
        for p in sorted((self.out / "static/photos").iterdir()):
            self.assertEqual(p.read_bytes(), (again / "static/photos" / p.name).read_bytes(), p.name)

    def test_a_page_without_a_photo_has_no_figure(self):
        self.assertNotIn('class="hero"', self.page("events/bare/index.html"))

    def test_an_own_photo_is_the_share_image(self):
        meta = HeadParser(self.page("events/own/index.html")).meta
        self.assertTrue(meta["og:image"].startswith(f"{settings.SITE_URL}/static/photos/own-share.jpg?v="))
        with Image.open(self.out / "static/photos/own-share.jpg") as img:
            self.assertEqual(img.size, settings.SHARE_SIZE)
        self.assertEqual(meta["og:image:alt"], "A red coupe on the start line")

    def test_someone_elses_photo_is_never_the_share_image(self):
        # A link preview has no room for the credit the licence asks for.
        meta = HeadParser(self.page("events/commons/index.html")).meta
        self.assertTrue(meta["og:image"].startswith(f"{settings.SITE_URL}/static/cards/events/commons.png?v="))
        self.assertFalse((self.out / "static/photos/commons-share.jpg").exists())


class ShareCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        make_fixture(cls.data)
        build.build(cls.data, cls.out)
        cls.pages = {p.relative_to(cls.out).as_posix(): p.read_text(encoding="utf-8")
                     for p in cls.out.rglob("*.html") if p.name != "404.html"}


    def test_every_page_has_a_share_image_that_exists(self):
        for rel, html in self.pages.items():
            meta = HeadParser(html).meta
            url = meta.get("og:image", "")
            self.assertTrue(url.startswith(f"{settings.SITE_URL}/static/"), rel)
            path = share_path(self.out, url)
            with Image.open(path) as img:
                self.assertEqual(img.size, settings.SHARE_SIZE, rel)
                self.assertEqual((meta["og:image:width"], meta["og:image:height"]),
                                 tuple(str(n) for n in settings.SHARE_SIZE), rel)
            self.assertTrue(meta["og:image:alt"].strip(), rel)
            self.assertEqual(meta["twitter:card"], "summary_large_image", rel)

    def test_the_image_url_changes_with_the_image(self):
        # Platforms cache an image by its URL, so new dates need a new one.
        for rel, html in self.pages.items():
            url = HeadParser(html).meta["og:image"]
            digest = hashlib.sha256(share_path(self.out, url).read_bytes()).hexdigest()[:8]
            self.assertTrue(url.endswith(f"?v={digest}"), rel)

    def test_an_edition_gets_its_own_card(self):
        # The edition's card carries its dates, so it cannot be the event's.
        event = (self.out / "static/cards/events/hill-climb.png").read_bytes()
        edition = (self.out / "static/cards/events/hill-climb/2026-autumn.png").read_bytes()
        self.assertNotEqual(event, edition)

    def test_the_card_alt_says_what_the_card_says(self):
        meta = HeadParser(self.pages["events/hill-climb/2026-autumn/index.html"]).meta
        self.assertEqual(meta["og:image:alt"], "Hill Climb Autumn 2026. Sun 25 Oct 2026. Shizuoka.")

    def test_a_name_too_long_for_the_card_fails_the_build(self):
        tmp = temp_dir(self)
        write_event(tmp / "data", "long", name_en=" ".join(["Extraordinarily"] * 12))
        self.assertIn("events/long.yml", errors_for(tmp / "data", tmp / "site"))



# Make-page photos (spec 4.12), on the cars fixture: Nissan's group (Nissan, Datsun, Prince,
# Nissan Diesel) has a page; Lotus, on two lists, does not. meet-b's 2026 list holds three
# Datsuns, each a 1970 "Car".
CAR_PHOTO = {"file": "datsun-meet-b", "make": "Datsun", "model": "Car", "alt_en": "A white Datsun Car coupe"}


def write_car_site(data: Path, photos_by_group=None, size=(1500, 1000), meta=(), icc=None, files=("datsun-meet-b",),
                   lists=NISSAN_LISTS):
    write_site(data, lists)
    if photos_by_group is not None:
        (data / "car_photos.yml").write_text(yaml.safe_dump(photos_by_group, sort_keys=False), encoding="utf-8")
    for stem in files:
        save_jpeg(data / "photos" / "cars" / f"{stem}.jpg", size, meta, icc=icc)


class CarPhotoValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = temp_dir(self)
        self.data, self.out = self.tmp / "data", self.tmp / "site"

    def errors(self, photos_by_group, **kw) -> str:
        write_car_site(self.data, photos_by_group, **kw)
        return errors_for(self.data, self.out)

    def accepts(self, photos_by_group, **kw) -> None:
        write_car_site(self.data, photos_by_group, **kw)
        build.build(self.data, self.out)

    def test_a_key_that_is_not_a_group_is_refused(self):
        self.assertIn("car_photos.yml: Toyota", self.errors({"Toyota": [CAR_PHOTO]}))

    def test_a_member_of_a_group_is_not_a_key_and_the_message_names_the_group(self):
        msg = self.errors({"Datsun": [CAR_PHOTO]})
        self.assertIn("car_photos.yml: Datsun", msg)
        self.assertIn("Nissan group", msg)

    def test_a_group_without_a_page_is_refused(self):
        msg = self.errors({"Lotus": [{**CAR_PHOTO, "make": "Lotus"}]})
        self.assertIn("Lotus has no make page yet; it gets one at 2 entry lists", msg)

    def test_a_make_outside_the_group_is_refused(self):
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "make": "Lotus"}]})
        self.assertIn("car_photos.yml: Nissan", msg)
        self.assertIn("Lotus", msg)

    def test_a_second_photo_waits_for_change_2(self):
        msg = self.errors({"Nissan": [CAR_PHOTO, {**CAR_PHOTO, "file": "two"}]}, files=("datsun-meet-b", "two"))
        self.assertIn("one photo per group until Photos change 2 ships", msg)

    def test_an_unknown_field_is_refused(self):
        self.assertIn("unknown field 'colour'", self.errors({"Nissan": [{**CAR_PHOTO, "colour": "White"}]}))

    def test_a_missing_required_field_is_refused(self):
        entry = {k: v for k, v in CAR_PHOTO.items() if k != "alt_en"}
        self.assertIn("missing required field 'alt_en'", self.errors({"Nissan": [entry]}))

    def test_an_event_needs_its_year(self):
        self.assertIn("event and year", self.errors({"Nissan": [{**CAR_PHOTO, "event": "meet-b"}]}))

    def test_an_event_must_exist(self):
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "event": "meet-z", "year": 2026}]})
        self.assertIn("meet-z", msg)

    def test_an_editions_year_must_be_the_photos_year(self):
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "event": "meet-b", "year": 2025, "edition": "2026"}]})
        self.assertIn("edition 2026", msg)
        self.assertIn("2025", msg)

    def test_an_edition_must_be_one_of_the_events(self):
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "event": "meet-b", "year": 2026, "edition": "2026-autumn"}]})
        self.assertIn("2026-autumn", msg)

    def test_credit_licence_and_source_come_together(self):
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "credit": "Someone"}]})
        self.assertIn("credit, license and source_url", msg)

    def test_a_file_with_no_entry_is_refused(self):
        msg = self.errors({"Nissan": [CAR_PHOTO]}, files=("datsun-meet-b", "stray"))
        self.assertIn("photos/cars/stray.jpg", msg)

    def test_an_entry_with_no_file_is_refused(self):
        self.assertIn("photos/cars/datsun-meet-b.jpg", self.errors({"Nissan": [CAR_PHOTO]}, files=()))

    def test_a_file_name_may_join_slugs_with_underscores(self):
        # The car, the event, the year (owner, 2026-11-27).
        name = "datsun-fairlady_meet-b_2026"
        self.accepts({"Nissan": [{**CAR_PHOTO, "file": name}]}, files=(name,))

    def test_a_file_name_that_is_not_slugs_joined_by_underscores_is_refused(self):
        for name in ("Datsun_meet", "datsun__meet", "_datsun", "datsun_", "datsun_-meet", "datsun meet"):
            with self.subTest(name):
                shutil.rmtree(self.tmp)
                msg = self.errors({"Nissan": [{**CAR_PHOTO, "file": name}]}, files=())
                self.assertIn(f"file {name!r}", msg)

    def test_a_file_named_twice_is_refused(self):
        # A third Lotus list gives Lotus a page too.
        photos_by_group = {"Nissan": [CAR_PHOTO], "Lotus": [{**CAR_PHOTO, "make": "Lotus"}]}
        msg = self.errors(photos_by_group, lists=NISSAN_LISTS + (("meet-e", 2026, ["Lotus"]),))
        self.assertIn("datsun-meet-b is named twice", msg)

    def test_metadata_left_in_is_refused_as_for_an_event_photo(self):
        msg = self.errors({"Nissan": [CAR_PHOTO]}, meta=("exif",))
        self.assertIn("photos/cars/datsun-meet-b.jpg still carries EXIF", msg)
        self.assertIn("already public", msg)

    def test_square_and_portrait_are_refused_with_their_ratio(self):
        for size, ratio in (((1500, 1500), "1.00:1"), ((1500, 2000), "0.75:1")):
            with self.subTest(size):
                shutil.rmtree(self.tmp)
                msg = self.errors({"Nissan": [CAR_PHOTO]}, size=size)
                self.assertIn("photos/cars/datsun-meet-b.jpg", msg)
                self.assertIn(ratio, msg)

    def test_a_photo_too_narrow_is_refused(self):
        self.assertIn("1440", self.errors({"Nissan": [CAR_PHOTO]}, size=(1200, 900)))

    def test_a_panorama_too_narrow_after_its_crop_is_refused(self):
        # 3000x700 crops to 1400x700.
        self.assertIn("1440", self.errors({"Nissan": [CAR_PHOTO]}, size=(3000, 700)))

    def test_a_model_its_edition_list_spells_otherwise_is_refused_naming_the_lists_models(self):
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "model": "Fairlady", "alt_en": "A white Datsun Fairlady", "event": "meet-b", "year": 2026,
                                       "edition": "2026"}]})
        self.assertIn("Fairlady", msg)
        self.assertIn("Datsun models are Car", msg)

    def test_a_model_its_edition_list_spells_the_same_is_accepted(self):
        self.accepts({"Nissan": [{**CAR_PHOTO, "event": "meet-b", "year": 2026, "edition": "2026"}]})

    def test_an_edition_whose_list_lacks_the_make_does_not_bind_the_model(self):
        # meet-a 2025 has Nissans and a Lotus, no Datsun.
        self.accepts({"Nissan": [{**CAR_PHOTO, "model": "Fairlady", "alt_en": "A white Datsun Fairlady", "event": "meet-a", "year": 2025,
                                  "edition": "2025"}]})

    # meet-b 2024 has no edition file, as Coppa di Tokyo 2024 has none; its 2026 list holds 1970 Datsuns.
    def test_a_model_the_events_lists_spell_otherwise_for_that_make_and_year_is_refused(self):
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "model": "Fairlady", "car_year": 1970, "event": "meet-b",
                                       "year": 2024}]})
        self.assertIn("Datsun Fairlady (1970)", msg)
        self.assertIn("1970 Datsun models are Car", msg)

    def test_two_cars_of_one_make_and_year_at_an_event_are_both_accepted(self):
        # A second meet-b list with a 1970 Datsun of another model.
        for model in ("Car", "Fairlady"):
            with self.subTest(model):
                shutil.rmtree(self.tmp)
                write_instance(self.data, "meet-b", 2025, instance_yaml(
                    "meet-b", 2025, "2025-05-10", "2025-05-10",
                    extra='list_as_of: 2025-05-01\ncars:\n  - entry_no: "01"\n    year: 1970\n'
                          "    make: Datsun\n    model: Fairlady\n"))
                self.accepts({"Nissan": [{**CAR_PHOTO, "model": model, "alt_en": f"A white Datsun {model}", "car_year": 1970, "event": "meet-b",
                                          "year": 2024}]})

    def test_another_year_or_no_car_year_is_not_held_to_the_lists(self):
        for extra in ({"car_year": 1971}, {}):
            with self.subTest(extra):
                shutil.rmtree(self.tmp)
                self.accepts({"Nissan": [{**CAR_PHOTO, "model": "Fairlady", "alt_en": "A white Datsun Fairlady", "event": "meet-b", "year": 2024, **extra}]})

    def test_alt_text_must_name_the_car_as_the_caption_does(self):
        self.accepts({"Nissan": [{**CAR_PHOTO, "model": "Fairlady", "alt_en": "A white Datsun Fairlady Z"}]})
        shutil.rmtree(self.tmp)
        msg = self.errors({"Nissan": [{**CAR_PHOTO, "model": "Fairlady", "alt_en": "A white Datsun 240Z"}]})
        self.assertIn("alt_en", msg)
        self.assertIn("Datsun Fairlady", msg)

    def test_the_same_picture_as_an_event_photo_has_the_same_alt_text(self):
        source = "https://commons.wikimedia.org/wiki/File:Test.jpg"
        credit = {"credit": "Test Author", "license": "CC BY-SA 4.0", "source_url": source}
        write_car_site(self.data, {"Nissan": [{**CAR_PHOTO, **credit}]})
        write_event(self.data, "meet-b", name_en="Meet B", extra=(
            "photo:\n  alt_en: A white Datsun Car, an old spelling\n  year: 2024\n"
            f"  credit: Test Author\n  license: CC BY-SA 4.0\n  source_url: {source}\n"))
        write_photo(self.data, "meet-b")
        msg = errors_for(self.data, self.out)
        self.assertIn("events/meet-b.yml", msg)
        self.assertIn("A white Datsun Car coupe", msg)

    def test_no_file_means_no_photos_and_the_cars_folder_is_not_an_event_photo(self):
        self.accepts(None, files=())
        self.accepts({"Nissan": [CAR_PHOTO]})


class CarPhotoPageTests(unittest.TestCase):
    ENTRY = {**CAR_PHOTO, "car_year": 1970, "event": "meet-b", "year": 2026, "edition": "2026"}

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        write_car_site(cls.data, {"Nissan": [cls.ENTRY]}, icc=b"profile bytes")
        build.build(cls.data, cls.out)

    def page(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def caption(self, rel="cars/nissan/index.html") -> str:
        return " ".join(re.search(r"(?s)<figcaption>(.*?)</figcaption>", self.page(rel)).group(1).split())

    def test_the_photo_sits_between_the_heading_and_the_lede(self):
        self.assertRegex(self.page("cars/nissan/index.html"),
                         r'(?s)</h1>\s*<figure class="hero">.*?</figure>\s*<p>\d+ cars on')

    def test_the_image_keeps_its_shape_at_three_widths_in_both_formats(self):
        html = self.page("cars/nissan/index.html")
        assert_picture(self, html, "static/photos/cars/datsun-meet-b", 480)
        self.assertIn('alt="A white Datsun Car coupe"', re.search(r"<img [^>]+>", html).group(0))
        assert_files(self, self.out / "static/photos/cars", "datsun-meet-b", {720: 480, 1080: 720, 1440: 960})

    def test_written_files_carry_no_exif_and_keep_the_colour_profile(self):
        written = sorted((self.out / "static/photos/cars").iterdir())
        self.assertEqual(len(written), 7, "three widths in two formats, and the share image")
        for p in written:
            with Image.open(p) as im:
                self.assertEqual(dict(im.getexif()), {}, p.name)
                self.assertEqual(im.info.get("icc_profile"), b"profile bytes", p.name)

    def test_the_caption_links_the_edition(self):
        self.assertEqual(self.caption(), 'Photo: 1970 Datsun Car at <a href="../../events/meet-b/2026/">Meet B 2026</a>')

    def test_the_japanese_caption_marks_the_car_as_english(self):
        self.assertEqual(self.caption("ja/cars/nissan/index.html"),
                         '写真：1970年式 <span lang="en">Datsun Car</span>'
                         '（<a href="../../events/meet-b/2026/">テストイベント 2026年</a>開催時）')
        img = re.search(r"<img [^>]+>", self.page("ja/cars/nissan/index.html")).group(0)
        self.assertIn('lang="en"', img)

    # The way back from the edition to the make page, as a list (spec 4.12).
    def test_the_edition_page_lists_the_photo_as_a_bullet_linked_to_its_make_page(self):
        html = self.page("events/meet-b/2026/index.html")
        self.assertRegex(html, r'<h2>Car photos from this event</h2>\s*<ul>\s*'
                               r'<li>1970 <a href="\.\./\.\./\.\./cars/nissan/">Datsun Car</a></li>\s*</ul>')

    def test_the_japanese_edition_page_lists_it_too(self):
        html = self.page("ja/events/meet-b/2026/index.html")
        self.assertRegex(html, r'<h2>この開催時に撮影された車の写真</h2>\s*<ul>\s*'
                               r'<li>1970年式 <a href="\.\./\.\./\.\./cars/nissan/"><span lang="en">Datsun Car</span></a></li>')

    def test_the_list_is_not_a_section(self):
        html = self.page("events/meet-b/2026/index.html")
        self.assertNotIn('href="#car-photos"', html)
        self.assertNotIn("photo", re.search(r"<title>(.*?)</title>", html).group(1).lower())

    def test_an_own_photo_is_the_share_image_in_both_languages(self):
        for rel in ("cars/nissan/index.html", "ja/cars/nissan/index.html"):
            meta = HeadParser(self.page(rel)).meta
            self.assertTrue(meta["og:image"].startswith(
                f"{settings.SITE_URL}/static/photos/cars/datsun-meet-b-share.jpg?v="), rel)
            self.assertEqual(meta["og:image:alt"], "A white Datsun Car coupe", rel)
        with Image.open(self.out / "static/photos/cars/datsun-meet-b-share.jpg") as im:
            self.assertEqual(im.size, settings.SHARE_SIZE)

    def test_every_other_page_is_byte_identical_to_a_build_without_the_photo(self):
        bare = self.tmp / "bare"
        write_car_site(bare / "data", None, files=())
        build.build(bare / "data", bare / "site")
        pages = sorted(p.relative_to(bare / "site") for p in (bare / "site").rglob("*.html"))
        self.assertGreater(len(pages), 10)
        for rel in pages:
            # The make page shows the photo; the edition page lists it (spec 4.12).
            if rel.as_posix() in ("cars/nissan/index.html", "ja/cars/nissan/index.html",
                                  "events/meet-b/2026/index.html", "ja/events/meet-b/2026/index.html"):
                continue
            self.assertEqual((self.out / rel).read_bytes(), (bare / "site" / rel).read_bytes(), rel)


class EventPhotoCarTests(unittest.TestCase):
    """An event photo that is also a make page's photo names the car and links its page (spec 4.10)."""
    SOURCE = "https://commons.wikimedia.org/wiki/File:Test.jpg"
    CREDIT = (', by <a href="https://commons.wikimedia.org/wiki/File:Test.jpg">Test Author</a>, '
              '<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>')

    @classmethod
    def setUpClass(cls):
        cls.tmp = temp_dir(cls)
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        credit = {"credit": "Test Author", "license": "CC BY-SA 4.0", "source_url": cls.SOURCE}
        write_car_site(cls.data, {"Nissan": [{**CAR_PHOTO, "car_year": 1970, **credit}]})
        write_event(cls.data, "meet-b", name_en="Meet B", extra=(
            "photo:\n  alt_en: A white Datsun Car coupe\n  year: 2024\n"
            f"  credit: Test Author\n  license: CC BY-SA 4.0\n  source_url: {cls.SOURCE}\n"))
        write_photo(cls.data, "meet-b")
        build.build(cls.data, cls.out)

    def caption(self, rel: str) -> str:
        html = (self.out / rel).read_text(encoding="utf-8")
        return " ".join(re.search(r"(?s)<figcaption>(.*?)</figcaption>", html).group(1).split())

    def test_the_event_page_names_the_car_and_links_its_make_page(self):
        self.assertEqual(self.caption("events/meet-b/index.html"),
                         'Photo: 1970 <a href="../../cars/nissan/">Datsun Car</a> at the 2024 event' + self.CREDIT)

    def test_the_edition_page_does_the_same(self):
        self.assertEqual(self.caption("events/meet-b/2026/index.html"),
                         'Photo: 1970 <a href="../../../cars/nissan/">Datsun Car</a> at the 2024 event' + self.CREDIT)

    def test_the_japanese_page_links_the_japanese_make_page(self):
        self.assertEqual(self.caption("ja/events/meet-b/index.html"),
                         '写真：1970年式 <a href="../../cars/nissan/"><span lang="en">Datsun Car</span></a>'
                         '（2024年開催時）、撮影：<a href="https://commons.wikimedia.org/wiki/File:Test.jpg" lang="en">'
                         'Test Author</a>、<a href="https://creativecommons.org/licenses/by-sa/4.0/" lang="en">'
                         'CC BY-SA 4.0</a>')


class PhotoSightingTests(unittest.TestCase):
    """A make page's events table also holds the events its photos were taken at (spec 4.11, 4.12).
    meet-d's 2026 list has no Nissan-group car, so only the photo puts Meet D on the Nissan page."""

    def build_with(self, entry) -> Path:
        tmp = temp_dir(self)
        write_car_site(tmp / "data", {"Nissan": [entry]})
        build.build(tmp / "data", tmp / "site")
        return tmp / "site"

    def row(self, site: Path, lang="") -> str:
        html = (site / lang / "cars/nissan/index.html").read_text(encoding="utf-8")
        table = re.search(r'(?s)id="dated-events">.*?</table>', html).group(0)
        return next(tr for tr in re.findall(r"(?s)<tr>.*?</tr>", table) if "meet-d" in tr)

    def test_the_photos_event_gets_a_row_linked_to_its_edition(self):
        site = self.build_with({**CAR_PHOTO, "car_year": 1970, "event": "meet-d", "year": 2026, "edition": "2026"})
        row = self.row(site)
        self.assertIn('<a href="../../events/meet-d/">Meet D</a>', row)
        self.assertIn('<a href="../../events/meet-d/2026/">Photographed in 2026</a>', row)
        self.assertIn('data-start="2026-05-10"', row)
        self.assertIn('<a href="../../events/meet-d/2026/">2026年に撮影</a>', self.row(site, "ja"))

    def test_without_an_edition_the_row_links_the_event_page(self):
        site = self.build_with({**CAR_PHOTO, "car_year": 1970, "event": "meet-d", "year": 2024})
        row = self.row(site)
        self.assertIn('<a href="../../events/meet-d/">Photographed in 2024</a>', row)
        self.assertIn('data-start="2026-05-10"', row)

    def test_a_photo_counts_towards_no_list_or_total(self):
        site = self.build_with({**CAR_PHOTO, "car_year": 1970, "event": "meet-d", "year": 2026, "edition": "2026"})
        html = (site / "cars/nissan/index.html").read_text(encoding="utf-8")
        self.assertIn("6 cars on 3 entry lists", html)
        lists = re.search(r'(?s)<details class="all-cars">.*?</details>', html).group(0)
        self.assertNotIn("meet-d", lists)

    def test_an_event_with_a_list_keeps_the_lists_count(self):
        site = self.build_with({**CAR_PHOTO, "car_year": 1970, "event": "meet-b", "year": 2026, "edition": "2026"})
        html = (site / "cars/nissan/index.html").read_text(encoding="utf-8")
        self.assertIn(">3 in 2026</a>", html)
        self.assertNotIn("Photographed", html)

    def test_the_build_check_names_a_photo_whose_event_the_table_lacks(self):
        photos_by_group = {"Nissan": [{"data": {**CAR_PHOTO, "event": "meet-d", "year": 2026}}]}
        pages = [{"name": "Nissan", "events": [{"slug": "meet-b"}]}]
        msg = car_pages.unlisted_photo_events(pages, photos_by_group)
        self.assertEqual(len(msg), 1)
        self.assertIn("meet-d", msg[0])
        self.assertIn("datsun-meet-b", msg[0])
        pages[0]["events"].append({"slug": "meet-d"})
        self.assertEqual(car_pages.unlisted_photo_events(pages, photos_by_group), [])


class CarPhotoCaptionTests(unittest.TestCase):
    """One build per caption shape."""

    def caption(self, entry, lang="", **kw) -> str:
        tmp = temp_dir(self)
        write_car_site(tmp / "data", {"Nissan": [entry]}, **kw)
        build.build(tmp / "data", tmp / "site")
        html = (tmp / "site" / lang / "cars/nissan/index.html").read_text(encoding="utf-8")
        self.html, self.site = html, tmp / "site"
        return " ".join(re.search(r"(?s)<figcaption>(.*?)</figcaption>", html).group(1).split())

    def test_an_event_without_an_edition_links_the_event_page(self):
        self.assertEqual(self.caption({**CAR_PHOTO, "car_year": 1970, "event": "meet-b", "year": 2024}),
                         'Photo: 1970 Datsun Car at <a href="../../events/meet-b/">Meet B 2024</a>')
        # With no edition named, no edition page lists it.
        edition = self.html_at("events/meet-b/2026/index.html")
        self.assertNotIn("Car photos from this event", edition)

    def html_at(self, rel: str) -> str:
        return (self.site / rel).read_text(encoding="utf-8")

    def test_without_an_event_there_is_no_link(self):
        self.assertEqual(self.caption({**CAR_PHOTO, "car_year": 1970}), "Photo: 1970 Datsun Car")

    def test_without_a_car_year_the_year_is_left_out(self):
        self.assertEqual(self.caption(CAR_PHOTO), "Photo: Datsun Car")
        self.assertEqual(self.caption(CAR_PHOTO, lang="ja"), '写真：<span lang="en">Datsun Car</span>')

    def test_someone_elses_photo_carries_credit_and_licence_only(self):
        credited = {**CAR_PHOTO, "credit": "Test Author", "license": "CC BY-SA 4.0",
                    "source_url": "https://commons.wikimedia.org/wiki/File:Test.jpg"}
        self.assertTrue(self.caption(credited, lang="ja").endswith("CC BY-SA 4.0</a>"))
        cap = self.caption(credited)
        self.assertEqual(cap, 'Photo: Datsun Car, by <a href="https://commons.wikimedia.org/wiki/File:Test.jpg">'
                              'Test Author</a>, <a href="https://creativecommons.org/licenses/by-sa/4.0/">'
                              'CC BY-SA 4.0</a>')
        # A link preview has no room for the credit.
        self.assertIn("static/cards/site.png", HeadParser(self.html).meta["og:image"])

    def test_a_panorama_is_cropped_to_two_to_one(self):
        tmp = temp_dir(self)
        write_car_site(tmp / "data", {"Nissan": [CAR_PHOTO]}, size=(3000, 1000))
        build.build(tmp / "data", tmp / "site")
        assert_files(self, tmp / "site/static/photos/cars", "datsun-meet-b", {720: 360, 1080: 540, 1440: 720})

    def test_pending_lists_a_make_page_photo_still_carrying_metadata(self):
        tmp = temp_dir(self)
        save_jpeg(tmp / "photos" / "cars" / "dirty.jpg", meta=("xmp",))
        self.assertEqual(photos.photos_with_metadata(tmp),
                         ["photos/cars/dirty.jpg carries XMP: run it through tools/photo.py"])


if __name__ == "__main__":
    unittest.main()
