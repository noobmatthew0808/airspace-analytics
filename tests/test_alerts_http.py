"""Local HTTP API contract: no live receiver or external ntfy required."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from backend.server import App
from backend import alerts

class AlertsAPITest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory()
  cls.old=alerts.DB_PATH
  alerts.DB_PATH=Path(cls.tmp.name)/'alerts.sqlite3'
  cls.http=ThreadingHTTPServer(('127.0.0.1',0),App)
  cls.port=cls.http.server_address[1]
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
  cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close();cls.thread.join(timeout=3)
  alerts.DB_PATH=cls.old;cls.tmp.cleanup()
 def call(self,path,payload=None,origin=None):
  if payload is None:request=Request(f'http://127.0.0.1:{self.port}{path}')
  else:
   headers={'Content-Type':'application/json'}
   if origin:headers['Origin']=origin
   request=Request(f'http://127.0.0.1:{self.port}{path}',data=json.dumps(payload).encode(),headers=headers,method='POST')
  with urlopen(request,timeout=8) as response:return json.load(response)
 def test_rule_lifecycle_and_redacted_ntfy(self):
  rule=self.call('/api/alerts/rule',{'label':'Test A380','field':'type','pattern':'A388','max_km':20,'max_ft':15000})
  self.assertTrue(rule['ok'])
  state=self.call('/api/alerts')
  self.assertEqual(state['rules'][0]['pattern'],'A388')
  self.assertEqual(state['rules'][0]['max_km'],20)
  self.call('/api/alerts/ntfy',{'topic':'private-example-123','token':'never-expose-this'})
  state=self.call('/api/alerts')
  self.assertTrue(state['ntfy']['token_set'])
  self.assertNotIn('never-expose-this',json.dumps(state))
  self.call('/api/alerts/delete',{'id':rule['id']})
  self.assertEqual(len(self.call('/api/alerts')['rules']),0)
 def test_cross_origin_and_invalid_rule(self):
  with self.assertRaises(HTTPError) as error:
   self.call('/api/alerts/rule',{'field':'type','pattern':'A388'},origin='https://evil.example')
  self.assertEqual(error.exception.code,403)
  with self.assertRaises(HTTPError) as error:
   self.call('/api/alerts/rule',{'field':'type','pattern':'<>invalid'})
  self.assertEqual(error.exception.code,400)
