'use strict';
const fs=require('node:fs');
const assert=require('node:assert/strict');
const path=require('node:path');
const js=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');
const begin=js.indexOf('// Suggestions use existing read-only daily analytics;');
const end=js.indexOf('let excludedEditorExpanded=false;',begin);
assert(begin>=0&&end>begin,'Suggestion logic must be isolated and testable');
const suggest=new Function(js.slice(begin,end)+';return suggestedAverageExclusions;')();
const dates=Array.from({length:44},(_,i)=>{
 const d=new Date(Date.UTC(2026,7,15+i));
 return d.toISOString().slice(0,10);
});
const low=dates[40],first=dates[0],today='2026-10-01';
const visits=dates.map(key=>({key,value:key===low?20:100,has_data:true}));
const observations=dates.map(key=>({key,value:key===low?200:1000,has_data:true}));
const run=(v=visits,o=observations,excluded=[])=>suggest(v,o,first,today,excluded);
const result=run();
assert.equal(result.length,1,'Only genuinely corroborated low days should appear');
assert.equal(result[0].date,low);
assert.equal(result[0].visitDrop,80);
assert.equal(result[0].observationDrop,80);
assert(result[0].comparisonDays>=3);
assert.equal(result[0].sameWeekday,true,'Prefer weekday-matched baseline when possible');
assert.equal(run(visits,observations,[low]).length,0,'Never recommend dates already excluded');
assert.equal(run(visits,observations.map(x=>x.key===low?{...x,value:800}:x)).length,0,
 'Low visits without unusually low observations are insufficient evidence');
assert.equal(run(visits,observations.map(x=>x.key===low?{...x,has_data:false}:x)).length,0,
 'Missing observation data must not be treated as zero');
assert.equal(run(visits.map(x=>x.key===low?{...x,has_data:false}:x)).length,0,
 'Missing visit data must not be treated as zero');
assert.equal(suggest(visits,observations,low,today).length,0,
 'Never flag the first potentially partial day');
assert.equal(suggest(visits,observations,first,low).length,0,
 'Never flag the current incomplete UK day');
assert.equal(suggest(visits.slice(0,7),observations.slice(0,7),first,today).length,0,
 'Do not guess from less than a week of earlier recorded days');
assert(js.includes('data-suggest-exclude='),'Add button must be rendered');
assert(js.includes("setExcludedAverageDays([...excluded,day]);"),
 'Only the user-selected Add handler should mutate excluded days');
assert(js.includes("excludedFold.addEventListener('toggle'"),'Suggestions load only on opening exclusions');
assert(js.includes("const observations=await daily('observations')"),
 'Stats must be based on actual observations, not only aircraft counts');
console.log('Suggested excluded days: 12 deterministic browser checks passed.');

assert(js.includes("const visits=await daily('flights')"));
assert(js.includes('already processing another analysis'));
