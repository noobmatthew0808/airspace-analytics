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

test('one-row table keeps FR24, SheetDB editing and optional local aircraft links',()=>{
 assert.match(source,/www\.flightradar24\.com\/data\/aircraft\//);
 assert.match(source,/flightsManageEdit/);
 assert.match(source,/flightsManageDelete/);
 assert.match(source,/action:'delete'/);
 assert.match(source,/action:selectedFlightId\?'update':'create'/);
 assert.match(source,/\/api\/flights\/records/);
 assert.match(source,/Live local map/);
 assert.match(source,/flights-highlight/);
 assert.match(source,/renderFlightsPage/);
});


test('LGW highlight is current flying route only, never historical itinerary',async()=>{
 const {flightStatusTestHelpers:h}=await exportsPromise;
 assert.equal(h.isCurrentGatwick({status:'Flying LGW – VIE',route:'LGW – VIE'}),true);
 assert.equal(h.isCurrentGatwick({status:'Flying VIE – LGW',route:'VIE – LGW'}),true);
 assert.equal(h.isCurrentGatwick({status:'Flying',route:''}),false);
 assert.equal(h.isCurrentGatwick({status:'At LGW',route:'LGW – VIE'}),false);
 assert.equal(h.isCurrentGatwick({status:'N/A',route:'LGW – VIE'}),false);
 assert.doesNotMatch(source,/lgw\(origin\)\|\|lgw\(destination\)/);
});

test('local last-seen is relative and Aerodrome-only, not network hex',async()=>{
 const {flightStatusTestHelpers:h}=await exportsPromise;
 const now=1795200000;
 assert.equal(h.relativeLocalSeen(now-50,now),'Seen just now');
 assert.equal(h.relativeLocalSeen(now-120,now),'Seen 2m ago');
 assert.equal(h.relativeLocalSeen(now-7200,now),'Seen 2h ago');
 assert.equal(h.relativeLocalSeen(now-86400*4,now),'Seen 4d ago');
 assert.equal(h.relativeLocalSeen(null,now),'');
 assert.match(source,/:8000\/aircraft\//);
 assert.match(source,/local_last_seen_at/);
 assert.match(source,/local_hex/);
});

test('one row per flight with visible Who and global Edit/Delete chooser',()=>{
 assert.doesNotMatch(source,/flights-mobile-meta-row/);
 assert.doesNotMatch(source,/flights-details-row/);
 assert.doesNotMatch(source,/data-edit-flight/);
 assert.doesNotMatch(source,/data-delete-flight/);
 assert.match(source,/flights-cell-who/);
 assert.match(source,/flightsManageBar/);
 assert.match(source,/flightsManageEdit/);
 assert.match(source,/flightsManageDelete/);
 assert.match(source,/flights-selectable/);
 assert.doesNotMatch(source,/flightsDatabase/);
 assert.doesNotMatch(source,/flights-source-credit/);
 assert.doesNotMatch(source,/Live from Google Sheets/);
 assert.doesNotMatch(source,/flights-table-bottom/);
 const css=fs.readFileSync('frontend/flights.css','utf8');
 assert.match(css,/\.flights-table \.fc-who\{display:table-column!important/);
 assert.match(css,/\.flights-table \.flights-cell-who\{display:table-cell!important/);
 assert.match(css,/\.flights-table-wrap\{overflow-x:hidden\}/);
 assert.match(source,/flightsDetailsContent/);
});

test('original filtered-reg copy and Google Sheet editing still present',()=>{
 assert.match(source,/filterFlightRows/);
 assert.match(source,/Copy Reg/);
 assert.match(source,/action:selectedFlightId\?'update':'create'/);
 assert.match(source,/action:'delete'/);
 assert.match(source,/getCurrentRegistration/);
});


test('new mobile table is a separate full-width five-column grid with no clipping',async()=>{
 const {flightStatusTestHelpers:h}=await exportsPromise;
 const css=fs.readFileSync('frontend/flights.css','utf8');
 assert.match(source,/<\/section><section class="flights-list"/);
 assert.match(css,/\.flights-table thead tr,\.flights-table tbody tr\.flights-row\{/);
 assert.match(css,/grid-template-columns:15\.5% 20% 14\.5% 28\.5% 21\.5%/);
 assert.match(css,/\.flights-table thead th,\.flights-table tbody tr\.flights-row td\{/);
 assert.match(css,/overflow:hidden!important/);
 assert.match(css,/\.flights-list\{width:calc\(100% \+ 28px\)!important/);
 assert.match(css,/\.flights-who-short\{display:inline!important\}/);
 assert.equal(h.shortWho('Matthew, Florence'),'Matthew +1');
 assert.equal(h.shortWho('Galina'),'Galina');
 assert.equal(h.shortWho('Matthew, Florence, Alice'),'Matthew +2');
});

test('no bold route or registration; highlight only credible current LGW route',async()=>{
 const {flightStatusTestHelpers:h}=await exportsPromise;
 assert.equal(h.isCurrentGatwick({status:'Flying · likely LGW–VIE',
   route:'LGW–VIE',route_confidence:'usual'}),false);
 assert.equal(h.isCurrentGatwick({status:'Flying LGW–VIE',
   route:'LGW–VIE',route_confidence:'plausible'}),true);
 const css=fs.readFileSync('frontend/flights.css','utf8');
 assert.match(css,/\.flights-table \.flights-reg,[\s\S]*?font-weight:400!important/);
 assert.match(css,/\.flights-table \.flights-cell-route\{font-size:11px!important;font-weight:400!important\}/);
});

test('compact display accepts only airport, credible route, Flying or N/A',async()=>{
 const {flightStatusTestHelpers:h}=await exportsPromise;
 assert.equal(h.compactDate('2026-11-25'),'25/11/26');
 assert.equal(h.compactStatus({status:'At LGW',at_airport:'LGW'}),'LGW');
 assert.equal(h.compactStatus({status:'Last landed MAN',at_airport:'MAN'}),'MAN');
 assert.equal(h.compactStatus({status:'Flying LGW – BTS',route:'LGW – BTS',route_confidence:'plausible'}),'LGW-BTS');
 assert.equal(h.compactStatus({status:'Flying · likely LYS–LGW',route:'LYS–LGW',route_confidence:'usual'}),'LYS-LGW');
 assert.equal(h.compactStatus({status:'Ground'}),'N/A');
 assert.match(source,/regLink\+statusBadge\(row\)/);
 assert.match(source,/flights-inline-detail/);
 assert.doesNotMatch(source,/id="flightsDetails"/);
});

test('historical registration display and current registration lookup are separate',async()=>{
 const {flightLogTestHelpers:h}=await exportsPromise;
 assert.equal(h.getCurrentRegistration('G-XLRB (9H-XLI)'),'9H-XLI');
 assert.match(source,/Registration at flight:/);
 assert.match(source,/Current registration:/);
 assert.match(source,/escapeHtml\(historical\)/);
});

test('mobile details span full width and live statuses use fixed aligned columns',()=>{
 const css=fs.readFileSync('frontend/flights.css','utf8');
 assert.match(css,/\.flights-table tbody tr\.flights-inline-detail>td\{display:block!important;width:100%!important;min-width:100%!important;max-width:100%!important/);
 assert.match(css,/grid-template-columns:minmax\(0,1fr\) 8\.2ch/);
 assert.match(source,/Last seen by your receiver/);
 assert.match(source,/lgw\(compactStatus\(liveFor\(row\)\)\)/);
});
