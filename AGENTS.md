# Development guardrails

This application lives on an Ubuntu 26.04 machine running ADSB.im/Ultrafeeder,
Aerodrome, SkyStats and commercial feeders. Never modify or restart those
services as part of this project's installer or updater. The source of truth is
`/opt/aerodrome/aircraft_history.db`; use exclusively read-only SQLite.

Core principles:
- Preserve all aviation data and avoid a second raw-observation database.
- Timezone: `Europe/London`, including DST.
- Keep aircraft, inferred flight visits and observations distinct.
- Mark incomplete/missing data instead of inventing zeros or 100% uptime.
- Work on iPhone and PC; retain dark/light themes.
- No CDN/network dependencies at website runtime.
- Server: Python stdlib. Frontend: HTML/CSS/JS. No bundler or pip dependencies.
- In-app update requests only signal the root-owned systemd path unit;
  unprivileged Git updater; fixed root restart of our own service.
- `NoNewPrivileges=true` on main web service. Never expose arbitrary shell/SQL.
- Future changes should pass `python3 -m unittest tests.test_backend -v`,
  `node --check frontend/app.js`, and `bash -n scripts/install.sh`.
- When changing version, update `VERSION` and `CHANGELOG.md`.
- User wants one terminal command to install and then entirely UI-led updates.
