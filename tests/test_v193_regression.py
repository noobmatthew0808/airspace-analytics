"""Small regression gate for launcher links and calendar error recovery."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class TestV193Regression(unittest.TestCase):
    def test_launcher_defaults_and_migration(self):
        js=(ROOT/'frontend/app.js').read_text()
        self.assertIn("id:'aerodrome',name:'Aerodrome'",js)
        self.assertIn("port:'1099',path:'/',icon:'radar',brand:'AD'",js)
        self.assertNotIn("port:'1573'",js)
        self.assertIn('airspace-links-v193-repaired',js)
        self.assertIn('...defaultLinks,...added',js)
        self.assertIn('id="zoomBack"',js)
    def test_future_calendar_is_blank_not_error(self):
        js=(ROOT/'frontend/app.js').read_text()
        self.assertIn('if(from<nowUK)',js)
        self.assertIn('let response={series:[]}',js)
        self.assertIn('Start must be before end',js)
        calendar=(ROOT/'frontend/calendar.js').read_text()
        self.assertIn('while(days.length < 42)',calendar)
        self.assertIn('data-heat-back',calendar)
    def test_logos_and_restricted_image_sources(self):
        self.assertTrue((ROOT/'frontend/brand/aerodrome.svg').exists())
        js=(ROOT/'frontend/app.js').read_text()
        self.assertIn('skystats/main/docs/logo/logo_icon.png',js)
        self.assertIn('raw.githubusercontent.com', (ROOT/'backend/server.py').read_text())
if __name__=='__main__': unittest.main()
