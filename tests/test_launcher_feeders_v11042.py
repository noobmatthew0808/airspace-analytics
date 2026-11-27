import copy
import json
import re
import sqlite3
import unittest
from pathlib import Path
from backend import shared_settings as settings


class LauncherFeedersV11042Tests(unittest.TestCase):
    def test_new_defaults_match_browser(self):
        app = (Path(__file__).resolve().parents[1] / 'frontend' / 'app.js').read_text()
        rows = json.loads(re.search(r'const launcherFeederLinksV11042=(\[.*?\]);', app, re.S).group(1))
        self.assertEqual(rows, settings.LAUNCHER_FEEDER_LINKS_V11042)
        self.assertEqual(settings.links(rows), rows)
        self.assertEqual(len({r['id'] for r in rows}), len(rows))
        self.assertTrue(all(r['group'] == 'feeders' and r['extraUrl'].startswith('https://') for r in rows))

    def test_existing_saved_shortcuts_are_migrated_once(self):
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory = sqlite3.Row
            conn.execute('CREATE TABLE config(key TEXT PRIMARY KEY, value TEXT)')
            original = {'excluded_days':['2026-11-09'], 'links':[
                {'id':'custom-1','name':'Custom','group':'stats','url':'https://example.org/'},
                {'id':'custom-dataero','name':'Data Aero','group':'stats','url':'https://radar.dataero.eu/user/dashboard','extraLabel':'Map','extraUrl':'https://radar.dataero.eu/map'},
                {'id':'old-tat','name':'The Air Traffic','group':'stats','url':'https://theairtraffic.com/'},
                {'id':'fr24','name':'Flightradar24','group':'feeders','port':'8754'},
            ],'revision':7,'migrated':['existing-browser'],'dates_initialized':True,'removed_links':['id:old-custom'],
            'feeder_links_v11033':True,'dataero_links_v11041':True}
            conn.execute('INSERT INTO config VALUES(?,?)',(settings.KEY,json.dumps(original)))
            new = settings._load(conn)
            self.assertEqual(new['revision'],8)
            self.assertEqual(new['links'][0],original['links'][0])
            self.assertEqual(new['links'][3],original['links'][3])
            self.assertEqual(new['links'][1],dict(original['links'][1],group='feeders'))
            self.assertEqual(new['links'][2]['url'],'https://theairtraffic.com/myip')
            self.assertEqual(new['links'][2]['extraUrl'],'https://globe.theairtraffic.com/')
            self.assertEqual(len(new['links']),len(original['links'])+len(settings.LAUNCHER_FEEDER_LINKS_V11042)-1)
            for key in ('excluded_days','migrated','removed_links','dates_initialized'):
                self.assertEqual(new[key],original[key])
            self.assertEqual(settings._load(conn),new)
            new['links']=[r for r in new['links'] if r.get('id')!='realtraffic']
            conn.execute('UPDATE config SET value=? WHERE key=?',(json.dumps(new),settings.KEY))
            self.assertEqual(settings._load(conn),new)

    def test_idempotence_and_capacity(self):
        items=[{'id':'dataero','name':'Dataero','group':'stats'}]
        self.assertTrue(settings._migrate_launcher_feeders(items))
        snapshot=copy.deepcopy(items)
        self.assertFalse(settings._migrate_launcher_feeders(items))
        self.assertEqual(items,snapshot)
        full=[{'id':str(i),'name':str(i),'group':'stats'} for i in range(100)]
        self.assertFalse(settings._migrate_launcher_feeders(full))
        self.assertEqual(len(full),100)
