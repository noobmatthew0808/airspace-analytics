"""Regression: tar1090 can be published on this Linux machine's LAN IP only."""
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError, HTTPError

from backend import alerts


class TestReceiverOnLAN(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = alerts.DB_PATH
        self.old_last = alerts._last_good_url
        alerts.DB_PATH = Path(self.temp.name) / 'alert-rules.sqlite3'
        alerts._last_good_url = None
        self.addresses = {'127.0.0.1', '192.168.1.187'}
        self.patch_ips = patch.object(alerts, '_local_addresses', return_value=self.addresses)
        self.patch_ips.start()

    def tearDown(self):
        self.patch_ips.stop()
        alerts.DB_PATH = self.old_db
        alerts._last_good_url = self.old_last
        self.temp.cleanup()

    def test_manual_pc_lan_ip_is_valid_but_other_hosts_are_rejected(self):
        local = 'http://192.168.1.187:1099/map/data/aircraft.json'
        alerts.save_receiver({'url':local})
        self.assertEqual(alerts.snapshot()['receiver_settings']['url'],local)
        for forbidden in (
            'http://192.168.1.188:1099/data/aircraft.json',
            'http://10.0.0.99:1099/data/aircraft.json',
            'http://example.com:1099/data/aircraft.json',
            'https://192.168.1.187:1099/data/aircraft.json',
            'http://192.168.1.187:1099/data/aircraft.json?x=1',
            'http://evil:pass@192.168.1.187:1099/data/aircraft.json',
            'http://192.168.1.187:99999/data/aircraft.json',
        ):
            with self.subTest(url=forbidden), self.assertRaises(ValueError):
                alerts.save_receiver({'url':forbidden})

    def test_auto_detects_lan_if_loopback_refuses_connection(self):
        good = 'http://192.168.1.187:1099/data/aircraft.json'
        tried = []
        def fetch(url):
            tried.append(url)
            if url == good:
                return {'now':time.time(),'aircraft':[{'hex':'abc123','t':'A388','seen':0}]}
            if url == good.replace('aircraft.json','receiver.json'):
                return {'lat':50.86,'lon':0.24}
            raise URLError('Connection refused')
        with patch.object(alerts,'_get_json',side_effect=fetch):
            sample,lat,lon=alerts.read_receiver()
            self.assertEqual(len(sample['aircraft']),1)
            self.assertEqual((lat,lon),(50.86,0.24))
            self.assertEqual(alerts._last_good_url,good)
            self.assertIn('http://127.0.0.1:1099/data/aircraft.json',tried)
            self.assertIn(good,tried)
            self.assertEqual(alerts.check_receiver()['source'],good)
            # A known good feed is polled first the next time.
            self.assertEqual(tried[-2],good)
        self.assertNotIn('http://192.168.1.188:1099/data/aircraft.json',tried)

    def test_local_url_candidate_list_prioritises_compatible_paths(self):
        urls=alerts._receiver_candidates(self.addresses)
        self.assertIn('http://192.168.1.187:1099/map/data/aircraft.json',urls)
        self.assertIn('http://192.168.1.187:1099/data/aircraft.json',urls)
        self.assertIn('http://192.168.1.187:8080/data/aircraft.json',urls)
        self.assertIn('http://192.168.1.187:1090/data/aircraft.json',urls)
        self.assertEqual(urls[0], 'http://127.0.0.1:1090/data/aircraft.json')
        self.assertEqual(len(set(urls)),len(urls))


    def test_new_live_ultrafeeder_port_triggers_registration_and_type_alerts(self):
        """The receiver's verified readsb JSON fields drive real alert rules."""
        alerts.save_receiver({'lat':'50.0','lon':'0.0'})
        alerts.save_rule({'label':'Watchlist','field':'registration','pattern':'HA-LDG',
                         'max_km':20,'max_ft':14000})
        alerts.save_rule({'label':'A340','field':'type','pattern':'A34*','max_km':20})
        feed={'now':time.time(),'aircraft':[{'hex':'abc123','r':'HA-LDG','t':'A346',
              'lat':50.01,'lon':0.0,'alt_baro':9000,'seen':0,'seen_pos':0}]}
        live_url='http://127.0.0.1:1090/data/aircraft.json'
        tried=[]
        def fetch(url):
            tried.append(url)
            if url==live_url:return feed
            if url==live_url.replace('aircraft.json','receiver.json'):return {}
            raise URLError('Unexpected feed')
        with patch.object(alerts,'_get_json',side_effect=fetch):
            payload,lat,lon=alerts.read_receiver()
        self.assertEqual((lat,lon),(50.0,0.0))
        self.assertEqual(tried[0],live_url)
        self.assertEqual(alerts._last_good_url,live_url)
        alerts.process_snapshot(payload,lat,lon)
        self.assertEqual({e['rule_label'] for e in alerts.snapshot()['events']},
                         {'Watchlist','A340'})
        self.assertTrue(all(e['distance_km']<20 for e in alerts.snapshot()['events']))

    def test_live_source_missing_dbflags_uses_aerodrome_military_category(self):
        """Readsb may omit dbFlags: trusted existing Aerodrome classification still works."""
        from backend import data
        dbfile=Path(self.temp.name)/'aerodrome.db'
        with sqlite3.connect(dbfile) as db:
            db.execute('CREATE TABLE seen_aircraft (icao TEXT PRIMARY KEY, registration TEXT, '
                       'aircraft_type TEXT, operator TEXT, category TEXT)')
            db.executemany('INSERT INTO seen_aircraft VALUES (?,?,?,?,?)',[
                ('abc123','G-TEST','A400','Military operator','military'),
                ('def456','G-CIVIL','A320','Civil operator','commercial')])
        alerts.save_rule({'label':'Military','field':'military','pattern':'YES','max_km':40})
        live={'aircraft':[
            {'hex':'abc123','r':'G-TEST','t':'A400','seen':0,'seen_pos':0,
             'lat':50.01,'lon':0.0,'alt_baro':8000},
            {'hex':'def456','r':'G-CIVIL','t':'A320','seen':0,'seen_pos':0,
             'lat':50.01,'lon':0.0,'alt_baro':8000}]}
        # The live feed contains full r/t, but no dbFlags on either aircraft.
        with patch.dict(os.environ, {'AIRSPACE_DB':str(dbfile)}):
            alerts.process_snapshot(live,50.0,0.0)
        self.assertEqual([e['hex'] for e in alerts.snapshot()['events']],['abc123'])

    def test_unreachable_manual_source_does_not_scan_other_hosts(self):
        wanted='http://192.168.1.187:1099/data/aircraft.json'
        alerts.save_receiver({'url':wanted})
        with patch.object(alerts,'_get_json',side_effect=URLError('refused')) as fetch:
            with self.assertRaisesRegex(ValueError,'Receiver URL unreachable'):
                alerts.read_receiver()
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(fetch.call_args.args[0],wanted)

    def test_ui_references_browser_host_without_hardcoding_site_ip(self):
        ui=(Path(__file__).resolve().parents[1]/'frontend'/'alerts-ui.js').read_text()
        self.assertIn("ae(location.hostname)",ui)
        self.assertIn("automatic localhost and LAN detection",ui)
        self.assertIn("result.source",ui)


if __name__ == '__main__':
    unittest.main()
