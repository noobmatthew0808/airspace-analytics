# Airspace Analytics

**v1.5.0 uses the original v1.3 zoom controls and chart drill-down**, with simplified top navigation.
The top-left Home button opens the launcher; Traffic and Patterns are beside it, with Settings at top right. Open the read-only Database from the bottom of Settings. Compare, Aircraft and Saved Views are removed from navigation. Charts scale to the phone width, and hourly charts label every hour on a single-day view.

To investigate unresolved commercial airline metadata without changing Aerodrome, run `python3 scripts/operator_diagnostics.py --days 7 --metric flights` on the Linux host. It reports missing callsigns and unrecognised prefixes, plus the number of commercial observations represented by each group.


A private, responsive, self-hosted ADS-B analytics homepage and historical explorer for an existing [Aerodrome](https://github.com/preston-peterson/aerodrome) installation.

**Design goal:** one Aerodrome database, no duplicate ADS-B collector, no changes to ADSB.im/Ultrafeeder/feeders, and a simple in-app update button.

![Project](https://img.shields.io/badge/Backend-Python%20stdlib-31dfc1) ![Frontend](https://img.shields.io/badge/Frontend-Vanilla%20JS%20%2B%20SVG-6795ff) ![Database](https://img.shields.io/badge/Database-Aerodrome%20SQLite%20(read--only)-cb8efa)

## What it includes

- **Home:** live-ish source status, today's unique aircraft, observations, peak concurrency, shortcuts to ADSB.im, Aerodrome, SkyStats, readsb map, receiver graphs, and optional Dozzle.
- **Explore:** flights / unique aircraft / observations, flexible windows (any rolling duration from minutes to years, exact custom start/end dates, or all recorded history), hourly/daily/weekly/monthly/yearly charts, recurring weekday/hour/month averages, aircraft category/type/airline breakdowns, click-to-drill, line/bar switch, bookmarks saved in the browser.
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
