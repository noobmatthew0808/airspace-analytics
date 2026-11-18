"""Live metadata should remain read-only and use IATA 3-letter routes."""
import unittest
from unittest.mock import patch

from backend import live_details

class TestLiveDetails(unittest.TestCase):
    def test_parsing_strict(self):
        self.assertEqual(live_details.parse_items('408345:GMILS,4CA76F:EIN5MW,wrong:bad'),
                         [('408345','GMILS'),('4CA76F','EIN5MW')])
        self.assertEqual(live_details.parse_items(''),[])

    def test_iata_only(self):
        self.assertEqual(live_details._route('EGKK','LEMD'), 'LGW – MAD')
        self.assertEqual(live_details._route('KJFK','EGLL'), 'JFK – LHR')
        self.assertEqual(live_details._route('XXXX','EGKK'),'')
        self.assertEqual(live_details._route('EGKK','EGKK'),'')

    def test_distance(self):
        self.assertEqual(live_details._km(51,0,51,0),0)
        self.assertGreater(live_details._km(51,0,52,0),100)

    def test_empty(self):
        with patch.object(live_details,'_readsb') as readsb:
            self.assertEqual(live_details.details({'items':'INVALID'}),{'aircraft':{}})
            readsb.assert_not_called()

    def test_no_uncontrolled_external_route_lookups(self):
        with patch.object(live_details,'_json') as lookup:
            self.assertEqual(live_details._lookup_from_aerodrome('G-ABCD'),'')
            lookup.assert_not_called()

    def test_readsb_source_labels(self):
        self.assertEqual(live_details._source_name('adsb_icao'), 'ADS-B')
        self.assertEqual(live_details._source_name('mlat'), 'MLAT')
        self.assertEqual(live_details._source_name('mode_s'), 'Mode S')
        self.assertEqual(live_details._source_name('tisb_icao'), 'TIS-B')
        self.assertEqual(live_details._source_name('adsr_icao'), 'ADS-R')
        self.assertEqual(live_details._source_name(None), '')

    def test_local_receiver_probe_finds_lan_feed(self):
        from unittest.mock import patch
        with patch.object(live_details.alerts, 'snapshot',
                          return_value={'receiver_settings': {'url': ''}}), \
             patch.object(live_details.alerts, '_local_addresses',
                          return_value={'127.0.0.1', '192.168.1.187'}):
            urls=live_details._candidate_feeds()
        self.assertTrue(any('192.168.1.187:1099/map/data/aircraft.json' in x for x in urls))

    def test_feed_from_lan_not_just_loopback(self):
        from unittest.mock import patch
        import time
        address='http://192.168.1.187:1099/map/data/aircraft.json'
        previous=live_details._FEED_LAST_GOOD
        try:
            with patch.object(live_details,'_docker_json',return_value={}), \
                 patch.object(live_details,'_candidate_feeds',return_value=(address,)), \
                 patch.object(live_details.alerts,'_receiver_url_allowed',return_value=True), \
                 patch.object(live_details.alerts,'_local_addresses',
                              return_value={'127.0.0.1','192.168.1.187'}), \
                 patch.object(live_details,'_json',
                              return_value={'now':time.time(),'aircraft':[{'hex':'4069CF','r':'G-CICF','t':'C42'}]}):
                value=live_details._readsb()
            self.assertEqual(value['aircraft'][0]['r'],'G-CICF')
            self.assertEqual(live_details._FEED_LAST_GOOD,address)
        finally:
            live_details._FEED_LAST_GOOD=previous

    def test_tar1090_sharded_db_uses_same_reg_and_type_as_map(self):
        from unittest.mock import patch
        previous=live_details._FEED_LAST_GOOD
        try:
            live_details._FEED_LAST_GOOD='http://192.168.1.187:1099/map/data/aircraft.json'
            live_details._DB_SHARD_CACHE.clear()
            def get_shard(url, timeout=None):
                if url.endswith('/4.js'):
                    return {'children':['40']}
                if url.endswith('/40.js'):
                    return {'69CF':['G-CICF','C42','0000']}
                raise OSError('not found')
            with patch.object(live_details,'_tar_db_roots',
                              return_value=('http://127.0.0.1:1099/map/db',)), \
                 patch.object(live_details,'_json',side_effect=get_shard):
                info=live_details._tar_aircraft_db(['4069CF'])
            self.assertEqual(info['4069CF']['registration'],'G-CICF')
            self.assertEqual(info['4069CF']['aircraft_type'],'C42')
        finally:
            live_details._FEED_LAST_GOOD=previous
            live_details._DB_SHARD_CACHE.clear()

    def test_location_uses_existing_receiver_json(self):
        from unittest.mock import patch
        previous=live_details._FEED_LAST_GOOD
        try:
            live_details._FEED_LAST_GOOD='http://192.168.1.187:1099/map/data/aircraft.json'
            with patch.object(live_details.alerts,'snapshot',
                              return_value={'receiver_settings':{'lat':None,'lon':None}}), \
                 patch.object(live_details.alerts,'_receiver_url_allowed',return_value=True), \
                 patch.object(live_details.alerts,'_local_addresses',
                              return_value={'127.0.0.1','192.168.1.187'}), \
                 patch.object(live_details,'_json',
                              return_value={'lat':50.82,'lon':0.24}):
                self.assertEqual(live_details._receiver_position(),(50.82,0.24))
        finally:
            live_details._FEED_LAST_GOOD=previous

    def test_tar_routeset_uses_three_letter_codes(self):
        from unittest.mock import patch
        import json
        previous=live_details._ROUTE_API_RETRY_AFTER
        class Response:
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return json.dumps([
                {'callsign':'BAW758','_airports':[{'iata':'LHR'},{'iata':'EAP'}],
                 'plausible':True}
            ]).encode()
        class Opener:
            def open(self,request,timeout=2):
                self.body=json.loads(request.data)
                return Response()
        opener=Opener()
        try:
            live_details._ROUTE_API_RETRY_AFTER=0
            live_details._TAR_ROUTE_CACHE.clear()
            with patch.object(live_details,'build_opener',return_value=opener):
                routes=live_details._batch_tar_routes(
                    [('40609C','BAW758')],{'40609C':{'lat':51.0,'lon':0.1}})
            self.assertEqual(routes['BAW758'],'LHR – EAP')
            self.assertEqual(opener.body['planes'][0]['callsign'],'BAW758')
        finally:
            live_details._ROUTE_API_RETRY_AFTER=previous
            live_details._TAR_ROUTE_CACHE.clear()

    def test_docker_json_uses_fixed_read_only_file(self):
        import json
        from unittest.mock import Mock, patch
        result=Mock(returncode=0,stdout=json.dumps({'aircraft':[]}).encode())
        with patch.object(live_details.subprocess,'run',return_value=result) as run:
            self.assertEqual(live_details._docker_json('aircraft.json'),{'aircraft':[]})
        self.assertEqual(run.call_args.args[0],
            ('docker','exec','ultrafeeder','cat','/run/readsb/aircraft.json'))
        with self.assertRaises(ValueError):
            live_details._docker_json('../etc/passwd')

    def test_docker_json_is_used_for_live_aircraft_before_urls(self):
        import time
        live={'now':time.time(),'aircraft':[
            {'hex':'398603','flight':'HOP51BV','type':'adsb_icao','lat':50.98,'lon':0.2}]}
        from unittest.mock import patch
        with patch.object(live_details,'_docker_json',return_value=live), \
             patch.object(live_details,'_candidate_feeds') as candidates:
            self.assertEqual(live_details._readsb()['aircraft'][0]['hex'],'398603')
            candidates.assert_not_called()

    def test_tar1090_real_db2_not_db_prioritized(self):
        from unittest.mock import patch
        url='http://192.168.1.187:1099/map/data/aircraft.json'
        with patch.object(live_details,'_candidate_feeds',return_value=(url,)), \
             patch.object(live_details.alerts,'_receiver_url_allowed',return_value=True), \
             patch.object(live_details.alerts,'_local_addresses',
                          return_value={'127.0.0.1','192.168.1.187'}):
            roots=live_details._tar_db_roots()
        self.assertEqual(roots[0],'http://192.168.1.187:1099/map/db2')
        self.assertIn('http://192.168.1.187:1099/map/db',roots)

    def test_db2_shards_fill_aircraft_registration_and_type(self):
        from unittest.mock import patch
        live_details._DB_SHARD_CACHE.clear()
        def mock_json(url,timeout=None):
            if url.endswith('/4.js'):return {'children':['40']}
            if url.endswith('/40.js'):return {'69CF':['G-CICF','C42','0000']}
            raise OSError('unknown shard')
        with patch.object(live_details,'_tar_db_roots',
                          return_value=('http://192.168.1.187:1099/map/db2',)), \
             patch.object(live_details,'_json',side_effect=mock_json):
            info=live_details._tar_aircraft_db(['4069CF'])
        self.assertEqual(info['4069CF']['registration'],'G-CICF')
        self.assertEqual(info['4069CF']['aircraft_type'],'C42')
        live_details._DB_SHARD_CACHE.clear()

    def test_docker_receiver_coords_fallback(self):
        from unittest.mock import patch
        with patch.object(live_details.alerts,'snapshot',
                          return_value={'receiver_settings':{'lat':None,'lon':None}}), \
             patch.object(live_details,'_docker_json',
                          return_value={'lat':50.82514,'lon':0.24566}), \
             patch.object(live_details,'_json') as http:
            self.assertEqual(live_details._receiver_position(),
                             (50.82514,0.24566))
            http.assert_not_called()
