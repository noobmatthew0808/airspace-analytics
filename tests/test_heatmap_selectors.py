"""Current year/month activity calendar listener regression checks."""
from pathlib import Path
import re
import unittest
APP=Path(__file__).resolve().parents[1]/'frontend'/'app.js'

class TestHeatmapSelectors(unittest.TestCase):
 def test_month_cards_have_collection_listener_and_back_button(self):
  js=APP.read_text(encoding='utf-8')
  self.assertIn("$$('[data-heat-month]',$('#heatmap')).forEach",js)
  self.assertIn("if(back)back.onclick=",js)
 def test_calendar_defaults_to_current_uk_month_and_can_return_to_year(self):
  js=APP.read_text(encoding='utf-8')
  # A page reload clears a previous calendar view; a deliberate Back to year
  # action still selects year while the page is open.
  self.assertIn('delete state.heatYear;delete state.heatMonth;delete state.heatScope;',js)
  self.assertIn(":ukToday().slice(0,7);",js)
  self.assertIn("const mode=state.heatScope==='year'?'year':'month';",js)
  self.assertIn("if(!['year','month'].includes(state.heatScope))state.heatScope='month';",js)
  self.assertIn("state.heatScope='year';persist();",js)
  self.assertIn("state.heatScope='month';persist();",js)

 def test_startup_migration_does_not_override_month_default(self):
  # Execute the actual initialization code, not just the calendar renderer.
  # This catches the v1.10.4 regression where startup forced 'year'.
  import json, shutil, subprocess
  if not shutil.which('node'):self.skipTest('Node.js not installed')
  js=APP.read_text(encoding='utf-8')
  init=js.split('// One-time migration:',1)[1].split('function setTheme(',1)[0]
  script="""
const vm = require('node:vm');
const init = """+json.dumps(init)+""";
for (const marker of [null,'1']) {
 const state = {};
 const localStorage = {
  getItem: () => marker,
  setItem: () => {}
 };
 vm.runInNewContext(init,{state,localStorage,persist:()=>{}});
 if(state.heatScope !== 'month')throw Error('Calendar startup default is '+state.heatScope);
}
"""
  result=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr)

 def test_single_element_selector_never_uses_foreach(self):
  js=APP.read_text(encoding='utf-8')
  self.assertIsNone(re.search(r'(?<!\$)\$\([^\n)]*\)\.forEach\(',js))

if __name__=='__main__':unittest.main()
