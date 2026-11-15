"""Aerodrome fallback: no copied observations, no duplicate rearm, and no live feed needed."""
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from backend import alerts


class AerodromeFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db_path=Path(self.tmp.name)/'aircraft_history.db'
        with sqlite3.connect(self.db_path) as db:
            db.execute("""CREATE TABLE all_sightings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, icao TEXT, callsign TEXT,
                aircraft_type TEXT, lat REAL, lon REAL, altitude REAL, seen_at INTEGER
            )""")
        self.alert_file=Path(self.tmp.name)/'alerts.sqlite3'
        self.previous_db=alerts.DB_PATH
        self.previous_cursor=alerts._aerodrome_cursor
        self.previous_live=alerts._last_good_url
        self.previous_scan=alerts._last_live_scan_at
        alerts.DB_PATH=self.alert_file
        alerts._aerodrome_cursor=0
        alerts._last_good_url=None
        alerts._last_live_scan_at=0
        self.environ=patch.dict(os.environ, {'AIRSPACE_DB':str(self.db_path)})
        self.environ.start()
        self.local=patch.object(alerts,'_local_addresses',return_value={'127.0.0.1'})
        self.local.start()
        self.network=patch.object(alerts,'_get_json',side_effect=URLError('Connection refused'))
        self.get=self.network.start()
        alerts.save_receiver({'lat':'50.0','lon':'0.0'})

    def tearDown(self):
        self.network.stop();self.local.stop();self.environ.stop()
        alerts.DB_PATH=self.previous_db
        alerts._aerodrome_cursor=self.previous_cursor
        alerts._last_good_url=self.previous_live
        alerts._last_live_scan_at=self.previous_scan
        self.tmp.cleanup()

    def sighting(self,hexcode='abc123',t='A388',lat=50.01,lon=0.01,alt=9000,age=0):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                'INSERT INTO all_sightings(icao,callsign,aircraft_type,lat,lon,altitude,seen_at)'
                ' VALUES(?,?,?,?,?,?,?)',
                (hexcode,'BAW123',t,lat,lon,alt,int(time.time())-age))

    def test_fallback_calculates_distance_from_saved_antenna_position(self):
        alerts.save_rule({'field':'type','pattern':'A388','max_km':20,'max_ft':12000})
        self.sighting()
        payload,lat,lon=alerts.read_receiver()
        self.assertEqual((lat,lon),(50.0,0.0))
        self.assertEqual(alerts._last_good_url,alerts._AERODROME_SOURCE)
        self.assertEqual(len(payload['aircraft']),1)
        self.assertLess(payload['aircraft'][0]['seen_pos'],30)
        alerts.process_snapshot(payload,lat,lon)
        events=alerts.snapshot()['events']
        self.assertEqual(len(events),1)
        self.assertLess(events[0]['distance_km'],20)
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM all_sightings').fetchone()[0],1)

    def test_gps_coordinates_keep_precision_without_being_hardcoded(self):
        # Fictional coordinates; private antenna location never belongs in Git.
        alerts.save_receiver({'lat':'51.123456789','lon':'-0.987654321'})
        cfg=alerts.snapshot()['receiver_settings']
        self.assertEqual(cfg['lat'],51.1234568)
        self.assertEqual(cfg['lon'],-0.9876543)
        self.assertLess(abs(cfg['lat']-51.123456789),0.0000001)

    def test_test_connection_does_not_consume_new_sightings(self):
        self.sighting()
        report=alerts.check_receiver()
        self.assertEqual(report['source'],alerts._AERODROME_SOURCE)
        self.assertTrue(report['coordinates_available'])
        self.assertEqual(report['aircraft'],1)
        payload,_,_=alerts.read_receiver()
        self.assertEqual(len(payload['aircraft']),1)
        again,_,_=alerts.read_receiver()
        self.assertEqual(again['aircraft'],[])
        self.assertEqual(self.get.call_count,5)  # one full localhost attempt, then DB cache

    def test_one_real_observation_is_not_two_exits(self):
        alerts.save_rule({'field':'type','pattern':'A388','max_km':20})
        self.sighting()
        a,lat,lon=alerts.read_receiver()
        alerts.process_snapshot(a,lat,lon)
        self.sighting(lon=1.0)
        a,lat,lon=alerts.read_receiver()
        alerts.process_snapshot(a,lat,lon)
        a,lat,lon=alerts.read_receiver()
        self.assertEqual(a['aircraft'],[])
        alerts.process_snapshot(a,lat,lon)
        self.assertEqual(alerts.snapshot()['rules'][0]['active'],1)
        self.sighting(lon=1.0)
        a,lat,lon=alerts.read_receiver()
        alerts.process_snapshot(a,lat,lon)
        self.assertEqual(alerts.snapshot()['rules'][0]['active'],0)
        self.sighting(lon=0.01)
        a,lat,lon=alerts.read_receiver()
        alerts.process_snapshot(a,lat,lon)
        self.assertEqual(len(alerts.snapshot()['events']),2)

    def test_separate_aircraft_same_type_trigger_independently(self):
        alerts.save_rule({'field':'type','pattern':'A388','max_km':20})
        self.sighting('abc123')
        self.sighting('def456')
        payload,lat,lon=alerts.read_receiver()
        alerts.process_snapshot(payload,lat,lon)
        self.assertEqual({e['hex'] for e in alerts.snapshot()['events']},{'abc123','def456'})

    def test_stale_observation_never_triggers(self):
        alerts.save_rule({'field':'type','pattern':'A388','max_km':20})
        self.sighting(age=300)
        a,lat,lon=alerts.read_receiver()
        self.assertEqual(a['aircraft'],[])
        alerts.process_snapshot(a,lat,lon)
        self.assertEqual(alerts.snapshot()['events'],[])

    def test_distance_rule_requires_saved_receiver_location(self):
        alerts.save_receiver({'url':'','lat':'','lon':''})
        alerts.save_rule({'field':'type','pattern':'A388','max_km':20})
        self.sighting()
        a,lat,lon=alerts.read_receiver()
        self.assertIsNone(lat)
        self.assertIsNone(lon)
        alerts.process_snapshot(a,lat,lon)
        self.assertEqual(alerts.snapshot()['events'],[])

    def test_no_full_scan_or_write_to_aerodrome(self):
        self.sighting()
        from backend import data
        statements=[]
        real=data.connection
        def traced():
            conn=real()
            conn.set_trace_callback(statements.append)
            return conn
        with patch.object(data,'connection',side_effect=traced):
            alerts.read_receiver()
        joined=' '.join(statements).lower()
        self.assertIn('order by id desc limit 2500',joined)
        self.assertNotIn('insert into',joined)
        self.assertNotIn('update all_sightings',joined)
        self.assertNotIn('delete from',joined)


if __name__=='__main__':
    unittest.main()
