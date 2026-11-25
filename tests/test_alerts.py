"""No receiver or network required: deterministic alert engine regression tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
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
    def test_avio_connection_uses_working_application_user_agent(self):
        key='avio_dummy_test_key'
        alerts.save_avio({'key':key})
        response=Mock()
        response.read.return_value=json.dumps({'tier':'contributor'}).encode()
        manager=Mock()
        manager.__enter__=Mock(return_value=response)
        manager.__exit__=Mock(return_value=False)
        opener=Mock()
        opener.open.return_value=manager
        with patch.object(alerts,'build_opener',return_value=opener):
            result=alerts.test_avio()
        req=opener.open.call_args.args[0]
        self.assertEqual(req.full_url,'https://avioadsb.org/v1/me')
        self.assertEqual(req.get_header('User-agent'),'AirspaceAnalytics-Flights/4')
        self.assertEqual(req.get_header('X-api-key'),key)
        self.assertNotIn(key,req.full_url)
        self.assertEqual(result['plan'],'contributor')

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
        self.assertEqual(len(alerts.validate_rule({'label':'Group of 100','field':'registration','pattern':valid})['pattern'].split(',')),100)
        with self.assertRaisesRegex(ValueError,'up to 100'):
            alerts.validate_rule({'label':'Group of 101','field':'registration','pattern':valid+',G-XTRA'})

    def test_invalid_rules(self):
        for value in ({'field':'zip','pattern':'A388'}, {'field':'type','pattern':'&bad'},
                      {'field':'type','pattern':'A388','min_ft':10000,'max_ft':5000},
                      {'field':'registration','pattern':'G-ABC','max_km':-1}):
            with self.assertRaises(ValueError):alerts.save_rule(value)
    def test_ntfy_shows_callsign_and_registration_without_duplicates(self):
        self.rule()
        alerts.save_notifier({'topic':'test_local_alerts'})
        all_planes=[
            plane('abc123',flight='WUK83GK',reg='G-WUKU',t='A21N',alt=9725),
            plane('abc124',flight='BAW123',reg='',t='B738',alt=10500),
            plane('abc125',flight='',reg='G-EZBH',t='A319',alt=8000),
            plane('abc126',flight='G-ABCD',reg='g-abcd',t='A21N',alt=7500),
        ]
        # Aircraft types for this test all match this test rule.
        alerts.save_rule({'label':'Aircraft types','field':'type',
                          'pattern':'A21N,B738,A319','max_km':25})
        # The default A380 test rule is intentionally not triggered here.
        alerts.process_snapshot({'aircraft':all_planes},50,0,now=100)
        response=Mock()
        response.status=200
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=None)
        opener=Mock(return_value=response)
        alerts.deliver_pending(now=100,opener=opener)
        bodies=[call.args[0].data.decode('utf-8') for call in opener.call_args_list]
        self.assertEqual(len(bodies),4)
        self.assertTrue(any(text.startswith('WUK83GK · G-WUKU · A21N · ') and
                            '9,725 ft' in text for text in bodies))
        self.assertTrue(any(text.startswith('BAW123 · B738 · ') for text in bodies))
        self.assertTrue(any(text.startswith('G-EZBH · A319 · ') for text in bodies))
        self.assertTrue(any(text.startswith('G-ABCD · A21N · ') for text in bodies))
        self.assertFalse(any('G-ABCD · g-abcd' in text for text in bodies))
        self.assertTrue(all(' km · ' in text for text in bodies))
        self.assertTrue(all(event['delivery']=='sent' for event in alerts.snapshot()['events']))

    def test_ntfy_tap_opens_selected_aircraft_on_local_map(self):
        self.rule()
        alerts.save_notifier({'topic':'test_local_alerts'})
        alerts.process_snapshot({'aircraft':[plane('abc123'),plane('def456')]},50,0,now=100)
        response=Mock()
        response.status=200
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=None)
        opener=Mock(return_value=response)
        with patch.object(alerts,'_local_addresses',return_value={
                '127.0.0.1','192.168.1.187','172.17.0.1'}):
            alerts.deliver_pending(now=100,opener=opener)
        urls={call.args[0].get_header('Click') for call in opener.call_args_list}
        self.assertEqual(urls,{
            'http://192.168.1.187:1099/map/?icao=ABC123&noIsolation',
            'http://192.168.1.187:1099/map/?icao=DEF456&noIsolation'
        })
        self.assertEqual(len([e for e in alerts.snapshot()['events'] if e['delivery']=='sent']),2)

    def test_local_click_prefers_home_lan_and_ignores_tailscale(self):
        with patch.object(alerts,'_local_addresses',return_value={
                '127.0.0.1','100.120.2.20','172.17.0.1',
                '192.168.122.1','192.168.1.187'}):
            self.assertEqual(alerts._tar1090_local_click_url('a1b2c3'),
                             'http://192.168.1.187:1099/map/?icao=A1B2C3&noIsolation')
            self.assertEqual(alerts._tar1090_local_click_url(),
                             'http://192.168.1.187:1099/map/')
            self.assertIsNone(alerts._tar1090_local_click_url('A1B2&3'))
        with patch.object(alerts,'_local_addresses',return_value={
                '127.0.0.1','100.120.2.20'}):
            self.assertIsNone(alerts._tar1090_local_click_url('abcdef'))

    def test_ntfy_test_notification_opens_local_map_without_hex(self):
        alerts.save_notifier({'topic':'test_local_alerts'})
        response=Mock()
        response.status=200
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=None)
        opener=Mock(return_value=response)
        with patch.object(alerts,'_local_addresses',return_value={'192.168.1.187'}):
            alerts.send_test(opener=opener)
        self.assertEqual(opener.call_args.args[0].get_header('Click'),
                         'http://192.168.1.187:1099/map/')

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
