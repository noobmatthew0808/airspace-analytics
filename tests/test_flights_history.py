"""Offline tests: observed landing confidence, source key handling and quota."""
import json
import time
import unittest
from datetime import datetime,timezone
from unittest.mock import MagicMock,patch
from backend import flights_history


class FlightHistoryTests(unittest.TestCase):
    def setUp(self):
        with flights_history._lock:
            self.cache=dict(flights_history._cache)
            self.last=flights_history._last_batch
            self.busy=flights_history._busy
            flights_history._cache.clear()
            flights_history._last_batch=0
            flights_history._busy=False

    def tearDown(self):
        with flights_history._lock:
            flights_history._cache.clear()
            flights_history._cache.update(self.cache)
            flights_history._last_batch=self.last
            flights_history._busy=self.busy

    def test_only_true_ground_or_low_arrivals(self):
        now=time.time()
        payload={'flights':[
            {'to':{'airport':'EGKK','iata':'LGW','time':now-20000,'seen':'ground'}},
            {'to':{'airport':'LOWW','iata':'VIE','time':now-10000,'seen':'low'}},
            {'to':{'airport':'EGLL','iata':'LHR','time':now-1000,'seen':'approach'}},
            {'to':{'airport':'LEBL','iata':'BCN','time':now+3600,'seen':'ground'}},
        ]}
        result=flights_history.parse_last_landing(payload,now=now)
        self.assertEqual(result['airport'],'VIE')
        self.assertEqual(result['evidence'],'low')
        self.assertEqual(result['time'],int(now-10000))

    def test_today_fleet_data_used_if_available_but_never_assumed(self):
        now=time.time()
        payload={'flights':[{'to':{'airport':'EGKK','iata':'LGW',
                'time':now-86400,'seen':'ground'}}],
                'today':{'available':True,'flights':[{
                    'to':{'airport':'LOWW','time':datetime.fromtimestamp(now-1000,timezone.utc).isoformat(),
                          'seen':'ground'}}]}}
        result=flights_history.parse_last_landing(payload,now=now)
        self.assertIsNotNone(result)
        self.assertEqual(result['airport'],'LOWW')

    def test_no_true_landing_remains_unknown(self):
        now=time.time()
        self.assertIsNone(flights_history.parse_last_landing({
            'flights':[{'to':None},{'to':{'airport':'EGKK','seen':'approach','time':now-400}}]},now))
        self.assertIsNone(flights_history.parse_last_landing({},now))

    def test_single_fixed_host_and_secret_only_in_header(self):
        now=time.time()
        response=MagicMock()
        response.headers={}
        response.read.return_value=json.dumps({'flights':[{
            'to':{'airport':'EGKK','iata':'LGW','time':now-3000,
                  'seen':'ground'}}]}).encode()
        response.__enter__.return_value=response
        opener=MagicMock(return_value=response)
        result=flights_history.fetch_one('G-WUKU','fake-key',opener)
        self.assertEqual(result['airport'],'LGW')
        request=opener.call_args.args[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertEqual(request.full_url,
            'https://api.flyitalyadsb.com/v2/flights/reg/G-WUKU')
        self.assertEqual(request.get_header('X-api-key'),'fake-key')
        self.assertNotIn('fake-key',request.full_url)

    def test_invalid_registration_or_missing_key_rejected(self):
        with self.assertRaises(ValueError):
            flights_history.fetch_one('../bad','key')
        with self.assertRaises(ValueError):
            flights_history.fetch_one('G-WUKU','')

    def test_background_queue_does_not_start_without_key(self):
        with patch.object(flights_history.threading,'Thread') as worker:
            flights_history.schedule(['G-WUKU'],'')
        worker.assert_not_called()

    def test_background_queue_bounded_and_throttled(self):
        with patch.object(flights_history.threading,'Thread') as worker:
            flights_history.schedule(['G-'+str(i).zfill(4) for i in range(12)],'key')
            args=worker.call_args.kwargs['args'][0]
            self.assertEqual(len(args),4)
            flights_history._busy=False
            flights_history.schedule(['G-EXTRA'],'key')
        worker.assert_called_once()

    def test_cached_result_is_only_used_when_unexpired(self):
        with flights_history._lock:
            flights_history._cache['G-WUKU']=(time.monotonic()+60,
                {'airport':'LGW','time':1795100000})
        self.assertEqual(flights_history.cached('G-WUKU')['airport'],'LGW')
        with flights_history._lock:
            flights_history._cache['G-WUKU']=(time.monotonic()-1,
                {'airport':'LGW','time':1795100000})
        self.assertIsNone(flights_history.cached('G-WUKU'))


if __name__=='__main__':
    unittest.main()
