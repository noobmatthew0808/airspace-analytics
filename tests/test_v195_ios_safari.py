"""PWA link routing: opening external services in full Safari without changing other platforms."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class SafariLauncherTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js not available")
    def test_external_links_only_on_ios_home_screen(self):
        script = r"""
const fs = require('node:fs');
const s = fs.readFileSync(process.argv[1], 'utf8');
const start = s.indexOf('function safariAppLink(url){');
const end = s.indexOf('\nfunction launcherGroup(', start);
if (start < 0 || end < 0) throw Error('Safari launcher missing');
const code = s.slice(start,end);
const build = new Function('navigator','window','hrefFor','esc','branding','icon',
  code+';return {safariAppLink,launcherEntry};');
const href = x => x.url || ('http://192.168.1.187:'+(x.port||8088)+(x.path||'/'));
const make = (nav,standalone) => build(nav,
  {matchMedia: () => ({matches: standalone})},
  href, String, () => '<span>logo</span>', () => '<svg></svg>');
const iphone = {userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_7_8)',standalone:true};
const win = {userAgent:'Mozilla/5.0 (Windows NT 10.0)'};
const local = {name:'ADSB.im',port:'1099',path:'/'};
const remote = {name:'ADS-B Exchange',url:'https://www.adsbexchange.com/myip/',
  extraLabel:'Feeder map',extraUrl:'https://globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2'};
function ok(yes,message) {if (!yes) throw Error(message)}
const ios = make(iphone,true);
const localHtml = ios.launcherEntry(local);
ok(localHtml.includes('href="x-safari-http://192.168.1.187:1099/"'), 'Local Safari link');
ok(!localHtml.includes('target="_blank"'), 'Custom scheme should not spawn blank PWA window');
const externalHtml = ios.launcherEntry(remote);
ok(externalHtml.includes('href="x-safari-https://www.adsbexchange.com/myip/"'), 'HTTPS Safari link');
ok(externalHtml.includes('href="x-safari-https://globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2"'), 'Secondary link');
ok(ios.launcherEntry({name:'Airspace Analytics'},true).includes('href="/analytics#explore"'), 'Internal analytics');
ok(make(win,false).launcherEntry(local).includes('href="http://192.168.1.187:1099/"'), 'Desktop unchanged');
ok(make({...iphone,standalone:false},false).launcherEntry(local).includes('href="http://192.168.1.187:1099/"'), 'Safari normal mode unchanged');
ok(make({userAgent:'Android'},true).launcherEntry(local).includes('href="http://192.168.1.187:1099/"'), 'Android unchanged');
"""
        out = subprocess.run(["node", "-e", script, str(ROOT / "frontend" / "app.js")],
                             text=True, capture_output=True, timeout=10)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_no_template_or_configuration_changes(self):
        js = (ROOT / "frontend" / "app.js").read_text()
        self.assertIn('const defaultLinks=[', js)
        self.assertIn('function renderExplore()', js)
        self.assertIn('function renderHome()', js)
        self.assertIn('function drillInto(', js)

if __name__ == "__main__":
    unittest.main()
