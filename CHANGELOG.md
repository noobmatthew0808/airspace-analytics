# Changelog

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
