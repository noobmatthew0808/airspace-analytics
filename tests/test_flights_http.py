"""Local HTTP integration for the personal Google Sheet flight log."""
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from backend.server import App
from backend import flights_log, flights_live


SAMPLE=[{'id':'1','date':'2025-08-02','from_airport':'LGW','to_airport':'VIE',
         'flight_code':'W95776','airline':'Wizz Air','airplane':'A321neo',
         'registration':'G-WUKU','who':'Matthew'}]


class FlightHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),App)
        cls.port=cls.server.server_address[1]
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=4)

    def setUp(self):
        self.original=dict(flights_log._CACHE)
        flights_log._CACHE.update(rows=None,at=0,error=None)

    def tearDown(self):
        flights_log._CACHE.clear()
        flights_log._CACHE.update(self.original)

    def request(self,path,body=None,origin=None):
        headers={}
        if origin:headers['Origin']=origin
        if body is not None:headers['Content-Type']='application/json'
        req=Request('http://127.0.0.1:'+str(self.port)+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,method='POST' if body is not None else 'GET')
        with urlopen(req,timeout=5) as response:return json.load(response)

    def test_original_sheet_loads_as_separate_tab_data(self):
        with patch.object(flights_log,'_fetch',return_value=SAMPLE):
            result=self.request('/api/flights/records')
        self.assertEqual(result['flights'][0]['registration'],'G-WUKU')
        self.assertEqual(result['flights'][0]['who'],'Matthew')
        self.assertEqual(result['source'],'Google Sheets via SheetDB')

    def test_cross_origin_cannot_delete_flights(self):
        with patch.object(flights_log,'mutate',return_value={'ok':True}) as mutate:
            with self.assertRaises(HTTPError) as exc:
                self.request('/api/flights/records',{'action':'delete','id':'1'},
                             origin='https://example.com')
            self.assertEqual(exc.exception.code,403)
            mutate.assert_not_called()

    def test_allowed_local_edit_passes_same_columns_to_sheet_bridge(self):
        with patch.object(flights_log,'_fetch',return_value=SAMPLE):
            loaded=self.request('/api/flights/records')
            self.assertEqual(len(loaded['flights']),1)
        with patch.object(flights_log,'mutate',return_value={'ok':True,'id':'1'}) as mutate:
            result=self.request('/api/flights/records',
                                {'action':'delete','id':'1'})
        self.assertTrue(result['ok'])
        self.assertEqual(mutate.call_args.args[0]['id'],'1')

    def test_live_unavailable_does_not_break_sheet_read(self):
        with patch.object(flights_live,'snapshot',return_value={
            'aircraft':{'G-WUKU':{'status':'N/A'}},
            'source':'Your antenna + network APIs','checked_at':int(time.time())}):
            status=self.request('/api/flights/live?regs=G-WUKU')
        self.assertEqual(status['aircraft']['G-WUKU']['status'],'N/A')
        with patch.object(flights_log,'_fetch',return_value=SAMPLE):
            records=self.request('/api/flights/records')
        self.assertEqual(len(records['flights']),1)


if __name__=='__main__':
    unittest.main()
