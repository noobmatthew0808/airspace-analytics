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

 def test_optional_extra_database_not_aerodrome(self):
  alerts=(ROOT/'backend/alerts.py').read_text()
  self.assertIn("alerts.sqlite3",alerts)
  self.assertIn("FROM seen_aircraft",alerts)
  self.assertNotIn("UPDATE seen_aircraft",alerts)
  self.assertNotIn("INSERT INTO sightings_hourly",alerts)
if __name__=='__main__':unittest.main()
