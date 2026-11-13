"""v1.9.8: shortcut editor must be compact, while analytics stay unchanged."""
from pathlib import Path
import subprocess
import shutil
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestLauncherEditor(unittest.TestCase):
    def test_existing_features_preserved(self):
        source=(ROOT/"frontend/app.js").read_text()
        for needle in (
            "function setTodayWindow()",
            "function checkTodayRollover()",
            "exclude_days:excludedAverageDays().join(',')",
            "state.metric=b.dataset.metric;persist();renderExplore()",
            'id="databaseInfo" class="database-hitbox" href="/analytics#database"',
            'id="launcherEditor"',
            "function drillInto(",
            "function renderChart(",
        ):
            self.assertIn(needle,source)

    def test_compact_editor_present(self):
        source=(ROOT/"frontend/app.js").read_text()
        style=(ROOT/"frontend/styles.css").read_text()
        self.assertIn('<details class="shortcut-edit-row"',source)
        self.assertIn('shortcut-edit-summary',source)
        self.assertIn("other.open=false",source)
        self.assertIn(".shortcut-edit-row[open]",style)
        self.assertIn("id=\"addLink\"",source)
        self.assertIn("id=\"saveLinks\"",source)
        self.assertIn("id=\"restoreLinks\"",source)

    @unittest.skipUnless(shutil.which("node"),"Node unavailable")
    def test_shortcuts_render_closed_and_keep_edit_fields(self):
        code=r"""
const fs=require('node:fs');
const s=fs.readFileSync(process.argv[1],'utf8');
const a=s.indexOf('function settingsLinks(){'), b=s.indexOf('function collectSettingsLinks()',a);
if(a<0||b<0)throw Error('Missing editor');
const render=new Function('getLinks','field','opts','esc','icon',s.slice(a,b)+';return settingsLinks;');
const links=[
 {name:'ADSB.im',group:'stats',port:'1099'},
 {name:'Aerodrome',group:'stats',port:'8000'},
 {name:'FlightDeck',group:'feeders',url:'https://www.tryflightdeck.com/map/account/feeder'}
];
const html=render(()=>links,(n,v)=>'<label>'+n+v+'</label>',()=>'',String,()=>'<svg></svg>')();
const count=(pattern)=>(html.match(pattern)||[]).length;
if(count(/<details class="shortcut-edit-row"/g)!==3)throw Error('Missing compact link entries');
if(count(/data-linkindex=/g)!==3)throw Error('Missing indexes');
for(const field of ['link-port','link-url','link-logo-domain','link-extra-label','link-extra-path'])
 if(!html.includes(field))throw Error('Missing editable field '+field);
for(const id of ['saveLinks','restoreLinks','addLink'])
 if(!html.includes('id="'+id+'"'))throw Error('Missing action '+id);
if(html.includes('class="shortcut-edit-row" open'))throw Error('Editors unexpectedly open');
"""
        p=subprocess.run(["node","-e",code,str(ROOT/"frontend/app.js")],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)

if __name__=="__main__":unittest.main()
