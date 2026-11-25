"""Offline regressions for optional sources: no external API or receiver needed."""
from datetime import datetime, timezone
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from backend import alerts, extra_flight_sources as extra

def state(now,hexcode='abc123',on_ground=False):
    return [hexcode,'EZY123  ','United Kingdom',now-2,now-1,-0.2,51.1,10000,on_ground,200,180,0,None,10000,'7000',False,0]

def sbs(now,hexcode='abc123'):
    dt=datetime.fromtimestamp(now,timezone.utc)
    fields=['MSG','3','1','1',hexcode,'1',dt.strftime('%Y/%m/%d'),dt.strftime('%H:%M:%S'),
            dt.strftime('%Y/%m/%d'),dt.strftime('%H:%M:%S'),'EZY123','30000','450','180','51.1','-0.2','','','','','','0']
    return ','.join(fields)

class OptionalSourceTests(unittest.TestCase):
    def test_opensky_maps_only_verified_hex_and_converts_units(self):
        now=int(time.time())
        payload={'time':now,'states':[state(now),state(now,'def456'),state(now-300,'111111')]}
        found=extra.parse_opensky(payload,{'abc123':'G-TEST','111111':'G-OLD'},now)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['r'],'G-TEST')
        self.assertEqual(found[0]['flight'],'EZY123')
        self.assertAlmostEqual(found[0]['alt_baro'],32808.4,places=1)
        self.assertAlmostEqual(found[0]['gs'],388.77,places=2)
        self.assertEqual(found[0]['seen_pos'],2)
        self.assertEqual(extra.parse_opensky({'time':now,'states':[state(now,on_ground=True)]},{'abc123':'G-TEST'},now)[0]['alt_baro'],'ground')
        with self.assertRaises(ValueError):extra.parse_opensky({'time':now-200,'states':[]},{},now)

    def test_oauth_only_with_permission_and_no_credentials_in_query(self):
        now=int(time.time())
        calls=[]
        def open_request(request,timeout=8):
            calls.append(request)
            if request.full_url==extra.TOKEN_URL:
                return io.BytesIO(json.dumps({'access_token':'mock-token','expires_in':1800}).encode())
            return io.BytesIO(json.dumps({'time':now,'states':[state(now)]}).encode())
        credentials={'client_id':'test-client','client_secret':'secret-demo','permission':True}
        with patch.object(extra,'_tokens',{}):
            with self.assertRaisesRegex(ValueError,'permission'):
                extra.opensky_lookup({**credentials,'permission':False},{'abc123':'G-TEST'},open_request)
            self.assertEqual(calls,[])
            self.assertEqual(extra.opensky_lookup(credentials,{'abc123':'G-TEST'},open_request)[0]['r'],'G-TEST')
            extra.opensky_lookup(credentials,{'abc123':'G-TEST'},open_request)
        self.assertEqual(len(calls),3)
        self.assertEqual(parse_qs(calls[0].data.decode())['grant_type'],['client_credentials'])
        self.assertEqual(parse_qs(urlsplit(calls[1].full_url).query),{'icao24':['abc123']})
        self.assertEqual(calls[1].get_header('Authorization'),'Bearer mock-token')
        self.assertNotIn('secret-demo',calls[1].full_url)

    def test_airplanes_registration_matching_and_timestamp(self):
        now=int(time.time())
        payload={'now':now*1000,'ac':[{'r':'GTEST','hex':'abc123','seen':1,'seen_pos':2},
                                      {'r':'G-OTHER','hex':'def456','seen':0}]}
        def opener(req,timeout=8):
            self.assertEqual(req.full_url,extra.AIRPLANES_URL+'G-TEST')
            return io.BytesIO(json.dumps(payload).encode())
        found=extra.airplanes_lookup('G-TEST',opener)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['r'],'G-TEST')
        self.assertEqual(found[0]['_source'],'airplanes.live')
        self.assertGreaterEqual(found[0]['seen'],1)
        payload['now']=(now-600)*1000
        with self.assertRaises(ValueError):extra.airplanes_lookup('G-TEST',opener)

    def test_sbs_discards_stale_messages_and_keeps_position_independent(self):
        now=int(time.time())
        hexcode,stamp,fields=extra._sbs(sbs(now),now)
        self.assertEqual(hexcode,'abc123')
        self.assertEqual(stamp,now)
        self.assertEqual(fields['position'],(51.1,-0.2))
        self.assertEqual(fields['alt_baro'],30000)
        self.assertIsNone(extra._sbs(sbs(now-600),now))
        with patch.object(extra,'_targets',{'abc123':'G-TEST'}),patch.object(extra,'_hub_fields',
          {'abc123':{'seen':(now,True),'alt_baro':(now,30000),'position':(now-80,(51.1,-0.2))}}):
            plane=extra._hub_planes()[0]
        self.assertEqual(plane['r'],'G-TEST')
        self.assertNotIn('lat',plane)

    def test_disabled_sources_never_schedule_network(self):
        with patch.object(extra,'_known',{}),patch.object(extra,'_targets',{}),patch.object(extra,'_cache',{}),patch.object(extra,'_hub_enabled',False),patch.object(extra,'_hub_touch',0),patch.object(extra.threading,'Thread') as thread:
            self.assertEqual(extra.collect(['G-TEST'],{'abc123':'G-TEST'},['G-TEST']),[])
            thread.assert_not_called()

    def test_credentials_are_local_and_permission_required(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(alerts,'DB_PATH',Path(tmp)/'alerts.sqlite3'):
            payload={'client_id':'example-client','key':'secret-demo','permission':False}
            with self.assertRaisesRegex(ValueError,'permission'):alerts.save_provider_key('opensky',payload)
            self.assertFalse(alerts.snapshot()['opensky']['key_set'])
            payload['permission']=True
            alerts.save_provider_key('opensky',payload)
            state=alerts.snapshot()
            self.assertTrue(state['opensky']['key_set'])
            self.assertNotIn('secret-demo',json.dumps(state))
            self.assertNotIn('example-client',json.dumps(state))
            with patch.object(extra,'test_opensky',return_value={'ok':True,'plan':'Verified'}):
                alerts.run_provider_test('opensky')
            self.assertTrue(alerts.snapshot()['provider_tests']['opensky']['ok'])
            alerts.save_provider_key('opensky',{'clear':True})
            self.assertFalse(alerts.snapshot()['opensky']['key_set'])
            self.assertNotIn('opensky',alerts.snapshot()['provider_tests'])
