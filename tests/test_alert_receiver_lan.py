"""Regression: tar1090 can be published on this Linux machine's LAN IP only."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError, HTTPError

from backend import alerts


class TestReceiverOnLAN(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = alerts.DB_PATH
        self.old_last = alerts._last_good_url
        alerts.DB_PATH = Path(self.temp.name) / 'alert-rules.sqlite3'
        alerts._last_good_url = None
        self.addresses = {'127.0.0.1', '192.168.1.187'}
        self.patch_ips = patch.object(alerts, '_local_addresses', return_value=self.addresses)
        self.patch_ips.start()

    def tearDown(self):
        self.patch_ips.stop()
        alerts.DB_PATH = self.old_db
        alerts._last_good_url = self.old_last
        self.temp.cleanup()

    def test_manual_pc_lan_ip_is_valid_but_other_hosts_are_rejected(self):
        local = 'http://192.168.1.187:1099/map/data/aircraft.json'
        alerts.save_receiver({'url':local})
        self.assertEqual(alerts.snapshot()['receiver_settings']['url'],local)
        for forbidden in (
            'http://192.168.1.188:1099/data/aircraft.json',
            'http://10.0.0.99:1099/data/aircraft.json',
            'http://example.com:1099/data/aircraft.json',
            'https://192.168.1.187:1099/data/aircraft.json',
            'http://192.168.1.187:1099/data/aircraft.json?x=1',
            'http://evil:pass@192.168.1.187:1099/data/aircraft.json',
            'http://192.168.1.187:99999/data/aircraft.json',
        ):
            with self.subTest(url=forbidden), self.assertRaises(ValueError):
                alerts.save_receiver({'url':forbidden})

    def test_auto_detects_lan_if_loopback_refuses_connection(self):
        good = 'http://192.168.1.187:1099/data/aircraft.json'
        tried = []
        def fetch(url):
            tried.append(url)
            if url == good:
                return {'now':time.time(),'aircraft':[{'hex':'abc123','t':'A388','seen':0}]}
            if url == good.replace('aircraft.json','receiver.json'):
                return {'lat':50.86,'lon':0.24}
            raise URLError('Connection refused')
        with patch.object(alerts,'_get_json',side_effect=fetch):
            sample,lat,lon=alerts.read_receiver()
            self.assertEqual(len(sample['aircraft']),1)
            self.assertEqual((lat,lon),(50.86,0.24))
            self.assertEqual(alerts._last_good_url,good)
            self.assertIn('http://127.0.0.1:1099/data/aircraft.json',tried)
            self.assertIn(good,tried)
            self.assertEqual(alerts.check_receiver()['source'],good)
            # A known good feed is polled first the next time.
            self.assertEqual(tried[-2],good)
        self.assertNotIn('http://192.168.1.188:1099/data/aircraft.json',tried)

    def test_local_url_candidate_list_prioritises_compatible_paths(self):
        urls=alerts._receiver_candidates(self.addresses)
        self.assertIn('http://192.168.1.187:1099/map/data/aircraft.json',urls)
        self.assertIn('http://192.168.1.187:1099/data/aircraft.json',urls)
        self.assertIn('http://192.168.1.187:8080/data/aircraft.json',urls)
        self.assertEqual(len(set(urls)),len(urls))

    def test_unreachable_manual_source_does_not_scan_other_hosts(self):
        wanted='http://192.168.1.187:1099/data/aircraft.json'
        alerts.save_receiver({'url':wanted})
        with patch.object(alerts,'_get_json',side_effect=URLError('refused')) as fetch:
            with self.assertRaisesRegex(ValueError,'Receiver URL unreachable'):
                alerts.read_receiver()
            self.assertEqual(fetch.call_count,1)
            self.assertEqual(fetch.call_args.args[0],wanted)

    def test_ui_references_browser_host_without_hardcoding_site_ip(self):
        ui=(Path(__file__).resolve().parents[1]/'frontend'/'alerts-ui.js').read_text()
        self.assertIn("ae(location.hostname)",ui)
        self.assertIn("automatic localhost and LAN detection",ui)
        self.assertIn("result.source",ui)


if __name__ == '__main__':
    unittest.main()
