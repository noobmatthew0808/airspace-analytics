#!/usr/bin/env bash
# Uninstalls ONLY Airspace Analytics systemd units. Preserves all project files
# and all Aerodrome/ADSB.im data. Run with sudo.
set -euo pipefail
if [[ "${EUID}" -ne 0 ]]; then echo 'Run: sudo bash scripts/uninstall.sh'; exit 1; fi
systemctl disable --now airspace-analytics-update.path 2>/dev/null || true
systemctl stop airspace-analytics-update.service 2>/dev/null || true
systemctl disable --now airspace-analytics.service 2>/dev/null || true
rm -f /etc/systemd/system/airspace-analytics.service \
      /etc/systemd/system/airspace-analytics-update.service \
      /etc/systemd/system/airspace-analytics-update.path
systemctl daemon-reload
echo 'Airspace Analytics service removed. Site files, Aerodrome database and ADS-B feeders remain untouched.'
