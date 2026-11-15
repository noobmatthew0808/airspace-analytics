"""No receiver or network required: deterministic alert engine regression tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from backend import alerts

def plane(hexcode, t='A388', lon=.05, flight='BAW1', reg='G-XLEA', alt=9000):
    return {'hex':hexcode,'t':t,'flight':flight,'r':reg,'lat':50.0,'lon':lon,
            'seen':0,'seen_pos':0,'alt_baro':alt,'dbFlags':0}

class AlertsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=alerts.DB_PATH
        alerts.DB_PATH=Path(self.tmp.name)/'alerts.sqlite3'
        alerts._last_sample.update(time=None,aircraft=0,error='offline',lat=None,lon=None)
    def tearDown(self):
        alerts.DB_PATH=self.old
        self.tmp.cleanup()
    def rule(self, **kw):
        return alerts.save_rule({'label':'A380','field':'type','pattern':'A388','max_km':25,'max_ft':12000,**kw})
    def test_distinct_airframes_and_no_duplicate(self):
        self.rule()
        alerts.process_snapshot({'aircraft':[plane('abc123'),plane('def123')]},50,0,now=100)
        alerts.process_snapshot({'aircraft':[plane('abc123'),plane('def123')]},50,0,now=104)
        result=alerts.snapshot()
        self.assertEqual(len(result['events']),2)
        self.assertEqual(result['rules'][0]['active'],2)
        self.assertEqual({x['hex'] for x in result['events']},{'abc123','def123'})
    def test_leave_reenter_rearms_without_cooldown(self):
        self.rule()
        alerts.process_snapshot({'aircraft':[plane('abc123')]},50,0,now=100)
        alerts.process_snapshot({'aircraft':[plane('abc123',lon=.7)]},50,0,now=103)
        alerts.process_snapshot({'aircraft':[plane('abc123',lon=.7)]},50,0,now=106)
        self.assertEqual(alerts.snapshot()['rules'][0]['active'],0)
        alerts.process_snapshot({'aircraft':[plane('abc123')]},50,0,now=109)
        self.assertEqual(len(alerts.snapshot()['events']),2)
    def test_distance_jitter(self):
        self.rule(max_km=10)
        alerts.process_snapshot({'aircraft':[plane('abc123',lon=.01)]},50,0,now=100)
        alerts.process_snapshot({'aircraft':[plane('abc123',lon=.14)]},50,0,now=104)
        alerts.process_snapshot({'aircraft':[plane('abc123',lon=.01)]},50,0,now=107)
        self.assertEqual(len(alerts.snapshot()['events']),1)
    def test_missing_position_does_not_trigger_or_rearm(self):
        self.rule()
        alerts.process_snapshot({'aircraft':[plane('abc123')]},50,0,now=100)
        missing=plane('abc123');missing.pop('lat');missing.pop('lon')
        for now in (104,108,112):alerts.process_snapshot({'aircraft':[missing]},50,0,now=now)
        self.assertEqual(alerts.snapshot()['rules'][0]['active'],1)
        self.assertEqual(len(alerts.snapshot()['events']),1)
    def test_filters(self):
        for field,pattern in [('type','A342,A343,A345,A346'),('registration','G-*'),
                              ('callsign','BAW*'),('hex','ABC123')]:
            alerts.save_rule({'label':field,'field':field,'pattern':pattern})
        alerts.process_snapshot({'aircraft':[plane('abc123',t='A346')]},50,0,now=100)
        self.assertEqual(len(alerts.snapshot()['events']),4)
    def test_altitude_range(self):
        self.rule(min_ft=8000,max_ft=12000)
        alerts.process_snapshot({'aircraft':[plane('abc123',alt=13000)]},50,0,now=100)
        self.assertEqual(len(alerts.snapshot()['events']),0)
        alerts.process_snapshot({'aircraft':[plane('abc123',alt=9000)]},50,0,now=103)
        self.assertEqual(len(alerts.snapshot()['events']),1)
        no_alt=plane('abc123');no_alt.pop('alt_baro')
        alerts.process_snapshot({'aircraft':[no_alt]},50,0,now=106)
        self.assertEqual(alerts.snapshot()['rules'][0]['active'],1)
    def test_restart_gap_not_an_exit_but_long_absence_is(self):
        self.rule()
        alerts.process_snapshot({'aircraft':[plane('abc123')]},50,0,now=100)
        alerts.process_snapshot({'aircraft':[]},50,0,now=110)
        alerts.process_snapshot({'aircraft':[plane('abc123')]},50,0,now=115)
        self.assertEqual(len(alerts.snapshot()['events']),1)
        alerts.process_snapshot({'aircraft':[]},50,0,now=900)
        alerts.process_snapshot({'aircraft':[plane('abc123')]},50,0,now=903)
        self.assertEqual(len(alerts.snapshot()['events']),2)
    def test_ntfy_secret_not_visible_on_api(self):
        alerts.save_notifier({'server':'https://ntfy.sh','topic':'unguessable','token':'tok-secret'})
        result=alerts.snapshot()
        self.assertTrue(result['ntfy']['token_set'])
        self.assertNotIn('tok-secret',json.dumps(result))
    def test_31_registration_values_in_one_rule(self):
        registrations = [f'G-EX{i:04d}' for i in range(31)]
        saved = alerts.validate_rule({'label':'Previously flown', 'field':'registration',
                                      'pattern':','.join(registrations),
                                      'max_km':5,'max_ft':10000})
        self.assertEqual(len(saved['pattern'].split(',')),31)
        alerts.save_rule(saved)
        target=plane('abc123',reg=registrations[-1],lon=.01,alt=8000)
        alerts.process_snapshot({'aircraft':[target]},50,0,now=100)
        self.assertEqual(len(alerts.snapshot()['events']),1)
        self.assertEqual(alerts.snapshot()['events'][0]['registration'],registrations[-1])

    def test_pattern_limit_100_and_reject_101(self):
        valid = ','.join(f'G-A{i:03d}' for i in range(100))
        self.assertEqual(len(alerts.validate_rule({'field':'registration','pattern':valid})['pattern'].split(',')),100)
        with self.assertRaisesRegex(ValueError,'up to 100'):
            alerts.validate_rule({'field':'registration','pattern':valid+',G-XTRA'})

    def test_invalid_rules(self):
        for value in ({'field':'zip','pattern':'A388'}, {'field':'type','pattern':'&bad'},
                      {'field':'type','pattern':'A388','min_ft':10000,'max_ft':5000},
                      {'field':'registration','pattern':'G-ABC','max_km':-1}):
            with self.assertRaises(ValueError):alerts.save_rule(value)
    def test_ntfy_delivered_once(self):
        self.rule();alerts.save_notifier({'topic':'topicXYZ'})
        alerts.process_snapshot({'aircraft':[plane('abc123')]},50,0,now=100)
        response=Mock();response.status=200;response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=None)
        opener=Mock(return_value=response)
        alerts.deliver_pending(now=100,opener=opener)
        alerts.deliver_pending(now=101,opener=opener)
        self.assertEqual(opener.call_count,1)
        self.assertEqual(alerts.snapshot()['events'][0]['delivery'],'sent')
if __name__=='__main__':unittest.main()
