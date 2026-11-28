import tempfile
import unittest
from datetime import date,timedelta,datetime,timezone
from pathlib import Path
from unittest.mock import patch
from backend import tracker as t

class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=patch.object(t,'PATH',Path(self.tmp.name)/'tracker.sqlite3');self.p.start()
        self.day=date.today().isoformat()
        self.s=t.clean(dict(flight='BA 123',date=self.day,origin='LGW',destination='BTS',notify=True))
    def tearDown(self):
        self.p.stop();self.tmp.cleanup()
    def test_suggestions_are_dated_read_only_and_deduplicated(self):
        row=dict(flight_code='BA123',date=self.day,from_airport='LGW',to_airport='BTS')
        old=dict(row,date=(date.today()-timedelta(days=2)).isoformat())
        self.assertEqual(len(t.suggestions([row,row,old],[],self.day)),1)
        self.assertEqual(t.suggestions([row], [self.s],self.day),[])
        self.assertEqual(row['flight_code'],'BA123')
    def test_trip_crud_and_keys_do_not_escape(self):
        t.mutate({'action':'add',**self.s})
        with self.assertRaises(ValueError):t.mutate({'action':'add',**self.s})
        t.save_key({'provider':'flightbyte','key':'test_key_12345'})
        self.assertTrue(t.settings()['flightbyte']['key_set'])
        self.assertNotIn('test_key_12345',str(t.settings()))
        with self.assertRaises(ValueError):t.save_key({'provider':'aerodatabox','key':'test_key_12345'})
        with patch.object(t.flights_log,'_CACHE',{'rows':[]}):
            snapshot=t.snapshot()
        self.assertNotIn('test_key_12345',str(snapshot))
        id=snapshot['trips'][0]['id']
        t.mutate({'action':'pause','id':id})
        self.assertFalse(t.snapshot()['trips'][0]['active'])
        t.mutate({'action':'delete','id':id})
        self.assertEqual(t.snapshot()['trips'],[])
    def test_flightbyte_exact_date_and_route(self):
        p={'carrierCode':'BA','flightNumber':'123','date':self.day,
           'departure':{'airport':{'iata':'LGW'},'gate':'12','times':{'scheduledGate':{'local':self.day+'T10:00:00'}}},
           'arrival':{'airport':{'iata':'BTS'},'baggage':'3','times':{'scheduledGate':{'local':self.day+'T13:00:00'}}},
           'equipment':{'tailNumber':'G-TEST'},'status':{'label':'Boarding'}}
        d=t.parse_flightbyte(p,self.s)
        self.assertEqual(d['dep_gate'],'12');self.assertEqual(d['belt'],'3')
        self.assertEqual(d['arrival_date'],self.day)
        self.assertFalse(t.parse_flightbyte(dict(p,date='2020-01-01'),self.s))
        self.assertFalse(t.parse_flightbyte(dict(p,arrival={'airport':{'iata':'LHR'}}),self.s))
    def test_aviationstack_and_airlabs_never_select_ambiguous_leg(self):
        r={'flight':{'iata':'BA123'},'flight_date':self.day,'departure':{'iata':'LGW','gate':'8'},'arrival':{'iata':'BTS','baggage':'4'}}
        self.assertEqual(t.parse_aviationstack({'data':[r]},self.s)['belt'],'4')
        self.assertFalse(t.parse_aviationstack({'data':[r,r]},self.s))
        a={'flight_iata':'BA123','dep_iata':'LGW','arr_iata':'BTS','dep_time':self.day+' 10:00','arr_baggage':'5'}
        self.assertEqual(t.parse_airlabs({'response':[a]},self.s)['belt'],'5')
        self.assertFalse(t.parse_airlabs({'response':[dict(a,dep_time='2020-01-01 10:00')]},self.s))
    def test_aerodatabox_date_and_registration(self):
        r={'number':'BA 123','departure':{'airport':{'iata':'LGW'},'scheduledTime':{'local':self.day+'T10:00:00'}},
           'arrival':{'airport':{'iata':'BTS'},'baggageBelt':'7'},'aircraft':{'reg':'G-TEST'}}
        self.assertEqual(t.parse_aerodatabox([r],self.s)['registration'],'G-TEST')
        self.assertFalse(t.parse_aerodatabox([r,r],self.s))
    def test_board_requires_current_feed_for_gate(self):
        stamp=datetime.fromisoformat(self.day+'T12:00:00+00:00').timestamp()
        d={'iata':'LGW','dir':'dep','date':self.day,'tz':'Europe/London','source':'feed','boardFetched':stamp,
           'rows':[{'flightNumber':'BA123','counterpart':{'iata':'BTS'},'basis':'board','planTime':self.day+'T12:00:00Z','gate':'14','callsign':'BAW123'}]}
        self.assertEqual(t.parse_board(d,self.s,'dep',self.day,stamp)['dep_gate'],'14')
        self.assertNotIn('dep_gate',t.parse_board(d,self.s,'dep',self.day,stamp+1000))
        self.assertFalse(t.parse_board(dict(d,truncated=True),self.s,'dep',self.day,stamp))
    def test_dedup_and_priority(self):
        f={}
        self.assertEqual(t._merge(f,{'dep_gate':'7'},'mapflights',100),[('dep_gate','7')])
        self.assertFalse(t._merge(f,{'dep_gate':'7'},'mapflights',101))
        self.assertFalse(t._merge(f,{'dep_gate':'8'},'flightbyte',102))
        self.assertFalse(t._merge(f,{'dep_gate':None},'mapflights',103))
        self.assertEqual(f['dep_gate']['value'],'7')
        self.assertEqual(t._merge(f,{'dep_gate':'9'},'mapflights',104),[('dep_gate','9')])
    def test_persistent_quota_and_cooldown(self):
        now=int(datetime.now(timezone.utc).timestamp())
        with t.db() as c:
            self.assertTrue(t._claim(c,'x','flightbyte',self.s,now))
            self.assertFalse(t._claim(c,'x','flightbyte',self.s,now+1))
        with t.db() as c:
            self.assertEqual(t._usage(c,'flightbyte',now),1)
            c.executemany('INSERT INTO attempts VALUES(?,?)',[('flightbyte',now)]*109)
            self.assertFalse(t._claim(c,'y','flightbyte',self.s,now))
