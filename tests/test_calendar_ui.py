"""Calendar regression checks: complete year/month date grids and leap days."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestCalendar(unittest.TestCase):
    def test_linked_assets(self):
        html=(ROOT/'frontend/index.html').read_text()
        self.assertIn('href="/calendar.css"',html)
        self.assertIn('src="/calendar.js"',html)

    @unittest.skipUnless(shutil.which('node'),'Node.js is optional')
    def test_year_month_calendar_days(self):
        js=(ROOT/'frontend/calendar.js').as_posix()
        code=f'''global.window={{}};require({js!r});
for(const [year,days] of [[2024,366],[2026,365]]){{
 const html=window.AirspaceCalendar.render([],{{level:'year',year}});
 if((html.match(/class="calendar-date /g)||[]).length!==days)throw Error('Year day count');
 if((html.match(/data-heat-month=/g)||[]).length!==12)throw Error('Month links');
}}
const feb=window.AirspaceCalendar.render([],{{level:'month',year:2024,month:2}});
if((feb.match(/class="calendar-date /g)||[]).length!==29)throw Error('Leap February');
'''
        result=subprocess.run(['node','-e',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
