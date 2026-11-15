"""Receiver controls are isolated, local-only, and never write into Aerodrome."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from backend import alerts

class ReceiverTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.old=alerts.DB_PATH
  alerts.DB_PATH=Path(self.temp.name)/'alerts.sqlite3'
 def tearDown(self):
  alerts.DB_PATH=self.old
  self.temp.cleanup()

 def test_manual_location_and_local_source(self):
  alerts.save_receiver({'url':'http://127.0.0.1:1099/map/data/aircraft.json','lat':'50.80','lon':'0.25'})
  with alerts.connect() as db:
   cfg=alerts.receiver_settings(db)
  self.assertEqual((cfg['lat'],cfg['lon']),(50.8,0.25))
  self.assertEqual(cfg['url'],'http://127.0.0.1:1099/map/data/aircraft.json')
  self.assertEqual(alerts.snapshot()['receiver_settings']['url'],cfg['url'])
  for bad in ['https://evil.example/aircraft.json','http://127.0.0.1:1099/admin','http://u:p@127.0.0.1:1099/data/aircraft.json']:
   with self.assertRaises(ValueError):alerts.save_receiver({'url':bad})
  for bad in [{'lat':'50.1','lon':''},{'lat':'100','lon':'1'},{'lat':'5','lon':'inf'}]:
   with self.assertRaises(ValueError):alerts.save_receiver(bad)

 def test_missing_antenna_position_allows_unrestricted_type_rule(self):
  a={'now':time.time(),'aircraft':[{'hex':'abc123','t':'A388','seen':0,'alt_baro':7000}]}
  with patch.object(alerts,'_get_json',side_effect=lambda u:a if u.endswith('aircraft.json') else (_ for _ in ()).throw(URLError('Missing receiver metadata'))):
   payload,lat,lon=alerts.read_receiver()
  self.assertEqual((lat,lon),(None,None))
  alerts.save_rule({'label':'A380 type-only','field':'type','pattern':'A388'})
  alerts.save_rule({'label':'A380 nearby','field':'type','pattern':'A388','max_km':20})
  alerts.process_snapshot(payload,lat,lon,now=101)
  self.assertEqual({e['rule_label'] for e in alerts.snapshot()['events']},{'A380 type-only'})

 def test_saved_location_overrides_optional_metadata(self):
  alerts.save_receiver({'lat':'50.3','lon':'0.07'})
  def fake_json(u):
   return {'now':time.time(),'aircraft':[]} if u.endswith('aircraft.json') else {'lat':51.0,'lon':1.0}
  with patch.object(alerts,'_get_json',side_effect=fake_json):
   _,lat,lon=alerts.read_receiver()
  self.assertEqual((lat,lon),(50.3,0.07))

 def test_invalid_aircraft_fields_do_not_break_other_alerts(self):
  alerts.save_rule({'label':'A380','field':'type','pattern':'A388','max_km':20,'max_ft':15000})
  alerts.save_rule({'label':'Military','field':'military','pattern':'YES'})
  payload={'aircraft':[
    {'hex':'abc001','t':'A388','lat':float('nan'),'lon':0.01,'seen':0,'seen_pos':0,'alt_baro':9000,'dbFlags':'N/A'},
    {'hex':'abc002','t':'A388','lat':50.0,'lon':0.01,'seen':0,'seen_pos':0,'alt_baro':9000,'dbFlags':'N/A'}]}
  alerts.process_snapshot(payload,50,0,now=101)
  self.assertEqual([e['hex'] for e in alerts.snapshot()['events']],['abc002'])

 def test_operator_name_matching_and_type_wildcard(self):
  saved=alerts.validate_rule({'field':'operator','pattern':'BRITISH AIRWAYS*','label':'BA'})
  self.assertEqual(saved['pattern'],'BRITISH AIRWAYS*')
  self.assertTrue(alerts._match_pattern('B74*','B748'))
  self.assertTrue(alerts._match_pattern('A34*','A346'))

if __name__=='__main__':unittest.main()
