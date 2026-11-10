"""End-to-end HTTP tests against a disposable fictional SQLite DB."""
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .make_sample_db import seed
from backend.server import App

class TestLocalAPI(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory()
  cls.db=Path(cls.tmp.name)/'fictional.db'
  seed(cls.db,18)
  os.environ['AIRSPACE_DB']=str(cls.db)
  cls.http=ThreadingHTTPServer(('127.0.0.1',0),App)
  cls.port=cls.http.server_address[1]
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
  cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.http.shutdown();cls.http.server_close()
  cls.thread.join(timeout=3)
  os.environ.pop('AIRSPACE_DB',None)
  cls.tmp.cleanup()
 def get(self,path):
  with urlopen(f'http://127.0.0.1:{self.port}{path}',timeout=15) as response:
   return response.status,response.headers,response.read()
 def test_html_and_static_assets(self):
  for path,typ in [('/','text/html'),('/styles.css','text/css'),('/app.js','text/javascript'),('/favicon.svg','image/svg+xml'),('/manifest.webmanifest','application/manifest+json'),('/apple-touch-icon.png','image/png'),('/icon-192.png','image/png')]:
   status,headers,body=self.get(path)
   self.assertEqual(status,200,path)
   self.assertIn(typ,headers['Content-Type'],path)
   self.assertTrue(body)
   self.assertIn('Content-Security-Policy',headers)
 def test_api_health_and_analytics(self):
  for path in ['/api/health','/api/overview','/api/filters','/api/database/tables',
      '/api/analytics?period=rolling&amount=46&unit=hours&metric=observations&bucket=hour',
      '/api/analytics?period=last_30d&metric=flights&bucket=weekday',
      '/api/patterns?period=last_7d&metric=aircraft',
      '/api/compare?period=today&bucket=hour&metric=flights',
      '/api/aircraft?q=A320','/api/aircraft/4ca123',
      '/api/database/rows?table=all_sightings&page=1&limit=30',
      '/api/update/status','/api/update/check']:
   code,headers,b=self.get(path)
   self.assertEqual(code,200,path)
   self.assertIsInstance(json.loads(b),dict)
 def test_export_and_sql_rejection(self):
  code,h,b=self.get('/api/database/export?table=all_sightings')
  self.assertEqual(code,200)
  self.assertTrue(b.startswith(b'\xef\xbb\xbf'))
  with self.assertRaises(HTTPError) as cm:
   self.get('/api/database/rows?table=sqlite_master')
  self.assertEqual(cm.exception.code,400)
 def test_update_requires_configured_repository(self):
  url=f'http://127.0.0.1:{self.port}/api/update/apply'
  req=Request(url, data=b'{}',method='POST', headers={'X-Update-Token':'not-the-secret','Content-Type':'application/json'})
  with self.assertRaises(HTTPError) as cm:
   urlopen(req,timeout=5)
  self.assertEqual(cm.exception.code,400)  # isolated test has no configured Git remote

if __name__=='__main__':unittest.main()
