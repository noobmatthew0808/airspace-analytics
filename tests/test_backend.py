import os
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from datetime import datetime,timezone
from .make_sample_db import seed
from backend import data

class TestReadOnlyAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.db=Path(cls.tmp.name)/'fictional.db'
        cls.count=seed(cls.db,60)
        os.environ['AIRSPACE_DB']=str(cls.db)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop('AIRSPACE_DB',None)
        cls.tmp.cleanup()

    def test_read_only_connection(self):
        with closing(data.connection()) as c:
            self.assertRaises(Exception,c.execute,"DELETE FROM seen_aircraft")
        self.assertTrue(self.db.exists())

    def test_health_and_overview(self):
        h=data.health()
        self.assertTrue(h['ok'])
        self.assertEqual(h['total_aircraft'],7)
        self.assertGreater(h['raw_observations'],100)
        o=data.overview()
        self.assertGreaterEqual(o['unique_today'],1)
        self.assertGreaterEqual(o['observations_today'],1)

    def test_grouped_metrics(self):
        for metric in ['flights','aircraft','observations']:
            for bucket in ['hour','day','week','month','year','weekday','hour_of_day','month_of_year']:
                a=data.analyze({'period':'last_7d','metric':metric,'bucket':bucket})
                self.assertGreaterEqual(a['total'],0)
                self.assertGreater(len(a['series']),0)
                self.assertTrue(a['breakdowns']['category'])
        self.assertGreater(data.analyze({'period':'last_7d','metric':'observations'})['total'],
                           data.analyze({'period':'last_7d','metric':'aircraft'})['total'])

    def test_category_and_airline_filter(self):
        base=data.analyze({'period':'last_7d','metric':'observations','category':'all'})
        military=data.analyze({'period':'last_7d','metric':'observations','category':'military'})
        self.assertLess(military['total'],base['total'])
        easy=data.analyze({'period':'last_7d','metric':'observations','airline':'easyJet'})
        self.assertGreater(easy['total'],0)
        only=data.analyze({'period':'last_7d','metric':'aircraft','type':'A320'})
        self.assertEqual(only['total'],1)

    def test_pattern(self):
        x=data.patterns({'period':'last_7d','metric':'flights'})
        self.assertEqual(len(x['heatmap']),168)
        self.assertEqual(len(x['weekday']),7)
        self.assertEqual(len(x['hourly']),24)

    def test_compare_with_numeric_timestamps(self):
        for preset in ['today','this_week','this_month','this_year','last_7d']:
            x=data.compare({'period':preset,'metric':'aircraft','bucket':'day','offset':'2'})
            self.assertIn('difference',x)
            self.assertLess(x['right']['start'],x['left']['start'])
        x=data.compare({'period':'last_7d','comparison':'custom','other_start':str(int(datetime.now(timezone.utc).timestamp())-16*86400),'other_end':str(int(datetime.now(timezone.utc).timestamp())-8*86400),'metric':'flights'})
        self.assertIn('left',x)

    def test_previous_calendar_year_comparison(self):
        x = data.compare({'period':'today','comparison':'year_ago','metric':'aircraft','bucket':'hour'})
        a = datetime.fromtimestamp(x['left']['start'],data.UK)
        b = datetime.fromtimestamp(x['right']['start'],data.UK)
        self.assertEqual(a.month,b.month)
        self.assertEqual(a.day,b.day)
        self.assertEqual(a.hour,b.hour)
        self.assertEqual(a.year,b.year+1)
        self.assertIsNone(x['change_percent'])  # No invented year-old baseline in fixture

    def test_recurring_averages_skip_unrecorded_periods(self):
        all_week = data.analyze({'period':'last_7d','metric':'aircraft','bucket':'weekday'})
        self.assertEqual(len(all_week['series']),7)
        self.assertTrue(any(p['samples'] >= 1 for p in all_week['series']))
        self.assertTrue(any(p['samples'] == 0 for p in all_week['series']))
        monday = data.coverage_eligible('2025-01-06','day',int(datetime(2025,1,1,tzinfo=data.UTC).timestamp()),int(datetime(2025,1,10,tzinfo=data.UTC).timestamp()),{})
        self.assertFalse(monday)

    def test_raw_tables_search_and_detail(self):
        self.assertIn('all_sightings',[t['name'] for t in data.list_tables()])
        d=data.table_rows('all_sightings',1,10,'4ca')
        self.assertTrue(d['rows'])
        self.assertTrue(data.aircraft_search('A320'))
        self.assertEqual(data.aircraft_detail('4ca123')['aircraft']['aircraft_type'],'A320')
        self.assertRaises(data.DataError,data.table_rows,'sqlite_master')

    def test_iso_epoch_uk_summer(self):
        self.assertEqual(data.epoch('2026-07-01T12:00'),int(datetime(2026,7,1,11,0,tzinfo=timezone.utc).timestamp()))

if __name__=='__main__':unittest.main()
