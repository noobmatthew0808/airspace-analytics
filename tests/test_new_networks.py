import io
import json
import time
import unittest
from unittest.mock import patch
from backend import new_networks as n, flights_live as live, api_budget

class NewNetworkTests(unittest.TestCase):
    def test_map_fresh_and_not_estimated(self):
        now=1800000000
        p={'hex':'abcdef','lat':50.8,'lon':0.2,'ageS':3,'registration':'G-ABCD','callsign':'BAW123','typecode':'A320','altBaro':32000,'gs':420,'origin':'EGKK','dest':'LIRF','kind':'airline'}
        payload={'now':now*1000,'ac':[p,dict(p,est=True),dict(p,ageS=121),dict(p,gndObj=True)]}
        out=n.parse_map(payload,now)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['r'],'G-ABCD')
        self.assertEqual(out[0]['seen_pos'],3)
        self.assertEqual(out[0]['route'],{'from':'EGKK','to':'LIRF'})
        self.assertNotIn('route_origin',out[0])
        with self.assertRaises(ValueError):n.parse_map(dict(payload,dataDelayS=60),now)
        with self.assertRaises(ValueError):n.parse_map(dict(payload,now=(now-90)*1000),now)

    def test_fly_strict_schema(self):
        now=1800000000
        p={'hex':'abcdef','seen':1,'seen_pos':2,'lat':50,'lon':0,'r':'G-ABCD','alt_baro':33000}
        self.assertEqual(n.parse_fly({'now':now,'ac':[p]},now)[0]['seen_pos'],2)
        with self.assertRaises(ValueError):n.parse_fly({'aircraft':[p]},now)

    def test_current_route_requires_matching_fresh_airframe(self):
        now=1800000000
        p={'flight':{'hex':'abcdef','callsign':'BAW123','origin':{'icao':'EGLL'},'dest':{'iata':'JFK'}},
           'live':{'hex':'abcdef','updated':now*1000}}
        self.assertEqual(n.parse_current(p,'BAW123','abcdef',now),('EGLL','JFK'))
        self.assertIsNone(n.parse_current(p,'BAW123','aaaaaa',now))
        self.assertIsNone(n.parse_current(dict(p,live={'hex':'abcdef','updated':(now-180)*1000}),'BAW123','abcdef',now))

    def test_history_requires_measured_landing_and_matching_reg(self):
        now=1800000000
        row={'hex':'abcdef','registration':'G-ABCD','dest':{'iata':'LGW'},'landingTime':(now-1200)*1000}
        payload={'hex':'abcdef','flights':[row,dict(row,registration='G-OTHER',landingTime=now*1000),dict(row,landingTime=None)]}
        self.assertEqual(n.parse_landing(payload,'abcdef','G-ABCD',now)['airport'],'LGW')
        self.assertEqual(n.parse_landing(payload,'abcdef','G-ABCD',now)['time'],now-1200)

    def test_map_request_is_regional_and_secret_header_only(self):
        key='mf_live_testfixture'
        def opener(req,timeout):
            self.assertTrue(req.full_url.startswith('https://map.flights/api/v1/near/'))
            self.assertIn('/250.0?limit=500',req.full_url)
            self.assertNotIn(key,req.full_url)
            self.assertEqual(req.get_header('X-api-key'),key)
            return io.BytesIO(json.dumps({'now':time.time()*1000,'ac':[]}).encode())
        self.assertEqual(n.near(n.MAP,key,(50.8,.2,450),opener),[])

    def test_parallel_scheduler_queues_all_eligible_sources_without_network_wait(self):
        keys={'adsb.fi':'','FlyItalyADSB':'test','adsb.lol':'test','ADSBiq':'test','AvioADSB':'test'}
        with patch.object(live,'_parallel_busy',set()),patch.object(live,'_ROTATION',{'retry_until':{}}),patch.object(api_budget,'remaining',return_value=0),patch.object(live.threading,'Thread') as thread:
            live._parallel_lookup(['G-ABCD'],keys)
            self.assertEqual(thread.call_count,5)
            live._parallel_lookup(['G-ABCD'],keys)
            self.assertEqual(thread.call_count,5)
