const fs=require('fs'),vm=require('vm');
const code=fs.readFileSync('frontend/live-terminal.js','utf8').replace(/^export /gm,'');
const css=fs.readFileSync('frontend/live-terminal.css','utf8');
const context={
 document:{hidden:false,addEventListener(){},getElementById(){return null}},
 window:{matchMedia:()=>({matches:true})}
};
vm.createContext(context);vm.runInContext(code,context);
function ok(value,message){if(!value)throw Error(message);}
const sample=' 408345 S     7000  GMILS      2775  128  317   51.000    0.215 -19.6   125    0';
const a=context.parseLine(sample);
ok(a&&a.hex==='408345'&&a.flight==='GMILS'&&a.squawk==='7000','fixed width parser');
ok(a.alt==='2775'&&a.speed==='128'&&a.heading==='317','flight figures');
ok(a.rssi==='-19.6'&&a.messages==='125'&&a.seen==='0','signal/messages/age');
ok(context.parseLine(sample.slice(0,20)+'        '+sample.slice(28)).flight==='','blank callsign');
ok(context.parseScreen([sample.split(''),sample.split('')]).length===1,'duplicate hex');
const raw=vm.runInContext('RAW_COLUMNS',context),nice=vm.runInContext('NICE_COLUMNS',context);
const fitRaw=vm.runInContext('RAW_FIT',context),fitNice=vm.runInContext('NICE_FIT',context);
ok(raw.length===12,'Raw table uses original 12 columns');
ok(nice.some(([key,title])=>key==='type'&&title==='Aircraft type'),'Nice aircraft type heading');
ok(nice.some(([key])=>key==='route'),'Nice IATA route column');
ok(nice.some(([key])=>key==='registration')&&nice.some(([key])=>key==='country'),'extra details');
ok(fitRaw.size===6&&fitNice.size===6,'six columns automatically fit phones');
ok(fitNice.has('type'),'aircraft type included in mobile fitting view');
const rows=[
 {hex:'AA0001',alt:'1000',type:'B789'},{hex:'AA0002',alt:'5000',type:'A320'},
 {hex:'AA0003',alt:'',type:''}
];
ok(context.sortAircraft(rows,'alt',false).map(r=>r.hex).join(',')==='AA0002,AA0001,AA0003','numeric descending, unknown last');
ok(context.sortAircraft(rows,'type',true).map(r=>r.hex).join(',')==='AA0002,AA0001,AA0003','aircraft type ascending, unknown last');
vm.runInContext("presentation='nice';",context);
context.chooseSort('type');
ok(vm.runInContext('sortKey==="type"&&sortAsc===true',context),'aircraft type ascending on first click');
context.chooseSort('type');
ok(vm.runInContext('sortKey==="type"&&sortAsc===false',context),'aircraft type descending on second click');
vm.runInContext("presentation='raw';sortKey='native';",context);
context.chooseSort('messages');
ok(vm.runInContext('sortKey==="messages"&&sortAsc===true',context),'Raw messages sortable');
ok(code.includes("document.addEventListener('visibilitychange'"),'disconnect on hidden browser tab');
ok(code.includes('source.close()'),'close on navigation');
ok(!code.includes('live-cards')&&!css.includes('.live-card{'),'No card UI');
ok(!code.includes('live-smaller')&&!code.includes('live-bigger'),'No manual font sizing');
ok(css.includes('[data-columns="fit"] .live-mobile-hidden{display:none}'),'responsive mobile table');
ok(css.includes('table-layout:fixed'),'mobile viewport fitting');
console.log('Live ADS-B Raw/Nice responsive tables, parsing, sorting, mobile fitting and lifecycle passed');
