"""Event photos and share cards (spec 4.11 and 8.3). Run: python -m unittest discover -s tests -v"""
import hashlib
import re
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build  # noqa: E402
from test_build import (HeadParser, instance_yaml, make_fixture, write_event,  # noqa: E402
                        write_instance, CARS)

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


def share_path(out: Path, url: str) -> Path:
    return out / url.removeprefix(f"{build.SITE_URL}/").split("?")[0]


def errors_for(data: Path, out: Path) -> str:
    with unittest.TestCase().assertRaises(build.BuildError) as caught:
        build.build(data, out)
    return "\n".join(caught.exception.errors)


class PhotoValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data, self.out = self.tmp / "data", self.tmp / "site"

    def tearDown(self):
        shutil.rmtree(self.tmp)

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
        self.assertEqual(build.photos_with_metadata(self.data),
                         ["photos/dirty.jpg carries XMP: run it through tools/photo.py"])
        self.assertEqual(build.photos_with_metadata(self.tmp / "empty"), [])

    def test_the_metadata_check_names_each_kind_and_passes_a_clean_file(self):
        p = self.tmp / "x.jpg"
        save_jpeg(p, meta=("exif", "xmp", "iptc", "comment"))
        self.assertEqual(build.photo_metadata(p), ["EXIF", "XMP", "IPTC", "comment"])
        save_jpeg(p, icc=b"not checked")
        self.assertEqual(build.photo_metadata(p), [])


class PhotoOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        write_event(cls.data, "own", name_en="Own Meet", extra=OWN_PHOTO)
        write_photo(cls.data, "own")
        write_instance(cls.data, "own", 2026, instance_yaml("own", 2026, "2026-10-18", "2026-10-18", extra=CARS))
        write_event(cls.data, "commons", name_en="Commons Meet", extra=CC_PHOTO)
        write_photo(cls.data, "commons", size=(2000, 1500))
        write_event(cls.data, "bare", name_en="Bare Meet")
        build.build(cls.data, cls.out)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def page(self, rel: str) -> str:
        return (self.out / rel).read_text(encoding="utf-8")

    def test_each_photo_is_written_at_both_widths_in_two_to_one(self):
        for slug in ("own", "commons"):
            for w in build.PHOTO_WIDTHS:
                with Image.open(self.out / f"static/photos/{slug}-{w}.jpg") as img:
                    self.assertEqual(img.size, (w, w // 2))

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

    def test_the_image_has_size_alt_and_both_widths(self):
        img = re.search(r"<img [^>]+>", self.page("events/own/index.html")).group(0)
        self.assertIn('alt="A red coupe on the start line"', img)
        self.assertIn('width="720" height="360"', img)
        self.assertIn("static/photos/own-720.jpg 720w", img)
        self.assertIn("static/photos/own-1440.jpg 1440w", img)
        self.assertNotIn('loading="lazy"', img, "it is the first thing on the page")

    def test_an_own_photo_names_its_edition_and_no_one(self):
        cap = re.search(r"(?s)<figcaption>(.*?)</figcaption>", self.page("events/own/index.html")).group(1)
        self.assertEqual(" ".join(cap.split()), "Photo: 2025 edition")

    def test_someone_elses_photo_carries_credit_source_licence_and_the_change(self):
        cap = re.search(r"(?s)<figcaption>(.*?)</figcaption>", self.page("events/commons/index.html")).group(1)
        self.assertIn('<a href="https://commons.wikimedia.org/wiki/File:Test.jpg">Test Author</a>', cap)
        self.assertIn('<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>', cap)
        self.assertIn("edited", cap)
        self.assertIn("2024 edition", cap)

    def test_the_same_photo_gives_the_same_bytes(self):
        again = self.tmp / "again"
        build.build(self.data, again)
        for p in sorted((self.out / "static/photos").iterdir()):
            self.assertEqual(p.read_bytes(), (again / "static/photos" / p.name).read_bytes(), p.name)

    def test_a_page_without_a_photo_has_no_figure(self):
        self.assertNotIn('class="hero"', self.page("events/bare/index.html"))

    def test_an_own_photo_is_the_share_image(self):
        meta = HeadParser(self.page("events/own/index.html")).meta
        self.assertTrue(meta["og:image"].startswith(f"{build.SITE_URL}/static/photos/own-share.jpg?v="))
        with Image.open(self.out / "static/photos/own-share.jpg") as img:
            self.assertEqual(img.size, build.SHARE_SIZE)
        self.assertEqual(meta["og:image:alt"], "A red coupe on the start line")

    def test_someone_elses_photo_is_never_the_share_image(self):
        # A link preview has no room for the credit the licence asks for.
        meta = HeadParser(self.page("events/commons/index.html")).meta
        self.assertTrue(meta["og:image"].startswith(f"{build.SITE_URL}/static/cards/events/commons.png?v="))
        self.assertFalse((self.out / "static/photos/commons-share.jpg").exists())


class ShareCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.data, cls.out = cls.tmp / "data", cls.tmp / "site"
        make_fixture(cls.data)
        build.build(cls.data, cls.out)
        cls.pages = {p.relative_to(cls.out).as_posix(): p.read_text(encoding="utf-8")
                     for p in cls.out.rglob("*.html") if p.name != "404.html"}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_every_page_has_a_share_image_that_exists(self):
        for rel, html in self.pages.items():
            meta = HeadParser(html).meta
            url = meta.get("og:image", "")
            self.assertTrue(url.startswith(f"{build.SITE_URL}/static/"), rel)
            path = share_path(self.out, url)
            with Image.open(path) as img:
                self.assertEqual(img.size, build.SHARE_SIZE, rel)
                self.assertEqual((meta["og:image:width"], meta["og:image:height"]),
                                 tuple(str(n) for n in build.SHARE_SIZE), rel)
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
        tmp = Path(tempfile.mkdtemp())
        try:
            write_event(tmp / "data", "long", name_en=" ".join(["Extraordinarily"] * 12))
            self.assertIn("events/long.yml", errors_for(tmp / "data", tmp / "site"))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
