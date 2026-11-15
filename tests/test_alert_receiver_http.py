"""Live HTTP routing for receiver settings, with mocked ADS-B source."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from backend.server import App
from backend import alerts

class ReceiverApiTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory()
  cls.old=alerts.DB_PATH
  alerts.DB_PATH=Path(cls.temp.name)/'alerts.sqlite3'
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),App)
  cls.host='http://127.0.0.1:'+str(cls.server.server_address[1])
  cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):
  cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)
  alerts.DB_PATH=cls.old;cls.temp.cleanup()

 def request(self,path,payload):
  req=Request(self.host+path,method='POST',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with urlopen(req,timeout=7) as response:return json.load(response)

 def test_store_and_check_without_modifying_aerodrome(self):
  data={'lat':'50.55','lon':'0.09','url':'http://127.0.0.1:1099/data/aircraft.json'}
  self.assertTrue(self.request('/api/alerts/receiver',data)['ok'])
  from urllib.parse import urlsplit
  self.assertEqual(json.load(urlopen(self.host+'/api/alerts'))['receiver_settings']['lat'],50.55)
  with patch.object(alerts,'read_receiver',return_value=({'aircraft':[{'hex':'abc123'}]},50.55,0.09)):
   status=self.request('/api/alerts/receiver/check',{})
  self.assertTrue(status['coordinates_available'])
  self.assertEqual(status['aircraft'],1)
  with self.assertRaises(HTTPError) as error:self.request('/api/alerts/receiver',{'url':'https://evil.example/aircraft.json'})
  self.assertEqual(error.exception.code,400)

if __name__=='__main__':unittest.main()
