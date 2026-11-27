"""Site identity, paths, and the prefecture and country tables more than one module reads."""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

SITE_NAME = "Classic Motoring Japan"
SITE_URL = "https://classicmotoringjapan.com"
# Also the search snippet, the share text and the llms.txt summary, so it has to say
# what the site covers without the home page's heading above it.
SITE_LEDE = ("Events across Japan for classic cars, Japanese and imported: when and where to watch, "
             "how to get there, and what you'll see.")
ABOUT_DESCRIPTION = ("How Classic Motoring Japan's event listings are translated from, and checked "
                     "against, each organiser's own announcements.")
ISSUES_URL = "https://github.com/tagawa/ClassicMotoringJapan/issues"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@ClassicMotoringJapan"
# Crawling is allowed; training on the text is not. Declared where a crawler already looks.
CONTENT_SIGNAL = "search=yes, ai-input=yes, ai-train=no"
# The same three preferences in the IETF AIPREF vocabulary (draft-ietf-aipref-vocab), for
# crawlers that read that working group's Content-Usage rule rather than Cloudflare's.
CONTENT_USAGE = "search=y, ai-use=y, train-ai=n"
# ARD renamed its manifest; the old path is still what scanners and older consumers read.
ARD_PATH = ".well-known/ard.json"
ARD_PREDECESSOR_PATH = ".well-known/ai-catalog.json"
UID_DOMAIN = "classicmotoringjapan.com"
# Public by design: search engines fetch /<key>.txt to confirm a ping came from this site.
# Changing it only means the next deploy resubmits every page (see scripts/indexnow.py).
INDEXNOW_KEY = "f257bb565b29833c5531031252154d80"
# Thunderbird has never read X-WR-CALNAME (bugzilla 168176, open since 2002): it names a
# subscribed calendar after the last path segment, so the file name has to read as a name.
FEED_FILE = "classic-car-events.ics"

ROOT = Path(__file__).resolve().parent.parent
JST = dt.timezone(dt.timedelta(hours=9))

# The privacy-enhanced domain: YouTube sets no cookies until the visitor presses play.
VIDEO_EMBED_URL = "https://www.youtube-nocookie.com/embed/"
VIDEO_WATCH_URL = "https://www.youtube.com/watch?v="

# Share cards (spec 8.3): what a link preview shows.
SHARE_SIZE = (1200, 630)
# A make group needs lists from this many editions for a page (spec 5, /cars/<group>/);
# a smaller one has a line on /cars/. Here so validate.py can name it without importing car_pages.
PAGE_MIN_EDITIONS = 3


def _stripes(colours, across: bool) -> str:
    """Equal bands on the 30 by 20 field every flag is drawn on."""
    size = (30 if across else 20) / len(colours)
    return "".join(
        f'<path fill="{c}" d="M{round(i * size, 2)} 0h{round(size, 2)}v20h-{round(size, 2)}z"/>' if across
        else f'<path fill="{c}" d="M0 {round(i * size, 2)}h30v{round(size, 2)}H0z"/>'
        for i, c in enumerate(colours))



def _star(cx: float, cy: float, r: float) -> str:
    """A five-pointed star, point up, as one path."""
    points = []
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.382
        angle = math.pi / 2 + i * math.pi / 5
        points.append(f"{round(cx + radius * math.cos(angle), 2)} {round(cy - radius * math.sin(angle), 2)}")
    return f'<path fill="#FFDE00" d="M{"L".join(points)}z"/>'


# The /ja/ page's lede and meta description, the same sentence, as on the home page.
JA_LEDE = "日本各地で開かれる、国産車・輸入車のクラシックカーイベントの日程、会場、入場料です。"

# The /ja/ page's prefecture names, keyed by the romanised form the data uses (no macrons).
# Validation rejects any other value, so a typo or a first event in a new prefecture
# fails the build here rather than printing nothing on that page.
PREFECTURES_JA = {
    "Hokkaido": "北海道", "Aomori": "青森県", "Iwate": "岩手県", "Miyagi": "宮城県",
    "Akita": "秋田県", "Yamagata": "山形県", "Fukushima": "福島県", "Ibaraki": "茨城県",
    "Tochigi": "栃木県", "Gunma": "群馬県", "Saitama": "埼玉県", "Chiba": "千葉県",
    "Tokyo": "東京都", "Kanagawa": "神奈川県", "Niigata": "新潟県", "Toyama": "富山県",
    "Ishikawa": "石川県", "Fukui": "福井県", "Yamanashi": "山梨県", "Nagano": "長野県",
    "Gifu": "岐阜県", "Shizuoka": "静岡県", "Aichi": "愛知県", "Mie": "三重県",
    "Shiga": "滋賀県", "Kyoto": "京都府", "Osaka": "大阪府", "Hyogo": "兵庫県",
    "Nara": "奈良県", "Wakayama": "和歌山県", "Tottori": "鳥取県", "Shimane": "島根県",
    "Okayama": "岡山県", "Hiroshima": "広島県", "Yamaguchi": "山口県", "Tokushima": "徳島県",
    "Kagawa": "香川県", "Ehime": "愛媛県", "Kochi": "高知県", "Fukuoka": "福岡県",
    "Saga": "佐賀県", "Nagasaki": "長崎県", "Kumamoto": "熊本県", "Oita": "大分県",
    "Miyazaki": "宮崎県", "Kagoshima": "鹿児島県", "Okinawa": "沖縄県",
}

# Where an organiser's list says a car was built: ISO 3166 code, the name read out in place
# of the flag, and the flag itself. Drawn here, not fetched, so the site still ships no image
# files and needs no emoji font, which Windows lacks for flags. Colours are each country's own.
# Any id inside a drawing starts "flag-" and is its alone, since one page can carry them all.
COUNTRIES = {
    "BR": ("Brazil", '<path fill="#009739" d="M0 0h30v20H0z"/><path fill="#FEDD00" d="M15 2l12.5 8L15 18 2.5 10z"/>'
           '<circle fill="#012169" cx="15" cy="10" r="4.5"/>'),
    # The small stars are drawn upright rather than turned to face the large one: at flag size
    # the turn cannot be seen.
    "CN": ("China", '<path fill="#EE1C25" d="M0 0h30v20H0z"/>' + _star(5, 5, 3)
           + "".join(_star(x, y, 1) for x, y in ((10, 2), (12, 4), (12, 7), (10, 9)))),
    "DE": ("Germany", _stripes(("#000000", "#DD0000", "#FFCC00"), across=False)),
    "FR": ("France", _stripes(("#000091", "#FFFFFF", "#E1000F"), across=True)),
    # The red saltire is counterchanged, which the clip path does: each arm shows on one side
    # of its diagonal only. Widths are the flag's own, scaled from a height of 30 to 20.
    "GB": ("Britain",
           '<clipPath id="flag-gb-arms"><path d="M15 10h15v10zv10H0zH0V0zV0h15z"/></clipPath>'
           '<path fill="#012169" d="M0 0h30v20H0z"/>'
           '<path stroke="#FFFFFF" stroke-width="4" d="M0 0l30 20M30 0L0 20"/>'
           '<path stroke="#C8102E" stroke-width="2.67" clip-path="url(#flag-gb-arms)" d="M0 0l30 20M30 0L0 20"/>'
           '<path stroke="#FFFFFF" stroke-width="6.67" d="M15 0v20M0 10h30"/>'
           '<path stroke="#C8102E" stroke-width="4" d="M15 0v20M0 10h30"/>'),
    "IT": ("Italy", _stripes(("#009246", "#FFFFFF", "#CE2B37"), across=True)),
    "JP": ("Japan", '<path fill="#FFFFFF" d="M0 0h30v20H0z"/><circle fill="#BC002D" cx="15" cy="10" r="6"/>'),
    "SE": ("Sweden", '<path fill="#006AA7" d="M0 0h30v20H0z"/><path fill="#FECC02" d="M9.38 0h3.75v20H9.38zM0 8h30v4H0z"/>'),
    # Fifty stars do not survive at this size, so the canton carries a grid of dots.
    "US": ("USA",
           _stripes(("#B22234", "#FFFFFF") * 6 + ("#B22234",), across=False)
           + '<path fill="#3C3B6E" d="M0 0h12v10.77H0z"/>'
           + "".join(f'<circle fill="#FFFFFF" cx="{1.5 + 2.25 * col}" cy="{1.6 + 2.5 * row}" r="0.5"/>'
                     for row in range(4) for col in range(5))),
}
