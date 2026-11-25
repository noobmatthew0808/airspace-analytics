"""Cross-provider integration regressions with no external network."""
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.error import HTTPError
from backend import alerts, api_budget, extra_flight_sources as extra, flights_live, regional_sources as regional

class SharedCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.area=(50.,0.,25.)
        self.patches=[
            patch.object(alerts,'DB_PATH',Path(self.tmp.name)/'alerts.sqlite3'),
            patch.object(api_budget,'_next',{}),
            patch.object(regional,'_region',self.area),
            patch.object(regional,'_enabled',{'AvioADSB','ADSBiq','airplanes.live','OpenSky Network','ADSBHub'}),
            patch.object(regional,'_cache',{}),patch.object(regional,'_errors',{}),
            patch.object(regional,'_next',{}),patch.object(regional,'_busy',set()),
        ]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def plane(self,hexcode='abc123',lon=.01,seen=0):
        return {'hex':hexcode,'r':'G-TEST','flight':'TST123','lat':50.,'lon':lon,
                'seen':seen,'seen_pos':seen,'alt_baro':9000,'t':'A320'}

    def test_provider_cooldown_is_shared_but_independent(self):
        req=Mock()
        with patch.object(api_budget.time,'monotonic',return_value=100):
            with self.assertRaises(HTTPError):
                api_budget.open_request('ADSBiq',Mock(side_effect=HTTPError('https://example.org',429,'',{'Retry-After':'180'},None)),req)
            blocked=Mock()
            with self.assertRaisesRegex(ValueError,'rate limited'):
                api_budget.open_request('ADSBiq',blocked,req)
            blocked.assert_not_called()
            self.assertEqual(api_budget.remaining('ADSBiq'),180)
            other=Mock(return_value='ok')
            self.assertEqual(api_budget.open_request('AvioADSB',other,req),'ok')
            other.assert_called_once()
        with patch.object(api_budget.time,'monotonic',return_value=281):
            self.assertEqual(api_budget.open_request('ADSBiq',Mock(return_value='ok'),req),'ok')

    def test_global_snapshot_reused_for_nearby_alerts_not_all_world(self):
        rows=[self.plane(),self.plane('def456',lon=20)]
        rows[1]['r']='G-OTHER'
        def opener(req,timeout=12):
            return io.BytesIO(json.dumps({'now':time.time(),'ac':rows}).encode())
        result=flights_live._global_snapshot(['G-OTHER'],'dummy',opener,'AvioADSB')
        self.assertEqual([p['r'] for p in result],['G-OTHER'])
        nearby=regional.aircraft()
        self.assertEqual([p['hex'] for p in nearby],['abc123'])
        self.assertEqual(nearby[0]['_network_source'],'AvioADSB')

    def test_new_sources_are_opt_in_and_duplicate_aircraft_only_alert_once(self):
        alerts.save_rule({'label':'Local','field':'type','pattern':'A320','max_km':20})
        alerts.save_rule({'label':'Backup','field':'type','pattern':'A320','max_km':20,'backup_apis':True})
        for source in ('AvioADSB','ADSBiq','airplanes.live','OpenSky Network'):
            regional.publish(source,[self.plane()])
        with patch.object(extra,'hub_nearby',return_value=[dict(self.plane(),_network_source='ADSBHub')]):
            found=regional.aircraft()
        self.assertEqual(len(found),5)
        alerts.process_snapshot({'aircraft':[]},50,0,now=100,external=found)
        alerts.process_snapshot({'aircraft':[]},50,0,now=104,external=found)
        self.assertEqual(len(alerts.snapshot()['events']),1)
        self.assertEqual(alerts.snapshot()['events'][0]['rule_label'],'Backup')
        self.assertEqual(alerts.snapshot()['receiver']['aircraft'],0)

    def test_stale_or_disabled_source_cannot_supply_alert_data(self):
        regional.publish('ADSBiq',[self.plane(seen=121)])
        regional.publish('AvioADSB',[self.plane('def456')])
        regional._enabled.remove('AvioADSB')
        self.assertEqual(regional.aircraft(),[])
        regional.publish('ADSBiq',[self.plane()])
        with patch.object(regional.time,'monotonic',return_value=time.monotonic()+121):
            self.assertEqual(regional.aircraft(),[])

    def test_permission_gate_and_saved_keys_schedule_correct_workers(self):
        keys={'AvioADSB':'dummy','ADSBiq':'dummy','OpenSky Network':{'permission':True}}
        with patch.object(regional.threading,'Thread') as thread,patch.object(extra,'set_region') as hub:
            regional.configure(self.area,keys,{'airplaneslive':{'ok':True},'adsbhub':{'ok':True}})
            self.assertEqual({c.kwargs['name'] for c in thread.call_args_list},
                 {'airspace-region-AvioADSB','airspace-region-ADSBiq','airspace-region-airplanes.live'})
            hub.assert_called_once_with(self.area,True)
            self.assertNotIn('OpenSky Network',regional._enabled)
            regional.configure(self.area,keys,{'opensky':{'ok':True}})
            self.assertIn('OpenSky Network',regional._enabled)
            self.assertTrue(any(c.kwargs['name']=='airspace-region-OpenSky Network' for c in thread.call_args_list))

    def test_temporary_rate_limit_does_not_remove_prior_verified_activation(self):
        with patch.object(alerts,'test_airplaneslive',return_value={'ok':True}):
            alerts.run_provider_test('airplaneslive')
        with patch.object(alerts,'test_airplaneslive',side_effect=ValueError('HTTP 429 retry 90')):
            with self.assertRaises(ValueError):alerts.run_provider_test('airplaneslive')
        self.assertTrue(alerts.snapshot()['provider_tests']['airplaneslive']['ok'])

    def test_fresh_same_airframe_can_fill_missing_fields_not_different_callsign(self):
        a=self.plane()
        a.pop('alt_baro')
        b=dict(self.plane(seen=4),_source='ADSBiq')
        self.assertEqual(flights_live._prefer(a,b)['alt_baro'],9000)
        b['flight']='DIFFERENT'
        self.assertNotIn('alt_baro',flights_live._prefer(a,b))

    def test_unknown_opensky_hex_allowed_only_in_regional_mode(self):
        now=time.time()
        payload={'time':now,'states':[['abc123','TEST','UK',now,now,0.,50.,1000,False,100.,90.,0,None,None,None,False,0]]}
        self.assertEqual(extra.parse_opensky(payload,{},now),[])
        self.assertEqual(extra.parse_opensky(payload,{},now,allow_unknown=True)[0]['hex'],'abc123')
