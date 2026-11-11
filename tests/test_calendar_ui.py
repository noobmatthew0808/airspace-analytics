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

    @unittest.skipUnless(shutil.which('node'),'Node.js not installed')
    def test_every_year_month_has_same_six_week_height(self):
        js=(ROOT/'frontend/calendar.js').as_posix()
        code=rf"""global.window={{}};require({js!r});
const html=window.AirspaceCalendar.render([],{{level:'year',year:2026}});
const cards=html.match(/<button class=\"calendar-month calendar-mini[\s\S]*?<\/button>/g)||[];
if(cards.length!==12)throw Error('Expected twelve calendar cards');
for(const [index, card] of cards.entries()){{
 const days=(card.match(/class=\"calendar-date /g)||[]).length;
 const blanks=(card.match(/class=\"calendar-blank\"/g)||[]).length;
 if(days+blanks!==42)throw Error('Month '+(index+1)+' has '+(days+blanks)+' day slots');
}}
const month=window.AirspaceCalendar.render([],{{level:'month',year:2026,month:11}});
if((month.match(/class=\"calendar-date /g)||[]).length!==30)throw Error('Monthly detail changed');
"""
        result=subprocess.run(['node','-e',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_missing_days_are_blank_even_with_zero_padding(self):
        js=(ROOT/'frontend/calendar.js').as_posix()
        code=f"""global.window={{}};require({js!r});
const x=window.AirspaceCalendar.render([
  {{key:'2026-11-09',value:19,has_data:true}},
  {{key:'2026-11-10',value:0,has_data:false}},
  {{key:'2026-11-11',value:0,has_data:false}}
],{{level:'year',year:2026}});
const known=(x.match(/calendar-date has-data/g)||[]).length;
const blank=(x.match(/calendar-date missing/g)||[]).length;
if(known!==1||blank!==364)throw Error('Missing days shown as activity: '+known+'/'+blank);
if((x.match(/data-heat-month=/g)||[]).length!==12)throw Error('Year cards are not clickable');
const month=window.AirspaceCalendar.render([],{{level:'month',year:2026,month:11}});
if(!month.includes('data-heat-back'))throw Error('Month lacks year-back control');
"""
        result=subprocess.run(['node','-e',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
