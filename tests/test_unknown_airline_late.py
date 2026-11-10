"""A blank call sign corrected later in the *same visit* is not a new flight."""
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from .make_sample_db import seed
from backend import data

class TestLateCallsign(unittest.TestCase):
    def test_later_known_callsign_attributes_earlier_unknown_visit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.db'
            seed(path,2)
            hour=(int(time.time())//3600-3)*3600
            with sqlite3.connect(path) as db:
                db.execute("INSERT INTO seen_aircraft (icao,category) VALUES ('faa123','commercial')")
                rows=[('faa123',hour,None,'A21N','A321neo',6,hour+3300,hour+3360),
                      ('faa123',hour+3600,'EZY1234','A21N','A321neo',6,hour+3900,hour+3960)]
                db.executemany('''INSERT INTO sightings_hourly
                    (icao,hour_bucket,callsign,aircraft_type,type_desc,sighting_count,first_seen_at,last_seen_at)
                    VALUES (?,?,?,?,?,?,?,?)''',rows)
            old=os.environ.get('AIRSPACE_DB')
            os.environ['AIRSPACE_DB']=str(path)
            try:
                result=data.analyze({'period':'custom','start':str(hour),'end':str(hour+7200),
                                     'bucket':'hour','metric':'flights','icao':'faa123'})
                self.assertEqual(result['total'],1)
                airlines={x['name']:x['value'] for x in result['breakdowns']['airline']}
                self.assertEqual(airlines,{'easyJet':1})
                records=data.analyze({'period':'custom','start':str(hour),'end':str(hour+7200),
                                      'bucket':'hour','metric':'observations','icao':'faa123'})
                self.assertEqual(records['total'],12)
            finally:
                if old is None:os.environ.pop('AIRSPACE_DB',None)
                else:os.environ['AIRSPACE_DB']=old
