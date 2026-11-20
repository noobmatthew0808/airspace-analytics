"""Deterministic tests of opt-in FlyItalyADSB backup, RSSI and privacy."""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import alerts, flyitaly


class ExternalAlertsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=alerts.DB_PATH
        alerts.DB_PATH=Path(self.tmp.name)/'alerts.sqlite3'
        flyitaly.clear()

    def tearDown(self):
        alerts.DB_PATH=self.old
        flyitaly.clear()
        self.tmp.cleanup()

    def local(self, code='abc123', rssi=-18):
        return {'hex':code,'r':'G-TEST','t':'A400','seen':0,
                'rssi':rssi,'alt_baro':9000}  # Mode S: no position

    def network(self, code='abc123', rssi=None):
        return {'hex':code,'r':'G-TEST','t':'A400','seen':1,'seen_pos':1,
                'lat':50.01,'lon':0.,'alt_baro':9000,'dbFlags':1}

    def events(self):
        return alerts.snapshot()['events']

    def test_old_schema_migrates_without_losing_rules_or_events(self):
        with sqlite3.connect(alerts.DB_PATH) as db:
            db.execute('CREATE TABLE rules (id INTEGER PRIMARY KEY,label TEXT NOT NULL,field TEXT NOT NULL,pattern TEXT NOT NULL,max_km REAL,min_ft INTEGER,max_ft INTEGER,enabled INTEGER NOT NULL,created INTEGER NOT NULL)')
            db.execute("INSERT INTO rules VALUES (1,'Old military','military','YES',40,NULL,NULL,1,1)")
            db.execute('CREATE TABLE events (id INTEGER PRIMARY KEY,rule_id INTEGER,rule_label TEXT NOT NULL,hex TEXT NOT NULL,callsign TEXT,registration TEXT,aircraft_type TEXT,distance_km REAL,altitude_ft INTEGER,created INTEGER NOT NULL,delivery TEXT NOT NULL DEFAULT \'pending\',attempts INTEGER NOT NULL DEFAULT 0,next_attempt INTEGER NOT NULL DEFAULT 0,last_error TEXT)')
            db.execute("INSERT INTO events(id,rule_label,hex,created,delivery) VALUES (1,'Historic','abc123',1,'sent')")
        result=alerts.snapshot()
        self.assertEqual(result['rules'][0]['use_flyitaly'],0)
        self.assertEqual(result['rules'][0]['network_only'],0)
        self.assertIsNone(result['rules'][0]['min_rssi'])
        self.assertEqual(result['events'][0]['delivery'],'sent')
        self.assertEqual(result['events'][0]['source'],'local')

    def test_rssi_can_trigger_posless_mode_s_and_reject_weak_signal(self):
        alerts.save_rule({'label':'Strong Mode S','field':'hex','pattern':'ABC123',
                          'min_rssi':-20})
        alerts.process_snapshot({'aircraft':[self.local(rssi=-25)]},50,0,now=100)
        self.assertEqual(self.events(),[])
        alerts.process_snapshot({'aircraft':[self.local(rssi=-18)]},50,0,now=103)
        self.assertEqual(len(self.events()),1)
        self.assertIsNone(self.events()[0]['distance_km'])

    def test_local_rules_never_see_network_only_aircraft_without_optin(self):
        alerts.save_rule({'label':'Existing military','field':'military','max_km':40})
        alerts.process_snapshot({'aircraft':[]},50,0,now=100,
                                external=[self.network()])
        self.assertEqual(self.events(),[])

    def test_backup_enriches_mode_s_identity_and_mlat_position_only_if_opted_in(self):
        alerts.save_rule({'label':'Local backup','field':'military','max_km':40,
                          'use_flyitaly':True})
        alerts.save_rule({'label':'Local only','field':'military','max_km':40})
        alerts.process_snapshot({'aircraft':[self.local()]},50,0,now=100,
                                external=[self.network()])
        self.assertEqual([e['rule_label'] for e in self.events()],['Local backup'])
        self.assertEqual(self.events()[0]['source'],'local')
        self.assertLess(self.events()[0]['distance_km'],40)

    def test_network_only_needs_both_explicit_optins_and_distance(self):
        for data in (
            {'network_only':True,'max_km':40},
            {'network_only':True,'use_flyitaly':True},
            {'network_only':True,'use_flyitaly':True,'max_km':40,'min_rssi':-20},
        ):
            with self.assertRaises(ValueError):
                alerts.save_rule({'label':'Invalid','field':'military',**data})
        alerts.save_rule({'label':'Network allowed','field':'military',
                          'use_flyitaly':True,'network_only':True,'max_km':40})
        alerts.process_snapshot({'aircraft':[]},50,0,now=100,
                                external=[self.network()])
        alerts.process_snapshot({'aircraft':[]},50,0,now=103,
                                external=[self.network()])
        self.assertEqual(len(self.events()),1)
        self.assertEqual(self.events()[0]['source'],'FlyItalyADSB')

    def test_network_only_remote_position_and_age_must_be_fresh(self):
        alerts.save_rule({'label':'Network allowed','field':'military',
                          'use_flyitaly':True,'network_only':True,'max_km':40})
        stale=self.network();stale['seen_pos']=80
        alerts.process_snapshot({'aircraft':[]},50,0,now=100,
                                external=[stale])
        self.assertEqual(self.events(),[])
        far=self.network();far['lat']=52.
        alerts.process_snapshot({'aircraft':[]},50,0,now=103,
                                external=[far])
        self.assertEqual(self.events(),[])
        fresh=self.network()
        alerts.process_snapshot({'aircraft':[]},50,0,now=106,
                                external=[fresh])
        self.assertEqual(len(self.events()),1)

    def test_private_key_is_not_returned_through_alerts_api(self):
        key='fia_TEST_MOCK_KEY_WITHOUT_REAL_CREDENTIAL'
        alerts.save_flyitaly({'key':key})
        snapshot=alerts.snapshot()
        self.assertTrue(snapshot['flyitaly']['key_set'])
        self.assertNotIn(key,json.dumps(snapshot))
        with sqlite3.connect(alerts.DB_PATH) as db:
            self.assertEqual(db.execute(
                "SELECT value FROM config WHERE key='flyitaly_key'").fetchone()[0],key)
        alerts.save_flyitaly({'clear':True})
        self.assertFalse(alerts.snapshot()['flyitaly']['key_set'])

    def test_key_and_backup_toggle_preserve_existing_rule_fields(self):
        rule=alerts.save_rule({'label':'A380','field':'type','pattern':'A388',
                              'max_km':20,'use_flyitaly':True})
        item=alerts.snapshot()['rules'][0]
        alerts.save_rule({**item,'id':rule,'enabled':False})
        modified=alerts.snapshot()['rules'][0]
        self.assertEqual(modified['use_flyitaly'],1)
        self.assertEqual(modified['enabled'],0)
        self.assertEqual(modified['max_km'],20)

    def test_network_only_notification_uses_network_title_not_local_click(self):
        alerts.save_rule({'label':'Military','field':'military',
                          'use_flyitaly':True,'network_only':True,'max_km':40})
        alerts.save_notifier({'topic':'localtesttopic'})
        alerts.process_snapshot({'aircraft':[]},50,0,now=100,external=[self.network()])
        response=Mock(status=200)
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=None)
        opener=Mock(return_value=response)
        alerts.deliver_pending(now=100,opener=opener)
        request=opener.call_args.args[0]
        self.assertIn('(network)',request.get_header('Title'))
        self.assertIsNone(request.get_header('Click'))
        self.assertEqual(request.get_header('Priority'),'3')


class ProviderTests(unittest.TestCase):
    def setUp(self):flyitaly.clear()
    def tearDown(self):flyitaly.clear()

    def test_https_header_response_timestamp_and_quota_are_validated(self):
        response=Mock()
        response.headers={
            'X-FIA-Plan':'feeder','X-FIA-Used-Month':'1',
            'X-FIA-Quota-Month':'10000000',
        }
        response.read.return_value=json.dumps({
            'now':time.time()-1,
            'ac':[{'hex':'abc123','seen':1,'seen_pos':1,'lat':50.1,'lon':0.}]
        }).encode()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=None)
        opener=Mock(return_value=response)
        status=flyitaly.fetch('mock_key',50.,0.,40.,opener=opener)
        req=opener.call_args.args[0]
        self.assertEqual(req.full_url,
                         'https://api.flyitalyadsb.com/v2/lat/50.0000000/lon/0.0000000/dist/40.0')
        self.assertEqual(req.get_header('X-api-key'),'mock_key')
        self.assertTrue(status['connected'])
        self.assertEqual(status['plan'],'feeder')
        self.assertGreater(flyitaly.aircraft()[0]['seen_pos'],1)

    def test_rejects_stale_response_and_never_reuses_old_cached_flight(self):
        response=Mock()
        response.headers={}
        response.read.return_value=json.dumps({
            'now':time.time()-120,
            'ac':[{'hex':'abc123','seen':0,'lat':50.0,'lon':0.}]
        }).encode()
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=None)
        with self.assertRaisesRegex(ValueError,'Stale'):
            flyitaly.fetch('mock_key',50.,0.,50.,opener=Mock(return_value=response))
        self.assertEqual(flyitaly.aircraft(),[])

    def test_external_api_does_not_run_during_local_matching(self):
        with patch.object(flyitaly,'fetch',side_effect=AssertionError('network call in matching')):
            alerts.process_snapshot({'aircraft':[{
                'hex':'abc123','r':'G-TEST','seen':0,'rssi':-10
            }]},50.,0.,now=100)


if __name__ == '__main__':
    unittest.main()
