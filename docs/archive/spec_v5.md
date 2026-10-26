# Classic Motoring Japan: Specification v5

Changes from v4: hosting is back to GitHub Pages and GitHub Actions, with files uploaded through github.com (no local git). Events can run more than once a year: each run is an edition with its own file.

**Authority:** this spec states intent and rules. For exact formats, `scripts/build.py` and `tests/` win.

## 1. Purpose

English-language guide to classic car events in Japan, for non-Japanese speakers who want to attend or photograph them.

**Problem:** Japanese events publish in Japanese only, assuming local knowledge. A visitor can't find out when an event runs, where to stand, whether it's free, how to get there without a car, or what cars will appear.

**Edge:** the author reads Japanese and checks every fact against the organizer's own sources, attending where possible. Verified, not scraped and machine-translated.

**Epicenter:** the evergreen event page. When, where to stand, how to get there, whether it's free, with a verified date.

**Non-goals:** not a car database, forum, or marketplace. Not comprehensive.

## 2. Users

| User | Need | Key page |
|---|---|---|
| Visitor planning a trip | Which events fall in my dates | Home (calendar), calendar feed |
| Resident enthusiast, non-JP speaker | What's on, how to get there | Evergreen event page |
| Photographer | Where to stand, what cars, what's allowed | Edition page, etiquette guide |

## 3. Scope, year 1

Classic car events anywhere in Japan that are of interest to an English-speaking reader, whether visiting from overseas or living here, and whether or not the author attends. Traffic from overseas arrived within weeks of launch, so geography and first-hand contact are no longer the filter; what an event needs is an official source (a site, flyer or organizer account) to verify against.

## 4. Content model

Canonical examples: `data/events/shcc.yml` and `data/events/shcc/2026-autumn.yml`.

**Event** (`data/events/<slug>.yml`): the things that stay the same every time it runs.
- Required: `slug`, `name_en`, `official_url`, `prefecture`, `venue_en`, `spectator_fee_jpy`, `last_verified`
- `spectator_fee_jpy` is required but may be `null`, for an event whose organizer has not announced the admission yet. It is the one field with three states: a number, `0` for free, and `null` for not announced, which the pages print as "Admission not announced" rather than as free. Writing `0` there would tell a visitor the day costs nothing, and a guess would be worse.
- Optional: `name_ja`, `organizer`, `summary_en`, `street_address`, `lat` and `lon` (together), `nearest_station`, `access_notes_en`, `typical_eras`, `typical_scale`, `spectator_notes_en`, `photography_notes_en`
- `name_ja` is optional because plenty of Japanese car events are named only in Latin script and have no Japanese form to give. Repeating the Latin name under `lang="ja"` would print it twice and tell a screen reader to read it with Japanese pronunciation rules, so the line is dropped instead, on every page and in the calendar description.

**Edition** (`data/events/<slug>/<edition-id>.yml`): one run of the event.
- File name: the year (`2026.yml`) for events that run once a year, or the year plus a lowercase word (`2026-spring.yml`, `2026-autumn.yml`) for events that run more than once.
- The file name is the edition's permanent ID. It forms the page address and the calendar UID, so it is never renamed, even if the date moves.
- Required: `slug`, `year`, `status` (confirmed, tentative or cancelled), `start`, `end`, `source_url`, `last_verified`, `sequence`
- Optional: `start_time` and `end_time` (together), `venue_en`, `street_address`, `lat` and `lon` (override the event's), `route` and `route_en`, `list_as_of` and `cars` (together), `videos`
- Display name: the event name plus the edition word, e.g. "Hill Climb Spring 2026". A year-only edition shows as "Hill Climb 2026".

**Route day** (item in `route`): one day on the road.
- Required: `date`, `checkpoints`
- Days run in order and every `date` falls inside the edition's `start`..`end`.

**Checkpoint** (item in `checkpoints`): one public stop, with the window the cars are expected in.
- Required: `start_time`, `place_en`, `prefecture`
- Optional: `end_time` (organizers leave some stops open-ended), `place_ja`
- Checkpoints run in order of `start_time` within a day. Windows overlap, which is normal.
- `prefecture` is given on every checkpoint even though sources print it only when it changes: a half-filled column cannot be scanned.
- `route_en` is a short lead-in above the tables for what a timetable cannot say, not a substitute for them.

**Video** (item in `videos`): a recording of this edition on YouTube.
- Required: `youtube_id` (the 11 characters after `watch?v=`, never a full URL), `label_en` (e.g. "Day 1")
- From the organiser's own channel or anyone else's. A video from any other channel is credited at the end of its label, using the channel's name in Latin script: "74th edition (video by SPACIOUS TV)". The credit then appears in the embed's `title` and in its "on YouTube" link.
- Embedded from `youtube-nocookie.com`, which is chosen once in `VIDEO_EMBED_URL` in `scripts/build.py`. That domain sets no cookies until the visitor presses play, but YouTube's player still loads with the page and uses browser storage. Each embed is lazy-loaded, carries a `title` of the edition name plus the label, and has a plain "Day 1 on YouTube" link under it for readers whose blocker removes the frame.
- An edition with videos leads with them, then the car list, then the route: a video exists only once an edition has run, so it marks the page as a look back without the build reading the clock. The visitor to a past edition wants to know what it was like and what came; last year's timetable matters least. Without videos the order is route, cars. The title, description and event-page link list the sections in the same order, since all of them read one `sections` list in `scripts/build.py`.
- Every edition page with a later edition links forward to it ("Next edition: 2–5 Oct 2026"), with "(dates not confirmed)" or "(cancelled)" after the link when that is its status. The link goes to the next edition's page, or to the event page when it has none.
- Every edition page links to the latest earlier edition of the same event that has videos ("Videos of the 2025 edition"). Earlier by date, not by today, since the build never reads the clock.
- An edition page with no videos of its own also embeds the first video of that earlier edition, as the last thing on the page under the heading "From the 2025 edition". It shows a first-time visitor what the event is like without pushing the route and entry list down, which is what the page is for until the edition has run. It shows one video only, because the full set is one link away, and it has the same lazy-loading, `title` ("La Festa Autunno 2025, Day 1") and "Day 1 on YouTube" link as the edition's own videos. The heading names the year so nobody mistakes last year's footage for this year's route. It and the link above both use the breadcrumb's edition label, so on an Autumn 2026 page whose videos come from the spring they read "From the Spring 2026 edition" and "Videos of the Spring 2026 edition". It does not count as a section: it doesn't create an edition page on its own, doesn't take the `videos` anchor, and isn't named in the title, description or event-page link, since none of those should suggest this edition has videos. Once an edition has videos of its own, they replace it.
- Embeds show YouTube's Error 153 when a built page is opened from disk: a `file://` page sends no referrer, and YouTube refuses an embed without one. Serve `site/` over HTTP to preview them.

**Car** (item in `cars`)
- Required: `make`, `model`
- Optional: `entry_no`, `year`, `colour`
- `entry_no` and `year` are each given for every car or for none. A column filled for some rows and blank for others cannot be scanned, the same reason every checkpoint carries its `prefecture`.
- The table renders only the columns at least one car fills. A rally entry list comes out as No./Year/Make/Model; a show that announces the models it will have on the floor comes out as Make/Model.
- Which kind of list it is is derived, never stored: cars with entry numbers are an "Entry list" and can withdraw, cars without are "Cars on display" and the line-up can change. The heading, the link from the evergreen page and the provisional caveat all follow from that one test.
- A source that names models rather than individual cars gives no year, and a model's production span is not the age of the car standing on the stand. Leaving `year` out is the correct reading of such a source, not a gap to be filled.

**Rules the build enforces**
- Slugs and edition words use lowercase letters, digits and single hyphens. Edition file names start with the year, and `year` must match it.
- Times and `entry_no` are quoted strings. Dates are unquoted. No UTC offsets: Japan is UTC+9 all year, applied at build time.
- Unknown fields are rejected. This blocks personal data (driver, navigator, owner, entrant, plate, chassis) and typos alike.
- An edition page exists only if `route`, `route_en`, `cars` or `videos` is present.
- Prose fields (`summary_en`, `access_notes_en`, `spectator_notes_en`, `photography_notes_en`, `route_en`) are capped at 75 words. A wall of text hides the facts inside it from anyone skimming, and a visitor planning a day out is always skimming. Over the cap the build fails and names the ways out: bullet points, a table, a diagram, or structured fields. The cap is deliberately above the longest real paragraph (66 words) and far below the route paragraphs it replaced (185 and 191).
- Prose fields may carry links written as `[text](https://...)`, and nothing else in the way of markup. Pages render them as anchors, and everything around them is still escaped. JSON-LD, the JSON feed and the word cap all see only the link text. The build rejects an `http://` link, a malformed one, or an HTML `<a>`, because any of those would otherwise reach the page as literal brackets or tags.
- Prose fields are also checked against `EDITORIAL_PHRASES` in `scripts/build.py`, a short list of recommendation constructions ("worth a look", "don't miss", "the practical way to"). A match fails the build. The test is whether cutting the words loses a fact: "a timetable giving an arrival window for every checkpoint, which is the practical way to plan a day around it" shipped on the La Festa Autunno page and lost nothing when the clause went. The list is deliberately narrow so a match is always real, which means it catches repeats rather than every first instance; section 7 carries the judgement the list cannot make. Matching is case-insensitive over NFKC-normalised text with curly apostrophes folded, and spans the line breaks a folded scalar leaves inside a phrase.
- The cap applies to what the page renders, not to a field in isolation. `nearest_station` and `access_notes_en` land in one `<dd>`, so they are capped on their combined length as well as individually. Without that, two fields sitting legally at 74 words each would render a 148-word block and pass. Any future pair of fields that share a block joins `COMBINED_PROSE` in `scripts/build.py`.

**Strips:** three diagrams share one set of classes (`.chart`, `.chart-when`, `.chart-track`, `.chart-axis`) and one rule: each is computed from the data the page already shows, carries its counts as visible text, and marks the bars `aria-hidden` as a restatement.

**Route chart:** a day-shape diagram sits above the route tables, one bar per checkpoint on one shared hour axis, so a reader can see at a glance which day starts late and which runs long. It is computed from the same `route` data the tables render and stores nothing, so it cannot disagree with them. Bars are positioned with percentages rather than an SVG `viewBox`, which would shrink its own labels on a phone. Each row's span and stop count are visible text, not only a bar; the bars themselves are `aria-hidden` as a restatement.

**Decade strip:** above an entry list, one bar per decade from the oldest car to the newest, scaled to the busiest decade. It answers "what will I actually see" from the table below it: the 2026 La Festa field is 21 cars of the 1950s against 5 prewar. A decade with no cars keeps its row and draws nothing, so a gap in the field stays visible instead of closing up and reading as a run. A list without years draws no strip at all: counting only the rows that happen to carry one would put a picture above a table it disagrees with.

**Year strip:** on the home page, one rail per year with a mark where each edition falls across the months, on a Jan/Apr/Jul/Oct axis. It shows the season the hobby runs in. Cancelled editions are drawn in muted grey rather than dropped, because the list below them says cancelled in words. It earns its place once a year holds several events; with two or three it is nearly empty. Past years drop off in the browser, not in the build, which never reads the clock: every year is rendered with a `data-year`, and the page hides the ones before today's year in Japan. The whole strip hides when no year is left. A past year is still in the list below, under Past events.

**Chips and dots:** `typical_eras` renders as outlined chips rather than a comma list, and the Dates table puts a small coloured dot before Confirmed / Not confirmed, and a cross before Cancelled. The cross is there because confirmed and cancelled are both red, so shape carries the difference. Both are `aria-hidden` and the word always stays, so colour is never the only signal. The Details column in that table is dropped when no edition in it has a page.

**Computed, never stored:** `list_provisional` (`list_as_of` before `end`, and `last_verified` no later than `end`), whether an edition is timed, and upcoming vs past, plus which years the strip shows (both in the browser, by Japan's date).

**Photos (later):** strip GPS data, mask registration plates, exclude or blur identifiable faces (肖像権). Storage decided at photo launch (see §10).

## 5. Site structure

```
/                               Calendar: upcoming, then past. One row per edition
/events/<slug>/                 Evergreen: what it is, access, fees, what you'll see, every edition's dates
/events/<slug>/<edition-id>/    Route and/or entry list (conditional)
/classic-car-events.ics         Calendar feed. The file name is deliberate: see 6.3
/api/events.json                Every edition as JSON, from the records the pages render
/llms.txt                       Plain-text index of every page and of the machine formats
/sitemap.xml
/robots.txt                     Allows everything; sitemap, Agentmap and Content-Signal
/.well-known/ard.json           ARD 1.0 capability manifest
/.well-known/ai-catalog.json    The same manifest at ARD's predecessor path
/.well-known/api-catalog        RFC 9727 linkset, anchored on the two feeds
/favicon.ico                    Browser icon; /static/favicon.svg is the sharp version
/404.html                       Served by Pages for any missing path: every event, root-absolute links, noindex, Fathom event '404 page shown'
/guides/spectating/             After the tracer bullet
/about/                         Where the facts come from, not affiliated, where to report an error (GitHub Issues)
```

## 6. Technical

**Stack:** Python 3 and Jinja2 in `scripts/build.py`. Vanilla JS only for the upcoming/past split. No framework, no build step beyond the script.

**Hosting:** GitHub Pages, deployed by GitHub Actions. There is no local git: files are uploaded through github.com, and each upload triggers the workflow. The workflow runs the tests first and publishes nothing if any fail. The browser test runs locally only.

**Reproducible:** the build never reads the clock. The same data gives byte-identical output.

**Safety:** the build only deletes an output folder that is empty or holds a previous build.

**Deferred:** source-change watcher, LLM translation drafts. Neither publishes anything without human review.

### 6.1 Dates and times

- All-day editions: dates only in JSON-LD. In the calendar feed, `VALUE=DATE` with an exclusive end (day after `end`), never converted to UTC.
- Timed editions: JSON-LD with `+09:00`. Calendar feed in UTC (`Z`), no time-zone block.

### 6.2 Structured data

One `schema.org/Event` block per edition: on the edition page if it exists, otherwise on the evergreen page. Cancelled maps to `EventCancelled`. Tentative stays `EventScheduled` with a visible caveat on the page.

Edition pages also carry a `BreadcrumbList` matching the visible trail above the `<h1>`: Home › event › edition label (e.g. "Autumn 2026"), the last entry unlinked, marked `aria-current="page"` and given no `item` URL. Evergreen pages, the home page and About have no trail, because it would say only "Home", which the header mark already is.

### 6.3 Calendar feed

- The file name is the calendar's name in Thunderbird, which has never read `X-WR-CALNAME` (bugzilla 168176, open since 2002) and names a subscription after the last path segment of its URL. `events.ics` showed as "events". Apple Calendar and Outlook read `X-WR-CALNAME`; `NAME` is RFC 7986's spelling of it, sent for clients that prefer it. Renaming the file breaks every existing subscription, so it is now as fixed as an edition ID.
- Every page offers a live subscription: a `webcal://` link for Apple Calendar and Outlook, and the `https://` URL for Google Calendar. A plain download would never receive updates.
- `UID` is `<slug>-<edition-id>@<domain>` and never changes. `DTSTAMP` comes from `last_verified`. Add 1 to `sequence` whenever a published date changes.

### 6.4 Map links

- A venue with `lat` and `lon` gets a `Map` link under its address on the evergreen page and on each edition page, pointing at `https://maps.apple.com/?ll=<lat>,<lon>&q=<venue>`. `ll` fixes the point and `q` only labels the pin, so a link can never search its way to the wrong place.
- The pair is optional and the page simply omits the link without it. Half a pair fails the build, as does a pair outside Japan's bounding box, which is what a swapped or mistyped pair looks like.
- Coordinates belong to the venue they were taken at, so an edition that names a `venue_en` of its own does not inherit the event's pin: it links only if it carries its own pair.
- Recorded to 4 decimal places (about 11 m) from a geocoder, never read off a map by eye, and cross-checked against a second source. Same rule as the route chart: what the map shows cannot contradict the address printed beside it.
- The pair also becomes `GEO` in the calendar feed and `geo` on the JSON-LD `Place`.
- The link carries a pin glyph before the word. It is inline SVG in `templates/icons.html`, like the header mark, so the site still ships no image files and makes no extra request: drawn on a 24 grid at `stroke-width` 2, coloured with `currentColor` so one glyph works in both themes, sized in the markup so a missing stylesheet leaves a 16px pin rather than a full-width one, and `aria-hidden` because "Map" already says it. The "Videos of the 2025 edition" link carries a play glyph drawn to the same rules (`video_icon` in the same file). Both share the `.icon` class for their spacing.

### 6.5 Design tokens

Plain CSS only: no preprocessor, no custom properties, no framework, so the site works on old and budget devices where `var()` is unsupported. Tokens are therefore a convention, written as literal values in `static/style.css` and restated under the dark-mode media query. Use only these values; add to the set with a reason rather than inventing a one-off.

| Token | Light | Dark |
|---|---|---|
| ink | `#1C1C1C` | `#EBEBEB` |
| background | `#FFFFFF` | `#141414` |
| muted | `#5C5C5C` | `#A8A8A8` |
| rule | `#E0E0E0` | `#333333` |
| brand (logo swoosh, links, focus ring, chart bars, status dot) | `#8C1C24` | `#D0636A` |
| note background / ink | `#FFF4D6` / `#5E4700` | `#3A300F` / `#F3D98B` |
| cancelled background / ink | `#FBE9E5` / `#8E2A1B` | `#3A1C16` / `#F2A493` |

The brand red is the site's one accent, so red on its own does not mean cancelled. Cancelled keeps its own darker red (1.08:1 from the brand red, so effectively the same colour) and is told apart by the word, the tinted box behind a badge or note, and the cross in the Dates table. The header logo is the designer's lockup (`ref/cmj-logo-3-wordmark-lockup-v3.svg`, wordmark in Liberation Serif converted to outlines) inlined in `templates/base.html` without its background rect and metadata. The swoosh is coloured from the stylesheet and the wordmark uses `currentColor`, so both change in dark mode. The favicon is the swoosh in white on a brand-red tile, redrawn on a 32 grid (stretched 1.6x vertically and thickened under the peak, since at true proportions it is under a pixel thick). `tools/favicon.py` draws both `static/favicon.svg` and the 16/32/48 `static/favicon.ico` from the logo file; it needs Pillow in the local `.venv` only, and a test fails if either file differs from a fresh run.

Spacing, on a 4/8 scale: 4, 8, 16, 24, 32, 48. Radius 8, and 4 for the focus ring only, since an 8px radius turns the outline round a short link into a pill. Measure 720. Type: 32, 24, 20, 16.

`StylesheetTokenTests` enforces these values for colours, font sizes, margin, padding, gap and border-radius. Its sets in `tests/test_build.py` are the enforced copy; change them with this table.

Two browser-support rules the stylesheet keeps:
- **No flex `gap`.** It resolves to nothing on IE and on Safari before 14.1, with no fallback, so a row silently closes up. Use margins on the children.
- **Grid is allowed** for `.events` and `.facts` because it degrades to readable stacked blocks where unsupported. `gap` inside a grid is fine for the same reason.

Both are pinned by tests, not by comment.

## 7. Editorial rules

- Every page shows its last verified date and links the official source.
- Entry lists show "Entry list as of YYYY-MM-DD" and, while provisional, "Provisional: cars may withdraw or change." A list published before the event stops being provisional once the edition has been re-verified after `end`: at that point the published list is the last word, so the warning would be false. Re-verifying on the closing day is not enough, because cars can still withdraw during the event.
- The pages state what is true and let the reader draw the conclusion. No advice, no recommendation, no telling a visitor what a fact means for their day. Every sentence has to carry a fact that would be lost if it were cut. `EDITORIAL_PHRASES` enforces the part of this a list can enforce.
- Translations are drafted, then human-reviewed. Never auto-published.
- Japanese names appear alongside English.
- No personal data, ever.

## 8. SEO

Titles carry search intent; the brand is the suffix. The home-page year comes from the latest year in the data.

- `Classic Car Events in Japan 2027 | Classic Motoring Japan`
- `<Event name>: Visitor Guide | Classic Motoring Japan`

Every page but the 404 carries a `description` and Open Graph tags (`og:title`, `og:description`, `og:url`, `og:type`, `og:site_name`), with `og:url` equal to the canonical link. No `og:image`: the site has no images of its own. Embedded videos bring YouTube's thumbnails, which are not the site's to put in a share card. The description is derived, never stored:

| Page | Description |
|---|---|
| Home | `SITE_LEDE` |
| Evergreen | First sentence of `summary_en`, links reduced to their text; without a summary, "Dates, venue and admission for <name> in <prefecture>." |
| Edition | "[Cancelled. / Dates not confirmed.] <Route / Entry list / Cars on display, as the page names them> for <name year>: <dates>, <venue>, <prefecture>." Status leads, so a cancelled edition's snippet cannot read as a listing. |
| About | `ABOUT_DESCRIPTION` |

Plus JSON-LD, `sitemap.xml`, the calendar feed, semantic HTML, and no client-side rendering of primary content.

### 8.1 Agent readability

GitHub Pages serves static files and sets no response headers of ours, so anything needing
content negotiation or a `Link:` header cannot be published from here at all. That rules out
Markdown negotiation (`Accept: text/markdown`) and RFC 8288 link relations permanently, short
of moving the site behind a proxy. What a file on disk can say:

| File | Standard | Holds |
|---|---|---|
| `/robots.txt` | Content Signals | `search=yes, ai-input=yes, ai-train=no` |
| `/api/events.json` | none | Every edition, from the same rows as the pages and the calendar |
| `/llms.txt` | llmstxt.org | Index of every page, and of the machine formats |
| `/.well-known/ard.json` | ARD 1.0 | Three entries: the JSON feed, the calendar, `llms.txt` |
| `/.well-known/ai-catalog.json` | ARD predecessor | The same bytes, at the path scanners still read |
| `/.well-known/api-catalog` | RFC 9727 | Linkset anchored on the JSON and calendar feeds |

ARD §5.1 gives three discovery mechanisms and the site serves all three: the well-known
manifest, `Agentmap:` in `robots.txt`, and `<link rel="ard">` in every page head. The path
matters more than it looks. `/.well-known/ard.json` is the only one a conformant consumer
MUST fetch; `ai-catalog.json` is the predecessor and consulting it is optional, so publishing
there alone is how a site passes a scanner while staying invisible to agents that follow the
spec. The manifest validates against both `ai-catalog.schema.json` and the current
`ArdManifest`, so it is written twice rather than forked, and `rel="ai-catalog"` points at
the predecessor path so each relation resolves to its own document.

OAuth metadata, an MCP server card and `auth.md` are deliberately absent. There is no auth
server and no MCP server, and a manifest for an endpoint that does not exist is a false
statement about the site, which costs more than the scan point it would win.

`build_api` states only what the data holds: a field the data does not carry is left out
rather than defaulted, which is what keeps a free event (`spectator_fee_jpy: 0`) distinct
from one whose fee is not announced (`null`, and so absent from the record). The JSON-LD
follows the same rule: `isAccessibleForFree` is omitted rather than set to false, since
false is a claim about the price and not the absence of one.

`actions/upload-pages-artifact` must be v5 with `include-hidden-files: true`. From v4 the
action tars the site with `--exclude=".[^/]*"`, which strips every dot-path, so `.well-known/`
never reaches Pages and both catalogs 404 on an otherwise green run. Nothing in the build or
the run reports it. `DeployWorkflowTests` guards the flag.

`/.well-known/api-catalog` serves as `application/octet-stream`, because RFC 9727 fixes a
path with no file extension and Pages types a file by its extension alone. RFC 9727 asks for
`application/linkset+json`. The body is correct and parses; the type cannot be corrected from
here, so this is the same class of limit as the `Link:` header, not something left undone.

## 9. Tracer bullet

One real event, one edition. Done when:

1. The event page passes Google's Rich Results Test with no errors.
2. Subscribing to the feed on a phone set to `Europe/London` shows correct dates and times.
3. Uploading a change on github.com produces a green run in the Actions tab and updates the live site.
4. An edition with a past end date appears under "Past", in a browser set to a non-Japan time zone.

Then: second event, then photos. Add the watcher only once manual source-checking becomes the time sink.

## 10. Open questions

1. Is `classicmotoringjapan.com` registered? Needed before the first public deploy, because calendar UIDs use it.
2. Photo archive size: decides whether photos go in the repository or in separate storage such as R2.
3. Is the source list for the 10 to 15 events complete, or is discovery still needed?
