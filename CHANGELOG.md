# Changelog

## 1.4.0 — One drill-down graph and integrated patterns

- Traffic starts at **all years**, then drill into **months → weeks → days → individual hours** by clicking the graph. Show the period breadcrumb at all times, with one-step Zoom out.
- A selected day displays local **time under every hourly point**. All 24 hour-of-day average ticks are individually labelled and can scroll horizontally on mobile rather than being skipped.
- Preserve one metric switch for estimated visits, unique aircraft, and observations; line/bar chart switch remains.
- One Show pies/Show bars control switches **all three** category/type/operator breakdowns together.
- Move the compact weekday × hour heatmap, average weekday, and average hour into the same Traffic page, synchronised to the current date and filters. A selected calendar day shows just one heatmap row.
- Remove Compare, separate Patterns page, Saved Views and duplicated top navigation on phones. On mobile, use one bottom navigation bar.
- Keep the separate launcher, read-only Aerodrome database, and existing authenticated update system untouched.
- Clip the earliest year to when Aerodrome history actually begins, avoiding months of misleading zero-valued data prior to collection.

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
