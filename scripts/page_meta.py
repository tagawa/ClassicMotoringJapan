"""What search engines and link previews read: meta descriptions and JSON-LD."""
from __future__ import annotations

import json
import re

from markupsafe import Markup

from formatting import prose_text
from settings import SITE_NAME, SITE_URL


# Structured data

def build_jsonld(r: dict) -> Markup:
    ev, ed = r["ev"], r["ed"]
    address = {"@type": "PostalAddress", "addressRegion": r["prefecture"], "addressCountry": "JP"}
    street = ed.get("street_address") or ev.get("street_address")
    if street:
        address["streetAddress"] = street
    place = {"@type": "Place", "name": r["venue"], "address": address}
    if r["pin"]:
        place["geo"] = {"@type": "GeoCoordinates",
                        "latitude": r["pin"]["lat"], "longitude": r["pin"]["lon"]}
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": r["full_name"],
        "startDate": r["start_dt"].isoformat() if r["is_timed"] else ed["start"].isoformat(),
        "endDate": r["end_dt"].isoformat() if r["is_timed"] else ed["end"].isoformat(),
        "eventStatus": "https://schema.org/EventCancelled" if ed["status"] == "cancelled"
                       else "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": place,
        "url": r["abs_url"],
    }
    # An unannounced admission is not a free one, and false would be a claim of its own.
    if ev["spectator_fee_jpy"] is not None:
        data["isAccessibleForFree"] = ev["spectator_fee_jpy"] == 0
        # No offer url: Google means a ticket page by it, and the data has none.
        data["offers"] = {"@type": "Offer", "price": ev["spectator_fee_jpy"], "priceCurrency": "JPY"}
    if ev.get("summary_en"):
        data["description"] = prose_text(ev["summary_en"]).strip()
    if ev.get("organizer"):
        # No url: official_url is often a tourism listing or a blog post, not the organiser's site.
        data["organizer"] = {"@type": "Organization", "name": ev["organizer"]}
    return jsonld_markup(data)


def jsonld_markup(data: dict) -> Markup:
    # "</" would close the script element early, whatever the JSON around it says.
    return Markup(json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/"))


def build_website_jsonld() -> Markup:
    """Where Google takes the site name shown in its results from. Home page only."""
    return jsonld_markup({"@context": "https://schema.org", "@type": "WebSite",
                          "name": SITE_NAME, "url": f"{SITE_URL}/"})


def build_breadcrumbs(r: dict) -> Markup:
    """The edition page's trail. The last entry is the page itself, so it carries no link."""
    items = [("Home", f"{SITE_URL}/"),
             (r["ev"]["name_en"], f"{SITE_URL}/events/{r['slug']}/"),
             (r["label"], None)]
    return jsonld_markup({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": n, "name": name, **({"item": url} if url else {})}
                            for n, (name, url) in enumerate(items, 1)],
    })


# Descriptions: what a search snippet or a shared link says before the page is opened

SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def event_description(ev: dict) -> str:
    """The summary's first sentence, since a snippet shows about 155 characters."""
    if ev.get("summary_en"):
        return SENTENCE_END_RE.split(" ".join(prose_text(ev["summary_en"]).split()), 1)[0]
    return f"Dates, venue and admission for {ev['name_en']} in {ev['prefecture']}."


def edition_description(r: dict) -> str:
    """Status first, so a cancelled edition's snippet cannot read like a normal listing."""
    status = {"cancelled": "Cancelled. ", "tentative": "Dates not confirmed. "}.get(r["ed"]["status"], "")
    return f"{status}{r['parts_phrase']} for {r['full_name']}: {r['when']}, {r['venue']}, {r['prefecture']}."


def list_phrase(parts: list[str]) -> str:
    """["Route", "Entry list", "Videos"] -> "Route, entry list and videos"."""
    return " and ".join(filter(None, [", ".join(parts[:-1]), *parts[-1:]])).lower().capitalize()


def event_notes_phrase(ev: dict) -> str | None:
    """The event page's notes, named for the edition page's link to them. None if it has none."""
    kinds = [kind for kind, present in (
        ("access", ev.get("nearest_station") or ev.get("access_notes_en")),
        ("spectator", ev.get("spectator_notes_en")),
        ("photography", ev.get("photography_notes_en"))) if present]
    return f"{list_phrase(kinds)} notes" if kinds else None
