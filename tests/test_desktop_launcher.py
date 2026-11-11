"""Desktop and launcher regression contracts for the v1.9.1 release."""
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class TestDesktopLauncher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / 'frontend/app.js').read_text()
        cls.css = (ROOT / 'frontend/styles.css').read_text()

    def test_grouped_requested_links(self):
        for label in ('View Stats', 'Feeder Website Status', 'Airspace Analytics',
                      'ADSB.im', 'SkyStats', 'tar1090 map', 'Dozzle',
                      'Flightradar24', 'AirNav Radar', 'FlightDeck', 'Plane Finder',
                      'ADS-B Exchange', 'FlightAware'):
            self.assertIn(label, self.js)
        self.assertIn("{id:'aerodrome'", self.js)
        for port in ('1099','5173','8000','1094','8754','30053','1093'):
            self.assertIn("port:'"+port+"'", self.js)
        self.assertIn("extraPath:'/map.html'", self.js)
        self.assertIn('globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2', self.js)

    def test_desktop_only_chart_scale(self):
        self.assertIn('window.innerWidth>=1050', self.js)
        self.assertIn('W=desktopMain?1120:720', self.js)
        self.assertIn('@media(min-width:1050px)', self.css)
        self.assertIn('grid-template-columns:repeat(6,minmax(0,1fr))',self.css)

    def test_settings_logo_editor(self):
        for token in ('link-group', 'link-extra-label', 'link-logo-domain',
                      'saveLinks', 'restoreLinks'):
            self.assertIn(token,self.js)

if __name__ == '__main__':
    unittest.main()
