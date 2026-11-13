"""Daily Traffic / Settings regression and London DST handling."""
from pathlib import Path
import subprocess
import shutil
import unittest
ROOT=Path(__file__).resolve().parents[1]

class TestV197UI(unittest.TestCase):
    def test_settings_and_chart_contract(self):
        js=(ROOT/'frontend/app.js').read_text()
        for token in ("function setTodayWindow()","function checkTodayRollover()",
            "function todayChartSeries(", "exclude_days:excludedAverageDays().join(',')",
            'id="launcherEditor"', 'id="excludedDaysEditor"',
            'id="databaseInfo" class="database-hitbox" href="/analytics#database"',
            "state.metric=b.dataset.metric;persist();renderExplore()"):
            self.assertIn(token,js)
        for missing in ('id="settingTheme"','id="settingMetric"','id="saveAppearance"','Open database →'):
            self.assertNotIn(missing,js)
        self.assertIn("setTheme('dark');",js)

    @unittest.skipUnless(shutil.which('node'),'Node.js unavailable')
    def test_daily_time_windows_including_dst(self):
        code=r"""
const fs=require('node:fs');
const s=fs.readFileSync(process.argv[1],'utf8');
const a=s.indexOf("const exclusionKey="),b=s.indexOf("// A previously paired browser",a);
if(a<0||b<a)throw Error("Date helpers not found");
const src=s.slice(a,b);
function make(){
 const state={},zoomHistory=[],storage=new Map();
 const localStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)};
 return new Function('state','zoomHistory','localStorage','persist','currentPage','renderExplore','Date',src+
 ';return {setTodayWindow,todayChartSeries,excludedAverageDays,setExcludedAverageDays,checkTodayRollover,setDay:day=>ukToday=()=>day};'
 )(state,zoomHistory,localStorage,()=>{},'explore',()=>{},Date);
}
const v=make();
if(v.excludedAverageDays().join()!=='2026-11-09')throw Error('Missing default exclusion');
v.setExcludedAverageDays([]);if(v.excludedAverageDays().length)throw Error('Cannot restore date');
for(const [day,n] of [['2026-11-13',24],['2026-03-29',23],['2026-10-25',25]]){
 v.setDay(day);v.setTodayWindow();
 const xs=v.todayChartSeries({bucket:'hour',series:[]});
 if(xs.length!==n)throw Error(day+' expected '+n+' hours, got '+xs.length);
 if(xs.some(x=>x.value!==null))throw Error('Blank hours invented data');
}
const next=make();next.setDay('2026-11-13');next.setTodayWindow();
next.setDay('2026-11-14');next.checkTodayRollover();
const vals=next.todayChartSeries({bucket:'hour',series:[]});
if(vals.length!==24)throw Error('Next day did not roll over');
"""
        result=subprocess.run(['node','-e',code,str(ROOT/'frontend/app.js')],capture_output=True,text=True,timeout=12)
        self.assertEqual(result.returncode,0,result.stderr)
