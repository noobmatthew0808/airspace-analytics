# Airspace Analytics

A private, responsive, self-hosted ADS-B analytics homepage and historical explorer for an existing [Aerodrome](https://github.com/preston-peterson/aerodrome) installation.

**Design goal:** one Aerodrome database, no duplicate ADS-B collector, no changes to ADSB.im/Ultrafeeder/feeders, and a simple in-app update button.

![Project](https://img.shields.io/badge/Backend-Python%20stdlib-31dfc1) ![Frontend](https://img.shields.io/badge/Frontend-Vanilla%20JS%20%2B%20SVG-6795ff) ![Database](https://img.shields.io/badge/Database-Aerodrome%20SQLite%20(read--only)-cb8efa)

## What it includes

- **Home (`/`)**: a compact application launcher. Airspace Analytics is always the first link; all other links can be added, removed and reordered in Settings.
- **Traffic (`/analytics#explore`)**: one interactive chart that starts with all recorded **years**, then drills down via **year → month → week → day → individual hours**. The selected period is visible above the graph, and **Zoom out** returns to the previous level. Every hourly point has its own time label; wide charts scroll horizontally on mobile.
- **Traffic breakdowns**: aviation category, aircraft types and commercial-airline/all-operator totals for the currently selected period. One **Show pies / Show bars** button changes all three visualisations together.
- **Hourly patterns, on Traffic**: a compact weekday × hour heatmap plus average traffic by weekday and by individual hour. These use the same selected period, metric and filters as the main graph. A single-day heatmap contracts to one row.
- **Range & filters**: optional controls for all history, any rolling duration, custom UK start/end time, aviation category, aircraft type, airline/operator and ICAO address. The default layout stays uncluttered.
- **Aircraft**: search historical aircraft and inspect recorded visits and observations.
- **Database**: browse a read-only whitelist of Aerodrome tables, search and export CSV without arbitrary SQL.
- **Settings**: editable launcher links, theme, data-source health, and authenticated GitHub updates/rollback. A paired browser remembers the update token; a new browser can pair from a collapsed control.
- **Mobile**: one bottom navigation bar, with no duplicated tabs at the top. Desktop uses a left sidebar.

The separate Compare and Patterns navigation pages and Saved Views feature were removed in v1.4, but the pattern charts remain available directly inside Traffic. The corresponding read-only historical API endpoints remain for backward compatibility.

All UI assets are bundled locally; there are no CDNs or mandatory npm packages. Python 3.10+ and a modern browser are enough. Node.js is **not** required after all.

## First-time installation on Ubuntu

1. Create a **public** GitHub repository (recommended initial name: `airspace-analytics`) in your account. Upload **the extracted contents** of the ZIP to its default branch. Do not upload the ZIP itself as a single file. Public is simplest for first-time cloning. Keep `.airspace-state/` and all database/configuration files out of GitHub.
2. On the Ubuntu laptop running Aerodrome, run this **one line**, replacing `YOURNAME` with your GitHub username:

   ```bash
   git clone https://github.com/YOURNAME/airspace-analytics.git ~/airspace-analytics && sudo bash ~/airspace-analytics/scripts/install.sh
   ```

3. The installer checks that the Aerodrome database exists and the normal Ubuntu user can read it, creates three dedicated systemd units, and starts the website. It prints the device's IP address and a **private update token**. Keep the token private.
4. Visit `http://192.168.1.187:8088` from the laptop or phone on the same network (adjust IP if changed). Visit **Settings → GitHub updates** and connect the update token once per browser if needed (previously paired browsers migrate automatically). The website can then update or restore its previous version from the UI.

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

**Performance:** one analysis at a time, ≤14 s SQL safety timeout, ≤5 million hourly aircraft rows, ≤1,200 chart points. Multi-year charts automatically group at the appropriate drill-down level, starting with years. No writes, VACUUM, migrations or indexes are applied to Aerodrome.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `AIRSPACE_DB` | `/opt/aerodrome/aircraft_history.db` | Path of the existing Aerodrome DB |
| `AIRSPACE_HOST` | `0.0.0.0` | Network interface (LAN access by default) |
| `AIRSPACE_PORT` | `8088` | Website port |

Website display settings and launcher shortcuts are stored in each browser's local storage, so iPhone and PC preferences are independent. They do not duplicate aircraft observations.

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

## Current UI and updates (v1.4)

The root URL is the service launcher; `/analytics#explore` opens Traffic on the same port. All links except the first, pinned Airspace Analytics link are editable through Settings. On mobile, all workspace destinations are in the bottom navigation; no top tabs or sidebar menu are repeated.

The historical chart opens on years. Tap a year to open its months, a month to open weeks, a week to open days, and a day to open every hour (UK time). The current selection is shown as a breadcrumb above the chart; the Zoom out button returns one step. The breakdown charts, weekday averages, hourly averages and heatmap use the same date range and filters. Changing metrics does not lose the selected date.

For arbitrary ranges, expand **Range & filters** and choose **All history**, **Last…** with any number/unit, or exact **From / to** dates. Custom ranges start at a sensible grouping for the duration and remain drillable. No fixed time presets are required.

To install this release over an existing v1.3 Git checkout, push the updated project files to the same GitHub repository, then open **Settings → GitHub updates → Check GitHub → Update now**. Your existing pairing code continues to work. Only the Airspace Analytics service is restarted; Aerodrome, ADSB.im, SkyStats, and the ADS-B feeders are untouched.
