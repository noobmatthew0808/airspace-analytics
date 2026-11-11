# Changelog

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
