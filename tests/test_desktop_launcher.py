"""Contract tests for desktop-only chart scale and launcher shortcuts."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class TestLauncher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js=(ROOT/'frontend/app.js').read_text()
        cls.css=(ROOT/'frontend/styles.css').read_text()

    def test_receiver_links_and_groups(self):
        for name in ('View Stats', 'Feeder Website Status', 'Airspace Analytics',
            'ADSB.im', 'SkyStats', 'tar1090 map', 'Aerodrome', 'Dozzle',
            'Flightradar24', 'AirNav Radar', 'FlightDeck', 'Plane Finder',
            'ADS-B Exchange', 'FlightAware'):
            self.assertIn(name,self.js)
        for url in ('/map/', '/stats.html', '/myip/',
            'https://globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2',
            'https://www.airnavradar.com/stations/EXTRPI737643',
            'https://www.tryflightdeck.com/map/account/feeder'):
            self.assertIn(url,self.js)
        for port in ('1573','5173','1099','8000','1094','8754','30053','1093'):
            self.assertIn("port:'"+port+"'",self.js)

    def test_settings_can_edit_both_groups(self):
        for marker in ('link-group','link-extra-label','link-extra-url','saveLinks','addLink'):
            self.assertIn(marker,self.js)

    def test_desktop_specific_chart_scale(self):
        self.assertIn("window.matchMedia('(min-width: 1000px)').matches",self.js)
        self.assertIn('W=desktop?1160:720',self.js)
        self.assertIn('@media(min-width:1000px)',self.css)
        self.assertIn('repeat(6,minmax(0,1fr))',self.css)
