/* No browser needed: deterministic regression for the month-only ranked Traffic list. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('frontend/app.js','utf8');
const css=fs.readFileSync('frontend/styles.css','utf8');
const start=source.indexOf('function isFullMonthChart(){');
const stop=source.indexOf('function drawCurrentChart(){',start);
assert.ok(start>0&&stop>start,'Month ranking helpers must stay near Traffic chart');

function helpers(state){
 return vm.runInNewContext(source.slice(start,stop)+
  '\n;({isFullMonthChart,rankMonthDays,renderMonthRanking});',
  {state,esc:v=>String(v).replace(/[&<>"]/g,''),
   fmt:v=>Number(v).toLocaleString('en-GB')});
}
const monthState={period:'custom',bucket:'week',start:'2026-11-01T00:00',end:'2026-12-01T00:00'};
const h=helpers(monthState);
assert.equal(h.isFullMonthChart(),true,'Month drilldown enables Graph');
assert.equal(helpers({...monthState,bucket:'month'}).isFullMonthChart(),false,'Yearly month bars should not enable Graph');
assert.equal(helpers({...monthState,bucket:'day'}).isFullMonthChart(),false,'Week drilldown should not enable Graph');
assert.equal(helpers({...monthState,period:'rolling'}).isFullMonthChart(),false);
assert.equal(helpers({...monthState,start:'2026-11-09T00:00'}).isFullMonthChart(),false);
assert.equal(helpers({...monthState,start:'2026-12-01T00:00',end:'2027-01-01T00:00'}).isFullMonthChart(),true,'December to January rollover works');
assert.equal(helpers({...monthState,start:'2024-02-01T00:00',end:'2024-03-01T00:00'}).isFullMonthChart(),true,'Leap-year month works');

const input=[
 {key:'2026-11-05',value:17,has_data:true},
 {key:'2026-11-02',value:29,has_data:true},
 {key:'2026-11-04',value:0,has_data:false},
 {key:'2026-11-03',value:29,has_data:true},
 {key:'2026-11-06',value:0,has_data:true},
 {key:'2026-11-01',value:0,has_data:false},
 {key:'invalid',value:100,has_data:true},
];
const ranked=h.rankMonthDays(input);
assert.equal(ranked.map(x=>x.key).join(','),'2026-11-02,2026-11-03,2026-11-05,2026-11-06,2026-11-01,2026-11-04',
  'Sort by busiest descending, tie by date, missing observations last');
assert.equal(input[0].key,'2026-11-05','Do not mutate the original chart series');
assert.equal(h.rankMonthDays([]).length,0);
const html=h.renderMonthRanking(input,'flights');
assert.match(html,/Busiest days/);
assert.match(html,/Most to least/);
assert.match(html,/visits/);
assert.equal((html.match(/class="month-rank-row/g)||[]).length,6);
assert.ok(html.indexOf('2026-11-02')<html.indexOf('2026-11-05'),'Busiest dates appear first');
assert.ok(html.indexOf('2026-11-06')<html.indexOf('2026-11-01'),'Non-observed dates appear last');
assert.match(html,/receiver may have been offline/);
assert.match(h.renderMonthRanking([], 'flights'),/No daily data/);

assert.match(source,/id="monthRankToggle"[^>]*>Graph<\/button>/);
assert.match(source,/id="monthRankPanel" class="month-rank-panel" hidden/);
assert.match(source,/a\.bucket==='week'&&isFullMonthChart\(\)/);
assert.match(source,/api\('\/api\/analytics',queryArgs\('day'\)\)/);
assert.match(source,/if\(rid!==renderId\|\|panel\.hidden\)return/);
assert.match(css,/\.month-rank-panel\[hidden\]\{display:none\}/);
console.log('PASS: Month-only Graph button, daily ranking, ties, absent data, months and existing chart safeguards');


// The requested button belongs to Activity Calendar's month view, NOT
// just the main Traffic chart's separately drilled down month.
const calendarSource=fs.readFileSync('frontend/calendar.js','utf8');
const sandbox={window:{}};
vm.runInNewContext(calendarSource,sandbox);
const sample=[{key:'2026-11-09',value:421,has_data:true},
              {key:'2026-11-10',value:457,has_data:true}];
const month=sandbox.window.AirspaceCalendar.render(sample,{level:'month',year:2026,month:11,metric:'flights'});
const year=sandbox.window.AirspaceCalendar.render(sample,{level:'year',year:2026,month:11,metric:'flights'});
assert.match(month,/November 2026/);
assert.match(month,/data-heat-back/);
assert.match(month,/data-heat-graph[^>]*>Graph<\/button>/);
assert.match(month,/id="calendarRankPanel" class="month-rank-panel" hidden/);
assert.doesNotMatch(year,/data-heat-graph/);
assert.doesNotMatch(year,/id="calendarRankPanel"/);
assert.match(source,/const graph=\$\('\[data-heat-graph\]'/);
assert.match(source,/ranking\.innerHTML=renderMonthRanking\(response\.series,metric\)/);
assert.match(source,/ranking\.hidden=!open/);
assert.match(source,/graph\.setAttribute\('aria-expanded',String\(open\)\)/);
console.log('PASS: Activity Calendar month header has Graph toggle, uses existing daily data, absent on year');
