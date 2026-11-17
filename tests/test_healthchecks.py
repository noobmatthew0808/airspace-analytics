"""Regression coverage for the Settings-only read-only monitoring integration."""
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
import json
import unittest

from backend import healthchecks


def reply(value):
    return BytesIO(json.dumps(value).encode('utf-8'))


class TestHealthchecks(unittest.TestCase):
    def setUp(self):
        healthchecks._CACHE.update(at=0.0, value=None)

    def test_two_checks_and_duration_of_recovered_outage(self):
        checks = {'checks': [
            {'name': 'Ubuntu Server', 'status': 'up', 'unique_key': 'a' * 40,
             'last_ping': '2026-11-17T18:03:00+00:00',
             'next_ping': '2026-11-17T18:04:00+00:00',
             'timeout': 60, 'grace': 120, 'n_pings': 120},
            {'name': 'ADSB.im Receiver', 'status': 'down', 'unique_key': 'b' * 40,
             'last_ping': '2026-11-17T16:00:00+00:00',
             'next_ping': None, 'timeout': 3600, 'grace': 960},
        ]}
        flips_ubuntu = [
            {'timestamp': '2026-11-17T18:02:00+00:00', 'up': 1},
            {'timestamp': '2026-11-17T18:00:00+00:00', 'up': 0},
        ]
        flips_adsb = [{'timestamp': '2026-11-17T18:30:00+00:00', 'up': 0}]
        with patch.object(healthchecks, 'urlopen', side_effect=[
                reply(checks), reply(flips_ubuntu), reply(flips_adsb)]) as hit:
            value = healthchecks.snapshot(refresh=True)
            self.assertEqual(len(value['checks']), 2)
            self.assertEqual(value['checks'][0]['outages'][0]['duration_seconds'], 120)
            self.assertFalse(value['checks'][0]['outages'][0]['ongoing'])
            self.assertEqual(value['checks'][1]['status'], 'down')
            self.assertTrue(value['checks'][1]['outages'][0]['ongoing'])
            # A second UI poll uses cache: no additional Healthchecks requests.
            self.assertEqual(healthchecks.snapshot(), value)
            self.assertEqual(hit.call_count, 3)
        self.assertNotIn('hcr_', json.dumps(value))
        self.assertNotIn('unique_key', json.dumps(value))
        self.assertNotIn('ping_url', json.dumps(value))

    def test_missing_project_check_is_not_reported_as_down(self):
        with patch.object(healthchecks, 'urlopen', side_effect=[
                reply({'checks': [{'name': 'Ubuntu Server', 'status': 'new'}]})]):
            value = healthchecks.snapshot(refresh=True)
        self.assertEqual(value['checks'][0]['status'], 'new')
        self.assertEqual(value['checks'][1]['status'], 'not_found')
        self.assertIn('project', value['checks'][1]['note'])

    def test_invalid_or_offline_key_reports_error_not_false_success(self):
        with patch.object(healthchecks, 'urlopen', side_effect=URLError('offline')):
            value = healthchecks.snapshot(refresh=True)
        self.assertEqual(value['checks'], [])
        self.assertIn('could not be reached', value['error'])

    def test_incomplete_flips_do_not_invent_downtime(self):
        flips = [{'timestamp': '2026-11-17T18:00:00+00:00', 'up': 1}]
        incidents = healthchecks._outages(flips, 'up', healthchecks.datetime.now(healthchecks.timezone.utc))
        self.assertEqual(incidents, [])


class TestMonitoringUIContract(unittest.TestCase):
    def test_section_is_in_settings_not_traffic_or_alerts(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / 'frontend/app.js').read_text()
        server = (root / 'backend/server.py').read_text()
        before_settings = js[:js.index('async function renderSettings()')]
        settings = js[js.index('async function renderSettings()'):js.index('function setUpdateInfo(')]
        self.assertNotIn('settingsRow(' + "'Server monitoring'", before_settings)
        self.assertIn("settingsRow('Server monitoring','',monitoringBox())", settings)
        self.assertIn("'/api/monitoring/healthchecks'", server)
        self.assertIn("async function renderExplore()", js)
        self.assertIn("function renderAlertsPage", (root / 'frontend/alerts-ui.js').read_text())


if __name__ == '__main__':
    unittest.main()
