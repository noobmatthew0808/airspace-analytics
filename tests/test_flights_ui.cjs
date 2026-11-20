/* Tests that preserve the uploaded Flight Tracker's exact filter semantics. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {test}=require('node:test');
const {pathToFileURL}=require('node:url');
const source=fs.readFileSync('frontend/flights-ui.js','utf8');
const dataUrl='data:text/javascript;base64,'+Buffer.from(source).toString('base64');

let exportsPromise=import(dataUrl);
const first={
 id:'1',date:'2025-10-29',from_airport:'LGW',to_airport:'BTS',
 flight_code:'W95776',airline:'Wizz Air',airplane:'A321neo',
 registration:'G-WUKU',who:'Matthew; Florence'
};
const second={
 id:'2',date:'2026-01-05',from_airport:'LGW',to_airport:'VIE',
 flight_code:'EZY102',airline:'easyJet',airplane:'A320',
 registration:'G-WUKU',who:'Matthew'
};
const third={
 id:'3',date:'2025-08-03',from_airport:'LHR',to_airport:'JFK',
 flight_code:'BA117',airline:'British Airways',airplane:'B777',
 registration:'G-OLD (G-EZBH)',who:'Florence'
};
const rows=[first,second,third];

test('same registration search regardless of spaces, hyphen or case',async()=>{
 const {filterFlightRows,flightLogTestHelpers:h}=await exportsPromise;
 for(const q of ['gwuku','g-wuku','G-WUKU','g wuku']){
  assert.deepEqual(filterFlightRows(rows,h.blankFilters(),q).map(r=>r.id),['2','1']);
 }
 assert.deepEqual(filterFlightRows(rows,h.blankFilters(),'g-ezbh').map(r=>r.id),['3']);
});

test('filter sets allow multiple values per category, AND across categories',async()=>{
 const {filterFlightRows,flightLogTestHelpers:h}=await exportsPromise;
 const f=h.blankFilters();
 f.airline=['Wizz Air','easyJet'];
 f.from_airport=['lgw'];
 assert.deepEqual(filterFlightRows(rows,f).map(r=>r.id),['2','1']);
 f.flight_code=['W95776'];
 assert.deepEqual(filterFlightRows(rows,f).map(r=>r.id),['1']);
 f.year=['2026'];
 assert.deepEqual(filterFlightRows(rows,f),[]);
});

test('Who filter splits commas semicolons and newlines, case-insensitively',async()=>{
 const {filterFlightRows,flightLogTestHelpers:h}=await exportsPromise;
 const f=h.blankFilters();
 f.who=['florence'];
 assert.deepEqual(filterFlightRows(rows,f).map(r=>r.id),['1','3']);
 assert.equal(h.normalizeWho(' Matthew;\n Florence, Alice '),'Matthew, Florence, Alice');
 assert.deepEqual(h.uniquePeople(rows),['Florence','Matthew']);
});

test('exact original four filtered statistics and latest-first dates',async()=>{
 const {filterFlightRows,flightLogTestHelpers:h}=await exportsPromise;
 const all=filterFlightRows(rows,h.blankFilters());
 assert.deepEqual(all.map(r=>r.id),['2','1','3']);
 assert.deepEqual(h.stats(all),{flights:3,regs:2,routes:3,years:2});
 const f=h.blankFilters();f.from_airport=['LGW'];
 assert.deepEqual(h.stats(filterFlightRows(rows,f)),{flights:2,regs:1,routes:2,years:2});
});

test('Copy Regs retains source behaviour including parenthetical current reg',async()=>{
 const {filterFlightRows,flightLogTestHelpers:h}=await exportsPromise;
 const all=filterFlightRows(rows,h.blankFilters());
 assert.deepEqual([...new Set(all.map(row=>h.getCurrentRegistration(row.registration)).filter(Boolean))],
                  ['G-WUKU','G-EZBH']);
 assert.equal(h.getCurrentRegistration('G-OLD (G-EZBH)'),'G-EZBH');
});

test('date parser accepts original ISO and DD/MM/YYYY SheetDB values',async()=>{
 const {flightLogTestHelpers:h}=await exportsPromise;
 assert.equal(h.toInputDate('03/08/2025'),'2025-08-03');
 assert.equal(h.toInputDate('2026-01-05'),'2026-01-05');
 assert.equal(h.yearFromRow({date:'03/08/2025'}),'2025');
});

test('new table retains FR24 links, Google Sheets writes, secondary local buttons',()=>{
 assert.match(source,/www\.flightradar24\.com\/data\/aircraft\//);
 assert.match(source,/data-edit-flight/);
 assert.match(source,/data-delete-flight/);
 assert.match(source,/action:'delete'/);
 assert.match(source,/action:selectedFlightId\?'update':'create'/);
 assert.match(source,/\/api\/flights\/records/);
 assert.match(source,/Local aircraft map/);
 assert.match(source,/flights-highlight/);
 assert.match(source,/renderFlightsPage/);
});
