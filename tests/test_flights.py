"""No-network tests for the original flight-log SheetDB semantics and live status."""
import tempfile
import time
import unittest
import sqlite3
import json
from unittest.mock import patch, Mock, MagicMock
from urllib.error import URLError

from backend import flights_log, flights_live


def flight(id='1',reg='G-WUKU',date='2025-07-04'):
    return {'id':id,'date':date,'from_airport':'LGW','to_airport':'BTS',
            'flight_code':'W95776','airline':'Wizz Air','airplane':'A321neo',
            'registration':reg,'who':'Matthew, Florence'}


class SheetDBTests(unittest.TestCase):
    def setUp(self):
        self.saved=dict(flights_log._CACHE)
        flights_log._CACHE.update(rows=None,at=0,error=None)
        self.rows=[flight('1'),flight('3','G-EZBH')]
        self.calls=[]

    def tearDown(self):
        flights_log._CACHE.clear()
        flights_log._CACHE.update(self.saved)

    def fake(self,path='',method='GET',payload=None,opener=None):
        self.calls.append((method,path,payload))
        if method=='GET':return [dict(row) for row in self.rows]
        if method=='POST':
            self.rows.extend(dict(row) for row in payload['data'])
            return {'created':len(payload['data'])}
        if method=='PATCH':
            for row in self.rows:
                if row['id']==path.split('/')[-1]:
                    row.update(payload['data'])
            return {'updated':1}
        if method=='DELETE':
            self.rows=[row for row in self.rows if row['id']!=path.split('/')[-1]]
            return {'deleted':1}
        raise AssertionError('Unexpected SheetDB operation')

    def test_source_endpoint_and_original_nine_columns(self):
        self.assertEqual(flights_log.SHEETDB,
                         'https://sheetdb.io/api/v1/9fnmgmxtdst8m')
        self.assertEqual(flights_log.COLUMNS,(
            'id','date','from_airport','to_airport','flight_code',
            'airline','airplane','registration','who'))

    def test_add_uses_original_lowest_unused_id_and_google_sheet(self):
        with patch.object(flights_log,'_fetch',side_effect=self.fake):
            result=flights_log.mutate({'action':'create','data':{
                **flight('ignored',reg='g-wuky'),
                'who':'Matthew; Florence'}})
            self.assertEqual(result['id'],'2')
            self.assertEqual(self.rows[-1]['registration'],'G-WUKY')
            self.assertEqual(self.rows[-1]['who'],'Matthew, Florence')
            self.assertEqual(self.calls[-1][0],'POST')
            self.assertEqual(self.calls[-1][2]['data'][0]['id'],'2')
            loaded=flights_log.read()
            self.assertEqual(len(loaded['flights']),3)
            self.assertEqual(loaded['source'],'Google Sheets via SheetDB')

    def test_patch_and_delete_target_original_sheet_id_only(self):
        with patch.object(flights_log,'_fetch',side_effect=self.fake):
            result=flights_log.mutate({'action':'update','id':'3',
                                       'data':flight('ignored','G-TEST')})
            self.assertEqual(result['id'],'3')
            self.assertEqual(self.rows[1]['registration'],'G-TEST')
            self.assertEqual(self.calls[-1][0],'PATCH')
            self.assertEqual(self.calls[-1][1],'/id/3')
            flights_log.mutate({'action':'delete','id':'1'})
            self.assertEqual([row['id'] for row in self.rows],['3'])
            self.assertEqual(self.calls[-1][0],'DELETE')

    def test_unavailable_google_sheet_shows_clearly_marked_cached_read(self):
        with patch.object(flights_log,'_fetch',side_effect=self.fake):
            flights_log.read()
        flights_log._CACHE['at']=time.monotonic()-16
        with patch.object(flights_log,'_fetch',side_effect=flights_log.SheetError('Network down')):
            info=flights_log.read()
            self.assertTrue(info['cached'])
            self.assertIn('unavailable',info['warning'])
            with self.assertRaisesRegex(ValueError,'Network down'):
                flights_log.mutate({'action':'create','data':flight()})

    def test_invalid_and_missing_ids_do_not_delete_sheet_rows(self):
        with patch.object(flights_log,'_fetch',side_effect=self.fake):
            with self.assertRaises(ValueError):
                flights_log.mutate({'action':'delete','id':'../../something'})
            with self.assertRaisesRegex(ValueError,'not found'):
                flights_log.mutate({'action':'delete','id':'765432'})
        self.assertEqual(len(self.rows),2)


class LiveStatusTests(unittest.TestCase):
    def setUp(self):
        self.old=dict(flights_live._REMOTE)
        self.old_other={k:dict(v) for k,v in flights_live._OTHER_REMOTE.items()}
        self.old_rotation={'at':flights_live._ROTATION['at'],
                           'cursor':flights_live._ROTATION['cursor'],
                           'retry_until':dict(flights_live._ROTATION['retry_until'])}
        flights_live._REMOTE.update(updated=0,aircraft=[],error=None)
        for value in flights_live._OTHER_REMOTE.values():
            value.update(updated=0.,aircraft=[],error=None)
        flights_live._ROTATION.update(at=0.,cursor=0,retry_until={})
        # Other tests exercise the same production API caches; fixtures must
        # not accidentally inherit their aircraft and claim they are live.
        self.provider_patches=[
            patch.object(flights_live.flights_history,'schedule'),
            patch.object(flights_live.flights_history,'cached',return_value=None),
            patch.object(flights_live.flights_routes,'cached_routes',return_value={}),
            patch.object(flights_live.adsbfi,'aircraft',return_value=[]),
            patch.object(flights_live.adsblol,'aircraft',return_value=[]),
            patch.object(flights_live.flyitaly,'aircraft',return_value=[]),
        ]
        for provider in self.provider_patches:provider.start()

    def tearDown(self):
        for provider in reversed(self.provider_patches):provider.stop()
        flights_live._REMOTE.clear()
        flights_live._REMOTE.update(self.old)
        for name,value in self.old_other.items():
            flights_live._OTHER_REMOTE[name].clear()
            flights_live._OTHER_REMOTE[name].update(value)
        flights_live._ROTATION.clear()
        flights_live._ROTATION.update(self.old_rotation)

    def test_registration_with_parentheses_matches_current_airframe(self):
        self.assertEqual(flights_live.current_registration('G-OLD (G-WUKU)'),'G-WUKU')
        self.assertEqual(flights_live.normal_reg('g-wuky'),'GWUKY')

    def test_no_data_is_not_incorrectly_called_parked(self):
        with patch.object(flights_live,'_local_planes',return_value=[]):
            with patch.object(flights_live,'_routes',return_value={}):
                data=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(data['aircraft']['G-WUKU']['status'],'N/A')

    def test_fresh_local_aircraft_with_cached_route_is_flying(self):
        local={'hex':'407abc','r':'G-WUKU','flight':'EZY76','alt_baro':33000,
               'gs':400,'seen':0,'seen_pos':2,'lat':51.2,'lon':0,'_source':'Your antenna'}
        with patch.object(flights_live,'_local_planes',return_value=[local]):
            with patch.object(flights_live,'_routes',return_value={'EZY76':'LGW – BTS'}):
                data=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        item=data['aircraft']['G-WUKU']
        self.assertEqual(item['status'],'Flying LGW – BTS')
        self.assertEqual(item['source'],'Your antenna')
        self.assertEqual(item['hex'],'407abc')

    def test_route_enrichment_is_used_only_for_current_live_callsign(self):
        local={'hex':'407abc','r':'G-WUKU','flight':'EZY76','alt_baro':33000,
               'gs':400,'seen':0,'seen_pos':2,'lat':51.2,'lon':0,
               '_source':'Your antenna'}
        with patch.object(flights_live,'_local_planes',return_value=[local]):
            with patch.object(flights_live,'_routes',return_value={}):
                with patch.object(flights_live.flights_routes,'cached_routes',
                                  return_value={'EZY76':'LGW–BTS'}) as routes:
                    result=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(result['aircraft']['G-WUKU']['status'],'Flying LGW–BTS')
        self.assertEqual(routes.call_args.args[0][0]['callsign'],'EZY76')
        self.assertEqual(routes.call_args.args[0][0]['lat'],51.2)

    def test_current_positionless_detection_uses_icao_without_stale_coordinates(self):
        local={'hex':'407abc','r':'G-WUKU','flight':'EZY76',
               'alt_baro':33000,'seen':0,'seen_pos':999,
               '_source':'Your antenna'}
        with patch.object(flights_live,'_local_planes',return_value=[local]):
            with patch.object(flights_live,'_routes',return_value={}):
                with patch.object(flights_live.flights_routes,'cached_routes',return_value={}) as routes:
                    result=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(result['aircraft']['G-WUKU']['status'],'Flying')
        routes.assert_called_once_with([{'callsign':'EZY76','icao':'407abc'}])

    def test_observed_usual_route_is_labelled_as_likely(self):
        local={'hex':'407abc','r':'G-WUKU','flight':'EZY76',
               'alt_baro':34000,'gs':410,'seen':0,'seen_pos':1,
               'lat':51.2,'lon':0,'_source':'Your antenna'}
        remote={'hex':'407abc','r':'G-WUKU','flight':'EZY76',
                'alt_baro':34000,'seen':0,'_source':'FlyItalyADSB',
                'route':{'from_iata':'LGW','to_iata':'VIE','count':7,
                         'source':'observed'}}
        with patch.object(flights_live,'_local_planes',return_value=[local]):
            with patch.object(flights_live,'_routes',return_value={}):
                result=flights_live.snapshot('G-WUKU',
                    network_fetch=lambda regs:[remote])
        self.assertEqual(result['aircraft']['G-WUKU']['status'],
                         'Flying · likely LGW–VIE')
        self.assertEqual(result['aircraft']['G-WUKU']['route_confidence'],'usual')
        self.assertEqual(result['aircraft']['G-WUKU']['route'],'LGW–VIE')

    def test_historical_arrival_keeps_unknown_current_position_distinct(self):
        evidence={'airport':'VIE','time':1795190000,'evidence':'ground'}
        with patch.object(flights_live,'_local_planes',return_value=[]):
            with patch.object(flights_live.flights_history,'cached',return_value=evidence):
                result=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(result['aircraft']['G-WUKU']['status'],'Last landed VIE')
        self.assertEqual(result['aircraft']['G-WUKU']['last_landed_at'],1795190000)

    def test_ground_near_verified_airport_is_at_airport(self):
        plane={'hex':'407abc','r':'G-WUKU','flight':'EZY76','alt_baro':'ground',
               'gs':2,'seen':0,'seen_pos':1,'lat':51.1481,'lon':-0.1903}
        with patch.object(flights_live,'_local_planes',return_value=[plane]):
            with patch.object(flights_live,'_airport_positions',return_value=[('LGW',51.1481,-0.1903)]):
                data=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(data['aircraft']['G-WUKU']['status'],'At LGW')

    def test_ground_without_confirmed_airport_is_not_labelled_at_airport(self):
        plane={'hex':'407abc','r':'G-WUKU','alt_baro':'ground',
               'seen':0,'seen_pos':1,'lat':-25.,'lon':160.,'gs':0}
        with patch.object(flights_live,'_local_planes',return_value=[plane]):
            with patch.object(flights_live,'_airport_positions',return_value=[]):
                data=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(data['aircraft']['G-WUKU']['status'],'Ground')

    def test_network_cache_ages_and_cannot_show_expired_plane_as_live(self):
        live={'hex':'407abc','r':'G-WUKU','alt_baro':33000,'seen':0,
              'seen_pos':0,'lat':51.2,'lon':0.3,'_source':'adsb.fi'}
        with patch.object(flights_live,'_local_planes',return_value=[]):
            first=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[live])
            self.assertTrue(first['aircraft']['G-WUKU']['status'].startswith('Flying'))
            flights_live._REMOTE['updated']=time.monotonic()-180
            second=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(second['aircraft']['G-WUKU']['status'],'N/A')

    def test_local_history_is_read_only_and_returns_newest_hex(self):
        db=sqlite3.connect(':memory:')
        db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE seen_aircraft(icao TEXT,registration TEXT,last_seen_at INTEGER)')
        now=int(time.time())
        db.executemany('INSERT INTO seen_aircraft VALUES (?,?,?)',[
            ('4080f7','G-WUKU',now-50),
            ('4080f8','G-WUKU',now-100),
            ('400001','G-EZBH',now-3600)])
        with patch.object(flights_live.data,'connection',return_value=db):
            found=flights_live._local_last_seen(['G-WUKU','g-ezbh','G-UNKNOWN'])
        self.assertEqual(found['GWUKU']['hex'],'4080f7')
        self.assertEqual(found['GWUKU']['last_seen_at'],now-50)
        self.assertEqual(found['GEZBH']['hex'],'400001')
        self.assertNotIn('GUNKNOWN',found)

    def test_untracked_aircraft_still_has_last_local_sighting(self):
        with patch.object(flights_live,'_local_planes',return_value=[]):
            with patch.object(flights_live,'_local_last_seen',
                              return_value={'GWUKU':{'hex':'4080f7','last_seen_at':1234567890}}):
                result=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(result['aircraft']['G-WUKU']['status'],'N/A')
        self.assertEqual(result['aircraft']['G-WUKU']['local_hex'],'4080f7')
        self.assertEqual(result['aircraft']['G-WUKU']['local_last_seen_at'],1234567890)

    def test_batched_providers_use_only_known_hosts_and_no_key_leaks(self):
        def fake(req,timeout=6):
            calls.append(req)
            content=json.dumps({'now':time.time(),'ac':[{
                'hex':'4080f7','r':'G-WUKU','alt_baro':32000,'seen':1}]}).encode()
            obj=MagicMock()
            obj.headers={}
            obj.read.return_value=content
            obj.__enter__=Mock(return_value=obj)
            obj.__exit__=Mock(return_value=None)
            return obj
        calls=[]
        for provider,key,endpoint in [
            ('adsb.fi','','https://opendata.adsb.fi/api/v2/registration/'),
            ('FlyItalyADSB','dummy-secret','https://api.flyitalyadsb.com/v2/reg/'),
            ('adsb.lol','dummy-secret','https://api.adsb.lol/v2/reg/'),
            ('AvioADSB','dummy-secret','https://avioadsb.org/v1/aircraft')]:
            with self.subTest(provider=provider):
                planes=flights_live._lookup_provider(['G-WUKU'],provider,key,opener=fake)
                self.assertEqual(planes[0]['_source'],provider)
                req=calls[-1]
                self.assertTrue(req.full_url.startswith(endpoint))
                self.assertNotIn('dummy-secret',req.full_url)
                self.assertEqual(req.get_header('X-api-key'),
                                 'dummy-secret' if key else None)

    def test_global_api_queries_rotate_across_saved_sources(self):
        used=[]
        with patch.object(flights_live,'_local_planes',return_value=[]):
            with patch.object(flights_live,'_local_last_seen',return_value={}):
                with patch.object(flights_live,'_configured_keys',return_value={
                    'FlyItalyADSB':'test-secret','adsb.lol':'other-secret'}):
                    with patch.object(flights_live,'_lookup_provider',
                                      side_effect=lambda regs,provider,key:used.append(provider) or []):
                        for _ in range(4):
                            flights_live._ROTATION['at']=0
                            flights_live._ROTATION['retry_until'].clear() # simulate next eligible interval
                            result=flights_live.snapshot('G-WUKU')
                            self.assertEqual(result['aircraft']['G-WUKU']['status'],'N/A')
        self.assertEqual(used,['adsb.fi','FlyItalyADSB','adsb.lol','adsb.fi'])

    def test_global_snapshot_filters_tracked_registrations_and_uses_documented_hosts(self):
        calls=[]
        def fake(req,timeout=12):
            calls.append(req)
            obj=MagicMock()
            obj.read.return_value=json.dumps({'now':time.time(),'ac':[
                {'hex':'4080f7','r':'G-WUKU','seen':1,'route_origin':'LGW','route_dest':'BTS'},
                {'hex':'4080f8','r':'G-OTHER','seen':1}]}).encode()
            obj.__enter__=Mock(return_value=obj)
            obj.__exit__=Mock(return_value=None)
            return obj
        for provider,key,url in [
            ('adsb.fi','','https://opendata.adsb.fi/api/v2/snapshot'),
            ('ADSBiq','iq_dummy-secret','https://api.adsbiq.com/v2/all')]:
            found=flights_live._lookup_provider(['G-WUKU','G-MISS'],provider,key,opener=fake)
            self.assertEqual([a['r'] for a in found],['G-WUKU'])
            self.assertEqual(found[0]['route_dest'],'BTS')
            self.assertEqual(calls[-1].full_url,url)
        self.assertEqual(calls[-1].get_header('Authorization'),'Bearer iq_dummy-secret')

    def test_icao_landing_code_is_converted_to_iata(self):
        with patch.object(flights_live,'_local_planes',return_value=[]):
            with patch.object(flights_live.flights_history,'cached',return_value={'airport':'EGKK','time':int(time.time())-3600}):
                result=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[])
        self.assertEqual(result['aircraft']['G-WUKU']['at_airport'],'LGW')

    def test_reported_routes_from_active_snapshot(self):
        aircraft={'hex':'4080f7','r':'G-WUKU','flight':'EZY123','seen':1,'alt_baro':30000,
                  'route_origin':'LGW','route_dest':'BTS'}
        with patch.object(flights_live,'_local_planes',return_value=[]):
            result=flights_live.snapshot('G-WUKU',network_fetch=lambda regs:[aircraft])
        self.assertEqual(result['aircraft']['G-WUKU']['route'],'LGW–BTS')
        self.assertEqual(result['aircraft']['G-WUKU']['route_confidence'],'reported')

    def test_reported_route_on_same_airframe_is_not_lost_to_fresher_position(self):
        local={'hex':'4080f7','r':'HA-LDG','flight':'WZZ580C','seen':0,'alt_baro':30000,'_source':'Your antenna'}
        remote=dict(local,seen=10,_source='ADSBiq',route_origin='HEMA',route_dest='EPMO')
        with patch.object(flights_live,'_local_planes',return_value=[local]),patch.object(flights_live,'_routes',return_value={}),patch.object(flights_live.live_details,'_iata',side_effect=lambda c:{'HEMA':'RMF','EPMO':'WMI'}.get(c,c or '')):
            item=flights_live.snapshot('HA-LDG',network_fetch=lambda regs:[remote])['aircraft']['HA-LDG']
        self.assertEqual(item['route'],'RMF–WMI')
        self.assertEqual(item['route_confidence'],'reported')

    def test_invalid_registration_or_too_many_rejected_without_network_calls(self):
        with self.assertRaises(ValueError):
            flights_live.snapshot('../evil',network_fetch=lambda regs:[])
        with self.assertRaises(ValueError):
            flights_live.snapshot(','.join('G-'+str(i).zfill(4) for i in range(82)),
                                  network_fetch=lambda regs:[])


if __name__=='__main__':
    unittest.main()
