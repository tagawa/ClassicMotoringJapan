"""Event and make-page photos: the metadata check, the crops, and the files the pages use."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, IptcImagePlugin

from settings import SHARE_SIZE

# Photos (spec 4.10): data/photos/<slug>.jpg, one per event, faces already blurred.
PHOTOS_DIR = "photos"
# Each written as JPEG and WebP. 1080 is for 3x phones, which need 1074px on a 390px screen
# and would otherwise take the 1440 (spec 4.10).
PHOTO_WIDTHS = (720, 1080, 1440)
PHOTO_MIN_WIDTH = PHOTO_WIDTHS[-1]
PHOTO_QUALITY = 80
# Make-page photos (spec 4.12) keep their own shape, between these two ratios; a wider one is
# cropped to the widest, since a panorama shows a car as a strip.
CAR_PHOTOS_DIR = "photos/cars"
CAR_RATIO_MIN = (4, 3)
CAR_RATIO_MAX = (2, 1)
# Licences that allow cropping and need no more than a credit. ND forbids the crop; NC is
# left out so the question of what counts as commercial never has to be answered.
PHOTO_LICENSES = {
    "CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/",
    "CC BY 3.0": "https://creativecommons.org/licenses/by/3.0/",
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY-SA 2.0": "https://creativecommons.org/licenses/by-sa/2.0/",
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
}


def _open_photo(path: Path) -> Image.Image:
    """The photo as RGB, keeping only its colour profile. tools/photo.py has already turned it."""
    with Image.open(path) as raw:
        icc = raw.info.get("icc_profile")
        img = raw.convert("RGB")
    img.info = {"icc_profile": icc} if icc else {}
    return img


def photo_metadata(path: Path) -> list[str]:
    """The kinds of metadata a JPEG still carries: EXIF, XMP, IPTC, comment, in that order.

    Each can hold the GPS position, the camera's serial number or the photographer's name;
    a comment is plain text, which some cameras and editors fill with a name or a place.
    tools/photo.py removes them all, and tools/pending.py and the build both call this.
    """
    with Image.open(path) as img:
        found = []
        if img.info.get("exif") or len(img.getexif()):
            found.append("EXIF")
        if img.info.get("xmp") or "XML:com.adobe.xmp" in img.info:
            found.append("XMP")
        if img.info.get("photoshop") or IptcImagePlugin.getiptcinfo(img):
            found.append("IPTC")
        if img.info.get("comment"):
            found.append("comment")
    return found


def photos_with_metadata(data_dir: Path) -> list[str]:
    """One line per photo in data/photos/ still carrying metadata, for tools/pending.py."""
    return [f"{p.relative_to(data_dir).as_posix()} carries {', '.join(kinds)}: run it through tools/photo.py"
            for p in sorted((data_dir / PHOTOS_DIR).rglob("*.jpg")) if (kinds := photo_metadata(p))]


def _crop(img: Image.Image, ratio_w: int, ratio_h: int) -> Image.Image:
    """The largest centred crop of img in the ratio ratio_w:ratio_h."""
    w, h = img.size
    if w * ratio_h > h * ratio_w:
        nw = h * ratio_w // ratio_h
        left = (w - nw) // 2
        return img.crop((left, 0, left + nw, h))
    nh = w * ratio_h // ratio_w
    top = (h - nh) // 2
    return img.crop((0, top, w, top + nh))


# Saved without exif=, so nothing the camera wrote (GPS included) reaches the site. The colour
# profile stays: it holds no personal data, and a phone's Display P3 shot would otherwise come
# out duller.
def _save_jpeg(img: Image.Image, path: Path, icc: bytes | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = {"icc_profile": icc} if icc else {}
    img.save(path, "JPEG", quality=PHOTO_QUALITY, optimize=True, progressive=True, **extra)


def _save_webp(img: Image.Image, path: Path, icc: bytes | None) -> None:
    # Method 6 saved about 5% more but took 2.4 times as long, paid on every build and test run.
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = {"icc_profile": icc} if icc else {}
    img.save(path, "WEBP", quality=PHOTO_QUALITY, method=4, **extra)


def _sources(stem: str, height: int) -> dict:
    """The hero's files, relative to the site root: the JPEG img and the WebP source."""
    return {"src": f"{stem}-{PHOTO_WIDTHS[0]}.jpg",
            "srcset": [(f"{stem}-{w}.jpg", w) for w in PHOTO_WIDTHS],
            "webp_srcset": [(f"{stem}-{w}.webp", w) for w in PHOTO_WIDTHS],
            "width": PHOTO_WIDTHS[0], "height": height}


def _write_widths(img: Image.Image, out_dir: Path, stem: str, icc: bytes | None) -> None:
    for w in PHOTO_WIDTHS:
        sized = img.resize((w, round(w * img.height / img.width)), Image.LANCZOS)
        _save_jpeg(sized, out_dir / f"{stem}-{w}.jpg", icc)
        _save_webp(sized, out_dir / f"{stem}-{w}.webp", icc)


def _write_share(img: Image.Image, path: Path, icc: bytes | None) -> None:
    _save_jpeg(_crop(img, *SHARE_SIZE).resize(SHARE_SIZE, Image.LANCZOS), path, icc)


def _credit(ph: dict) -> dict:
    return {"credit": ph.get("credit"), "license": ph.get("license"),
            "license_url": PHOTO_LICENSES.get(ph.get("license")), "source_url": ph.get("source_url")}


def _linked_cars(car_photos: dict, make_pages: dict):
    """Each make-page photo with the car as its caption names it and the make page it is on."""
    for item in (item for items in car_photos.values() for item in items):
        ph = item["data"]
        if ph["make"] in make_pages:
            yield ph, {"car_year": ph.get("car_year"), "car": f"{ph['make']} {ph['model']}",
                       "path": make_pages[ph["make"]]}


def photo_car(ev: dict, car_photos: dict, make_pages: dict) -> dict | None:
    """The car in an event's photo, when the same picture is a make page's (spec 4.10)."""
    source = (ev.get("photo") or {}).get("source_url")
    return next((car for ph, car in _linked_cars(car_photos, make_pages)
                 if source and ph.get("source_url") == source), None)


def edition_cars(car_photos: dict, make_pages: dict) -> dict:
    """The make-page photos taken at each edition, keyed (event, edition), for its page's list (spec 4.12)."""
    found = {}
    for ph, car in _linked_cars(car_photos, make_pages):
        if ph.get("edition"):
            found.setdefault((ph["event"], ph["edition"]), []).append(
                ((ph["make"], ph["model"], ph.get("car_year") or 0), car))
    return {key: [car for _, car in sorted(pairs, key=lambda p: p[0])] for key, pairs in found.items()}


def photo_info(ev: dict, car: dict | None = None) -> dict | None:
    """What the templates need for an event's photo. Paths are relative to the site root."""
    ph = ev.get("photo")
    if not ph:
        return None
    slug, own = ev["slug"], "credit" not in ph
    return {"alt": ph["alt_en"], "year": ph["year"], "own": own, "stem": f"static/photos/{slug}", "car": car,
            **_sources(f"static/photos/{slug}", PHOTO_WIDTHS[0] // 2), **_credit(ph),
            # A link preview has no room for the credit a licence asks for, so only the
            # site's own photos are ever shared that way.
            "share": f"static/photos/{slug}-share.jpg" if own else None}


def car_photo_size(w: int, h: int) -> tuple[int, int]:
    """A make-page photo's size once anything wider than CAR_RATIO_MAX is cropped to it."""
    rw, rh = CAR_RATIO_MAX
    return (h * rw // rh, h) if w * rh > h * rw else (w, h)


def car_photo_problem(w: int, h: int) -> str | None:
    """Why a make-page photo of w x h cannot be used, or None. The build and tools/photo.py both ask."""
    rw, rh = CAR_RATIO_MIN
    if w * rh < h * rw:
        return (f"{w}x{h} is {w / h:.2f}:1. Make-page photos are landscape, from {rw}:{rh} "
                f"({rw / rh:.2f}:1) to {CAR_RATIO_MAX[0]}:{CAR_RATIO_MAX[1]}")
    cw, ch = car_photo_size(w, h)
    if cw < PHOTO_MIN_WIDTH:
        cropped = f", {cw}x{ch} once cropped to 2:1," if (cw, ch) != (w, h) else ""
        return (f"{w}x{h}{cropped} is too small. It needs at least {PHOTO_MIN_WIDTH} wide, "
                f"so the page stays sharp on a high-density screen")
    return None


def car_photo_info(item: dict, rows: list[dict], events: dict) -> dict:
    """What a make page needs for its photo; rows are in the page's language, for the caption's link."""
    ph, (w, h) = item["data"], car_photo_size(*item["size"])
    stem, own = f"static/photos/cars/{ph['file']}", "credit" not in ph
    row = next((r for r in rows if r["slug"] == ph.get("event") and r["id"] == ph.get("edition")
                and r["has_page"]), None)
    return {"alt": ph["alt_en"], "own": own, "stem": stem,
            **_sources(stem, round(PHOTO_WIDTHS[0] * h / w)), **_credit(ph),
            "share": f"{stem}-share.jpg" if own else None,
            "car_year": ph.get("car_year"), "car": f"{ph['make']} {ph['model']}",
            "ev": events.get(ph.get("event")), "year": ph.get("year"), "row": row}


def write_car_photo(item: dict, data_dir: Path, out_dir: Path) -> None:
    info = car_photo_info(item, [], {})
    img = _open_photo(data_dir / CAR_PHOTOS_DIR / f"{item['data']['file']}.jpg")
    icc = img.info.get("icc_profile")
    shown = _crop(img, *CAR_RATIO_MAX) if car_photo_size(*img.size) != img.size else img
    _write_widths(shown, out_dir, info["stem"], icc)
    if info["share"]:
        _write_share(img, out_dir / info["share"], icc)


def write_photo(ev: dict, data_dir: Path, out_dir: Path) -> None:
    info = photo_info(ev)
    img = _open_photo(data_dir / PHOTOS_DIR / f"{ev['slug']}.jpg")
    icc = img.info.get("icc_profile")
    _write_widths(_crop(img, 2, 1), out_dir, info["stem"], icc)
    if info["share"]:
        _write_share(img, out_dir / info["share"], icc)
