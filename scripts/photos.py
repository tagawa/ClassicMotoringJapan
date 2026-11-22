"""Event photos: the metadata check, the crops, and the files the pages use."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, IptcImagePlugin

from settings import SHARE_SIZE

# Photos (spec 4.10): data/photos/<slug>.jpg, one per event, faces already blurred.
PHOTOS_DIR = "photos"
# Two to one, so a phone still shows the facts under the photo on the first screen.
PHOTO_WIDTHS = (720, 1440)
PHOTO_MIN_WIDTH = PHOTO_WIDTHS[-1]
PHOTO_QUALITY = 80
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
            for p in sorted((data_dir / PHOTOS_DIR).glob("*.jpg")) if (kinds := photo_metadata(p))]


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


def _save_jpeg(img: Image.Image, size: tuple[int, int], path: Path, icc: bytes | None) -> None:
    # Saved without exif=, so nothing the camera wrote (GPS included) reaches the site. The
    # colour profile stays: it holds no personal data, and a phone's Display P3 shot would
    # otherwise come out duller.
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = {"icc_profile": icc} if icc else {}
    img.resize(size, Image.LANCZOS).save(path, "JPEG", quality=PHOTO_QUALITY, optimize=True,
                                         progressive=True, **extra)


def photo_info(ev: dict) -> dict | None:
    """What the templates need for an event's photo. Paths are relative to the site root."""
    ph = ev.get("photo")
    if not ph:
        return None
    slug, own = ev["slug"], "credit" not in ph
    return {"alt": ph["alt_en"], "year": ph["year"], "own": own,
            "src": f"static/photos/{slug}-{PHOTO_WIDTHS[0]}.jpg",
            "srcset": [(f"static/photos/{slug}-{w}.jpg", w) for w in PHOTO_WIDTHS],
            "width": PHOTO_WIDTHS[0], "height": PHOTO_WIDTHS[0] // 2,
            "credit": ph.get("credit"), "license": ph.get("license"),
            "license_url": PHOTO_LICENSES.get(ph.get("license")), "source_url": ph.get("source_url"),
            # A link preview has no room for the credit a licence asks for, so only the
            # site's own photos are ever shared that way.
            "share": f"static/photos/{slug}-share.jpg" if own else None}


def write_photo(ev: dict, data_dir: Path, out_dir: Path) -> None:
    info = photo_info(ev)
    img = _open_photo(data_dir / PHOTOS_DIR / f"{ev['slug']}.jpg")
    icc = img.info.get("icc_profile")
    hero = _crop(img, 2, 1)
    for src, w in info["srcset"]:
        _save_jpeg(hero, (w, w // 2), out_dir / src, icc)
    if info["share"]:
        _save_jpeg(_crop(img, *SHARE_SIZE), SHARE_SIZE, out_dir / info["share"], icc)
