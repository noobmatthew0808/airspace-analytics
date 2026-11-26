"""Datalink adapters and session lifecycle; no external traffic or credentials."""
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from urllib.error import HTTPError
from backend import acars, alerts

class Response(io.BytesIO):
    status=200
    headers={}
    def __init__(self,payload):
        super().__init__(json.dumps(payload).encode())

class AcarsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for obj,name,value in [(alerts,'DB_PATH',Path(self.tmp.name)/'alerts.sqlite3'),(acars,'_sessions',{}),(acars,'_next',{}),(acars,'_busy',set()),(acars,'_test_busy',set())]:
            p=patch.object(obj,name,value);p.start();self.addCleanup(p.stop)
        self.now=time.time()
        self.ident={'reg':'G-TEST','hex':'abcdef','aliases':[]}
        self.calls=[]
    def opener(self,*payloads):
        it=iter(payloads)
        def open(req,timeout=12):
            self.calls.append(req)
            return Response(next(it))
        return open
    def msg(self,**kwargs):
        return dict(timestamp=self.now-10,tail='G-TEST',flight='AB0012',text='TEST WEATHER',id='msg1',**kwargs)
    def test_avio(self):
        rows,note=acars.fetch('avio','G-TEST','reg',self.now-43200,self.now,'avio_testkey',dict(self.ident),opener=self.opener({'messages':[self.msg(),dict(self.msg(),tail='G-OTHER')]}))
        self.assertEqual(len(rows),1)
        self.assertIn('latest hour',note)
        self.assertEqual(parse_qs(urlsplit(self.calls[0].full_url).query)['tail'],['G-TEST'])
        self.assertEqual(self.calls[0].get_header('X-api-key'),'avio_testkey')
    def test_vdliq_archive_and_exact_matching(self):
        row={'timestamp':self.now-36000,'icaoHex':'abcdef','tail':'G-TEST','flightNumber':'AB0012','uuid':'vd1','sourceType':'VDL2','text':'TEST'}
        result,_=acars.fetch('vdliq','G-TEST','reg',self.now-43200,self.now,'iq_testkey',dict(self.ident),opener=self.opener({'messages':[row],'truncated':True}))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['protocol'],'VDL2')
        self.assertEqual(parse_qs(urlsplit(self.calls[0].full_url).query)['history'],['1'])
        self.assertEqual(self.calls[0].get_header('Authorization'),'Bearer iq_testkey')
    def test_airframes_resolves_registration_and_uses_icao(self):
        identity={'reg':'G-TEST','hex':'','aliases':[]}
        row={'id':1,'timestamp':acars._iso(self.now-60),'airframe':{'tail':'G-TEST','icao':'abcdef'},'sourceType':'ACARS','text':'TEST'}
        rows,_=acars.fetch('airframes','G-TEST','reg',self.now-43200,self.now,'key',identity,opener=self.opener({'tail':'G-TEST','icao':'abcdef'},[row]))
        self.assertEqual(len(rows),1)
        self.assertEqual(identity['hex'],'abcdef')
        self.assertEqual(parse_qs(urlsplit(self.calls[1].full_url).query)['icao'],['abcdef'])
    def test_drama(self):
        row={'id':'d1','timestamp':acars._iso(self.now-10),'registration':'G-TEST','flightNumber':'AB0012','cleanedText':'TEST','protocol':'ACARS'}
        rows,_=acars.fetch('drama','AB12','flight',self.now-43200,self.now,'key',{'reg':'','hex':''},opener=self.opener({'items':[row]}))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['match'],'exact')
        self.assertEqual(parse_qs(urlsplit(self.calls[0].full_url).query)['flightNumber'],['AB12'])
    def test_callsign_and_linked_airframe(self):
        rows,_=acars.fetch('avio','TEST12','flight',self.now-3600,self.now,'key',dict(self.ident),opener=self.opener({'messages':[dict(self.msg(),adsb={'flight':'TEST12'}),dict(self.msg(),id='msg2',flight='AB15')]}))
        self.assertEqual([r['match'] for r in rows],['exact','linked airframe'])
    def test_normalization_and_dedup(self):
        a=acars._normal('avio',self.msg());b=acars._normal('vdliq',dict(self.msg(),id='msg2'))
        s={'messages':[],'since':self.now-3600}
        self.assertEqual(len(acars._merge(s,[a,b],self.now)),1)
        self.assertEqual(s['messages'][0]['sources'],['avio','vdliq'])
        self.assertEqual(acars._merge(s,[acars._normal('vdliq',dict(self.msg(),id='msg2'))],self.now),[])
        self.assertIsNone(acars._normal('avio',{'timestamp':'not a date','text':'x'}))
    def test_settings_reuse_and_redaction(self):
        alerts.save_avio({'key':'avio_testkey123'})
        alerts.save_adsbiq({'key':'iq_testkey123'})
        acars.save_key('airframes',{'key':'secret-airframes'})
        state=acars.settings()
        self.assertTrue(state['providers']['avio']['reused_key'])
        self.assertTrue(state['providers']['vdliq']['reused_key'])
        self.assertTrue(state['providers']['airframes']['key_set'])
        for key in ('avio_testkey123','iq_testkey123','secret-airframes'):
            self.assertNotIn(key,json.dumps(state))
        with patch.object(acars,'_request',return_value={'messages':[]}):
            self.assertTrue(acars.test('vdliq')['ok'])
        acars.save_key('vdliq',{'key':'other-test-key'})
        self.assertFalse(acars.settings()['providers']['vdliq']['test'])
    def test_session_tracking_notification_and_stop(self):
        alerts.save_notifier({'topic':'test-private'})
        s=acars.search({'query':'G-TEST','hours':12})
        self.assertEqual(s['kind'],'reg')
        acars.track({'id':s['id'],'duration':3})
        internal=acars._sessions[s['id']]
        msg=acars._normal('avio',self.msg())
        msg['timestamp']=internal['tracking_start']-1
        opener=self.opener({})
        acars._notify(internal,[msg],opener)
        self.assertEqual(len(self.calls),0)
        msg['timestamp']=internal['tracking_start']
        acars._notify(internal,[msg],opener)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(acars.read(s['id'])['notify_count'],1)
        self.assertNotIn('messages',acars.read()['tracking'][0])
        acars.stop({'id':s['id']})
        self.assertRaises(ValueError,acars.read,s['id'])
    def test_invalid_inputs_and_rate_limit(self):
        for q in ('../secret','<script>',''):
            self.assertRaises(ValueError,acars.search,{'query':q})
        self.assertRaises(ValueError,acars.search,{'query':'G-TEST','hours':99})
        def limited(req,timeout=12):
            raise HTTPError(req.full_url,429,'limited',{'Retry-After':'30'},None)
        with self.assertRaisesRegex(ValueError,'HTTP 429'):
            acars._request('drama',opener=limited)
        self.assertGreater(acars._next['drama'],time.monotonic())
