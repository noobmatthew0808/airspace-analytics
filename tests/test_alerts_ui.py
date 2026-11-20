"""Static integration contract for compact Alerts tab and receiver controls."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
class TestAlertsUI(unittest.TestCase):
 def test_separate_tab_without_replacing_traffic(self):
  app=(ROOT/'frontend/app.js').read_text()
  assert "function renderExplore()" in app
  assert "function renderChart(" in app
  assert "function todayChartSeries(" in app
  assert "renderAlertsPage" in app
  ui=(ROOT/'frontend/alerts-ui.js').read_text()
  for field in ['alertReceiverForm','alertReceiverCheck','alertNtfyForm','alertTest','alertAdd',
                'data-toggle','data-edit','alertHistory','alertApi']:
   self.assertIn(field,ui)
  self.assertIn('maxlength="1800"',ui)
  self.assertIn('aircraft seen (30s)',ui)
  self.assertNotIn('data-preset',ui)
  self.assertNotIn('alert-quick',ui)

 def test_compact_editor_and_keyless_provider_in_configuration(self):
  ui=(ROOT/'frontend/alerts-ui.js').read_text()
  css=(ROOT/'frontend/alerts.css').read_text()
  for label in ('Backup APIs','Configuration &amp; Logs','alertApis',
                'alertHistory','alertNtfy','alertReceiver','alertAllConfig'):
   self.assertIn(label,ui)
  self.assertNotIn('Also alert for network-only aircraft',ui)
  self.assertNotIn('name="network_only"',ui)
  self.assertNotIn('Minimum RSSI',ui)
  self.assertNotIn('min_rssi',ui)
  self.assertIn('Key saved',ui)
  self.assertIn('Test connection',ui)
  self.assertIn('api.adsb.lol/v2',ui)
  self.assertIn('api.flyitalyadsb.com/v2',ui)
  self.assertIn('opendata.adsb.fi/api',ui)
  self.assertIn('alertAdsbfiTest',ui)
  self.assertIn('alert-compact-top',css)
  self.assertIn('alert-compact-limits',css)
  self.assertEqual(ui.count('name="backup_apis"'),1)

 def test_optional_extra_database_not_aerodrome(self):
  alerts=(ROOT/'backend/alerts.py').read_text()
  self.assertIn("alerts.sqlite3",alerts)
  self.assertIn("FROM seen_aircraft",alerts)
  self.assertNotIn("UPDATE seen_aircraft",alerts)
  self.assertNotIn("INSERT INTO sightings_hourly",alerts)
if __name__=='__main__':unittest.main()
