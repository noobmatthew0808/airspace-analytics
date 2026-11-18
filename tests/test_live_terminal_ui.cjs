const fs=require('fs');
const vm=require('vm');
const code=fs.readFileSync('frontend/live-terminal.js','utf8').replace(/^export /gm,'');
const context={document:{hidden:false,addEventListener(){},getElementById(){return null}},window:{matchMedia:()=>({matches:true})}};
vm.createContext(context);vm.runInContext(code,context);
function ok(test,msg){if(!test)throw Error(msg);}
const sample=' 408345 S     7000  GMILS      2775  128  317   51.000    0.215 -19.6   125    0';
const a=context.parseLine(sample);
ok(a&&a.hex==='408345'&&a.flight==='GMILS'&&a.squawk==='7000','fixed width parsing');
ok(a.alt==='2775'&&a.speed==='128'&&a.heading==='317','flight measurements');
ok(a.rssi==='-19.6'&&a.messages==='125'&&a.seen==='0','signal, messages and age');
ok(context.parseLine(sample.slice(0,20)+'        '+sample.slice(28)).flight==='','blank callsign');
ok(context.parseScreen([sample.split(''),sample.split('')]).length===1,'deduplicate ICAO');
const values=context.sorted([{hex:'AA0001',alt:'1000'},{hex:'AA0002',alt:'5000'},{hex:'AA0003',alt:''}],'alt',-1);
ok(values.map(v=>v.hex).join(',')==='AA0002,AA0001,AA0003','numeric sort missing last');
ok(code.includes("document.addEventListener('visibilitychange'"),'background pause');
ok(code.includes("source.close()"),'stop source');
console.log('Live ADS-B: parser, blank fields, sorting and pause checks passed');
