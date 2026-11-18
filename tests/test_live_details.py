"""Live metadata should remain read-only and use IATA 3-letter routes."""
import unittest
from unittest.mock import patch

from backend import live_details

class TestLiveDetails(unittest.TestCase):
    def test_parsing_strict(self):
        self.assertEqual(live_details.parse_items('408345:GMILS,4CA76F:EIN5MW,wrong:bad'),
                         [('408345','GMILS'),('4CA76F','EIN5MW')])
        self.assertEqual(live_details.parse_items(''),[])

    def test_iata_only(self):
        self.assertEqual(live_details._route('EGKK','LEMD'), 'LGW – MAD')
        self.assertEqual(live_details._route('KJFK','EGLL'), 'JFK – LHR')
        self.assertEqual(live_details._route('XXXX','EGKK'),'')
        self.assertEqual(live_details._route('EGKK','EGKK'),'')

    def test_distance(self):
        self.assertEqual(live_details._km(51,0,51,0),0)
        self.assertGreater(live_details._km(51,0,52,0),100)

    def test_empty(self):
        with patch.object(live_details,'_readsb') as readsb:
            self.assertEqual(live_details.details({'items':'INVALID'}),{'aircraft':{}})
            readsb.assert_not_called()

    def test_no_uncontrolled_external_route_lookups(self):
        with patch.object(live_details,'_json') as lookup:
            self.assertEqual(live_details._lookup_from_aerodrome('G-ABCD'),'')
            lookup.assert_not_called()

    def test_readsb_source_labels(self):
        self.assertEqual(live_details._source_name('adsb_icao'), 'ADS-B')
        self.assertEqual(live_details._source_name('mlat'), 'MLAT')
        self.assertEqual(live_details._source_name('mode_s'), 'Mode S')
        self.assertEqual(live_details._source_name('tisb_icao'), 'TIS-B')
        self.assertEqual(live_details._source_name('adsr_icao'), 'ADS-R')
        self.assertEqual(live_details._source_name(None), '')
