"""Calendar regression checks: full date grids, leap days and month selection."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestCalendar(unittest.TestCase):
    def test_calendar_assets_linked(self):
        html=(ROOT/'frontend/index.html').read_text()
        self.assertIn('href="/calendar.css"',html)
        self.assertIn('src="/calendar.js"',html)

    @unittest.skipUnless(shutil.which('node'),'Node.js not installed')
    def test_js_calendar_date_counts(self):
        js=(ROOT/'frontend/calendar.js').as_posix()
        code=f'''global.window={{}};require({js!r});
for(const [year, expected] of [[2024,366],[2026,365]]){{
 const html=window.AirspaceCalendar.render([],{{level:'year',year}});
 const cells=(html.match(/class="calendar-date /g)||[]).length;
 if(cells!==expected)throw Error(`Expected ${{expected}}, got ${{cells}}`);
}}
const feb=window.AirspaceCalendar.render([],{{level:'month',year:2024,month:2}});
if((feb.match(/class="calendar-date /g)||[]).length!==29)throw Error('Leap February lost');
if(!feb.includes('February 2024'))throw Error('Month title missing');
const year=window.AirspaceCalendar.render([],{{level:'year',year:2026}});
if((year.match(/data-heat-month=/g)||[]).length!==12)throw Error('Month navigation missing');
'''
        result=subprocess.run(['node','-e',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
