#!/usr/bin/env bash
# One-time systemd installation. Run as: sudo bash scripts/install.sh
set -euo pipefail
if [[ "${EUID}" -ne 0 ]]; then echo 'Run with sudo: sudo bash scripts/install.sh'; exit 1; fi
OWNER="${SUDO_USER:-}"
if [[ -z "${OWNER}" || "${OWNER}" == root ]]; then echo 'Run as your normal user with sudo, not as root directly.'; exit 1; fi
HOME_DIR="$(getent passwd "$OWNER" | cut -d: -f6)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$ROOT" != "$HOME_DIR"/* ]]; then echo "For safety, place the project within $HOME_DIR"; exit 1; fi
if [[ ! -f "$ROOT/frontend/index.html" || ! -f "$ROOT/backend/server.py" ]]; then echo 'Incomplete project.'; exit 1; fi
if ! command -v python3 >/dev/null || ! command -v git >/dev/null || ! command -v systemctl >/dev/null; then echo 'Python 3, git and systemd are required.'; exit 1; fi
if [[ ! -f /opt/aerodrome/aircraft_history.db ]]; then echo 'Aerodrome database not found at expected location.'; exit 1; fi
if ! runuser -u "$OWNER" -- test -r /opt/aerodrome/aircraft_history.db; then echo 'Website user cannot read Aerodrome database.'; exit 1; fi
install -d -o "$OWNER" -g "$(id -gn "$OWNER")" -m 700 "$ROOT/.airspace-state"
touch "$ROOT/.airspace-state/update-request"
chown "$OWNER:$(id -gn "$OWNER")" "$ROOT/.airspace-state/update-request"
cat > /etc/systemd/system/airspace-analytics.service <<UNIT
[Unit]
Description=Airspace Analytics dashboard (read-only Aerodrome)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$OWNER
Group=$(id -gn "$OWNER")
WorkingDirectory=$ROOT
Environment=PYTHONUNBUFFERED=1
Environment=AIRSPACE_DB=/opt/aerodrome/aircraft_history.db
Environment=AIRSPACE_PORT=8088
ExecStart=/usr/bin/python3 -m backend
Restart=always
RestartSec=3
TimeoutStopSec=15
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
UNIT
cat > /etc/systemd/system/airspace-analytics-update.service <<UNIT
[Unit]
Description=Apply verified fast-forward Airspace Analytics GitHub update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$OWNER
Group=$(id -gn "$OWNER")
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 $ROOT/scripts/update_worker.py
ExecStartPost=+/usr/bin/systemctl restart airspace-analytics.service
TimeoutStartSec=180
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

UNIT
cat > /etc/systemd/system/airspace-analytics-update.path <<UNIT
[Unit]
Description=Watch for local Airspace Analytics update requests

[Path]
PathChanged=$ROOT/.airspace-state/update-request
Unit=airspace-analytics-update.service

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now airspace-analytics.service
systemctl enable --now airspace-analytics-update.path
printf '\nInstalled at http://%s:8088\n' "$(hostname -I | awk '{print $1}')"
echo 'Only the Airspace Analytics service was installed. ADS-B feeders were not restarted.'
