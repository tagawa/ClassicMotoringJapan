# Classic Motoring Japan: Specification v7

Changes from v6 (section 8): event and edition titles drop the brand suffix, every page carries `og:locale`, and event-page meta descriptions are capped at 160 characters.

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

Ideally pre-1980 cars, Japanese and imported. This is the focus for new events, research and recommendations, not a hard filter. Events already on the site that admit later cars stay; don't suggest removing them. For a new mixed-era event, state its cutoff year and let me decide; don't ask whether post-1980 cars count.

## 4. Content model

Canonical examples: `data/events/shcc.yml` and `data/events/shcc/2026-autumn.yml`.

### 4.1 Event

`data/events/<slug>.yml`: the things that stay the same every time it runs.
- Required: `slug`, `name_en`, `official_url`, `prefecture`, `venue_en`, `spectator_fee_jpy`, `last_verified`
- `spectator_fee_jpy` is required but may be `null`, for an event whose organizer has not announced the admission yet. It is the one field with three states: a number, `0` for free, and `null` for not announced, which the pages print as "Admission not announced" rather than as free. Writing `0` there would tell a visitor the day costs nothing, and a guess would be worse. Once an edition is over the phrase says nothing useful, so past entries drop it: under Past events on the home page by CSS (`#past-list .fee-unannounced`), and on an edition page by a script that removes the Cost row once the edition's last day has ended in Japan. A published fee stays on past entries.
- Optional: `name_ja`, `organizer`, `summary_en`, `street_address`, `lat` and `lon` (together), `nearest_station`, `access_notes_en`, `typical_eras`, `typical_scale`, `spectator_notes_en`, `photography_notes_en`, `cutoff_year`
- `cutoff_year` is the newest build year the organiser accepts, printed on the home page as "Cars to 1975". Give it only where a source states one year exactly. "About 2000", "the early 1980s", or a figure reported for one past edition is not a cutoff, and an event without the field claims none. Exceptions the rule carries (cars the organiser approves specially, later examples of the same model) stay in `summary_en`.
- `name_ja` is optional because plenty of Japanese car events are named only in Latin script and have no Japanese form to give. Repeating the Latin name under `lang="ja"` would print it twice and tell a screen reader to read it with Japanese pronunciation rules, so the line is dropped instead, on every page and in the calendar description.

### 4.2 Edition

`data/events/<slug>/<edition-id>.yml`: one run of the event.
- File name: the year (`2026.yml`) for events that run once a year, or the year plus a lowercase word (`2026-spring.yml`, `2026-autumn.yml`) for events that run more than once.
- The file name is the edition's permanent ID. It forms the page address and the calendar UID, so it is never renamed, even if the date moves.
- Required: `slug`, `year`, `status` (confirmed, tentative or cancelled), `start`, `end`, `source_url`, `last_verified`, `sequence`
- Optional: `start_time` and `end_time` (together; each day's hours, so on a multi-day edition they hold only when every day keeps the same hours, and an edition whose days differ goes without, its times in the prose), `venue_en`, `street_address`, `lat` and `lon` (override the event's), `prefecture`, `route` and `route_en`, `list_as_of` and `cars` (together), `videos`, `cutoff_year`
- `cutoff_year` on an edition is for an event whose limit moves each year (Toyota Automobile Museum: 1996 for 2026). It overrides the event's on that edition's home-page entry only.
- `prefecture` on an edition is for an event that moves between prefectures (British Car Festival: Gifu in 2026, Aichi in 2027). It overrides the event's wherever the edition is printed: its page and snippet, its home-page entry, the calendar, the structured data and the JSON feed. The event page keeps the event's. It needs `venue_en` beside it, since alone it would print the event's venue in a prefecture that venue is not in.
- Display name: the event name plus the edition word, e.g. "Hill Climb Spring 2026". A year-only edition shows as "Hill Climb 2026".

### 4.3 Route day

Item in `route`: one day on the road.
- Required: `date`, `checkpoints`
- Days run in order and every `date` falls inside the edition's `start`..`end`.

### 4.4 Checkpoint

Item in `checkpoints`: one public stop, with the window the cars are expected in.
- Required: `start_time`, `place_en`, `prefecture`
- Optional: `end_time` (organizers leave some stops open-ended), `place_ja`
- Checkpoints run in order of `start_time` within a day. Windows overlap, which is normal.
- `prefecture` is given on every checkpoint even though sources print it only when it changes: a half-filled column cannot be scanned.
- `route_en` is a short lead-in above the tables for what a timetable cannot say, not a substitute for them.

### 4.5 Video

Item in `videos`: a recording of this edition on YouTube, or the organiser's own guide to it published beforehand.
- Required: `youtube_id` (the 11 characters after `watch?v=`, never a full URL), `label_en` (e.g. "Day 1")
- From the organiser's own channel or anyone else's. A video from any other channel is credited at the end of its label, using the channel's name in Latin script: "74th edition (video by SPACIOUS TV)". The credit then appears in the embed's `title` and in the link under it. Videos from the site's own channel (`YOUTUBE_CHANNEL_URL` in `scripts/build.py`) carry no credit: "video by Classic Motoring Japan" on its own pages would say nothing.
- Embedded from `youtube-nocookie.com`, which is chosen once in `VIDEO_EMBED_URL` in `scripts/build.py`. That domain sets no cookies until the visitor presses play, but YouTube's player still loads with the page and uses browser storage. Each embed is lazy-loaded, carries a `title` of the edition name plus the label, and has a plain link under it, its text the label alone ("Day 1"), for readers whose blocker removes the frame.
- An edition with videos leads with them, then the car list, then the route: a video exists only once an edition has run, so it marks the page as a look back without the build reading the clock. The visitor to a past edition wants to know what it was like and what came; last year's timetable matters least. The one exception is an organiser's pre-event guide (Fujioka Oldies 2026, a slideshow on parking and the day's programme), which is added before the edition runs because it carries facts the text sources lack; the page then leads with it too, and it replaces the "From the 2025 edition" embed below. Without videos the order is route, cars. The title, description and event-page link list the sections in the same order, since all of them read one `sections` list in `scripts/build.py`.
- Every edition page with a later edition links forward to it ("Next edition: 2–5 Oct 2026"), with "(dates not confirmed)" or "(cancelled)" after the link when that is its status. The link goes to the next edition's page, or to the event page when it has none.
- Every edition page links to the latest earlier edition of the same event that has videos ("Videos of the 2025 edition"). Earlier by date, not by today, since the build never reads the clock.
- An edition page with no videos of its own also embeds the first video of that earlier edition, as the last thing on the page under the heading "From the 2025 edition". It shows a first-time visitor what the event is like without pushing the route and entry list down, which is what the page is for until the edition has run. It shows one video only, because the full set is one link away, and it has the same lazy-loading, `title` ("La Festa Autunno 2025, Day 1") and "Day 1" link as the edition's own videos. The heading names the year so nobody mistakes last year's footage for this year's route. It and the link above both use the breadcrumb's edition label, so on an Autumn 2026 page whose videos come from the spring they read "From the Spring 2026 edition" and "Videos of the Spring 2026 edition". It does not count as a section: it doesn't create an edition page on its own, doesn't take the `videos` anchor, and isn't named in the title, description or event-page link, since none of those should suggest this edition has videos. Once an edition has videos of its own, they replace it.
- Embeds show YouTube's Error 153 when a built page is opened from disk: a `file://` page sends no referrer, and YouTube refuses an embed without one. Serve `site/` over HTTP to preview them.

### 4.6 Car

Item in `cars`.
- Required: `make`, `model`
- Optional: `entry_no`, `year`, `colour`, `country`
- `country` is where a car was built, as an ISO 3166 two-letter code from `COUNTRIES` in `scripts/build.py` (IT, GB, DE, FR, US, JP, SE). Give it on a car in two cases: the organiser's list prints a country column (the four Coppa lists), or the car's make has no single country and the model settles it (a Ford Mustang is US). A car without one takes its make's home country from `data/makes.yml`, so most lists need no `country` at all. A make given `null` there has no single country (Ford, Heinkel, Arnolt), and its cars show no flag unless given one. A car's own value always wins: one Coppa list has a Brighton-built BMW Isetta marked GB. Leave it off a car the organiser gives two countries for ("I/F").
- `data/makes.yml` is that table: one make per line, alphabetical, `Make: CODE` or `Make: null` with a comment saying why. It is data, not code, because it changes when a new entry list brings a new make. The build rejects a code it has no flag for and a make listed twice (YAML would otherwise keep the last without a word), and a site with no such file builds without flags from makes. The flag drawings and country names stay in `COUNTRIES` in the builder.
- `entry_no` is given for every car or for none. A column filled for some rows and blank for others cannot be scanned, the same reason every checkpoint carries its `prefecture`. `year` is not held to that: an organiser's list sometimes leaves one car's year blank (Coppa di Tokyo 2025, entry 73), and the car stays in with an empty Year cell, because a car without a year is better than no car. A year is never filled in from the model's production span.
- The table renders only the columns at least one car fills. A rally entry list comes out as No./Year/Make/Model; a show that announces the models it will have on the floor comes out as Make/Model.
- Which kind of list it is is derived, never stored: cars with entry numbers are an "Entry list" and can withdraw, cars without are "Cars on display" and the line-up can change. The heading, the link from the evergreen page and the provisional caveat all follow from that one test.
- A source that names models rather than individual cars gives no year, and a model's production span is not the age of the car standing on the stand. Leaving `year` out is the correct reading of such a source, not a gap to be filled.

### 4.7 Rules the build enforces

- Slugs and edition words use lowercase letters, digits and single hyphens. Edition file names start with the year, and `year` must match it.
- Times and `entry_no` are quoted strings. Dates are unquoted. No UTC offsets: Japan is UTC+9 all year, applied at build time.
- Unknown fields are rejected. This blocks personal data (driver, navigator, owner, entrant, plate, chassis) and typos alike.
- An edition page exists only if `route`, `route_en`, `cars` or `videos` is present.
- Prose fields (`summary_en`, `access_notes_en`, `spectator_notes_en`, `photography_notes_en`, `route_en`) are capped at 75 words. A wall of text hides the facts inside it from anyone skimming, and a visitor planning a day out is always skimming. Over the cap the build fails and names the ways out: bullet points, a table, a diagram, or structured fields. The cap is deliberately above the longest real paragraph (66 words) and far below the route paragraphs it replaced (185 and 191).
- Prose fields may carry links written as `[text](https://...)`, and nothing else in the way of markup. Pages render them as anchors, and everything around them is still escaped. JSON-LD, the JSON feed and the word cap all see only the link text. The build rejects an `http://` link, a malformed one, or an HTML `<a>`, because any of those would otherwise reach the page as literal brackets or tags.
- Prose fields are also checked against `EDITORIAL_PHRASES` in `scripts/build.py`, a short list of recommendation constructions ("worth a look", "don't miss", "the practical way to"). A match fails the build. The test is whether cutting the words loses a fact: "a timetable giving an arrival window for every checkpoint, which is the practical way to plan a day around it" shipped on the La Festa Autunno page and lost nothing when the clause went. The list is deliberately narrow so a match is always real, which means it catches repeats rather than every first instance; section 7 carries the judgement the list cannot make. Matching is case-insensitive over NFKC-normalised text with curly apostrophes folded, and spans the line breaks a folded scalar leaves inside a phrase.
- The cap applies to what the page renders, not to a field in isolation. `nearest_station` and `access_notes_en` land in one `<dd>`, so they are capped on their combined length as well as individually. Without that, two fields sitting legally at 74 words each would render a 148-word block and pass. Any future pair of fields that share a block joins `COMBINED_PROSE` in `scripts/build.py`.

### 4.8 Diagrams

**Strips:** four diagrams share one set of classes (`.chart`, `.chart-when`, `.chart-track`, `.chart-axis`) and one rule: each is computed from the data the page already shows, carries its counts as visible text, and marks the bars `aria-hidden` as a restatement.

**Route chart:** a day-shape diagram sits above the route tables, one bar per checkpoint on one shared hour axis, so a reader can see at a glance which day starts late and which runs long. It is computed from the same `route` data the tables render and stores nothing, so it cannot disagree with them. Bars are positioned with percentages rather than an SVG `viewBox`, which would shrink its own labels on a phone. Each row's span and stop count are visible text, not only a bar; the bars themselves are `aria-hidden` as a restatement.

**Entry list headings:** the decade strip and the make strip draw the same bars, so each has its own sub-heading, "By decade" and "By make", and a heading appears only with the strip it names. The two sit side by side where both fit (each column wraps below 288px, so a phone stacks them with no breakpoint), and each row is label, bar and count on one line; the count is a bare number on screen and reads "5 cars" to a screen reader. Below them the table folds into a `<details>` summarised "All 50 cars", since the strips already say what is in it. A list with neither strip (a show's announced line-up) has no headings and shows its table open, because nothing above it would say what the fold hides. The flag definitions stay outside the fold. In use since 2026-10-17, from the design team's mockups in `ref/design-mockups/`.

**Country flags:** in a list where any car has a `country`, each car's flag sits before its make in the "All cars" table, 24 by 16. The flags are drawn in `COUNTRIES` as inline SVG, each defined once per page and only if the page uses it, so the site still ships no image files; an emoji flag would show as two letters on Windows. Each carries the country's name as its accessible name and tooltip. Their colours are the countries' own and sit outside the token table; the ring round each is the rule token. Every make cell in such a list is indented by the flag's width, so a make that wraps hangs clear of the flag and a car with no country still lines up. In use since 2026-10-13. On the four Coppa lists the country is the organiser's own column; on every other list it is the make's home country, from 2026-10-14. The JSON carries whichever country the page shows.

**Decade strip:** above an entry list, one bar per decade from the oldest car to the newest, scaled to the busiest decade. It answers "what will I actually see" from the table below it: the 2026 La Festa field is 21 cars of the 1950s against 5 prewar. A decade with no cars keeps its row, counts 0 and draws nothing, so a gap in the field stays visible instead of closing up and reading as a run. A list without years draws no strip at all. Where some cars have no year, the strip ends with a line that counts them ("No year given: 1 car") and draws no bar, so its counts still add up to the table's rows.

**Make strip:** between the decade strip and the table, one bar per make with two or more cars, busiest first and alphabetical within a count, scaled to the busiest make, then a single line for the rest: "and 14 makes with one car each". A make with one car gets no row because it would only repeat its table row. Makes are counted as the table spells them, so Fiat, Fiat-Abarth and Gilco-Fiat are three. It is drawn only when every row has an entry number: there a row is a car, whereas a show's announced line-up names models, and two models are not two cars.

**Venue maps:** each event on the home page has a 96px thumbnail map of Japan beside it, with a dot for its venue; where several share a date, each keeps its own. The 2026-10-17 mockups proposed one small overview beside the year strip instead, and the thumbnails were kept. An overview map of every upcoming venue above the list was tried and dropped (2026-10-06): at a size where the dots could be told apart it took up too much of the page.
- Dots come from `venue_pin`, so they follow the Map link's rules (§6.4): no coordinates means no dot and no thumbnail, never a guessed one.
- The coastline is `data/japan_outline.json`: Natural Earth 1:50m (public domain), main islands only, written once by the local `tools/japan_outline.py`. The build fetches nothing.
- `map_point` in `scripts/build.py` projects the coastline and the dots alike, so they cannot disagree. A test fails if a real venue falls outside `MAP_LON`/`MAP_LAT`; an Okinawa or far-north venue needs an inset or wider bounds first.
- The outline is sent once per page as `<path id="japan">` and reused by every map through `<use xlink:href>`.
- A cancelled edition's dot is grey, like `.off` in the strips. Every map is `aria-hidden`, since the prefecture is printed beside it.

**Year strip:** on the home page, one rail per year with a mark where each edition falls across the months, on a Jan/Apr/Jul/Oct axis. It shows the season the hobby runs in. Cancelled editions are drawn in muted grey rather than dropped, because the list below them says cancelled in words. It earns its place once a year holds several events; with two or three it is nearly empty. Past years drop off in the browser, not in the build, which never reads the clock: every year is rendered with a `data-year`, and the page hides the ones before today's year in Japan. The whole strip hides when no year is left. A past year is still in the list below, under Past events. The same script greys every bar whose last day has passed, in the colour cancelled ones use, since neither is a date to keep, and marks today on this year's rail: a tick placed by the same day-of-year sum the build uses for the bars, with "Today" on a line of its own above the rail so it can never sit on the year's label (since 2026-10-17).

**Chips and dots:** `typical_eras` renders as outlined chips rather than a comma list, and the Dates table puts a small coloured dot before Confirmed / Not confirmed, and a cross before Cancelled. The cross is there because confirmed and cancelled are both red, so shape carries the difference. Both are `aria-hidden` and the word always stays, so colour is never the only signal. The Details column in that table is dropped when no edition in it has a page. Once a confirmed edition's last day has ended in Japan, its status reads Held instead of Confirmed; the build never reads the clock, so the page carries the last day and the browser swaps the word, and without JavaScript it stays Confirmed, which is still true. Cancelled and Not confirmed keep their words. The calendar feed and JSON-LD keep `CONFIRMED` and `EventScheduled`, which stay correct after the day.

### 4.9 Computed, never stored

`list_provisional` (`list_as_of` before `end`, and `last_verified` no later than `end`), whether an edition is timed, and upcoming vs past, plus which years the strip shows (both in the browser, by Japan's date).

### 4.10 Photos (later)

Strip GPS data, mask registration plates, exclude or blur identifiable faces (肖像権). Storage decided at photo launch (see §9).

## 5. Site structure

```
/                               Calendar: upcoming, then past, under a ruled heading per month ("October 2026").
                                Each date appears once with the weekday and no year ("Sat 24 to Sun 25 Oct"), and
                                every edition on exactly those dates sits beneath it. A date with a day on this
                                weekend's Saturday or Sunday in Japan (the one in progress, on a Sunday) gets a
                                "This weekend" badge from the script. Past events sit under their own "Past events"
                                heading, folded behind "Show 28 events", the count written by the script that fills
                                it; the heading is outside the fold so the past months are not read as part of
                                Upcoming. Each date is drawn as a calendar leaf
                                (weekdays on a brand-red band, days beneath; months only when the days cross into the
                                next), aria-hidden behind the full date as hidden text. A past leaf's band is muted grey,
                                as a past bar is on the year strip. Per edition, each behind its own glyph: prefecture,
                                admission, "Driven route" when the edition has `route` or `route_en`, "Cars to <year>"
                                when a cutoff is on record. The full stops are hidden text, so a screen reader still
                                hears each fact end. From the 2026-10-17 mockups in `ref/design-mockups/`.
/ja/                            Every edition in Japanese, generated from existing fields: see 6.6. Linked as 日本語
                                from the home page header, and back as English
/events/<slug>/                 Evergreen: what it is, access, fees, what you'll see, every edition's dates
/events/<slug>/<edition-id>/    Route and/or entry list (conditional). With two or more sections, "On this page" jumps to
                                each, counted from what it shows: "Videos (2)", "Entry list (50 cars)" or "Cars on
                                display (12 models)", "Route (4 days)", or plain "Route" for one only described.
                                Videos sit two to a row where both fit.
/classic-car-events.ics         Calendar feed. The file name is deliberate: see 6.3
/events/<slug>/<edition-id>.ics One confirmed edition, to add to a calendar once: see 6.3
/api/events.json                Every edition as JSON, from the records the pages render
/llms.txt                       Plain-text index of every page and of the machine formats
/sitemap.xml
/robots.txt                     Allows everything; sitemap, Agentmap, Content-Signal and Content-Usage
/.well-known/ard.json           ARD v0.91 capability manifest
/.well-known/ai-catalog.json    The same manifest at ARD's predecessor path
/.well-known/api-catalog        RFC 9727 linkset, anchored on the two feeds
/<INDEXNOW_KEY>.txt             IndexNow key, public by design: see 8.2
/favicon.ico                    Browser icon; /static/favicon.svg is the sharp version
/404.html                       Served by Pages for any missing path: every event, root-absolute links, noindex, Fathom event '404 page shown'
/guides/spectating/             Planned, not built
/about/                         Where the facts come from, not affiliated, where to report an error (GitHub Issues), the site's YouTube channel.
                                Every page's footer also links the channel, "Report an error on GitHub" and About
```

## 6. Technical

**Stack:** Python 3 and Jinja2 in `scripts/build.py`. Vanilla JS only for the upcoming/past split, the "This weekend" badge, the year strip's Today mark and greyed bars, and dropping what has passed (Held, add-to-calendar links, "Admission not announced"). The home list is headed "Events" in the markup and holds every edition, oldest first, grouped by month (`month_groups`); the script that moves the past ones out renames it "Upcoming", so a reader without JavaScript never sees a 2023 date under that word. It moves whole dates, never single editions, which is why editions share a date entry only when both their first and last days match. A month with dates on both sides of today is headed in both lists, a month left empty loses its Upcoming heading, and Past runs newest first by month and by date. No framework, no build step beyond the script.

**Hosting:** GitHub Pages, deployed by GitHub Actions. There is no local git: files are uploaded through github.com, and each upload triggers the workflow. The workflow runs the tests first and publishes nothing if any fail. The browser test runs locally only.

**Analytics:** Fathom, which counts pageviews and nothing else on its own. Clicks are reported by one script in `templates/base.html`: each counted element names its event in a `data-fathom` attribute, a link reporting on click and a `<details>` on opening (not on closing). Fathom can never rename an event, so a renamed one starts a new count; the names are pinned by `FathomEventTests`, which also fails on any name it does not know. Each event carries the page path, sent by Fathom itself. Since 2026-10-17:

| Event | Counted element |
|---|---|
| `Calendar file downloaded` | "Add to Apple Calendar or Outlook" (6.3) |
| `Google Calendar form opened` | "Add to Google Calendar" (6.3) |
| `Calendar feed subscribe clicked` | The footer's `webcal://` subscription link |
| `Google Calendar feed help opened` | The footer's Google Calendar steps, opened |

`404 page shown` (section 5) is sent by the 404 page's own script, on load.

**Accessibility:** reviewed against WCAG 2.1 AA on 2026-10-26, and each defect it found is now a test.

- Japanese inside an English field (an organiser, the Japanese half of a street address, a word in prose) is marked `lang="ja"` by the `mark_ja` filter, so a screen reader switches voice. `JapaneseRunTests` scans every page of the real site for Japanese left unmarked, so a new field that can hold Japanese fails the suite until its template uses the filter.
- A table box (`.table-wrap`) is a focusable region named after its table, because a table wider than a phone scrolls inside it and Safari gives a keyboard no other way to scroll it.
- Inline scripts are ES5 with no newer DOM methods (`NodeList.forEach`, `dataset`), pinned by `ScriptSyntaxTests`: on an old browser a newer one stops the rest of the script.

**Reproducible:** the build never reads the clock. The same data gives byte-identical output.

**Safety:** the build only deletes an output folder that is empty or holds a previous build.

**Upkeep:** two checks run without anyone remembering them, since 2026-10-17.

| Check | Runs | Reports by |
|---|---|---|
| Outbound links in `data/` (`scripts/check_links.py`) | Weekly, in `.github/workflows/links.yml`, never in the build | A failed run, which GitHub emails to whoever last edited the cron line |
| Reviews of the site's output (`tools/reviews.yml`) | At the start of each local Claude Code session, by a SessionStart hook running `tools/due.py --next-review` | Claude raising the most overdue area, one per session |

- The link check fails only on a link that is certainly gone: 404, 410, a domain that no longer resolves, or a video YouTube's oEmbed will not describe (removed, private or unembeddable). A refusal, rate limit or timeout is listed as unsure and the run stays green, because a weekly false alarm would teach everyone to ignore the email. A dead link is fetched a second time before it counts.
- A review is due after `REVIEW_DAYS` in `tools/due.py`. Reviews exist because tests only check what someone thought to assert: the JSON-LD gave every event's `official_url` as its organiser's website from the start, which was often a tourism listing or a blog post, and no test could have caught it.
- GitHub disables a scheduled workflow after 60 days without activity in the repository, and emails a warning first.

**Deferred:** source-change watcher, LLM translation drafts. Neither publishes anything without human review.

### 6.1 Dates and times

- Readers get weekdays, from `fmt_span`: "Sun 18 Oct" on the home page (hidden text behind the leaf `fmt_leaf` draws), where the month heading carries the year, and "Fri 2 to Mon 5 Oct 2026" in a page's When row. A span across the new year names both years even on the home page, since one heading cannot. Descriptions, `llms.txt` and the "Next edition" link keep the shorter "2–5 Oct 2026".
- All-day editions: dates only in JSON-LD. In the calendar feed, `VALUE=DATE` with an exclusive end (day after `end`), never converted to UTC.
- Timed editions: JSON-LD with `+09:00`, from the first day's opening to the last day's closing. Calendar feed in UTC (`Z`), no time-zone block. A multi-day timed edition is the first day's hours with `RRULE:FREQ=DAILY;COUNT=<days>`, because one block from the first opening to the last closing would claim the event runs through the night. The When row reads "Sat 20 to Sun 21 Feb 2027, 10:00 to 17:00 Japan time each day". Google's add-event form documents no repeat rule, so its link gives such an edition as all-day dates with the daily hours as the first line of the details.

### 6.2 Structured data

One `schema.org/Event` block per edition: on the edition page if it exists, otherwise on the evergreen page. Cancelled maps to `EventCancelled`. Tentative stays `EventScheduled` with a visible caveat on the page.

A known fee gives `isAccessibleForFree` and an `offers` with the price in JPY and no `url`, since Google means a ticket page by that and the data has none. The `organizer` carries a name only: `official_url` is often a tourism listing, a blog post or an Instagram account rather than the organiser's site, so giving it as the organiser's URL would be a false claim.

The home page carries a `WebSite` block (site name and root URL) and no other page does. Google takes the site name shown in its results from it.

Edition pages also carry a `BreadcrumbList` matching the visible trail above the `<h1>`: Home › event › edition label (e.g. "Autumn 2026"), the last entry unlinked, marked `aria-current="page"` and given no `item` URL. Evergreen pages, the home page and About have no trail, because it would say only "Home", which the header mark already is.

### 6.3 Calendar feed

- The file name is the calendar's name in Thunderbird, which has never read `X-WR-CALNAME` (bugzilla 168176, open since 2002) and names a subscription after the last path segment of its URL. `events.ics` showed as "events". Apple Calendar and Outlook read `X-WR-CALNAME`; `NAME` is RFC 7986's spelling of it, sent for clients that prefer it. Renaming the file breaks every existing subscription, so it is now as fixed as an edition ID.
- Every page offers a live subscription: a `webcal://` link for Apple Calendar and Outlook, and the `https://` URL for Google Calendar. A plain download would never receive updates.
- Each confirmed edition can also be added on its own, since 2026-10-17. Two links sit under the date in an edition page's When row, and in a row of their own under the edition's row in the event page's Dates table, running from the Dates column to the right-hand edge, since a phone leaves the Dates column alone too narrow (the row carries no label, as the row above names the edition): "Add to Apple Calendar or Outlook" downloads `/events/<slug>/<edition-id>.ics`, and "Add to Google Calendar" opens Google's add-event form (`calendar.google.com/calendar/render?action=TEMPLATE`) filled from the same record, because Google Calendar on Android cannot open an .ics file. The file holds the feed's own `VEVENT` for that edition, UID included, so an app that also subscribes sees one event. It carries no calendar name, so the app adds the event to a calendar the visitor already has instead of offering a new one. A saved copy never updates, so tentative and cancelled editions get neither link nor file. The links carry `data-hide-after` with the last day, and a script removes them once that day has ended in Japan; without JavaScript they stay, which does no harm.
- `UID` is `<slug>-<edition-id>@<domain>` and never changes. `DTSTAMP` comes from `last_verified`. Add 1 to `sequence` whenever a published date changes.

### 6.4 Map links

- A venue with `lat` and `lon` gets a `Map` link under its address on the evergreen page and on each edition page, pointing at `https://maps.apple.com/?ll=<lat>,<lon>&q=<venue>`. `ll` fixes the point and `q` only labels the pin, so a link can never search its way to the wrong place.
- The pair is optional and the page simply omits the link without it. Half a pair fails the build, as does a pair outside Japan's bounding box, which is what a swapped or mistyped pair looks like.
- Coordinates belong to the venue they were taken at, so an edition that names a `venue_en` of its own does not inherit the event's pin: it links only if it carries its own pair.
- Recorded to 4 decimal places (about 11 m) from a geocoder, never read off a map by eye, and cross-checked against a second source. Same rule as the route chart: what the map shows cannot contradict the address printed beside it.
- The pair also becomes `GEO` in the calendar feed and `geo` on the JSON-LD `Place`.
- The link carries a pin glyph before the word. It is inline SVG in `templates/icons.html`, like the header mark, so the site still ships no image files and makes no extra request: drawn on a 24 grid at `stroke-width` 2, coloured with `currentColor` so one glyph works in both themes, sized in the markup so a missing stylesheet leaves a 16px pin rather than a full-width one, and `aria-hidden` because "Map" already says it. The "Videos of the 2025 edition" link carries a play glyph drawn to the same rules (`video_icon` in the same file), and so do the home list's fact glyphs: the same pin before the prefecture, a ticket before the admission, a road between two ends before "Driven route", and a car in profile before "Cars to". All share the `.icon` class for their spacing.

### 6.5 Design tokens

Plain CSS only: no preprocessor, no custom properties, no framework, so the site works on old and budget devices where `var()` is unsupported. Tokens are therefore a convention, written as literal values in `static/style.css` and restated under the dark-mode media query. Use only these values; add to the set with a reason rather than inventing a one-off.

| Token | Light | Dark |
|---|---|---|
| ink | `#1C1C1C` | `#EBEBEB` |
| background | `#FFFFFF` | `#141414` |
| muted | `#5C5C5C` | `#A8A8A8` |
| rule | `#E0E0E0` | `#333333` |
| brand (logo swoosh, links, focus ring, chart bars, status dot, "This weekend" badge and the home list's date-leaf band, both with background-token text) | `#8C1C24` | `#D0636A` |
| note background / ink | `#FFF4D6` / `#5E4700` | `#3A300F` / `#F3D98B` |
| cancelled background / ink | `#FBE9E5` / `#8E2A1B` | `#3A1C16` / `#F2A493` |

The brand red is the site's one accent, so red on its own does not mean cancelled. Cancelled keeps its own darker red (1.08:1 from the brand red, so effectively the same colour) and is told apart by the word, the tinted box behind a badge or note, and the cross in the Dates table. The header logo is the designer's lockup (`ref/logo/cmj-logo-3-wordmark-lockup-v3.svg`, wordmark in Liberation Serif converted to outlines) inlined in `templates/base.html` without its background rect and metadata. The swoosh is coloured from the stylesheet and the wordmark uses `currentColor`, so both change in dark mode. The favicon is the swoosh in white on a brand-red tile, redrawn on a 32 grid (stretched 1.6x vertically and thickened under the peak, since at true proportions it is under a pixel thick). `tools/favicon.py` draws both `static/favicon.svg` and the 16/32/48 `static/favicon.ico` from the logo file; it needs Pillow in the local `.venv` only, and a test fails if either file differs from a fresh run.

Spacing, on a 4/8 scale: 4, 8, 16, 24, 32, 48. A margin may also be one of these negated, as the container's half of the margins that stand in for flex `gap` on a row that wraps. Radius 8, and 4 for the focus ring and the flags only, since an 8px radius turns the outline round a short link, or a flag 16px high, into a pill. Measure 720. Type: 32, 24, 20, 16.

`StylesheetTokenTests` enforces these values for colours, font sizes, margin, padding, gap and border-radius. Its sets in `tests/test_build.py` are the enforced copy; change them with this table.

Two browser-support rules the stylesheet keeps:
- **No flex `gap`.** It resolves to nothing on IE and on Safari before 14.1, with no fallback, so a row silently closes up. Use margins on the children.
- **Grid is allowed** for `.events` and `.facts` because it degrades to readable stacked blocks where unsupported. `gap` inside a grid is fine for the same reason.

Both are pinned by tests, not by comment.

### 6.6 Japanese page

An experiment, set 2026-10-18 because 86% of the YouTube channel's views and most of the site's search visitors were in Japan. It shows every edition in Japanese without a single translated sentence: all of it is generated from fields the data already has, so a new event costs nothing here.

| Shown | From |
|---|---|
| Name | `name_ja`, or the English name inside `lang="en"` when the event has none, so a screen reader does not read it with Japanese rules |
| Dates | `fmt_span_ja`: 10月18日(日), 10月24日(土)〜25日(日); both years when a span crosses one. Month headings 2026年10月 |
| Hours | `start_time`〜`end_time` on a timed edition, with （各日） when it spans days |
| Prefecture | `PREFECTURES_JA`, all 47, checked against Japan Post's postcode data. Validation rejects any `prefecture` not in it, on an event or an edition |
| Admission | 入場無料, 入場料 1,000円, or 入場料未発表 |
| Status | 日程未確定 (tentative), 中止 (cancelled) |
| Links | 情報元： and the `official_url` domain, not 公式サイト, since `official_url` is often a tourism listing or a blog (the reason `event.html` says Source); 詳細（英語） to the English page |

Left out: venues (the data holds English names only, and a Japanese one would need a lookup for every event), routes, entry lists, videos and prose. Past editions drop out in the browser, as on the home page, and a month goes with its last one. The page is `lang="ja"`; the logo link and the footer are `lang="en"`. `/` and `/ja/` name each other with `hreflang`, and no other page carries it.

**The experiment's rule:** keep the page if it gets 20 or more visits in the month to 2027-01-18 from outside referrers (search engines or other sites); otherwise delete it, with `templates/ja.html`, the `_ja` helpers, `JA_LEDE`, the header links and their tests. `PREFECTURES_JA` and its validation can stay. Raw visits overstate demand, since English readers click 日本語 out of curiosity, so measure in Fathom filtered to Page = `/ja/`, read by Referrers. `tools/reviews.yml` raises the check on the day.

## 7. Editorial rules

- Every page shows its last verified date and links the official source. On an event or edition page both sit in the facts block ("Last verified 2026-10-06, against careventnavi.jp"). The source is named by its domain, because `source_url` and `official_url` are often a listing, a blog post, a venue's page or a video rather than the organiser's own, and a domain is true of all of them. The event page shows the organiser as plain text beside a "Source" link to `official_url`, and its date is the latest check of the event or any edition, so it names no single source, above the entry list and route, not in the footer: it is what sets the site apart from longer lists, so it must not be under 90 table rows. The home page footer gives the most recent check across all of them.
- Entry lists show "As of YYYY-MM-DD" under their heading (which already says what the list is) and, while provisional, "Provisional: cars may withdraw or change." A list published before the event stops being provisional once the edition has been re-verified after `end`: at that point the published list is the last word, so the warning would be false. Re-verifying on the closing day is not enough, because cars can still withdraw during the event.
- The pages state what is true and let the reader draw the conclusion. No advice, no recommendation, no telling a visitor what a fact means for their day. Every sentence has to carry a fact that would be lost if it were cut. `EDITORIAL_PHRASES` enforces the part of this a list can enforce.
- Translations are drafted, then human-reviewed. Never auto-published.
- Japanese names appear alongside English.
- No personal data, ever.

## 8. SEO

Titles carry search intent. Event and edition pages carry no brand suffix: Google shows the site name separately, taken from the WebSite JSON-LD, and with the suffix 41 of 64 titles ran past the roughly 60 characters a result shows (audit of the live site, 2026-10-20). The home, Japanese, About and 404 pages keep it, because without it "About" names nothing. The home-page title is fixed text, with no year: a year taken from the data named the furthest edition, so it read 2027 during 2026.

- `Classic car events in Japan | Classic Motoring Japan`
- `<Event name>: Visitor Guide`
- `<Event name> <edition>: <sections, as the page names them>`

Every page but the 404 carries a `description` and Open Graph tags (`og:title`, `og:description`, `og:url`, `og:type`, `og:site_name`, `og:locale`), with `og:url` equal to the canonical link. `og:locale` is `en_GB` on English pages and `ja_JP` on the Japanese one; left out, link previews assume `en_US`. No `og:image`: the site has no images of its own. Embedded videos bring YouTube's thumbnails, which are not the site's to put in a share card. The description is derived, never stored. An event page's is capped at 160 characters, about what a result snippet shows, and over the cap the build fails and names the event. Edition descriptions are not capped: they are built only from facts (name, dates, venue), so a status prefix or one more section would otherwise force a venue name to be shortened to meet a soft search limit.

| Page | Description |
|---|---|
| Home | `SITE_LEDE` |
| Evergreen | First sentence of `summary_en`, links reduced to their text; without a summary, "Dates, venue and admission for <name> in <prefecture>." So the summary's first sentence has to fit the cap on its own. |
| Edition | "[Cancelled. / Dates not confirmed.] <Route / Entry list / Cars on display, as the page names them> for <name year>: <dates>, <venue>, <prefecture>." Status leads, so a cancelled edition's snippet cannot read as a listing. |
| About | `ABOUT_DESCRIPTION` |
| Japanese timetable | `JA_LEDE`, which is also its lede |

Plus JSON-LD, `sitemap.xml`, the calendar feed, semantic HTML, and no client-side rendering of primary content.

### 8.1 Agent readability

GitHub Pages serves static files and sets no response headers of ours, so anything needing
content negotiation or a `Link:` header cannot be published from here at all. That rules out
Markdown negotiation (`Accept: text/markdown`) and RFC 8288 link relations permanently, short
of moving the site behind a proxy. What a file on disk can say:

| File | Standard | Holds |
|---|---|---|
| `/robots.txt` | Content Signals; IETF AIPREF drafts | `Content-Signal: search=yes, ai-input=yes, ai-train=no`, and the same preferences as `Content-Usage: search=y, ai-use=y, train-ai=n` |
| `/api/events.json` | none | Every edition, from the same rows as the pages and the calendar |
| `/llms.txt` | llmstxt.org | Index of every page, and of the machine formats |
| `/.well-known/ard.json` | ARD v0.91 (`specVersion` 1.0 is the AI Catalog's) | Three entries: the JSON feed, the calendar, `llms.txt` |
| `/.well-known/ai-catalog.json` | ARD predecessor | The same bytes, at the path scanners still read |
| `/.well-known/api-catalog` | RFC 9727 | Linkset anchored on the JSON and calendar feeds, with the About page, which lists both, as `service-doc` |

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
follows the same rule: `isAccessibleForFree` and `offers` are omitted rather than set to
false or 0, since either is a claim about the price and not the absence of one.

`actions/upload-pages-artifact` must be v5 with `include-hidden-files: true`. From v4 the
action tars the site with `--exclude=".[^/]*"`, which strips every dot-path, so `.well-known/`
never reaches Pages and both catalogs 404 on an otherwise green run. Nothing in the build or
the run reports it. `DeployWorkflowTests` guards the flag.

`/.well-known/api-catalog` serves as `application/octet-stream`, because RFC 9727 fixes a
path with no file extension and Pages types a file by its extension alone. RFC 9727 asks for
`application/linkset+json`. The body is correct and parses; the type cannot be corrected from
here, so this is the same class of limit as the `Link:` header, not something left undone.

### 8.2 IndexNow

IndexNow is the only way to tell Bing about a new page without a Bing account, and Bing's index
also feeds DuckDuckGo, Yahoo and Ecosia. Google does not take part and has had no anonymous ping
since 2023, so Google finds pages through the `Sitemap:` line in `robots.txt` alone. No search
engine account is used or wanted.

The key is `INDEXNOW_KEY` in `scripts/build.py`, and the build writes it to `/<key>.txt` at the
root, where it covers every URL on the host. It is public on purpose: engines fetch it to confirm
a submission came from the site. `scripts/indexnow.py` runs in two places in the workflow:

| Step | When | Does |
|---|---|---|
| `changed` | Build job, after the build, before deploy | Fetches every sitemap URL live and keeps those whose bytes differ from the new build |
| `submit` | Own job, after deploy | Posts those URLs to `api.indexnow.org` |

- The live site is the record of what was last sent, so nothing is stored. The comparison has to
  run before deploy, since afterwards the live site is the new build.
- A live page that cannot be fetched (a new page 404s, or a timeout) counts as changed.
- If the key file is not live, nothing has ever been sent, and every page goes once.
- Neither step can block a deploy. `changed` is `continue-on-error`. `submit` goes red only on
  400, 403 or 422, which mean the key or the request is wrong; any other answer, or no answer, is
  a warning.
- Not covered, by choice: a deleted page is never submitted (the next crawl finds the 404), and a
  page whose submission failed is not retried until it changes again.
- Changing the key only means the next deploy resubmits every page.

The first upload must put the workflow up before the scripts. Scripts first would put the key
file live while no comparison step exists, and the first real run would then see the key, treat
the site as already submitted, and send only changed pages. Workflow first, then `scripts` and
`tests` in one drag.

## 9. Open questions

1. Photo archive size: decides whether photos go in the repository or in separate storage such as R2.
2. Is the source list for the 10 to 15 events complete, or is discovery still needed?
