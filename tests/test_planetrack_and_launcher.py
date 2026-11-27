import io
import json
import sqlite3
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from backend import planetrack as pt, shared_settings as settings, alerts, regional_sources


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()

class PlaneTrackTests(unittest.TestCase):
    def setUp(self):
        pt.reset()
    def tearDown(self):
        pt.reset()

    def test_live_mapping_and_conservative_freshness(self):
        now=1_800_000_000
        row={'icao24':'4076A3','callsign':'BAW123','registration':'G-XWBA','type':'A35K',
             'squawk':'2175','lat':51.4,'lon':-0.1,'altitude':36000,'velocity':447,'heading':284,
             'last_seen':iso(now-2)}
        result=pt.parse_live({'meta':{'generated_at':iso(now-2)},'aircraft':[row,dict(row,icao24='invalid'),dict(row,last_seen=iso(now-90))]},now)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0],{'hex':'4076a3','flight':'BAW123','r':'G-XWBA','t':'A35K','squawk':'2175','lat':51.4,'lon':-.1,'alt_baro':36000,'gs':447,'track':284,'seen':17,'seen_pos':17,'_source':'PlaneTrack','_network_source':'PlaneTrack'})
        self.assertEqual(pt.parse_live({'meta':{'generated_at':iso(now)},'aircraft':[dict(row,on_ground=True)]},now)[0]['alt_baro'],'ground')
        with self.assertRaisesRegex(ValueError,'Stale'):
            pt.parse_live({'meta':{'generated_at':iso(now-100)},'aircraft':[row]},now)

    def test_history_only_consistent_completed_routes(self):
        now=1_800_000_000
        leg={'callsign':'BAW123','arrival_time':iso(now-3600),'departure':{'airport':'EGLL'},'arrival':{'airport':'KJFK'}}
        self.assertEqual(pt.parse_history({'flights':[leg]},'BAW123',now),('EGLL','KJFK'))
        self.assertIsNone(pt.parse_history({'flights':[leg,dict(leg,arrival={'airport':'KLAX'})]},'BAW123',now))
        self.assertIsNone(pt.parse_history({'flights':[dict(leg,arrival_time=iso(now+3600))]},'BAW123',now))

    def test_free_usage_test_uses_header_not_url(self):
        key='pt_free_test_fixture'
        def fake(request,timeout):
            self.assertEqual(request.full_url,'https://planetrack.ai/v1/usage')
            self.assertEqual(request.get_header('X-api-key'),key)
            return io.BytesIO(json.dumps({'tier':'free','monthly_credits':2000,'credits_remaining':1500}).encode())
        self.assertTrue(pt.test(key,fake)['ok'])
        self.assertEqual(pt.status()['monthly_used'],500)
        self.assertNotIn(key,json.dumps(pt.status()))

    def test_credit_reserve_prevents_live_request(self):
        key='pt_free_test_fixture'
        pt._identity=pt.fingerprint(key)
        with patch.object(pt,'_usage',return_value={'tier':'free','monthly_quota':2000,'monthly_used':1990,'credits_remaining':10}),patch.object(pt,'_request') as request:
            pt._worker(key,pt._identity,'live')
            request.assert_not_called()
        self.assertIn('reserve',pt.status()['error'])

    def test_cache_key_binding_and_age(self):
        key='pt_free_test_fixture'
        pt._identity=pt.fingerprint(key)
        pt._planes=[{'hex':'abcdef','seen':20,'seen_pos':20,'lat':51,'lon':0,'_source':'PlaneTrack'}]
        pt._stamp=time.monotonic()-10
        self.assertGreaterEqual(pt.cached(pt._identity)[0]['seen'],30)
        self.assertEqual(pt.cached(pt.fingerprint('different-key')),[])
        pt._stamp=time.monotonic()-130
        self.assertEqual(pt.cached(pt._identity),[])

    def test_schedule_limits_shared_live_and_history(self):
        key='pt_free_test_fixture'
        with patch.object(pt.api_budget,'remaining',return_value=0),patch.object(pt.threading,'Thread') as thread:
            pt.ensure_live(key)
            pt.ensure_live(key)
            self.assertEqual(thread.call_count,1)
            pt._busy=False
            pt.ensure_live(key)
            self.assertEqual(thread.call_count,1)
            pt.usual_routes(key,['BAW123'])
            self.assertEqual(thread.call_count,2)
            pt._busy=False
            pt.usual_routes(key,['BAW456'])
            self.assertEqual(thread.call_count,2)

class TatThreeLinksTests(unittest.TestCase):
    def test_merge_existing_cards_preserves_other_rows(self):
        rows=[{'id':'custom','name':'Custom','group':'stats','url':'https://example.org/'},
              {'id':'old-tat','name':'The Air Traffic','group':'feeders','url':'https://theairtraffic.com/myip'},
              {'id':'theairtraffic-mlat','name':'TheAirTraffic MLAT','group':'feeders','url':'https://theairtraffic.com/sync/uk-ireland/feeder?id=Polegate_ADS-B'}]
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory=sqlite3.Row
            conn.execute('CREATE TABLE config(key TEXT PRIMARY KEY,value TEXT)')
            state={'excluded_days':['2026-11-09'],'links':rows,'revision':4,'migrated':[],'dates_initialized':True,'feeder_links_v11033':True,'dataero_links_v11041':True,'launcher_feeders_v11042':True}
            conn.execute('INSERT INTO config VALUES(?,?)',(settings.KEY,json.dumps(state)))
            result=settings._load(conn)
            self.assertEqual(len(result['links']),2)
            self.assertEqual(result['links'][0],rows[0])
            self.assertEqual(result['links'][1],{'id':'theairtraffic','name':'TheAirTraffic',**settings.TAT_THREE_LINKS})
            self.assertEqual(result['revision'],5)
            self.assertEqual(settings._load(conn),result)
            self.assertEqual(settings.links(result['links']),result['links'])
            with self.assertRaisesRegex(ValueError,'Invalid shortcut URL'):
                settings.links([dict(result['links'][1],thirdUrl='javascript:alert(1)')])
