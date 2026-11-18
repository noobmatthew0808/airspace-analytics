# v1.10.12 — Live ADS-B is table-only on every device

- Both **Raw** and **Nice** modes are proper sortable website tables, not cards and not a console-text block. Raw keeps all 12 original `viewadsb` columns and their actual native stream; Nice adds the aircraft **type** column alongside registration, country, route (three-letter IATA), distance and message counts.
- Tap any heading (including **Aircraft type**) once to sort ascending, again to sort descending. Each view has a `Sort` dropdown for fields hidden in the compact mobile view, plus a direction control. Default `Receiver order` preserves the original incoming order.
- On phones **Fit screen** automatically presents six high-value table columns with readable text and no zoom controls. Optional **All columns** exposes the complete horizontal scrolling table, retaining a sticky first column. This applies to Raw and Nice.
- Raw uses restrained terminal-inspired mono styling; Nice is the same live table with the site's standard styling. No change to the stream's ~500ms refresh cadence, metadata enrichment implementation, service permissions, database or other website tabs.
- Website connections still pause when Safari is backgrounded or the user leaves Live; Ultrafeeder continues running.

# v1.10.11 — Mobile-friendly Live ADS-B with Raw/Nice toggle

- Add **Nice UI** aircraft cards for phones and sortable table for desktop, alongside the existing **Raw UI** viewadsb console. Raw view adds smaller mobile typography, horizontal scrolling and text size buttons; the original 500 ms terminal stream is preserved unchanged.
- Nice UI includes registration, country, squawk, route, distance, messages and signal strength. Routes display **IATA three-letter codes only** (such as `LGW – MAD`). A missing code, unknown aircraft or unresolved route stays blank instead of inventing a value.
- Reuse the local readsb `aircraft.json`, Aerodrome's read-only `seen_aircraft` and `route_cache`, its shipped airport ICAO→IATA map, and (for uncached airline callsigns) Aerodrome's existing route-resolver HTTP endpoint. Metadata is requested approximately every eight seconds only while Live is visible; the live PTY screen still refreshes on every original terminal redraw.
- Close the on-demand terminal stream and metadata requests whenever the browser tab is hidden, the device locks, or the visitor navigates away. Ultrafeeder continues decoding independently.
- No new collectors, persistent databases, pip/npm packages or changed feeder/systemd configuration. Traffic, Alerts, Settings and other features unchanged.

# v1.10.10 — Live terminal cleanup and Docker permission guidance

- Removed the explanatory paragraph beneath the Live ADS-B terminal; other Live page elements and all other website pages are unchanged.
- Improved the terminal header to identify Docker socket permission failures explicitly instead of only reporting that the terminal exited.
- Documented the optional Linux service-user Docker permission fix. No permissions are changed automatically, and no feeders, databases, Docker containers, or other systemd services are modified.

# v1.10.9 — Live ADS-B terminal

- Added a Live ADS-B tab with a direct read-only stream of the existing viewadsb terminal (native ~500ms refresh, not 1s aircraft.json polling).
- Separated stream from Alerts, Traffic and Aerodrome; closes viewer when leaving the page and limits concurrent viewers.
- Requires website user Docker access; does not change permissions, install software or restart feeders. Routes need separate enrichment.

# v1.10.8 — Read-only Healthchecks monitoring in Settings (17 November 2026)

- Add a collapsible **Server monitoring** section inside Settings, showing the existing Ubuntu Server and ADSB.im Receiver Healthchecks.io statuses, last/next heartbeat, schedule, grace and recorded downtime intervals.
- Retrieve status changes through Healthchecks.io's free read-only Management API v3 using a backend-only project key, with a 45-second cache and no browser-side credentials or additional dependencies.
- Display only actual recorded down/up transitions; unknown history is never counted as uptime. History follows Healthchecks.io retention (current calendar month and two prior months).
- Supports iPhone/desktop, manual refresh and an automatic refresh while Settings monitoring is open.
- A check outside the read-only key's project appears as unavailable, **not down**.
- No changes to Traffic charts, Alerts logic, aircraft data, Aerodrome, Docker, feeder services, notification delivery or existing Settings functions.

# v1.10.7 — Local map opens selected aircraft from ntfy (15 November 2026)

- Tapping a real Airspace Analytics ntfy aircraft notification now opens local tar1090 with the matched aircraft selected, centered and highlighted using its ICAO hex.
- The app detects its home LAN address automatically, preferring 192.168.x.x; no Tailscale, Shortcuts, manual URL configuration or public access needed.
- The existing Send test button opens the local tar1090 map without selecting a plane.
- No changes to alert matching, notification delivery/retries, Traffic, Aerodrome, ADS-B feeder processes, database schema, or other preferences.
- Test the actual tap behaviour on an iPhone connected to the same home Wi-Fi; historical alerts may target an aircraft no longer in live receiver range.

# v1.10.5 — Repair Activity calendar month default (15 November 2026)

- Correct an existing startup migration that forced the Activity calendar to the year view after v1.10.4 initialized its month default.
- Opening Traffic now shows the current month in Europe/London automatically. The existing Back to year button still shows the entire year and month-selection buttons still work.
- Only change the calendar initialization; no changes to the Traffic charts, analytics, Alerts, notifications, database, or updater.
- Add a startup-execution regression test to prevent the calendar default from being overwritten again.

# v1.10.4 — Default Activity calendar to current month (15 November 2026)

- When Traffic loads, open the Activity calendar on the current UK month instead of its full-year overview.
- Keep the existing year overview, month selection, Back to year navigation, Traffic chart, drilldowns, Alerts, Aerodrome database, notifications and updater unchanged.

# v1.10.3 — Larger alert lists and more accurate aircraft count

- Allow up to 100 patterns per Alerts rule.
- Show recent aircraft rather than only new database rows when using Aerodrome fallback.
- Preserve incremental alert matching, existing Traffic and notification delivery.
- Add tests for 31 registrations, the 100-item limit and stable counts.

# v1.10.2 — Aerodrome alert fallback and compact Alerts page (15 November 2026)

- Continue preferring fresh tar1090 aircraft.json when available.
- If live HTTP isn't reachable, read only newly recorded sightings from Aerodrome's existing SQLite history; calculate position/altitude conditions using antenna coordinates saved locally in Alerts.
- Never copy aircraft history or write to Aerodrome; limit the recent-sightings query to 2,500 newest rows and ignore stale observations.
- Track processed row IDs to prevent a single recorded outside-position from counting as multiple exits. The connection-test action never consumes an observation.
- Preserve seven decimal places when saving antenna latitude and longitude (previously rounded to two, introducing up to hundreds of metres of distance error).
- Remove Beluga/A380/Boeing 747/A340 shortcut buttons; all aircraft types are still configurable with Add rule.
- Keep Traffic, heatmaps, settings, ntfy delivery, chart zoom and updater unchanged.

# v1.10.1 — Receiver connection fix (15 November 2026)

- Detect ADS-B aircraft.json on this Linux machine's LAN IP as well as localhost, including tar1090's /map/data and /data paths on ports 1099 and 8080.
- Allow editing the receiver feed URL in Alerts using the machine's actual LAN IPv4 address, but reject other devices and external hosts.
- Remember the most recently working feed path; show it on a successful connection test.
- Skip HTTP proxies and external redirects for local receiver requests.
- Add dedicated regression tests. No changes to Traffic, Aerodrome history, alert matching, ntfy delivery or the website updater.

# v1.10.0 — Aircraft alerts (staged)

- Open Receiver setup inside Alerts for auto-detected or manually configured local feed/antenna coordinates, with connection test.
- Improve malformed aircraft field handling and broaden A340/747 ICAO type presets.
- Update obsolete Traffic contract tests to match v1.9.8 and require all tests to pass cleanly.

- New compact Alerts tab beside Traffic; previous Traffic drilldown, charts and launcher unchanged.
- Per-aircraft ICAO hex state tracking, independent rules for type, registration, callsign, hex, operator or military; distance and minimum/maximum barometric altitude filters.
- Live Ultrafeeder JSON polling with receiver.json location, read-only Aerodrome metadata fallback, and separate local alerts-only SQLite state (not a second sightings database).
- ntfy settings, optional bearer token, test push and recent events. Events rearm on confirmed exit, not a shared type-wide cooldown; handles temporary position loss and signal jitter.
- Work in isolated feature branch pending local receiver/ntfy acceptance and full regression checks; release to main only after review.

# Changelog

## v1.9.8 — 13 November 2026
- Make launcher management a compact list with individually expandable shortcut editors; keep Save, Remove, Reorder, Add and Restore Defaults.
- Leave the v1.9.7 daily Traffic default, automatic midnight rollover, measure buttons, all-time average exclusions, database navigation and dark theme unchanged.
- Add regression tests for editor rendering and existing controls. No Aerodrome or feeder changes.


## v1.9.7 — 13 November 2026
- Default Traffic to today's Europe/London calendar day with its full hourly x-axis, without changing zoom or saved aircraft history. Roll to the next date at midnight and on tab return.
- Offer Visits, Aircraft and Samples as live buttons beside the Traffic heading; keep dark theme only.
- Exclude 9 November 2026 from all-time weekday/hour averages by default. Add/remove other excluded days in Settings. This browser-only preference never changes Aerodrome's SQLite data or the main graph.
- Keep launcher link management collapsed until selected. Make the existing Aerodrome database details panel an invisible link to the database explorer.
- Preserve current service launcher, charts, date heatmap, database browsing, and updater logic; add new regression tests.


## v1.9.6 — 11 November 2026
- Roll back v1.9.5's unsupported Safari deep-link scheme after iOS reported invalid addresses.
- Restore the exact working v1.9.4 launcher: normal HTTP(S) links and prior browser behaviour.
- Add regression tests. Leave all charts, calendars, database code, styling and updater unchanged.


## v1.9.5 — 11 November 2026
- On iOS Home Screen web apps, launcher links request full Safari via the iOS 17+ x-safari-http(s) URL scheme (including HTTP local addresses).
- Leave links unchanged in regular Safari, Android, desktop browsers, and internal Airspace Analytics navigation.
- Add browser-simulation regression tests for both local and external launcher links.
- No edits to styles, database, Aerodrome collection, heatmaps, charts, or updater.


## v1.9.4 — 11 November 2026
- Fix launcher error `$(...).forEach is not a function` by using the multi-element `$$()` selector.
- Add a regression test for single-element selectors used with Array methods.
- No changes to traffic charts, database, heatmap, links, logos, updater, or styling.


## v1.9.3 — 11 November 2026
- Restore Aerodrome to View Stats and repair ADSB.im's port to 1099 on existing browsers, keeping custom launcher shortcuts.
- Show official Aerodrome and SkyStats icons; improve icon fit and permit only their trusted image hosts.
- Prevent a future-month selection from hiding the year calendar with “Start must be before end”. Back to year remains available.
- Preserve the entire ADS-B analytics/query engine, charts, zoom, calendar rendering, and updater.


## v1.9.2 — 11 November 2026
- Equal-size month cards throughout the year activity calendar on desktop and mobile.
- Unrecorded days remain blank, and tapping a month works as before.
- No changes to aircraft statistics or other website sections.

## v1.9.1 — 11 November 2026
- Complete the exact requested launcher shortcuts and service-logo fallback, including browser migration of previously saved built-in shortcuts.
- Preserve the existing mobile Traffic layout and 38 passing tests while refining desktop graph/calendar proportions.
- Keep the Settings shortcut editor functional with logo-domain and secondary feeder-map fields.


## v1.9.0 — 11 November 2026
- Desktop-only Traffic layout: a wider working area, shorter main traffic chart and six calendar months per row on large monitors. Phone Traffic layout and its graph interactions remain unchanged.
- Launcher rebuilt into **View Stats** and **Feeder Website Status** with the exact supplied receiver addresses, plus independent feeder-map links for Plane Finder and ADS-B Exchange.
- Brand-coloured icons use service website favicons where available, with matching readable local fallback marks when offline. Existing app favicon is used for the Airspace Analytics tile.
- One-time migration refreshes the built-in link destinations while preserving custom-added links; the Settings editor now supports group, logo domain and an optional second link.
- No Aerodrome database, ADS-B feeder, systemd service, retention, or updater logic changes.


## v1.8.0 — 10 November 2026
- Year calendar now leaves days with no actual observed aircraft empty rather than colouring zero-filled API buckets. Unobserved days have faint unboxed date numbers only.
- Year calendar is the default. Tap anywhere on a month card to open that month's daily calendar; tap the year button to return. Removed the Year/Month selector.
- Added verified airline ICAO callsign prefixes observed in the user's hourly export (Eurowings, BA Cityflyer, Norwegian, ITA, easyJet Switzerland, DHL, AJet, Air Algérie, AeroLogic, etc.) and normalised known 3-letter operator codes to full names.
- Actual user export analysis: 3,972 hourly records; 424 commercial records had previously unrecognised nonblank callsign prefixes; 223 had no usable callsign/operator. Residual Unknown is kept rather than invented.
- All Aerodrome and receiver data remain read-only. No feeder or service configuration changed.


## v1.7.0 — 10 November 2026
- Sparse traffic charts place year/month/week bars at the left, retaining full-width time scale.
- No transient corner notifications.
- Year heatmap is a full 12-month calendar of daily traffic; select a month for its month calendar.
- Removed Week and Day heatmap controls.
- GitHub updates are one-click from trusted local/Tailscale clients, with same-origin checks but no update token required.
- Estimated commercial visits first marked Unknown are attributed to a recognised airline if a callsign appears later within the same continuous visit.
- Added tests for sparse chart layout, calendar drilldown and airline late identification.

# Changelog

## v1.5.0 — 10 November 2026
- Restored v1.3 traffic chart zoom behaviour, rather than v1.4 fixed year-to-hour navigation.
- Hourly and average-by-hour charts fit phone width, with every hour labelled on 24-hour views.
- Selected date period moved to a header above the main graph; hourly x-axis shows hour numbers only.
- Removed horizontal chart scrolling and touch pointermove tooltips; taps still zoom into traffic intervals.
- Replaced sidebar/mobile bottom tabs with Home, Traffic and Patterns at top left, Settings cog at top right.
- Removed Compare, Aircraft and Saved Views navigation; moved Database into Settings as a link.
- Kept the v1.3 analytics and read-only Aerodrome database engine. Added an optional read-only script for unknown airline diagnosis.
- Single chart-style button controls all breakdown panels.

# Changelog

## 1.3.0 — Flexible analysis and cleaner presentation

- Replaced time-preset chips and the 46-hour example with a single duration control (minutes through years), custom UK date/time range, or all history. Available in Traffic, Patterns and Compare.
- Remove explanatory boxes, installation/about section, and recurring caveat banners; retain real error messages.
- Fix weekday averages showing 0 after a fresh Aerodrome install: include observed partial days when enough minute samples exist; no sample now returns null/dash, not zero.
- Separate commercial airline breakdown from all-aviation operator breakdown. Add conservative airline-prefix inference from recognised commercial callsigns; no records or categories are overwritten.
- Make existing update pairing automatic on the browser that already has a token, and hide the token input under optional new-browser pairing. The backend remains authenticated.
- Numeric comparison offset rather than a list of arbitrary preset choices.


## 1.2.0 — Compact redesign

- Separate application launcher at `/`, with Airspace Analytics pinned as the first link. No duplicated statistics, large hero, or promotional copy.
- Analytics workspace available at `/analytics` on the **same port**, retaining the existing Aerodrome read-only data APIs.
- Reduced analytics navigation to Traffic, Patterns, Compare, Aircraft, Database and Settings.
- Simplified Traffic view: single primary graph, metric toggle, quick date choices, automatic grouping, click-to-drill, Zoom out/Reset, and line/bar modes.
- Moved aviation breakdowns, deeper filters, explanations and saved views into collapsible sections.
- Launcher links now support Add, Remove, Move up/down, Reset defaults and editable full URLs/ports; the pinned Analytics link cannot be accidentally deleted.
- Retained the existing in-app authenticated GitHub updater and prior `sessionStorage` update token.
- Mobile interface and typography redesigned for density and clarity.

## 1.1.0

Original release with Aerodrome read-only reporting, update controls, and historical analysis.
