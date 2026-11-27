"""Focused offline tests for the v1.10.32 settings/API/cache refinement."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import alerts, shared_settings, flights_log

def shortcut(id,name=None):
    return {'id':id,'name':name or id,'group':'feeders','url':'https://example.org/'+id}

class SharedPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=patch.object(alerts,'DB_PATH',Path(self.tmp.name)/'alerts.sqlite3')
        self.db.start()
    def tearDown(self):
        self.db.stop()
        self.tmp.cleanup()
    def migrate(self,client,dates,items,legacy=True):
        return shared_settings.update({'action':'migrate','client':client,'excluded_days':dates,'links':items,'has_legacy_links':legacy})
    def test_two_devices_merge_existing_dates_and_custom_shortcuts(self):
        first=self.migrate('browser-one',['2026-11-09'],[shortcut('existing'),shortcut('laptop')])
        second=self.migrate('browser-two',['2026-11-09','2026-11-24'],[shortcut('existing'),shortcut('phone')])
        self.assertEqual(second['excluded_days'],['2026-11-09','2026-11-24'])
        self.assertEqual([x['id'] for x in second['links']],['existing','laptop','phone'])
        self.assertEqual(shared_settings.read(),second)
        self.assertEqual(self.migrate('browser-two',[],[]),second)
    def test_removed_date_and_link_are_not_resurrected_by_old_browser(self):
        first=self.migrate('browser-one',['2026-11-09','2026-11-24'],[shortcut('existing'),shortcut('remove')])
        second=shared_settings.update({'action':'remove_day','day':'2026-11-24'})
        third=shared_settings.update({'action':'links','revision':second['revision'],'links':[shortcut('existing')]})
        migrated=self.migrate('browser-two',['2026-11-24'],[shortcut('remove'),shortcut('phone')])
        self.assertEqual(migrated['excluded_days'],['2026-11-09'])
        self.assertEqual([x['id'] for x in migrated['links']],['existing','phone'])
        with self.assertRaisesRegex(ValueError,'another device'):
            shared_settings.update({'action':'links','revision':third['revision'],'links':[]})
    def test_fresh_browser_does_not_override_shared_shortcuts(self):
        first=self.migrate('browser-one',[],[shortcut('custom')])
        later=self.migrate('browser-new',None,[shortcut('default')],False)
        self.assertEqual(later['links'],first['links'])
        self.assertEqual(later['excluded_days'],[])
    def test_feeder_link_correction_preserves_all_other_settings_and_is_one_time(self):
        old=[{'id':'adsbiq','name':'ADSBiq','url':'https://adsbiq.com/my-stations','extraUrl':'https://adsbiq.com/stats'},
             {'id':'avioadsb','name':'AvioADSB','url':'https://avioadsb.org/dashboard','sub':'Receiver dashboard and API usage'},
             {'id':'adsbhub','name':'ADSBHub','url':'https://www.adsbhub.org/statistic.php'},
             {'id':'opensky','name':'OpenSky Network','url':'https://opensky-network.org/my-opensky'},
             shortcut('custom')]
        # Simulate the unmodified v1.10.32 SQLite record.
        state={'excluded_days':['2026-11-24'],'links':old,'revision':7,
               'migrated':['browser-one'],'dates_initialized':True}
        with alerts.connect() as c:
            c.execute('INSERT INTO config(key,value) VALUES(?,?)',(shared_settings.KEY,json.dumps(state)))
        updated=shared_settings.read()
        self.assertEqual(updated['revision'],8)
        self.assertEqual(updated['excluded_days'],state['excluded_days'])
        self.assertEqual([r['id'] for r in updated['links']],[r['id'] for r in old])
        self.assertEqual(updated['links'][0]['extraUrl'],old[0]['extraUrl'])
        self.assertEqual(updated['links'][-1],old[-1])
        for row in updated['links'][:-1]:
            self.assertEqual(row['url'],shared_settings.FEEDER_LINK_FIXES[row['id']])
        self.assertEqual(shared_settings.read(),updated)
        # A deliberate later user edit is not overwritten by the migration.
        edited=updated['links']
        edited[0]['url']='https://example.org/my-custom-adsbiq'
        result=shared_settings.update({'action':'links','revision':8,'links':edited})
        self.assertEqual(shared_settings.read(),result)
        self.assertEqual(result['links'][0]['url'],'https://example.org/my-custom-adsbiq')

    def test_old_browser_feeder_links_are_corrected_on_import(self):
        old=[{'id':'adsbiq','name':'ADSBiq','url':'https://adsbiq.com/my-stations'}]
        result=self.migrate('browser-old',['2026-11-24'],old)
        self.assertEqual(result['links'][0]['url'],shared_settings.FEEDER_LINK_FIXES['adsbiq'])
        self.assertEqual(result['excluded_days'],['2026-11-24'])

    def test_dataero_correction_only_touches_dataero_and_preserves_later_edits(self):
        other=shortcut('custom')
        old={'id':'dataero','name':'Dataero','group':'feeders','url':'https://radar.dataero.eu/map',
             'extraLabel':'Claim receiver','extraUrl':'https://radar.dataero.eu/contribute/connect','tone':'sky'}
        state={'excluded_days':['2026-11-24'],'links':[other,old],'revision':7,
               'migrated':['browser-one'],'dates_initialized':True,'feeder_links_v11033':True}
        with alerts.connect() as c:
            c.execute('INSERT INTO config(key,value) VALUES(?,?)',(shared_settings.KEY,json.dumps(state)))
        updated=shared_settings.read()
        self.assertEqual(updated['revision'],8)
        self.assertEqual(updated['excluded_days'],state['excluded_days'])
        self.assertEqual(updated['links'],[other,{**old,**shared_settings.DATAERO_LINKS}])
        self.assertEqual(shared_settings.read(),updated)
        updated['links'][1]['url']='https://example.org/my-dataero'
        result=shared_settings.update({'action':'links','revision':8,'links':updated['links']})
        self.assertEqual(shared_settings.read(),result)
        self.assertEqual(result['links'][1]['url'],'https://example.org/my-dataero')
        imported=self.migrate('browser-two',None,[old])
        self.assertEqual(imported['links'],result['links'])

    def test_old_dataero_import_and_removed_dataero(self):
        old={'name':'Dataero','group':'feeders','url':'https://radar.dataero.eu/map'}
        result=self.migrate('browser-one',[],[old,shortcut('custom')])
        self.assertEqual(result['links'][0],{**old,**shared_settings.DATAERO_LINKS})
        removed=shared_settings.update({'action':'links','revision':result['revision'],'links':[shortcut('custom')]})
        self.assertEqual(self.migrate('browser-two',[],[old])['links'],removed['links'])

    def test_invalid_settings_rejected(self):
        with self.assertRaises(ValueError):shared_settings.update({'action':'add_day','day':'2026-02-31'})
        with self.assertRaises(ValueError):self.migrate('browser-one',[],[{'name':'Unsafe','url':'javascript:alert(1)'}])
        self.assertEqual(shared_settings.read()['revision'],0)
    def test_test_result_is_server_persistent_and_bound_to_key(self):
        key='avio_example_private_key'
        alerts.save_provider_key('avioadsb',{'key':key})
        with patch.object(alerts,'test_avio',return_value={'ok':True,'plan':'contributor','aircraft':None}):
            alerts.run_provider_test('avioadsb')
        first=alerts.snapshot()['provider_tests']['avioadsb']
        self.assertTrue(first['ok'])
        self.assertNotIn(key,json.dumps(alerts.snapshot()))
        self.assertNotIn('credential',first)
        self.assertEqual(alerts.snapshot()['provider_tests']['avioadsb'],first)
        with patch.object(alerts,'test_avio',side_effect=ValueError('HTTP 401')):
            with self.assertRaises(ValueError):alerts.run_provider_test('avioadsb')
        self.assertFalse(alerts.snapshot()['provider_tests']['avioadsb']['ok'])
        alerts.save_provider_key('avioadsb',{'key':'avio_another_private_key'})
        self.assertNotIn('avioadsb',alerts.snapshot()['provider_tests'])
        self.assertTrue(alerts.snapshot()['avioadsb']['key_set'])
    def test_keyless_results_are_persisted(self):
        with patch.object(alerts,'test_adsbfi',return_value={'aircraft':17}):
            alerts.run_provider_test('adsbfi')
        self.assertTrue(alerts.snapshot()['provider_tests']['adsbfi']['ok'])
        self.assertFalse(alerts.snapshot()['adsbfi']['key_set'])

class PersistentSheetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=dict(flights_log._CACHE)
        self.path=Path(self.tmp.name)/'sheet.json'
        self.patches=[patch.object(flights_log,'CACHE_PATH',self.path),patch.object(flights_log,'_cache_enabled',True)]
        for p in self.patches:p.start()
        flights_log._CACHE.update(rows=None,at=0,error=None)
        self.rows=[{'id':'1','date':'2026-10-23','from_airport':'LGW','to_airport':'CDG','flight_code':'U28409','airline':'easyJet','airplane':'A320','registration':'G-EZBH','who':'Example'}]
    def tearDown(self):
        flights_log._CACHE.clear()
        flights_log._CACHE.update(self.old)
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_disk_cache_loads_after_restart_without_network(self):
        flights_log._remember(self.rows)
        self.assertTrue(self.path.exists())
        self.assertEqual(os.stat(self.path).st_mode&0o777,0o600)
        flights_log._CACHE.update(rows=None,at=0,error=None)
        with patch.object(flights_log,'_cache_enabled',False):flights_log.start_cache()
        with patch.object(flights_log,'_fetch',side_effect=AssertionError('no external request')):
            self.assertEqual(flights_log.read_cached()['flights'],self.rows)
    def test_stale_snapshot_is_returned_without_waiting_for_network(self):
        flights_log._remember(self.rows)
        flights_log._CACHE['at']=time.monotonic()-flights_log.REFRESH_PERIOD-1
        with patch.object(flights_log,'_schedule_refresh') as schedule,patch.object(flights_log,'_fetch',side_effect=AssertionError('must not block')):
            result=flights_log.read_cached()
        schedule.assert_called_once_with(False)
        self.assertEqual(result['flights'],self.rows)
    def test_confirmed_delete_updates_snapshot_without_waiting_for_remote_refresh(self):
        flights_log._remember(self.rows)
        with patch.object(flights_log,'_fetch',side_effect=[self.rows,{'deleted':1}]):
            flights_log.mutate({'action':'delete','id':'1'})
        self.assertEqual(flights_log.read_cached()['flights'],[])
        self.assertEqual(json.loads(self.path.read_text())['flights'],[])
    def test_failed_remote_edit_cannot_overwrite_snapshot(self):
        flights_log._remember(self.rows)
        with patch.object(flights_log,'_fetch',side_effect=[self.rows,{'deleted':0}]):
            with self.assertRaises(ValueError):flights_log.mutate({'action':'delete','id':'1'})
        self.assertEqual(flights_log.read_cached()['flights'],self.rows)
