# v1.10.31 — AvioADSB connection test

- Use the same application User-Agent for the AvioADSB connection test as the existing aircraft snapshot request, verified by the user's terminal comparison. Add an offline regression test. No other behavior changed.

# v1.10.30 — aligned live status and durable evidence

- Align registration and live status in separate fixed subcolumns, use a full-width expanded row with receiver last-seen and tracking links, and emphasize LGW in the live status, not the historical route.
- Use adsb.fi's documented feeder snapshot for multiple registrations; add optional ADSBiq contributor snapshot and its route fields, stagger source requests, retain actual observation times and local sightings through misses, normalize ICAO airport history to IATA, and expose provider health in the cached live response. Expire airborne evidence after 120 seconds and retain observed landing evidence up to seven days with time shown in details. Preserve previous route and registration handling.
- Add ADSBiq key configuration and more informative AvioADSB test errors; keep secrets in existing private local state. No external keys committed. No Traffic, exclusion, notification or receiver logic changed.

# v1.10.29 — mobile fit, recovered callsign routes, registration changes and AvioADSB

- Inset the mobile table, align full-width dividers, simplify expanded details, and retain the registration at the time of flight while tracking the current registration.
- Display the usual callsign itinerary as a fallback (evidence in expanded details), preserve routes across provider changes for the same callsign, and retain stricter LGW highlighting.
- Serialize suggested-exclusion queries to prevent them contending with each other; bounded automatic retry and a manual Retry button, never automatic exclusion.
- Add optional AvioADSB contributor global aircraft snapshot support with private key configuration under Alerts → Configuration & Logs → APIs, no faster than every eight minutes; do not use it for alert rules.

# v1.10.28 — compact flight rows and background status cache

- Display date as DD/MM/YY and place compact airport/route/Flying/N/A status beside registration. Expand flight details inline; preserve FR24, Aerodrome, filters and Manage controls.
- Refresh registration statuses on the server independently of browser visits, persist a bounded atomic local cache, and retain recently observed airport evidence for up to 24 hours. Expire stale airborne positions; never promote usual routes to current routes. Use existing provider rotation and throttles.
- Add isolated regression tests for compact states, expiry and evidence.

# v1.10.27 — Suggested dates to exclude (manual review)

- In Settings → Excluded days from averages, add **Suggested dates to exclude** beneath the existing manual exclusion list. Suggestions load only when this section is expanded; each proposal shows the date, estimated visits versus a historical median, observation records versus a historical median, percentage drops and comparison sample size.
- Analyze the last 90 days of Aerodrome's existing read-only daily analytics, prefer same-weekday comparisons where there are at least three earlier matches, and otherwise use 7–28 earlier recorded dates. Suggest only when both estimated visits (at least 50% down) and observation records (at least 35% down) are unusually low. Skip today, the first partial date, dates with no recorded observations and already-excluded dates; show no suggestions if there is insufficient evidence.
- **Never exclude automatically.** A date is added to the existing browser-only excluded-days storage solely when its **Add to excluded** button is pressed. The 64-date cap, Include again controls and current weekday/hour average calculations remain unchanged. No Aerodrome database writes, background monitoring, new service or external dependencies.
- Add a compact responsive card layout and deterministic regression tests for confidence thresholds, missing data, incomplete dates, existing exclusions and explicit manual-only action. Leave Traffic, Alerts, Flights, receiver and updater behaviour unchanged.

# v1.10.26 — Activity Calendar month Graph button

- Correct the location of the new month-ranking option: add **Graph** beside the year-back control inside the **Activity Calendar** month header (as pictured by the user). It is absent from the twelve-month calendar year view.
- Pressing Graph expands/collapses a busiest-to-quietest daily ranking using the **already-fetched calendar daily analytics**, current Traffic metric and filters. No additional network calls, database changes, chart modifications or new UI outside the Activity Calendar.
- Leave the prior main chart and every other Traffic, Alerts, Flights, feeder and notification feature untouched. Extend the existing month-ranking browser regression to verify the calendar month/year markup and event wiring.

# v1.10.25 — Month Traffic Graph button: busiest days

- Only when the main Traffic chart is drilled into a **single calendar month** (the month-to-week timeline level), display a small **Graph** button alongside the existing chart controls.
- Press Graph to expand or collapse a compact daily ranked list, sorting every date returned by the existing **daily** analytics endpoint from most to fewest observations for the selected metric (Visits/Aircraft/Samples), breaking ties by ascending date. Days without recorded observations are marked — and kept at the bottom; zero could otherwise imply the receiver was online.
- The original chart, year/month/week/day/hour navigation, filters, metric selection, graph types, alerts, flight log, database and other pages are unmodified. The additional read-only daily request only runs when the user taps Graph, and stale responses are discarded on navigation.
- Added deterministic Node regression tests for month-only visibility, 2026 December rollover, leap year, sorting/ties/missing observations and Traffic wiring; full Python/browser and unchanged Traffic anchor regression still run.

# v1.10.24 — Include registration in aircraft push notifications

- Every ntfy aircraft alert now shows **callsign · registration · aircraft type · distance · altitude** when the registration is known, e.g. `WUK83GK · G-WUKU · A21N · 40.0 km · 9,725 ft`. If only one identifier is available, show it once; do not display empty placeholders or duplicate callsign/registration values.
- Keep the existing ntfy topic, priority, tap-to-tar1090 aircraft selection, source label, per-aircraft deduplication, alert rules and API configuration. No changes to the alert threshold logic, ADS-B receiver or website's other pages.
- Offline regression test covers complete callsign+registration, callsign-only, registration-only, identical identifiers, altitude/distance preservation and delivered status.

# v1.10.23 — Fix Flights clipping and add real route/history sources

- Make flight list its own lower-padding, full-width section beneath existing filters. Replace the accumulated conflicting mobile table sizing with one deterministic CSS-grid five-column row (Date/Route/Flight/Reg+live/Who), hard min-width rules and no sideways clipping. Show compact Who label on phone and preserve full names in details/SheetDB; use consistent regular-weight route and registration text.
- Research confirmed ADSB.im is the source for the user's feeder tar1090 routes (historical aggregator patterns plus ACARS/VDL2). Prefer its `/api/0/routeset` in one batched, cached asynchronous source lookup; fall back to adsb.lol only when necessary. Validate actual HTTP response shape and plausibility flags; report source health without exposing private keys.
- Use existing saved FlyItalyADSB key to request `?with=route` (observed usual callsign route) for its existing batch live status requests; label such suggestions `Flying · likely XXX–YYY` and do not highlight LGW as a confirmed current route solely from history. Fix one-item FlyItaly list queries with a trailing comma as its official API documents.
- Add rate-limited read-only FlyItalyADSB observed flight history (`/v2/flights/reg/{reg}`) to display `Last landed XXX` from recent confirmed ground/low arrival evidence, not a false `At XXX` claim. Respect nightly-only history on the user's Pro feeder benefit and only use same-day data where genuinely entitled. Never slow the live API/local receiver or mutate the Google Sheet.
- Add `scripts/diagnose_flight_sources.py` for read-only real-network testing of actual tar1090 route config, both public route APIs, FlyItaly callsign routes and latest historical landing from the Ubuntu receiver. CI uses mocked responses; the diagnostic is how to validate real access and sample route success.
- Full regression tests for source fallback, FlyItaly query format/headers, route confidence/colour, history parsing/time/freshness, background rate limits, mobile widths, Google Sheets safety and unchanged Traffic/Alerts.

# v1.10.22 — Flights: true one-row table, Manage mode, plausible current routes

- Replace the mobile split-row layout with **one table row per flight**, visibly showing Date, Route, Flight, Registration/live and Who. Desktop retains Airline/Aircraft columns. Keep the existing Google Sheets route, registrations, filter state, all four filtered counters, Copy Reg's and FR24 links untouched.
- Remove repeating Edit/Delete/More buttons from every flight. A single **Manage** button at the top reveals **Edit**, **Delete** and **Done**; choose an action and then tap a flight row. Delete still asks for confirmation. Tapping a row outside Manage opens the flight-details sheet with hidden airline/aircraft fields and local/FR24 links.
- Remove the `Live from Google Sheets` text and information popover from the Flights page. SheetDB remains the sole source of truth, but its routine source label no longer clutters the interface. Errors still show feedback when Google Sheets is unavailable.
- Address the chronic `Flying`-without-route status: prefer existing Aerodrome route_cache; for currently broadcasting callsigns with a fresh position and no local route, submit a **separate, batched adsb.lol routeset** request with aircraft callsign/position. Only accept valid, *plausible* two-airport routes; leave `Flying` otherwise. Server-thread-only HTTP, with a 180-second global query spacing, 30-minute positive cache, 10-minute missing-route cache, no key, no redirects/proxies and strict response limits. The UI makes an early 12-second read-only refresh to pick up an asynchronously resolved route, then reverts to 35-second checks. Live-only Gatwick highlighting remains.
- Fix a pre-existing live-API startup edge case: a zero-initialized monotonic timestamp must allow the first lookup immediately after reboot, not suppress it for the first 35 seconds. This also eliminates an intermittent baseline regression.
- No writes or migrations to Google Sheets, Aerodrome, Alerts, Traffic or Live ADS-B. Existing three provider registration-status rotation, Aerodrome last-seen links, site update process and ntfy settings are preserved.
- Tests cover one-row CSS/DOM requirements, safe Manage selection, filtered search/copy/statistics, no live source clutter, plausible vs impossible routes, endpoint constraints, source throttling, route-cache freshness and non-blocking integration.

# v1.10.21 — Flights: balanced phone table, Aerodrome last seen and provider rotation

- Correct iPhone table overflow without compressing the whole website. Display Date, original flight Route, Flight code and Registration/live in a four-column table; every row has a narrow, **always visible** second line showing **Who, Edit, Delete and More**. Keep desktop full-width columns and detailed actions.
- Restrict the turquoise Gatwick highlight strictly to a **current live** airborne route involving LGW/EGKK, never to the logged route of a flight taken years ago or to on-ground aircraft near Gatwick.
- Query Aerodrome's existing **read-only** `seen_aircraft(icao, registration, last_seen_at)` table once per batch, matched against registration. Place **Seen 12m ago** next to the FR24 registration and link it to Aerodrome's actual `http://<local-host>:8000/aircraft/<ICAO hex>` page. Show nothing if this antenna has never seen the registration. Network data cannot claim local sightings.
- Reuse existing Alerts-stored credentials and rotate **global registration lookups** across adsb.fi (no key), FlyItalyADSB and adsb.lol when their keys are configured. Do not change alert workers: their already cached geographic API data is still eligible as additional enrichment. Only one global provider per 35-second refresh cycle, bounded registration batches, independent freshness limits, automatic cooldown after failure or rate limiting, zero additional secrets or services. Receiver data takes precedence and all errors fail open to the personal flight list.
- Rebuild the seven unchanged multi-select filter controls as a small evenly spaced grid, preserving exact search, Copy Reg's, filtered stats and Google Sheet CRUD. Replace the bottom source strip with a compact header information popover containing required attributions. Suppress outdated search results from overwriting a newer registration lookup.
- Tests cover original SheetDB functionality, live-only Gatwick status checks, local last-seen SQLite/hex, multi-provider rotation, no secrets in URLs, aligned mobile details, table overflow protections and all existing Traffic/Alerts/Live ADS-B regressions. No Aerodrome/Google Sheets schema or receiver/feeding changes.

# v1.10.20 — Integrate original Google Sheets Flight Tracker as a Flights tab

- Thoroughly audited the user's complete uploaded `live-main 2.zip`: HTML, JavaScript, CSS, readme, service worker, manifest, SVG logo and image assets. New standalone **Flights** tab in the same top navigation, without replacing Traffic, Live ADS-B, Alerts, Database, Settings or the launcher.
- Preserve all nine SheetDB-backed Google Sheet fields (`id,date,from_airport,to_airport,flight_code,airline,airplane,registration,who`), the **exact original SheetDB API endpoint**, add/edit/delete semantics, lowest unused positive ID, normalized dates and people, case-insensitive multi-select Year/Airline/Who/From/To/Airplane/Flight filters, punctuation-insensitive registration search, and filtered **Copy Reg's**/four counts (Flights, Regs, Routes, Years). No migration or second database.
- Move the original large flight cards into a dense, responsive table. On mobile show Date, Route, Flight, Registration/live and a discreet `···` actions control; hidden details retain airline, aircraft, who, editing, deletion, historical FR24 and local tar1090 links. Tap a registration to open the original FR24 aircraft-history page. Highlight logged or live connections involving **LGW**.
- Add best-effort read-only live statuses by registration, using existing local Ultrafeeder, existing cached providers and a single bounded public adsb.fi registration batch at most once every 30 seconds; client refresh 35 seconds. Display `Flying AAA – BBB` only for an actual live callsign with a route in Aerodrome's existing route cache; otherwise `Flying`, `At XXX` only for recent ground coordinates within 2 km of an airport, `Ground` if the airport cannot be verified, or `N/A` if nothing fresh is known. Do not invent last parked airport positions or rely on previous booked flights.
- The new server-side SheetDB bridge uses the original Google Sheet as the **single source of truth**, without changing it or loosening the site's Content Security Policy. It only accepts locally authorised, same-origin edits, fixed HTTPS destination, bounded responses and no redirects/proxies. Brief in-memory cached read-only data is explicitly labelled when SheetDB goes offline; writes are rejected during an outage rather than diverted elsewhere.
- New Flights files and routes are isolated; no changes to receiver, feeder services, existing alert rules/notifications, Aerodrome schema or Flight Tracker's original GitHub repository. Existing dark/light palette and mobile layout retained. Free read-only aircraft APIs may have incomplete coverage; a live-status lookup is never a required prerequisite for flight log operations.
- Extensive new Python and Node tests for source-compatible filtering, date normalization, registration suffix handling, filtered copy, filter statistics, SheetDB methods and ID allocation, anti-cross-origin writes, cached data fallback, fresh live positions, ground-airport attribution and unknown-status handling.

# v1.10.19 — Compact classic Alerts editor, keyless adsb.fi backup and one switch

- Restore the small, familiar add/edit alert form. Name and Match by are aligned to an equal-height two-column row, then Codes/pattern and one aligned row of Distance, Min altitude and Max altitude. Remove the large explanatory section panels and the extra network-only checkbox.
- **Backup APIs** is now the only per-rule source switch. OFF (default) = local Ultrafeeder only. ON = local immediate matching plus independent external API enrichment; if a distance is specified, recently seen network aircraft may trigger within that radius. An unlimited-distance rule cannot generate network-only alerts. Existing alert definitions, statuses, history and ntfy settings remain intact.
- Add **adsb.fi** to Configuration & Logs → APIs. Its public v3 geographic API requires **no key** and uses nautic-mile radii, converted from website kilometres. Include a separate no-key **Test connection** button, with timestamp/error/aircraft count. adsb.fi feeder-only global snapshots are authorised automatically by the receiver's public IP; we avoid downloading a huge global dataset. Display source attribution.
- The local three-second alert worker is unchanged. The three optional external caches run independently at rate-conscious intervals, without remote calls in the local worker; offline providers never stop local alerts. Existing FlyItalyADSB and adsb.lol private-key fields and status remain unchanged.
- Added regression coverage for one-switch semantics, legacy SQLite fields, API redaction, keyless provider URL and NM conversion, source attribution, short mobile editor layout and HTTP routes. No ADSB.im/receiver/feed changes, and no modifications to Traffic, Live ADS-B or Aerodrome.

# v1.10.18 — Tidy Alerts setup and reserve adsb.lol as an independent API

- A compact mobile-first Alerts editor groups aircraft identity, distance/altitude limits and **two** source controls. The controls are **Backup APIs** (default OFF: enrich aircraft detected locally, using configured FlyItalyADSB and/or adsb.lol APIs) and **Also alert for network-only aircraft** (default OFF: permit provider detections without local reception; requires a kilometre distance limit). Local Ultrafeeder never waits for external data.
- Retire RSSI as an alert requirement and remove it from the interface. The old schema column is kept for safe upgrade but no longer evaluated; on rule saves it is cleared. This avoids failing a previously saved rule silently because it had an obsolete RSSI requirement.
- Move the prior full-length notification, receiver, API and recent-alert areas behind a collapsed **Configuration & Logs** foldout. Every section, including **Recent alerts**, is now a compact, independently collapsible heading.
- Under **APIs**, provide separate FlyItalyADSB and adsb.lol panels with fixed, read-only HTTPS endpoints, private key Save, Test, Remove and Show/Hide typed-key controls. The UI clearly reports **Key saved** / **Connected** and reports provider aircraft counts and errors without returning stored keys. Existing FlyItaly keys remain in local private state, unchanged.
- Add the optional adsb.lol feeder-key API provider, ready for use when the receiver becomes eligible. Poll every 30 seconds only if a key and rule opt-in exist; convert the provider's nautical-mile radius to the site's kilometres. Rate-limit backoff, source freshness and independent pollers preserve the existing local performance.
- Deduplicate network aircraft by ICAO hex across both providers, preferring fresher positions. Preserve local-first triggering and one event per rule+aircraft, network-only source labels, ntfy priority 3, local tar1090 links for local aircraft, and Aerodrome as read-only fallback.
- Regression tests cover multi-network matching, legacy settings and notifications, server-side API-key redaction, RSSI retirement and the collapsible mobile interface. No updates to Traffic, Live ADS-B, adsb.im, Ultrafeeder or other feeder services.

# v1.10.17 — Optional FlyItalyADSB network backup and local RSSI alerts

- New optional FlyItalyADSB API integration on the Alerts page. Save or remove a key privately in the existing permission-restricted local alert-state database; only `key_set`, connection status, quotas, and errors appear in API responses. Never store credentials in GitHub or browser JavaScript.
- Local Ultrafeeder remains the primary, independent 3-second alert source. A separate daemon polls the provider's documented `/v2/lat/{lat}/lon/{lon}/dist/{km}` endpoint every ~12 seconds only when an enabled rule opts in and a key/antenna location exist. Cache expires after 36 seconds; no network request runs inside local matching.
- Each rule can independently opt into `FlyItalyADSB backup` (fill missing aircraft registration/type, military flag and network MLAT position by matching ICAO hex) and optionally `Allow network-only` (requires a distance limit). Existing rules default to local-only and are not changed.
- Add optional per-rule minimum RSSI (dBFS), evaluated exclusively on *local* readsb signal strength. Missing RSSI never becomes a positive match. A strong signal is not a verified kilometre distance.
- Network-only events are explicitly labelled and do not link to the receiver's local tar1090 selection when the plane may not exist on that map. Existing ntfy priority 3, deduplication, local URLs and notification settings remain unchanged.
- SQLite schema migrations preserve existing rules, occupancy, events and notification settings. Existing read-only Aerodrome metadata fallback is retained. No changes to receiver, feeders, Aerodrome, Traffic, Live ADS-B frontend or external containers.
- Added unit tests for migrations, secret redaction, no network dependencies in local processing, RSSI, opt-in controls, timestamp validity, military MLAT enrichment, network-only deduplication and notification source distinction.

# v1.10.16 — Fix Alerts live aircraft source selection (20 November 2026)

- Prefer the verified live Ultrafeeder readsb feed at `http://127.0.0.1:1090/data/aircraft.json` before older localhost tar1090 ports. Also discover port 1090 on same-machine LAN addresses; retain the existing URL restrictions, overrides and Aerodrome fallback.
- Preserve the existing 3-second matching loop, registration/type/altitude/position filters, per-airframe deduplication and ntfy delivery. No Docker permissions, receiver configuration, feeder, database schema, frontend or Traffic/Live UI changes.
- When live readsb does not include `dbFlags`, continue classifying military aircraft via the existing read-only Aerodrome `seen_aircraft.category` lookup. Unknown classifications and missing positions remain unknown rather than being fabricated.
- Test live feed selection, registration/type alerts, military category enrichment, old port discovery and Aerodrome fallback. A saved custom feed URL still takes precedence: if it points at an obsolete endpoint, update it in Alerts → Receiver setup to the working port 1090 URL or clear it for automatic discovery.

# v1.10.15 — Fix live metadata from the existing Ultrafeeder and tar1090

- Preserve Raw UI exactly as currently working: no frontend JS, CSS, terminal rendering, timing or layout changes.
- Read current aircraft.json and receiver.json directly from the already-running Ultrafeeder container, with fixed read-only Docker commands, using access already available to the website's Raw tab. Fall back to same-host HTTP if container JSON is unavailable or stale.
- Correct aircraft registration/type lookup to use tar1090's db2 directory (as configured by upstream tar1090), not only the previously incorrect db path; retain older db installations as fallback.
- Continue using readsb source classification, three-letter IATA routes and distances in nmi, including direct receiver.json coordinates. Look up tar1090 shards only for aircraft missing r/t in the live JSON.
- Include small non-sensitive metadata availability counts in the details API response for diagnosis if a specific local installation differs. No receiver addresses/coordinates or secrets are exposed in these counts.
- No modifications to Ultrafeeder, other feeders, Aerodrome, Traffic, Alerts, historical data, or Raw/Pretty UI controls.

# v1.10.14 — Match tar1090's local aircraft details and fit Raw automatically

- Reuse the same local tar1090/readsb aircraft.json feed that Alerts discovers, including same-host LAN addresses. Previous Live metadata looked only at loopback ports, leaving registration, distance and Source blank when tar1090 showed them.
- When readsb does not embed a registration/type, use tar1090's own on-host read-only aircraft database shards (db/4.js and deeper) as a bounded fallback, without downloading or installing another database.
- Obtain receiver coordinates from the configured location or the working feed's receiver.json and compute distance in nautical miles. Preserve three-letter IATA airport routes; optional, time-limited batched requests to tar1090's existing public routeset format fill missing routes, with caching and backoff. No external route service is required to view raw aircraft.
- Raw UI remains the genuine original v1.10.10 terminal output but scales font automatically to the screen width, eliminating sideways scrolling. On narrow phones the fixed-width console may be very small.
- Pretty UI keeps the exact 13-column compact table and header-only sorting. The entire heading cell now accepts touch/pointer input on iOS, toggling ascending then descending.
- No new collectors/databases, no change to other pages or to the existing ADS-B services.

# v1.10.13 — Restore real Raw and build exact compact Pretty

- **Raw UI** restored to the working v1.10.10 terminal display: exact PTY redraw text in the original scrolling pre element. No sorting or layout controls in Raw. Raw/Pretty is the only mode toggle.
- **Pretty UI** redesigned as a **single** compact HTML table with exactly the user's 13 columns (Hex ID, Callsign, Reg, Route, Type, Squawk, Alt. (ft), Spd. (kt), Dist. (nmi), Messages, Seen, RSSI, Source), all visible on mobile. Responsive text, compact row height, fixed percentage column widths and no horizontal scrolling.
- Tap any Pretty heading for ascending, tap again for descending. Removed the entire separate Sort toolbar, Fit/All selector, cards and font sizing controls.
- Readsb's existing position-source metadata now supplies the Source column; convert the existing distance-km field to nautical miles for Pretty. Preserve 3-letter IATA airport codes in Route, and leave unavailable values unknown.
- Original 500ms live feed and existing on-demand lifecycle remain unchanged. No changes to other pages, Aerodrome, Docker/feeder services or databases.

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
