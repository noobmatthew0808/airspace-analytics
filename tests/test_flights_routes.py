"""Offline regression checks for the independent adsb.lol routeset enrichment."""
import json
import time
import unittest
from unittest.mock import MagicMock,patch

from backend import flights_routes


def plane(call='EZY123',lat=51.3,lon=0.1):
    return {'callsign':call,'lat':lat,'lon':lon}


class RouteTests(unittest.TestCase):
    def setUp(self):
        with flights_routes._lock:
            self.cache=dict(flights_routes._cache)
            self.last=flights_routes._last_request
            self.busy=flights_routes._busy
            flights_routes._cache.clear()
            flights_routes._last_request=0
            flights_routes._busy=False

    def tearDown(self):
        with flights_routes._lock:
            flights_routes._cache.clear()
            flights_routes._cache.update(self.cache)
            flights_routes._last_request=self.last
            flights_routes._busy=self.busy

    def test_parses_plausible_two_airport_route(self):
        payload=[[{'callsign':'EZY123','plausible':True,
                   '_airport_codes_iata':'LGW-BTS'}]]
        self.assertEqual(flights_routes.parse_routes(payload,['EZY123']),
                         {'EZY123':'LGW–BTS'})
        self.assertEqual(flights_routes.parse_routes([
            {'callsign':'EZY123','plausible':1,'_airport_codes_iata':'LGW-VIE'}
        ],['EZY123']),{'EZY123':'LGW–VIE'})

    def test_unknown_and_implausible_routes_do_not_become_fact(self):
        payload=[{'callsign':'EZY123','plausible':False,'_airport_codes_iata':'LGW-BTS'},
                 {'callsign':'OTHER3','plausible':True,'_airport_codes_iata':'LGW-VIE'},
                 {'callsign':'EZY123','plausible':True,'_airport_codes_iata':'LGW-CDG-VIE'}]
        self.assertEqual(flights_routes.parse_routes(payload,['EZY123']),{})

    def test_airport_objects_are_supported(self):
        payload=[[{'callsign':'EZY123','plausible':True,
                   '_airports':[{'iata':'LGW'},{'iata':'VIE'}]}]]
        self.assertEqual(flights_routes.parse_routes(payload,['EZY123']),
                         {'EZY123':'LGW–VIE'})

    def test_one_bounded_post_no_credentials(self):
        response=MagicMock()
        response.headers={}
        response.read.return_value=json.dumps([[
            {'callsign':'EZY123','plausible':True,
             '_airport_codes_iata':'LGW-BTS'}]]).encode()
        response.__enter__.return_value=response
        opener=MagicMock(return_value=response)
        result=flights_routes.fetch_routes([plane()],opener=opener)
        self.assertEqual(result,{'EZY123':'LGW–BTS'})
        req=opener.call_args.args[0]
        self.assertEqual(req.get_method(),'POST')
        self.assertEqual(req.full_url,'https://adsb.im/api/0/routeset')
        self.assertNotIn('X-api-key',req.headers)
        body=json.loads(req.data)
        self.assertEqual(body,{'planes':[{'callsign':'EZY123','lat':51.3,'lng':0.1}]})

    def test_secondary_route_service_after_primary_failure(self):
        response=MagicMock()
        response.headers={}
        response.read.return_value=json.dumps([{
            'callsign':'EZY123','plausible':True,
            '_airport_codes_iata':'LGW-VIE'}]).encode()
        response.__enter__.return_value=response
        def opener(request,timeout=5):
            urls.append(request.full_url)
            if request.full_url.startswith('https://adsb.im/'):
                raise OSError('Simulated primary outage')
            return response
        urls=[]
        found=flights_routes.fetch_routes([plane()],opener=opener)
        self.assertEqual(found,{'EZY123':'LGW–VIE'})
        self.assertEqual(urls,list(flights_routes.SOURCES))
        self.assertEqual(flights_routes.health()['source'],
                         'https://api.adsb.lol/api/0/routeset')
        self.assertIn('adsb.im',flights_routes.health()['last_error'])

    def test_malformed_coordinates_and_callsigns_never_trigger_request(self):
        opener=MagicMock()
        self.assertEqual(flights_routes.fetch_routes([
            plane('HELLO',51.2,0.1),plane('EZY123',1000,2),
            plane('EZY123',float('nan'),0.2)],opener=opener),{})
        opener.assert_not_called()

    def test_cache_returns_recent_result_and_batches_new_calls_only(self):
        with flights_routes._lock:
            flights_routes._cache['EZY123']=(time.monotonic()+600,'LGW–BTS')
        with patch.object(flights_routes.threading,'Thread') as worker:
            found=flights_routes.cached_routes([plane(),plane('BAW23',51.3,0.1)])
        self.assertEqual(found,{'EZY123':'LGW–BTS'})
        worker.assert_called_once()
        args=worker.call_args.kwargs['args'][0]
        self.assertEqual([p['callsign'] for p in args],['BAW23'])

    def test_missing_position_does_not_request_any_routes(self):
        with patch.object(flights_routes.threading,'Thread') as worker:
            answer=flights_routes.cached_routes([{'callsign':'EZY123'}])
        self.assertEqual(answer,{})
        worker.assert_not_called()

    def test_adsbim_icao_without_position_does_not_send_fake_coordinates(self):
        response=MagicMock()
        response.headers={}
        response.read.return_value=json.dumps([{'callsign':'WZZ580C','plausible':False,'_airport_codes_iata':'RMF-WMI'}]).encode()
        response.__enter__.return_value=response
        opener=MagicMock(return_value=response)
        self.assertEqual(flights_routes.fetch_routes([{'callsign':'WZZ580C','icao':'abc123'}],opener),{'WZZ580C':'RMF–WMI'})
        self.assertEqual(json.loads(opener.call_args.args[0].data),{'planes':[{'callsign':'WZZ580C','icao':'abc123'}]})
        self.assertEqual(opener.call_count,1)

    def test_conflicting_route_candidates_are_rejected(self):
        payload=[{'callsign':'WZZ580C','plausible':True,'_airport_codes_iata':code} for code in ('RMF-WMI','BUD-LGW')]
        self.assertEqual(flights_routes.parse_routes(payload,['WZZ580C']),{})

    def test_throttle_prevents_excessive_route_lookups(self):
        flights_routes._last_request=time.monotonic()
        with patch.object(flights_routes.threading,'Thread') as worker:
            answer=flights_routes.cached_routes([plane()])
        self.assertEqual(answer,{})
        worker.assert_not_called()


if __name__=='__main__':
    unittest.main()
