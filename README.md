# Airspace Analytics

**v1.5.0 uses the original v1.3 zoom controls and chart drill-down**, with simplified top navigation.
The top-left Home button opens the launcher; Traffic and Patterns are beside it, with Settings at top right. Open the read-only Database from the bottom of Settings. Compare, Aircraft and Saved Views are removed from navigation. Charts scale to the phone width, and hourly charts label every hour on a single-day view.

To investigate unresolved commercial airline metadata without changing Aerodrome, run `python3 scripts/operator_diagnostics.py --days 7 --metric flights` on the Linux host. It reports missing callsigns and unrecognised prefixes, plus the number of commercial observations represented by each group.


A private, responsive, self-hosted ADS-B analytics homepage and historical explorer for an existing [Aerodrome](https://github.com/preston-peterson/aerodrome) installation.

**Design goal:** one Aerodrome database, no duplicate ADS-B collector, no changes to ADSB.im/Ultrafeeder/feeders, and a simple in-app update button.

![Project](https://img.shields.io/badge/Backend-Python%20stdlib-31dfc1) ![Frontend](https://img.shields.io/badge/Frontend-Vanilla%20JS%20%2B%20SVG-6795ff) ![Database](https://img.shields.io/badge/Database-Aerodrome%20SQLite%20(read--only)-cb8efa)

## v1.10.21 Flights refinements

The phone layout now fits **four flight columns** without horizontal scrolling, with **Who, Edit, Delete and More** shown on a tidy second line for each flight. The seven original multi-select filters form an aligned two-row grid on phones. Date, route, code, registration and all SheetDB data remain unchanged.

**Gatwick highlight applies only to the aircraft's current live flight route** (when the real-time route contains LGW/EGKK). It never highlights an earlier LGW journey stored in your Sheet.

**Last seen locally** is separate from worldwide tracking. Beside the registration, `Seen Xm ago` links to `http://<host>:8000/aircraft/<ICAO hex>`, using solely the registration's latest `seen_aircraft.last_seen_at` and hex in the read-only Aerodrome database. If your receiver never saw it, there's no invented time or link. The FR24 registration link is unchanged.

Global status lookups rotate across the accessible documented registration endpoints from **adsb.fi, FlyItalyADSB and adsb.lol**, using the existing keys already saved in Alerts. Missing credentials skip that service automatically; one bounded provider lookup is selected per 35-second cycle with cache aging and backoff. Already cached nearby API sightings are still considered. Remote errors never block the Google Sheets flight records. No additional API setup is necessary for the keyless adsb.fi source.

The bottom data-source footer has been removed. Providers are credited in a small `ⓘ` control beside the Sheet status. All Google Sheets operations, filters, FR24 aircraft links, registration search and four filtered statistics remain exactly as before.

## Personal Flights tab (v1.10.20)

The independent **Flights** tab brings the complete personal Flight Tracker from the user's supplied `live-main 2.zip` into Airspace Analytics. Its original GitHub Pages project does **not** need to be deleted or migrated.

**Google Sheets remains your only flight-log database.** The exact uploaded SheetDB endpoint `https://sheetdb.io/api/v1/9fnmgmxtdst8m` and all nine original sheet columns are retained. The new local server's `/api/flights/records` endpoint merely forwards the same read/create/update/delete operations to SheetDB, protecting the existing dashboard's same-origin content policy. Read-only cached data may appear briefly if SheetDB goes down, visibly labelled; writes cannot fall back to a different database. You need no new SheetDB API key and must keep the existing SheetDB account/Google Sheet active.

The original behaviour remains:

- **Search registrations** by any substring ignoring case, hyphens, spaces or punctuation, e.g. `gwuku`, `g-wuku` and `G-WUKU` are equivalent.
- **Seven multi-select filters**: Year, Airline, Who (splits comma/semicolon/newline-separated names), From, To, Airplane and Flight. Selections OR within one filter and AND across filters.
- **Filtered stats**: Flights, distinct displayed registration text, routes and years. **Copy Reg's** copies distinct *current* registrations of the filtered rows, comma-space separated (for `G-OLD (G-NEW)`, this copies `G-NEW`).
- **Add/edit/delete** using the original form fields and a lowest-unused positive integer ID. Dates in Google Sheets can be ISO or DD/MM/YYYY; editing converts to ISO. Clicking the registration opens its aircraft history on Flightradar24.
- **New compact table** replaces the bubble cards. On a phone it shows date, route, flight code, registration/live status and the `···` details button. Details retain airline, aircraft, who, Edit, Delete, FR24 history and a tar1090 local aircraft map link when a live hex is known. Gatwick/EGKK/LGW routes or current locations are highlighted.

**Live status is best effort, not flight-log data.** The extra read-only `/api/flights/live?regs=…` endpoint checks the same on-host readsb feed plus already cached API data and one bounded public adsb.fi registration batch at most every 30 seconds. Requests stop when the Flights page is closed; the interface refreshes live badges every 35 seconds without reloading Google Sheets. No new API key is needed. Local live positions take priority; routes are shown only when the currently broadcasting callsign has a read-only route in Aerodrome's route cache. A reliable nearby on-ground position may show `At LGW` (or another recognised airport); otherwise the status is `Ground`, `Flying`, or `N/A`, rather than an unverified last parking location. This cannot track an aircraft that all networks have stopped receiving.

The live-status panel credits [adsb.fi](https://adsb.fi/) per its licence. Nothing in this feature writes into Aerodrome, starts another SDR, changes existing feeders, alters ntfy alerts, or exposes private FlyItaly/adsb.lol API keys. The existing Airspace Analytics UI updater installs this release and keeps its rollback support.

## What it includes

- **Home:** live-ish source status, today's unique aircraft, observations, peak concurrency, shortcuts to ADSB.im, Aerodrome, SkyStats, readsb map, receiver graphs, and optional Dozzle.
- **Flights:** your independent Google Sheets personal flight log, seven multi-select filters, registration search, filtered stats and Copy Reg's, add/edit/delete, dense table, FR24 registration links, best-effort live status and LGW highlights.\n- **Explore:** flights / unique aircraft / observations, flexible windows (any rolling duration from minutes to years, exact custom start/end dates, or all recorded history), hourly/daily/weekly/monthly/yearly charts, recurring weekday/hour/month averages, aircraft category/type/airline breakdowns, click-to-drill, line/bar switch, bookmarks saved in the browser.
- **Patterns:** 7 × 24 average-traffic heatmap, typical weekday and hour profiles, filtered by measurement, period and aircraft.
- **Aircraft:** search historical ICAO codes, callsigns, aircraft types or operators; inspect stored observations.
- **Database:** view a whitelist of Aerodrome tables, paginate, search, CSV export (up to 5,000 rows at a time); never execute arbitrary SQL.
- **Settings:** dark/light theme, editable local-service shortcuts, version checks, update, restore previous version, database health and storage.
- **Security:** an unprivileged web server, read-only SQLite connections, local-network-only update endpoint with cross-origin checks, separate updater systemd unit, read-safe queries with a time budget, no unsafe code execution endpoint.

All UI assets are bundled locally; there are no CDNs or mandatory npm packages. Python 3.10+ and a modern browser are enough. Node.js is **not** required after all.

## First-time installation on Ubuntu

1. Create a **public** GitHub repository (recommended initial name: `airspace-analytics`) in your account. Upload **the extracted contents** of the ZIP to its default branch. Do not upload the ZIP itself as a single file. Public is simplest for first-time cloning. Keep `.airspace-state/` and all database/configuration files out of GitHub.
2. On the Ubuntu laptop running Aerodrome, run this **one line**, replacing `YOURNAME` with your GitHub username:

   ```bash
   git clone https://github.com/YOURNAME/airspace-analytics.git ~/airspace-analytics && sudo bash ~/airspace-analytics/scripts/install.sh
   ```

3. The installer checks that the Aerodrome database exists and the normal Ubuntu user can read it, creates three dedicated systemd units, and starts the website. It prints the device's IP address.
4. Visit `http://192.168.1.187:8088` from the laptop or phone on the same network (adjust IP if changed). Visit **Settings → GitHub updates** and select **Update now**. No update token is needed on this trusted-network deployment.

**No Python virtual environment, npm install, compilation, Docker installation, or database migration is required.** The installer does not stop, restart or reconfigure Aerodrome or any feeders.

The installer deliberately requires an existing Aerodrome DB at `/opt/aerodrome/aircraft_history.db`. It creates the directory and status files *inside the cloned website repository*, not in the Aerodrome directory.

### Updating from the website

1. Push new project source to your GitHub default branch. The repository needs to be under your control because updates execute its Python source as the website user.
2. Go to **Settings → GitHub updates → Check GitHub**.
3. Select **Update now** and confirm. On browsers that are not yet paired, use the collapsed **Connect updates on this browser** setting once.
4. The website signals `airspace-analytics-update.path` (systemd), which starts the unprivileged updater. It only performs a **fast-forward Git update** (local tracked edits or history rewrites block installation), checks the Python code and required assets, and restarts **only** `airspace-analytics.service`.
5. If code validation fails, the updater tries to restore the old code. It does not automatically verify HTTP health after restarting; use the Restore previous action or CLI fallback if an update breaks startup. **Restore previous** in Settings resets to the prior working commit saved from the most recent successful update.

**Limitations:** A damaged Linux installation, Git authentication failure, a database schema change, or an update that breaks live runtime behaviour may still need terminal troubleshooting. Rollback is a safety aid, not a substitute for proper backups. Updating an updater service definition itself requires rerunning the initial installer script. Do not expose this HTTP website directly to the public internet. Tailscale is the recommended remote-access path.

### Offline / local first-run check (development only)

You can run the site on a different machine with a sample, **fictional** database without touching your real Aerodrome data:

```bash
python3 tests/make_sample_db.py /tmp/airspace-demo.db --days 45
AIRSPACE_DB=/tmp/airspace-demo.db AIRSPACE_PORT=18888 python3 -m backend
```

Open `http://localhost:18888`. Stop with Ctrl+C. This demo has invented aircraft data and is only for testing.

### Automated tests

```bash
python3 -m unittest tests.test_backend -v
node --check frontend/app.js  # optional, if Node is installed
bash -n scripts/install.sh
```

## Where the data comes from

The source of truth is **one** Aerodrome SQLite file:

`/opt/aerodrome/aircraft_history.db`

The service opens SQLite connections using URI `mode=ro` and `PRAGMA query_only=ON`, and uses the following existing tables:

| Existing table | Used for |
|---|---|
| `sightings_hourly` | Fast time-series, category/type/airline breakdowns, estimated session boundaries |
| `seen_aircraft` | Aircraft classification, descriptions, operator, registration, country |
| `route_cache` | Airline enrichment when Aerodrome knows it |
| `concurrent_minute` | Today’s peak concurrent, sample-coverage proxy |
| `all_sightings` | Recent per-aircraft observations, first/latest date, and database viewer |
| Other whitelisted Aerodrome tables | Browsing/export only |

The website does **not** duplicate observations into another database. Small transient in-memory query results are cached for about 75 seconds to reduce database reads. Your 10-second Aerodrome collection interval remains unchanged.

### Definitions and caveats

**Observations:** sum of `sightings_hourly.sighting_count`, generally approximating the number of stored polling observations. This is **not** the count of individual decoded radio messages. 10 seconds between polls does not mean every radio message was saved.

**Unique aircraft:** distinct ICAO hex aircraft identifiers in the selected period. The same aircraft can appear in multiple time buckets. The sum of the per-bucket unique counts can exceed the unique total for the whole window.

**Flights (estimated visits):** first sighting of a new receiver coverage session, inferred from hourly rows with a 30-minute separation or callsign change. Multiple flights by the same airframe within the same hour can be merged; missing gaps and receiver dropouts can produce estimation errors. It is not a certified flight/journey count. The derived value is never written to Aerodrome.

**Hourly rollups:** ideal for periods spanning months and years, but custom minute-level boundaries may include full partial hour summaries. Date bucketing uses `Europe/London`, including daylight saving.

**Weekday/hour/month-of-year averages:** the mean of recorded calendar days (with at least 30 recorded minute samples per day) or recorded hours (with at least 5 minute samples). Partial days are included as their observed daily total, **not scaled up to a 24-hour estimate**. A day with no samples is returned as unavailable (`null`/dash), not a traffic count of zero. Month-of-year means still require a sufficiently complete calendar month.

**Airlines:** the commercial-only airline chart uses `route_cache.airline`, `seen_aircraft.operator`, then a conservative known airline ICAO callsign prefix mapping. Unrecognised commercial traffic remains `Unknown airline`. The all-aviation **Operators** view retains GA/military owner/operator labels separately, including category-specific Unknown values; it never mislabels GA as an airline.

**Commercial / general aviation / military / helicopter / unknown:** Aerodrome's current aircraft categories, which might be revised as metadata updates.

**Sample coverage percentage:** the number of `concurrent_minute` records divided by expected minutes in the selected period, capped at 100%. This is a **proxy**, not a guaranteed uptime metric. Month-of-year averages require 70% minute-sample availability; weekday and hour charts instead accept observed partial periods. Aerodrome may omit some genuinely empty minutes. A quiet hour could also mean no aircraft in range.

**Retention:** the website obeys Aerodrome's configured retention and cannot recreate history that Aerodrome has already deleted. Make long-term backup/retention decisions separately. Periods before initial collection return no observations; they are not reconstructed from FR24/FlightAware.

**Performance:** one analysis at a time, ≤14 s SQL safety timeout, ≤5 million hourly aircraft rows, ≤1,200 chart points. For multi-year data choose weekly/monthly/yearly grouping. No writes, VACUUM, migrations or indexes are applied to Aerodrome.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AIRSPACE_DB` | `/opt/aerodrome/aircraft_history.db` | Path of the existing Aerodrome DB |
| `AIRSPACE_HOST` | `0.0.0.0` | Network interface (LAN access by default) |
| `AIRSPACE_PORT` | `8088` | Website port |

Website display settings and shortcuts are stored in each browser's local storage (so iPhone and PC preferences are independent).

### Managing the service

Normal updates need no terminal. For initial diagnosis only:

```bash
sudo systemctl status airspace-analytics.service
sudo systemctl status airspace-analytics-update.path
sudo journalctl -u airspace-analytics.service --no-pager -n 50
```

### Uninstall without touching ADS-B

```bash
sudo bash ~/airspace-analytics/scripts/uninstall.sh
```

This removes the three **Airspace Analytics** systemd units only. Aerodrome, ADSB.im, existing Docker containers, and database are not affected. The project folder and update token are left on disk so you may reinstall if needed.

## Security notes

- **LAN/Tailscale only:** the UI uses HTTP without HTTPS by default. No router port forwarding; other LAN users may see your historical aircraft data. VPN/Tailscale is preferred for remote access.
- The update token is created locally, stored in `.airspace-state/update-token` with permissions 0600, and transmitted only to the website when updating. The UI migrates a previously entered token into this browser’s local storage, so normal updates require no repeated entry. A new browser can be paired separately if necessary.
- The updater is triggered by a systemd path unit, *not* by giving a web request privileged command execution. Only the updater's fixed `systemctl restart airspace-analytics.service` post-action runs as root.
- Future public-facing deployments would require HTTPS and full login protection for **all** data and settings endpoints.
- Never commit your actual Aerodrome database, `config.yaml`, `.airspace-state/`, secrets, or update token to GitHub.

## Project structure

```text
frontend/          HTML, CSS, JavaScript, SVG artwork and web-app manifest
backend/data.py    Read-only SQLite analysis and pattern engine
backend/server.py  Lightweight HTTP API, static file hosting and update requests
scripts/install.sh One-time systemd installation
scripts/update_worker.py  Git verification, update and rollback
scripts/uninstall.sh      Safe removal of only the website services
tests/             Fictional database generator and automated tests
VERSION            Site version
```

## License

MIT — see `LICENSE`.

## v1.2 compact redesign and update from v1.1

The normal URL `http://<your-host>:8088/` is now a simple **application launcher**. Its first, fixed link is **Airspace Analytics**, which opens `http://<your-host>:8088/analytics#explore` on the same port. The other links can be edited, removed, added and reordered under **Settings → Launcher links**. The links live in each browser's storage, so changes made on a phone do not automatically appear on a PC.

The Analytics workspace now exposes Traffic and Patterns at the top, plus Settings with a database explorer link. Traffic displays a single main chart, flexible duration/date controls, metric selector (Visits, Aircraft, Samples), grouping, a click-to-drill zoom with a **Zoom out** button, and collapsible Filters and Breakdowns. No new aircraft collection process or writeable database is created.

To upgrade an already-installed Git checkout, **commit the changed files to that same GitHub repository's default branch**. Then, from the still-running v1.1 website, open **Settings → GitHub updates → Check GitHub → Update now**. The site's existing private update token remains valid. There is no need to rerun the installer or edit Aerodrome. The new interface takes effect after the existing updater restarts only Airspace Analytics.

If GitHub's website is used to upload this release, extract the ZIP locally and replace project files in the **same repository**, not a new one. Do not upload this ZIP as a single file; upload its contents. Particularly important files are `VERSION`, `frontend/app.js`, `frontend/styles.css`, `frontend/index.html`, and `CHANGELOG.md`. The backend and installer have no functional changes in this release.

The home screen intentionally contains no analytics charts; use the pinned Analytics button to open the workspace. On mobile, Analytics has compact bottom navigation; the Database section remains accessible from the menu in the upper-left.

## v1.3 — streamlined personal interface

Traffic, Patterns and Compare share a single date-range control: **Last** (input any number and select minutes, hours, days, weeks, months or years), **Dates** (custom UK start/end), or **All time**. No fixed 46-hour example or oversized preset strip. The Patterns screen now reports actual recorded-day averages even while Aerodrome is newly collecting, rather than displaying misleading zeros for incomplete calendar days.

The **Commercial airlines** chart excludes general aviation and can identify familiar carriers from callsigns like `EZY123` when Aerodrome's operator field is empty. Choose **Operators · all** to include owners and non-airline operators. No source records are changed.

The website no longer shows routine caveat boxes, the About Installation panel, or the Understanding These Numbers section. Update actions remain authenticated, but an already paired browser no longer displays or requests the token each time.

## v1.7.0: traffic chart and activity calendar

- Sparse year, month and week charts anchor their first recorded bucket at the left.
- Activity calendar is a 12-month year grid or a one-month day grid; choose month names to drill into a month.
- Airline estimates: the original Aerodrome source remains unchanged. If a callsign is identified later within one continuous flight visit, the initial unknown visit's breakdown attribution is corrected. It does not identify genuinely unknown aircraft.
- The Settings updater needs no pairing token. Access to the update endpoint is limited to trusted local/Tailscale client ranges with same-origin browser checks. **Anyone who can use the site's update action from that trusted network can request a GitHub update.** Keep the site off the public internet.
- No transient corner notifications. Action errors remain visible inline where relevant.

### Year calendar and airline codes (v1.8)

The calendar uses `series[].has_data`, not the zero-filled traffic value, to avoid colouring days before Aerodrome started collecting. No-data days have no cell background or border; faint date numbers preserve a readable calendar layout. Tap a year month card to open its daily view, and the year button to return.

Airline labels are inferred from a small, explicit set of ICAO three-letter callsign prefixes. The mapping is deliberately conservative and updated against the [IATA DAQCP airline code list](https://www.iata.org/contentassets/2335b0082f4f41c9941cc5f3428c2698/airline-members.pdf), [IATA airline directory](https://www.iata.org/en/about/members/airline-list/), [ICAO operator list](https://www.icao.int/CORSIA/AeroplaneOperators), [FAA three-letter list](https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap3_section_1.html), and carrier/airport airline profiles. Missing/unmatched callsigns are *not* invented.


### Desktop layout and launcher shortcuts (v1.9.1)

The launcher at `/` now has two compact sections. **View Stats** links to Airspace Analytics (`/analytics#explore`), ADSB.im (`:1573`), SkyStats (`:5173`), tar1090 (`:1099/map/`) and Dozzle (`:1094`). **Feeder Website Status** links to Flightradar24 (`:8754`), AirNav Radar's station page, FlightDeck's account/feeder page, Plane Finder (`:30053/stats.html`, plus `:30053/map.html`), ADS-B Exchange status (plus feeder-only map), and FlightAware (`:1093`). Relative local ports use the browser's current hostname, so the launcher can be opened by LAN IP or Tailscale name.

On the first page load after updating, saved built-in links are replaced with the newly requested destinations. Other user-created shortcuts are preserved. The launcher editor in Settings supports group assignment, ports, paths, explicit URLs, logo domain, and an optional secondary link. Customizations remain in **that browser's local storage**, not in Aerodrome's database, so edits on PC do not synchronize to the phone.

Site favicons are loaded from Google's public favicon endpoint (with a strict image-only Content Security Policy) and never include private local URLs. If the service's icon cannot be fetched, its colour-coded monogram appears automatically. The local Airspace tile uses this project's own favicon; SkyStats and tar1090 also have distinct labelled fallback tiles.

Only desktop breakpoints (1050px and above) alter Traffic/chart sizing. The mobile Traffic stylesheet and zoom behaviour are not changed.


## Aircraft Alerts — v1.10

Open **Alerts** next to Traffic. Create rules by aircraft type, registration,
callsign, ICAO hex, operator or military flag. Example types: A388 (A380),
A3ST/A337 (Beluga), B74* (747 family), A34* (A340 family).
Set a maximum **ground distance (km)** from the antenna and optional
minimum/maximum **barometric altitude (feet)**. Leave a limit empty to disable it.

Alerts monitors the receiver's live `aircraft.json` every three seconds in the
website's Python service, even after closing the phone or browser. It first tries
the existing Ultrafeeder readsb JSON at `http://127.0.0.1:1090/data/aircraft.json`,
then other same-host tar1090 HTTP endpoints automatically. Under **Alerts → Receiver setup**,
you can optionally supply a localhost feed URL and manual antenna latitude/
longitude when `receiver.json` lacks them. **Test connection** checks the
configured live feed. Distance-limited rules require a fresh aircraft position
and known antenna coordinates; type/hex-only rules do not.

Each **rule + aircraft hex** has independent activation state, persisted
through restarts. Two simultaneous A380s generate independent notifications.
A tracked aircraft rearms only after two consecutive confirmed exits
(with boundary hysteresis), or a long uninterrupted absence.

Under **Notifications**, configure an existing ntfy topic, optional access
token, and send a test. Subscribe to that topic using the ntfy iPhone app.
The default server is `https://ntfy.sh`; ntfy publishing requires HTTPS.

Aerodrome's `/opt/aerodrome/aircraft_history.db` is accessed read-only for
optional missing aircraft metadata. The only extra writable file is
`.airspace-state/alerts.sqlite3` in this same project, holding rules, active
state, notifications settings and recent event history—not duplicate aircraft
observations. No extra container, package or service needs installing.

## Alerts source fallback

Alerts uses live local aircraft.json when available (about 3-second checks).
If that network endpoint cannot be reached, Alerts automatically reads recent
**new** sightings from the existing read-only Aerodrome database, so alert
processing can continue at Aerodrome's 10-second recording resolution.
It never writes to Aerodrome or copies its observations.

To use distance rules, enter the **antenna's latitude and longitude** in the
local **Alerts → Receiver setup** form and press Save receiver. These coordinates
are saved in the local `.airspace-state/alerts.sqlite3` file, not committed to
GitHub. There is no need to enter the web map address as the feed URL; leave
that input blank for automatic discovery and database fallback.

Type and registration rules don't require a position. Distance-limited rules
need both an antenna location and a usable aircraft position. Rechecking the
same Aerodrome observation does not rearm an aircraft; only new observations
can confirm a departure. No additional service or database installation is
required.

If a previously saved **Aircraft feed URL** still points to port 1099 and fails,
change it to `http://127.0.0.1:1090/data/aircraft.json` or clear the field
and save to let the app automatically select the working endpoint. The live
source supplies registration, type, position and barometric altitude when
available, but not every aircraft has a fresh position; `dbFlags` may be missing.
For military rules, the existing read-only Aerodrome classification is used
when available. Unclassified military aircraft cannot be guaranteed to trigger.


### Compact Alerts and three independent backup providers (v1.10.19)

Go to **Alerts → Configuration & Logs → APIs**. The following independent
providers are available:

- **FlyItalyADSB**: enable Fly Italy ADSB in ADSB.im; register for the
  [free API / feeder benefit](https://flyitalyadsb.com/data/api/account/).
  Paste the secret into its private field; **Save key** and **Test connection**.
- **adsb.lol**: continue feeding until your station qualifies for a
  [feeder API key](https://www.adsb.lol/receiver). Add the key when eligible.
  A missing key does not interfere with the other providers.
- **adsb.fi**: **no key is needed**. The official
  [open data API](https://github.com/adsbfi/opendata/blob/main/README.md)
  offers a keyless local aircraft search and automatically recognises a
  contributor's **public IP address** for the extra global snapshot endpoint.
  The website uses the small local `v3/lat/lon/dist` query, not a huge global
  download. Press **Test connection** under adsb.fi. To verify feeder-only
  benefits on the same laptop / public IP as the feeder, check the HTTP status
  for `https://opendata.adsb.fi/api/v2/snapshot` (200 means recognised,
  403 means not currently entitled). Public requests may work even without
  contributor recognition.

**One checkbox per rule: Backup APIs.** Default **OFF**, which keeps the
rule exactly **local receiver only**. When checked, local sightings stay
instant; optional API datasets may supply missing fields, military flags and
MLAT positions. If the rule also specifies a distance in kilometres, aircraft
seen **only by a network** may trigger within that radius. A rule with
Backup APIs on but **no distance limit** still requires local reception. The
former separate network-only checkbox and all RSSI options have been removed
from the editor.

All providers use per-provider, rate-conscious, independent polls (FlyItaly
about 12 seconds, adsb.lol about 30 seconds, adsb.fi about 60 seconds) only
when an enabled rule needs backup data; network requests never run inside
the local three-second matching loop. The closest geographical queries are
limited and time-gated; duplicate ICAO hex records are merged by freshest
available position, with one notification per rule/aircraft until rearmed.
Distances in UI are kilometres; network endpoints expecting nautical miles
are converted at query time.

The compact rule editor places **Name** beside **Match by**, a single
pattern line and a row of distance, min altitude and max altitude fields,
then the single **Backup APIs** switch. The Alerts page still offers
collapsible Notifications, Receiver, APIs and Recent alerts under
**Configuration & Logs**. The local ntfy topic, priority 3 and historical
events remain unchanged. This update makes no changes to SDR, ADSB.im,
UltraFeeder, Aerodrome or Traffic/Live ADS-B modules.

API test buttons report provider HTTP access and aircraft counts only;
they **do not** send test aircraft notifications. Receiver test checks your
own readsb source and antenna coordinates. Notification test sends a
priority-3 message to ntfy; successful HTTP receipt does not guarantee
the iPhone displayed a push banner.

## Live ADS-B terminal (v1.10.9)

**Live ADS-B** in the analytics header streams the real curses terminal from `docker exec -e TERM=xterm -t ultrafeeder viewadsb` through read-only same-origin SSE. Terminal redraws appear as produced, normally every 500 ms. This does not poll readsb's 1-second JSON or use a second SDR, and no ADS-B services or the Aerodrome database are changed. On mobile the original terminal can be scrolled horizontally.

The Airspace Analytics service user needs Docker permissions without sudo for this tab. Docker membership grants substantial host privileges and is not configured by this feature. If unavailable, the Live view shows a connection error; existing features still operate. ADS-B broadcasts do not include departure/destination, so stock viewadsb cannot show them without a separate route lookup.


## Live terminal: Docker socket permission denied (v1.10.10)

If Live ADS-B shows `permission denied while trying to connect to the docker API`, the website's systemd user cannot access `/var/run/docker.sock`. This is **not** an SDR decoder failure; a GitHub website-only update cannot change that Linux permission.

One optional way to allow the website service account to use Docker is:

```bash
sudo usermod -aG docker "$(systemctl show -p User --value airspace-analytics.service)"
sudo systemctl restart airspace-analytics.service
```

**Security:** Docker group membership effectively provides root-equivalent privileges to that Linux user, including the web service and its update scripts. Only do this on a trusted local host if you accept the extra privilege. The website itself deliberately does not add itself to Docker or modify these permissions. A dedicated local viewer relay could be designed instead to avoid giving the web service general Docker access.


## Live ADS-B: Raw and Nice (v1.10.11)

Use the **Nice UI / Raw UI** toggle on the Live ADS-B page. On phones, Nice UI defaults to readable aircraft cards; desktop defaults to a table. Both have a sort selector/direction, and all table headers can be tapped to sort. Raw UI is the genuine `viewadsb` curses output with smaller mobile text, horizontal swipe and A−/A+ sizing. The real terminal updates on its own ~500ms redraw cadence; neither mode creates another receiver or collector.

The table and cards show all available live terminal fields plus **registration, registration country, estimated ground distance in km, and flight route**. Registration/type come from your existing local readsb aircraft feed when available, falling back to the read-only Aerodrome `seen_aircraft` registry. Country comes from Aerodrome. Distance is calculated from receiver coordinates and current received positions when both are known; otherwise it is marked unavailable. Route codes come from existing read-only Aerodrome `route_cache` records or Aerodrome's already installed callsign route resolver, converted using `/opt/aerodrome/static/airports.json` (which includes 3-letter IATA codes). A small backup mapping covers common airports in case the local airport file is missing. A route is shown as `LGW – MAD` **only when both endpoints have valid IATA codes**. An unavailable or ambiguous route is shown as `—`; route data isn't transmitted over ADS-B and can be stale.

Extra aircraft details are requested on-demand every ~8 seconds, independent of the raw terminal's native redraw timing. Navigating away or putting Safari in the background stops the website viewer and aborts its metadata requests; when you return, it reconnects. Your existing Ultrafeeder and alert workers keep running 24/7. All database access by Airspace Analytics remains read-only; Aerodrome may populate its *own* route cache when its existing route-resolver endpoint is called. No extra network service or database is added to the website.


## Table-only Live ADS-B (v1.10.12)

Live ADS-B has two display choices, **Raw** and **Nice**, and both are actual HTML tables fed by the existing `viewadsb` terminal stream (approximately 500ms redraw). There is no card interface or monospace text-dump view. Raw preserves the original 12 terminal headings/data in a dark, terminal-inspired table. Nice includes the original readings plus aircraft type, registration, country, distance and `LGW – MAD`-style three-letter IATA routes from the existing local Aerodrome/readsb metadata endpoint (when available).

Every heading is clickable to sort by that field: first click ascending, second click descending, and subsequent clicks toggle. Aircraft type can be sorted in Nice mode. For phones, **Fit screen** automatically shows the six most useful columns without needing to change the font; **All columns** reveals the entire horizontal scrollable table (first column stays visible). The Sort menu can select even columns hidden in Fit screen. Desktop shows all fields with normal horizontal scrolling if necessary. The user's visit controls the viewer: navigating away and backgrounding Safari stop the on-demand stream, not the underlying SDR or Ultrafeeder.


## Live ADS-B v1.10.13 — faithful Raw and 13-column Pretty

There are exactly two options at the top of Live ADS-B: **Raw UI** and **Pretty UI**. The selected option is remembered per browser. **Raw UI** is restored from the original v1.10.10 working implementation: it displays the genuine PTY text of the Ultrafeeder viewadsb command (including its original columns, cursor clearing, fixed spacing and ~500 ms screen redraws). It has no sorting controls, no alternative table layout and no manual resizing buttons.

**Pretty UI** is one compact website table showing all of these headings, in this exact order, including on mobile: **Hex ID, Callsign, Reg, Route, Type, Squawk, Alt. (ft), Spd. (kt), Dist. (nmi), Messages, Seen, RSSI, Source**. Its columns use an explicit percentage width allocation summing to 100%, with responsive font sizing and minimal row padding on narrow screens. It never hides columns or uses horizontal scrolling; on small phones the text is necessarily very small. Every heading is clickable: first click sorts ascending, second click descending, then alternating. The only sort controls are the heading titles themselves.

The 500 ms raw receiver stream is the live source for both views. Registration, aircraft type, 3-letter IATA route, geographic distance (converted from km to nautical miles) and the readsb source classification are added by the existing on-demand local live/details endpoint. These extras may arrive after the initial live frame, and unknown details show a dash. Sources include ADS-B, MLAT, Mode S, TIS-B and ADS-R when readsb supplies them. Messages, seen-age and RSSI come from the original terminal stream. There are no other lookups or extra decoders.

The browser still closes the on-demand terminal connection when the Live tab is left or Safari becomes hidden; the underlying Ultrafeeder/feeds continue running. This release does not modify any feeder, Aerodrome, installed systemd unit, Alert page or Traffic dashboard.


## Live ADS-B: tar1090 data parity and Raw auto-fit (v1.10.14)

The Live page's receiver metadata reuses Alerts' local aircraft.json discovery strategy. This includes the host LAN URL if loopback is unavailable (such as tar1090 served from the same Ubuntu laptop at port 1099 under /map/). These metadata requests run only while Pretty UI is viewed; the original ~500ms receiver terminal stream remains independent.

Registration and aircraft type come directly from readsb's r/t fields when available; otherwise the backend reads the same local tar1090 db/prefix.js shards used by tar1090's dbloader, with short request limits and caching. Source uses readsb's type classification. Distance is calculated in nautical miles using the existing receiver coordinates or the local receiver.json.

Aerodrome's existing route_cache remains preferred. The optional route enrichment uses the public batch routeset format already used by tar1090 (api.adsb.lol) to fill missed routes, with strict timeout, caching and backoff. This optional external request sends aircraft callsigns and positions, as tar1090's route feature does; the receiver still works offline. Only confirmed three-letter IATA routes such as LGW – MAD are displayed. If unavailable, the field shows a dash.

Raw still shows the actual viewadsb PTY terminal frame, not a recreated table. It now automatically scales monospace font size to the width of the available screen (including rotation) rather than requiring horizontal scrolling. The text of a 132-column console will necessarily be small on narrow iPhones. Pretty still fits all 13 columns on-screen; clicking or tapping the whole heading cell toggles ascending and descending.


## Live metadata source correction (v1.10.15)

Pretty UI now first reads live aircraft.json and receiver.json directly from the already-working Ultrafeeder Docker container, at /run/readsb/aircraft.json and /run/readsb/receiver.json. These commands are fixed read-only Docker exec commands: no shell, restart, extra decoder or new container. If the files are unavailable, the previous validated same-host HTTP readsb feed is used instead.

For registrations and aircraft types absent from readsb JSON, Pretty also consults tar1090's existing sharded aircraft database, prioritising /map/db2/ (matching tar1090's databaseFolder) and retaining /map/db/ as an older compatibility fallback. The requests run only while Pretty is being viewed and are cached and capped. Routes continue to use three-letter IATA codes. Source and distance in nautical miles come from current readsb data and receiver location.

To diagnose an installation where fields are still missing, the read-only /api/live/details endpoint returns a metadata_status object with counts only: receiver_aircraft, matched_receiver_aircraft, tar1090_db_matches and receiver_location_available. For example, visit /api/live/details?items=4069CF:GCICF from the same website address. A zero matched_receiver_aircraft means no live decoder match was available for the requested hex; a false receiver_location_available explains a blank distance. No precise coordinates or database contents are returned in this diagnostic summary.

Raw UI remains completely unchanged from the working prior version.
