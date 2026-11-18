/* Actual viewadsb PTY bytes. No simulated aircraft data or polling. */
let source=null,drawPending=0;
const ROWS=42,COLS=132;
let grid,y,x,saveY,saveX,mode,escapeCode,boxMode;
const BOX={q:'─',x:'│',l:'┌',k:'┐',m:'└',j:'┘',n:'┼',t:'├',u:'┤',w:'┬',v:'┴'};
function blank(){return Array(COLS).fill(' ');}
function reset(){grid=Array.from({length:ROWS},blank);y=0;x=0;saveY=0;saveX=0;mode='normal';escapeCode='';boxMode=false;}
function limit(n,hi){return Math.min(hi,Math.max(0,n));}
function escapeCommand(cmd){
 const a=escapeCode.replace(/^[?>]/,'').split(';').map(s=>Number(s)||0),p=a[0]||1,q=a[1]||1;
 if(cmd==='H'||cmd==='f'){y=limit(p-1,ROWS-1);x=limit(q-1,COLS-1);}
 else if(cmd==='A')y=limit(y-p,ROWS-1);
 else if(cmd==='B')y=limit(y+p,ROWS-1);
 else if(cmd==='C')x=limit(x+p,COLS-1);
 else if(cmd==='D')x=limit(x-p,COLS-1);
 else if(cmd==='G')x=limit(p-1,COLS-1);
 else if(cmd==='d')y=limit(p-1,ROWS-1);
 else if(cmd==='J'){
   if(a[0]===2||a[0]===3)grid=Array.from({length:ROWS},blank);
   else if(a[0]===1){for(let row=0;row<=y;row++)for(let col=0;col<(row===y?x+1:COLS);col++)grid[row][col]=' ';}
   else for(let row=y;row<ROWS;row++)for(let col=(row===y?x:0);col<COLS;col++)grid[row][col]=' ';
 }else if(cmd==='K'){
   const low=a[0]===1||a[0]===2?0:x,high=a[0]===1?x+1:COLS;
   for(let col=low;col<high;col++)grid[y][col]=' ';
 }else if(cmd==='s'){saveY=y;saveX=x;}
 else if(cmd==='u'){y=saveY;x=saveX;}
 else if(cmd==='h'&&escapeCode.includes('1049'))grid=Array.from({length:ROWS},blank);
}
function char(c){
 if(x>=COLS){x=0;y++;}
 if(y>=ROWS){grid.shift();grid.push(blank());y=ROWS-1;}
 grid[y][x++]=boxMode?(BOX[c]||c):c;
}
function ingest(s){
 for(const c of s){
  if(mode==='esc'){
   if(c==='['){mode='csi';escapeCode='';}
   else if(c==='('||c===')')mode='charset';
   else{if(c==='7'){saveY=y;saveX=x;}else if(c==='8'){y=saveY;x=saveX;}else if(c==='c')reset();mode='normal';}
   continue;
  }
  if(mode==='charset'){boxMode=c==='0';mode='normal';continue;}
  if(mode==='csi'){
   if(c>='@'&&c<='~'){escapeCommand(c);mode='normal';escapeCode='';}
   else if(escapeCode.length<48)escapeCode+=c;
   else mode='normal';
   continue;
  }
  if(c==='\x1b'){mode='esc';continue;}
  if(c==='\r'){x=0;continue;}
  if(c==='\n'){y++;if(y>=ROWS){grid.shift();grid.push(blank());y=ROWS-1;}continue;}
  if(c==='\b'){x=Math.max(0,x-1);continue;}
  if(c==='\x0e'){boxMode=true;continue;}
  if(c==='\x0f'){boxMode=false;continue;}
  if(c==='\t'){do{char(' ');}while(x%8&&x<COLS);continue;}
  if(c>=' ')char(c);
 }
}


// Raw remains the real viewadsb feed. Nice displays the SAME screen data
// with optional read-only Aerodrome and readsb enrichment.
const RAW_COLUMNS=[
 ['hex','Hex'],['mode','Mode'],['squawk','Sqwk'],['flight','Flight'],
 ['alt','Alt'],['speed','Spd'],['heading','Hdg'],['posA','Dist / Lat'],
 ['posB','Dir / Lon'],['rssi','RSSI'],['messages','Msgs'],['seen','Seen']
];
const NICE_COLUMNS=[
 ['flight','Flight'],['type','Aircraft type'],['route','Route'],
 ['alt','Altitude'],['distance','Distance'],['seen','Seen'],
 ['registration','Registration'],['country','Country'],['hex','Hex'],
 ['squawk','Squawk'],['speed','Speed'],['heading','Heading'],
 ['messages','Messages'],['rssi','RSSI'],['mode','Mode'],['posA','Lat / Dist'],['posB','Lon / Dir']
];
const NUMERIC=new Set(['alt','speed','heading','distance','posA','posB','rssi','messages','seen']);
const RAW_FIT=new Set(['hex','flight','alt','posA','messages','seen']);
const NICE_FIT=new Set(['flight','type','route','alt','distance','seen']);
let aircraft=[],metadata={},presentation='raw',mobileColumns='fit',sortKey='native',sortAsc=true;
let metadataTimer=null,metadataRequest=null,fetching=false,lastMetadata=0;
let distanceHeader=false,permissionDenied=false;
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=(value)=>String(value??'').trim()?safe(value):'—';
function parseLine(line){
 const part=(a,b)=>line.slice(a,b).trim();
 const hex=part(0,7).replace(/^~/,'').toUpperCase();
 if(!/^[0-9A-F]{6}$/.test(hex)||line.length<48)return null;
 return {hex,mode:part(8,12),squawk:part(14,18),flight:part(20,28),
  alt:part(29,35),speed:part(36,40),heading:part(42,45),
  posA:part(47,54),posB:part(55,63),rssi:part(64,69),
  messages:part(70,75),seen:part(78,83)};
}
function parseScreen(screen){
 const lines=screen.map(row=>Array.isArray(row)?row.join(''):String(row));
 const header=lines.find(row=>/\bHex\b.*\bMode\b.*\bSqwk\b/.test(row));
 distanceHeader=Boolean(header&&/\bDist\b/.test(header));
 const found=new Map();
 for(const line of lines){
  const row=parseLine(line);
  if(!row)continue;
  const existing=found.get(row.hex);
  if(!existing||Number(row.seen||999)<=Number(existing.seen||999))found.set(row.hex,row);
 }
 return [...found.values()];
}
function enhanced(row){
 const info=metadata[row.hex]||{};
 return {...row,
  type:info.aircraft_type||'',
  registration:info.registration||'',
  country:info.country||'',
  route:info.route||'',
  distance:info.distance_km!==undefined&&info.distance_km!==null?
    String(info.distance_km):distanceHeader?row.posA:''
 };
}
function sortAircraft(list,key=sortKey,ascending=sortAsc){
 if(key==='native')return [...list];
 return [...list].sort((a,b)=>{
  const left=String(a[key]??'').trim(),right=String(b[key]??'').trim();
  if(!left||!right)return !left&&!right?a.hex.localeCompare(b.hex):!left?1:-1;
  let compare;
  if(NUMERIC.has(key)){
   const x=Number(left),y=Number(right);
   compare=Number.isFinite(x)&&Number.isFinite(y)?x-y:left.localeCompare(right,undefined,{numeric:true});
  }else compare=left.localeCompare(right,undefined,{numeric:true});
  return (ascending?1:-1)*compare||a.hex.localeCompare(b.hex);
 });
}
function columns(){
 const raw=presentation==='raw',fields=raw?RAW_COLUMNS:NICE_COLUMNS;
 return fields.map(([key,name])=>[key,
  key==='posA'?(distanceHeader?(raw?'Dist':'Terminal distance'):'Latitude'):
  key==='posB'?(distanceHeader?(raw?'Dir':'Receiver direction'):'Longitude'):name]);
}
function phoneName(key,name){
 const compact={type:'Type',alt:'Alt',distance:'Dist',registration:'Reg',messages:'Msgs',heading:'Hdg'};
 return compact[key]||name;
}
function status(message,connected=false){
 const node=document.getElementById('live-terminal-state');
 const led=document.getElementById('live-terminal-led');
 if(node)node.textContent=message;
 if(led)led.classList.toggle('active',connected);
}
function paint(){
 const head=document.getElementById('live-table-head');
 const body=document.getElementById('live-table-body');
 const count=document.getElementById('live-count');
 if(count)count.textContent=aircraft.length+' aircraft';
 if(!head||!body)return;
 const raw=presentation==='raw',visible=columns(),fit=raw?RAW_FIT:NICE_FIT;
 const list=sortAircraft(raw?aircraft:aircraft.map(enhanced));
 head.innerHTML='<tr>'+visible.map(([key,name])=>
  '<th scope="col" data-col="'+safe(key)+'" class="'+(fit.has(key)?'':'live-mobile-hidden')+'" aria-sort="'+
    (sortKey===key?(sortAsc?'ascending':'descending'):'none')+'">'+
   '<button type="button" class="live-heading'+(sortKey===key?' selected':'')+'" data-sort="'+safe(key)+'" aria-label="Sort by '+safe(name)+'">'+
    '<span class="live-long-label">'+safe(name)+'</span><span class="live-short-label">'+safe(phoneName(key,name))+'</span>'+
    (sortKey===key?(sortAsc?' ↑':' ↓'):'')+'</button></th>').join('')+'</tr>';
 if(!list.length){
  body.innerHTML='<tr><td class="live-empty" colspan="'+visible.length+'">Waiting for aircraft…</td></tr>';
  return;
 }
 body.innerHTML=list.map(row=>'<tr>'+visible.map(([key])=>
  '<td class="'+(fit.has(key)?'':'live-mobile-hidden')+'" data-col="'+safe(key)+'" title="'+safe(row[key]??'')+'">'+
   label(row[key])+'</td>').join('')+'</tr>').join('');
}
function renderSortSelect(){
 const select=document.getElementById('live-sort');
 if(!select)return;
 select.innerHTML='<option value="native">Receiver order</option>'+
  columns().map(([key,name])=>'<option value="'+safe(key)+'">'+safe(name)+'</option>').join('');
 select.value=sortKey;
 const direction=document.getElementById('live-direction');
 if(direction)direction.textContent=sortAsc?'↑ Ascending':'↓ Descending';
}
function chooseSort(key,toggle=true){
 const valid=columns().some(([field])=>field===key);
 if(key!=='native'&&!valid)return;
 if(key===sortKey&&toggle&&key!=='native')sortAsc=!sortAsc;
 else if(key!==sortKey){sortKey=key;sortAsc=true;}
 renderSortSelect();paint();
}
function showMode(){
 const root=document.getElementById('live-terminal-panel');
 if(!root)return;
 root.dataset.presentation=presentation;
 root.dataset.columns=mobileColumns;
 const valid=columns().some(([key])=>key===sortKey);
 if(sortKey!=='native'&&!valid){sortKey='native';sortAsc=true;}
 root.querySelectorAll('[data-presentation]').forEach(button=>{
  const active=button.dataset.presentation===presentation;
  button.classList.toggle('selected',active);
  button.setAttribute('aria-pressed',String(active));
 });
 root.querySelectorAll('[data-columns]').forEach(button=>{
  const active=button.dataset.columns===mobileColumns;
  button.classList.toggle('selected',active);
  button.setAttribute('aria-pressed',String(active));
 });
 renderSortSelect();paint();
 if(presentation==='nice')refreshMetadata();
}
function redraw(){
 drawPending=0;aircraft=parseScreen(grid);paint();
 if(presentation==='nice'&&aircraft.length&&Date.now()-lastMetadata>6500&&!fetching)refreshMetadata();
}
function stopMetadata(){
 if(metadataTimer){clearInterval(metadataTimer);metadataTimer=null;}
 if(metadataRequest){metadataRequest.abort();metadataRequest=null;}
 fetching=false;
}
export function stopLiveTerminal(){
 if(source){source.close();source=null;}
 if(drawPending){cancelAnimationFrame(drawPending);drawPending=0;}
 stopMetadata();
}
async function refreshMetadata(){
 if(presentation!=='nice'||fetching||!aircraft.length||document.hidden||!document.getElementById('live-terminal-panel'))return;
 fetching=true;lastMetadata=Date.now();
 const controller=new AbortController();metadataRequest=controller;
 const request=aircraft.slice(0,100).map(a=>a.hex+':'+a.flight).join(',');
 try{
  const response=await fetch('/api/live/details?items='+encodeURIComponent(request),{signal:controller.signal,cache:'no-store'});
  if(!response.ok)throw Error('Metadata temporarily unavailable');
  const data=await response.json();
  if(metadataRequest!==controller)return;
  metadata=data.aircraft||{};
  paint();
 }catch(error){
  if(error.name!=='AbortError')console.warn('Live ADS-B enrichment unavailable');
 }finally{
  if(metadataRequest===controller)metadataRequest=null;
  fetching=false;
 }
}
function connect(){
 if(source||document.hidden||!document.getElementById('live-terminal-panel'))return;
 reset();aircraft=[];metadata={};permissionDenied=false;lastMetadata=0;
 paint();status('Connecting…');
 const current=new EventSource('/api/live/terminal');source=current;
 current.onopen=()=>{if(source===current)status('Connected',true);};
 current.onmessage=event=>{
  if(source!==current)return;
  try{
   const chunk=JSON.parse(event.data);
   if(typeof chunk!=='string')return;
   if(/permission denied/i.test(chunk)&&/docker/i.test(chunk)){
    permissionDenied=true;status('Docker permission denied');
   }
   ingest(chunk);
   if(!drawPending)drawPending=requestAnimationFrame(redraw);
  }catch{status('Unrecognised terminal data');}
 };
 current.addEventListener('stopped',event=>{
  if(source!==current)return;
  current.close();source=null;stopMetadata();
  let message={};try{message=JSON.parse(event.data);}catch{}
  status(permissionDenied?'Docker permission denied — check Linux permissions':message.error||'Terminal stopped');
 });
 current.onerror=()=>{if(source===current)status('Disconnected — reconnecting');};
 metadataTimer=setInterval(refreshMetadata,8000);
}
document.addEventListener('visibilitychange',()=>{
 if(!document.getElementById('live-terminal-panel'))return;
 if(document.hidden){stopLiveTerminal();status('Paused — tab hidden');}
 else connect();
});
export function renderLiveTerminal(){
 stopLiveTerminal();reset();aircraft=[];metadata={};
 presentation='raw';mobileColumns='fit';sortKey='native';sortAsc=true;
 document.getElementById('page').innerHTML=
 '<div class="page-heading"><h1 class="page-title">Live ADS-B</h1></div>'+
 '<section id="live-terminal-panel" class="live-terminal-panel">'+
 '<div class="live-terminal-top"><span class="live-terminal-led" id="live-terminal-led"></span>'+
 '<strong>ultrafeeder / viewadsb</strong><span id="live-terminal-state">Connecting…</span>'+
 '<span class="live-count" id="live-count">0 aircraft</span></div>'+
 '<div class="live-toolbar"><div class="live-segment" role="group" aria-label="Aircraft table style">'+
 '<button type="button" data-presentation="raw">Raw</button>'+
 '<button type="button" data-presentation="nice">Nice</button></div>'+
 '<div class="live-segment live-columns" role="group" aria-label="Visible columns">'+
 '<button type="button" data-columns="fit">Fit screen</button>'+
 '<button type="button" data-columns="all">All columns</button></div></div>'+
 '<div class="live-sortbar"><label for="live-sort">Sort</label>'+
 '<select id="live-sort"><option value="native">Receiver order</option></select>'+
 '<button type="button" id="live-direction">↑ Ascending</button></div>'+
 '<div class="live-table-scroll" tabindex="0" role="region" aria-label="Live aircraft list">'+
 '<table class="live-table"><thead id="live-table-head"></thead>'+
 '<tbody id="live-table-body"></tbody></table></div></section>';
 const panel=document.getElementById('live-terminal-panel');
 panel.addEventListener('click',event=>{
  const mode=event.target.closest('[data-presentation]');
  if(mode){presentation=mode.dataset.presentation;showMode();return;}
  const width=event.target.closest('[data-columns]');
  if(width){mobileColumns=width.dataset.columns;showMode();return;}
  const heading=event.target.closest('[data-sort]');
  if(heading)chooseSort(heading.dataset.sort);
 });
 document.getElementById('live-sort').addEventListener('change',event=>chooseSort(event.target.value,false));
 document.getElementById('live-direction').addEventListener('click',()=>{
  if(sortKey==='native')return;
  sortAsc=!sortAsc;chooseSort(sortKey,false);
 });
 showMode();connect();
}
