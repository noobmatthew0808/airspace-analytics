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

const COLUMNS=[
 ['flight','Flight'],['hex','Hex'],['registration','Reg'],['country','Country'],['route','Route'],
 ['squawk','Squawk'],['alt','Altitude'],['speed','Speed'],['heading','Heading'],
 ['distance','Distance'],['posA','Lat / Dist'],['posB','Lon / Dir'],
 ['rssi','RSSI'],['messages','Messages'],['seen','Seen'],['mode','Mode']
];
const NUMBER_FIELDS=new Set(['alt','speed','heading','distance','posA','posB','rssi','messages','seen']);
let aircraft=[],metadata={},presentation='nice',layout='cards',order='seen',ascending=true;
let metadataTimer=null,metadataRequest=null,fetching=false,lastMetadata=0,fontSize=10;
let distanceHeader=false,permissionDenied=false;
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label=(value,suffix='')=>String(value??'').trim()?safe(value)+suffix:'—';
function parseLine(line){
 const slice=(a,b)=>line.slice(a,b).trim();
 const hex=slice(0,7).replace(/^~/,'').toUpperCase();
 if(!/^[0-9A-F]{6}$/.test(hex)||line.length<48)return null;
 return {hex,mode:slice(8,12),squawk:slice(14,18),flight:slice(20,28),
  alt:slice(29,35),speed:slice(36,40),heading:slice(42,45),
  posA:slice(47,54),posB:slice(55,63),rssi:slice(64,69),
  messages:slice(70,75),seen:slice(78,83)};
}
function parseScreen(lines){
 const strings=lines.map(line=>Array.isArray(line)?line.join(''):String(line));
 const header=strings.find(s=>/\bHex\b.*\bMode\b.*\bSqwk\b/.test(s));
 distanceHeader=Boolean(header&&/\bDist\b/.test(header));
 const seen=new Map();
 for(const line of strings){
  const plane=parseLine(line);if(!plane)continue;
  const previous=seen.get(plane.hex);
  if(!previous || Number(plane.seen||999)<=Number(previous.seen||999))seen.set(plane.hex,plane);
 }
 return [...seen.values()];
}
function record(raw){
 const info=metadata[raw.hex]||{};
 return {...raw,registration:info.registration||'',country:info.country||'',
  type:info.aircraft_type||'',route:info.route||'',
  distance:info.distance_km!==undefined&&info.distance_km!==null
   ?String(info.distance_km):distanceHeader?raw.posA:''};
}
function sorted(list,key=order,direction=ascending?1:-1){
 return [...list].sort((a,b)=>{
  const A=String(a[key]??'').trim(),B=String(b[key]??'').trim();
  if(!A||!B)return (!A&&!B)?a.hex.localeCompare(b.hex):!A?1:-1;
  let delta=NUMBER_FIELDS.has(key)?Number(A)-Number(B):A.localeCompare(B,undefined,{numeric:true});
  if(!Number.isFinite(delta))delta=A.localeCompare(B,undefined,{numeric:true});
  return direction*delta||a.hex.localeCompare(b.hex);
 });
}
function headerNames(){
 return COLUMNS.map(([key,name])=>[key,
  key==='posA'?(distanceHeader?'Terminal distance':'Latitude'):
  key==='posB'?(distanceHeader?'Direction':'Longitude'):name]);
}
function status(text,connected=false){
 const labelEl=document.getElementById('live-terminal-state'),led=document.getElementById('live-terminal-led');
 if(labelEl)labelEl.textContent=text;
 if(led)led.classList.toggle('active',connected);
}
function displayRows(){
 const cards=document.getElementById('live-cards'),table=document.getElementById('live-table-rows');
 const head=document.getElementById('live-table-head'),count=document.getElementById('live-count');
 if(count)count.textContent=aircraft.length+' aircraft';
 if(!cards||!table||!head)return;
 const list=sorted(aircraft.map(record));
 head.innerHTML='<tr>'+headerNames().map(([key,title])=>
  '<th scope="col" aria-sort="'+(order===key?(ascending?'ascending':'descending'):'none')+'">'+
  '<button type="button" data-order="'+key+'" class="live-heading'+(order===key?' selected':'')+'">'+safe(title)+
  (order===key?(ascending?' ↑':' ↓'):'')+'</button></th>').join('')+'</tr>';
 if(!list.length){
  cards.innerHTML='<div class="live-empty">Waiting for aircraft…</div>';
  table.innerHTML='<tr><td class="live-empty" colspan="'+COLUMNS.length+'">Waiting for aircraft…</td></tr>';return;
 }
 cards.innerHTML=list.map(a=>
  '<article class="live-card"><div class="live-card-top"><div><strong>'+label(a.flight||a.registration||a.hex)+'</strong>'+
  '<small>'+label(a.registration||a.hex)+(a.type?' · '+label(a.type):'')+'</small></div>'+
  '<span class="live-age">'+label(a.seen,'s')+' ago</span></div>'+
  '<div class="live-route">'+label(a.route)+'</div>'+
  '<div class="live-card-main"><div><small>Altitude</small><b>'+label(a.alt,' ft')+'</b></div>'+
  '<div><small>Speed</small><b>'+label(a.speed,' kt')+'</b></div>'+
  '<div><small>Distance</small><b>'+label(a.distance, distanceHeader&&a.distance===a.posA?' nmi':' km')+'</b></div></div>'+
  '<div class="live-card-extra"><span>Country <b>'+label(a.country)+'</b></span>'+
  '<span>Squawk <b>'+label(a.squawk)+'</b></span>'+
  '<span>Heading <b>'+label(a.heading,'°')+'</b></span>'+
  '<span>Msgs <b>'+label(a.messages)+'</b></span>'+
  '<span>RSSI <b>'+label(a.rssi,' dB')+'</b></span>'+
  '<span>Hex <b>'+label(a.hex)+'</b></span></div>'+
  '</article>').join('');
 table.innerHTML=list.map(a=>'<tr>'+COLUMNS.map(([key])=>'<td>'+label(a[key])+'</td>').join('')+'</tr>').join('');
}
function displayRaw(){
 const node=document.getElementById('live-terminal-screen');
 if(node)node.textContent=grid.map(row=>row.join('').replace(/ +$/,'')).join('\n').replace(/\n+$/,'')||'Waiting for receiver…';
}
function redraw(){
 drawPending=0;displayRaw();aircraft=parseScreen(grid);
 if(presentation==='nice')displayRows();
 if(aircraft.length&&Date.now()-lastMetadata>6500&&!fetching)refreshMetadata();
}
function chooseSort(key,toggle=true){
 if(!COLUMNS.some(([f])=>f===key))return;
 if(key===order&&toggle)ascending=!ascending;
 else if(key!==order){order=key;ascending=true;}
 const select=document.getElementById('live-sort');
 const dir=document.getElementById('live-direction');
 if(select)select.value=order;
 if(dir)dir.textContent=ascending?'↑ Asc':'↓ Desc';
 displayRows();
}
function showMode(){
 const root=document.getElementById('live-terminal-panel');if(!root)return;
 root.dataset.presentation=presentation;root.dataset.layout=layout;
 root.querySelectorAll('[data-presentation]').forEach(button=>{
  const active=button.dataset.presentation===presentation;
  button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));
 });
 root.querySelectorAll('[data-layout]').forEach(button=>{
  const active=button.dataset.layout===layout;
  button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));
 });
 if(presentation==='nice')displayRows();
}
function closeMetadata(){
 if(metadataTimer){clearInterval(metadataTimer);metadataTimer=null;}
 if(metadataRequest){metadataRequest.abort();metadataRequest=null;}
 fetching=false;
}
export function stopLiveTerminal(){
 if(source){source.close();source=null;}
 if(drawPending){cancelAnimationFrame(drawPending);drawPending=0;}
 closeMetadata();
}
async function refreshMetadata(){
 if(fetching||!aircraft.length||document.hidden||!document.getElementById('live-terminal-panel'))return;
 lastMetadata=Date.now();fetching=true;
 const controller=new AbortController();metadataRequest=controller;
 const items=aircraft.slice(0,100).map(a=>a.hex+':'+a.flight).join(',');
 try{
  const response=await fetch('/api/live/details?items='+encodeURIComponent(items),{signal:controller.signal,cache:'no-store'});
  if(!response.ok)throw Error('details unavailable');
  const data=await response.json();
  if(metadataRequest!==controller)return;
  metadata=data.aircraft||{};
  if(presentation==='nice')displayRows();
 }catch(error){
  // Metadata is optional: do not interrupt the raw terminal if missing.
  if(error.name!=='AbortError')console.warn('Live metadata unavailable');
 }finally{
  if(metadataRequest===controller)metadataRequest=null;
  fetching=false;
 }
}
function connect(){
 if(source||document.hidden||!document.getElementById('live-terminal-panel'))return;
 reset();aircraft=[];metadata={};permissionDenied=false;lastMetadata=0;
 displayRaw();displayRows();status('Connecting…');
 const feed=new EventSource('/api/live/terminal');source=feed;
 feed.onopen=()=>{if(source===feed)status('Connected',true);};
 feed.onmessage=event=>{
  if(source!==feed)return;
  try{
   const chunk=JSON.parse(event.data);
   if(typeof chunk!=='string')return;
   if(/permission denied/i.test(chunk)&&/docker/i.test(chunk)){permissionDenied=true;status('Docker permission denied');}
   ingest(chunk);if(!drawPending)drawPending=requestAnimationFrame(redraw);
  }catch{status('Invalid terminal data');}
 };
 feed.addEventListener('stopped',event=>{
  if(source!==feed)return;
  feed.close();source=null;closeMetadata();
  let data={};try{data=JSON.parse(event.data);}catch{}
  status(permissionDenied?'Docker permission denied — check Linux permissions':data.error||'Terminal exited');
 });
 feed.onerror=()=>{if(source===feed)status('Disconnected — reconnecting');};
 metadataTimer=setInterval(refreshMetadata,8000);
}
document.addEventListener('visibilitychange',()=>{
 if(!document.getElementById('live-terminal-panel'))return;
 if(document.hidden){stopLiveTerminal();status('Paused — tab hidden');}
 else connect();
});
export function renderLiveTerminal(){
 stopLiveTerminal();reset();aircraft=[];metadata={};
 presentation='nice';layout=window.matchMedia('(max-width:700px)').matches?'cards':'table';
 order='seen';ascending=true;fontSize=10;
 document.getElementById('page').innerHTML=
 '<div class="page-heading"><h1 class="page-title">Live ADS-B</h1></div>'+
 '<section id="live-terminal-panel" class="live-terminal-panel">'+
 '<div class="live-terminal-top"><span class="live-terminal-led" id="live-terminal-led"></span>'+
 '<strong>ultrafeeder / viewadsb</strong><span id="live-terminal-state">Connecting…</span>'+
 '<span id="live-count" class="live-count">0 aircraft</span></div>'+
 '<div class="live-toolbar"><div class="live-segment">'+
 '<button type="button" data-presentation="nice">Nice UI</button>'+
 '<button type="button" data-presentation="raw">Raw UI</button></div>'+
 '<div class="live-segment live-layout"><button type="button" data-layout="cards">Cards</button>'+
 '<button type="button" data-layout="table">Table</button></div></div>'+
 '<div class="live-sortbar"><label for="live-sort">Sort by</label>'+
 '<select id="live-sort">'+COLUMNS.map(([key,name])=>'<option value="'+key+'">'+safe(name)+'</option>').join('')+'</select>'+
 '<button type="button" id="live-direction">↑ Asc</button></div>'+
 '<div id="live-cards" class="live-cards"></div>'+
 '<div class="live-table-scroll"><table class="live-table"><thead id="live-table-head"></thead>'+
 '<tbody id="live-table-rows"></tbody></table></div>'+
 '<div class="live-rawbar"><span>Original terminal · swipe sideways</span>'+
 '<button type="button" id="live-smaller" aria-label="Smaller raw text">A−</button>'+
 '<button type="button" id="live-bigger" aria-label="Larger raw text">A+</button></div>'+
 '<div class="live-terminal-scroll" role="region" aria-label="Original viewadsb terminal" tabindex="0">'+
 '<pre class="live-terminal-screen" id="live-terminal-screen">Connecting…</pre></div></section>';
 const panel=document.getElementById('live-terminal-panel');
 panel.addEventListener('click',event=>{
  const view=event.target.closest('[data-presentation]');
  if(view){presentation=view.dataset.presentation;showMode();return;}
  const change=event.target.closest('[data-layout]');
  if(change){layout=change.dataset.layout;showMode();return;}
  const heading=event.target.closest('[data-order]');
  if(heading)chooseSort(heading.dataset.order);
 });
 document.getElementById('live-sort').addEventListener('change',event=>chooseSort(event.target.value,false));
 document.getElementById('live-direction').addEventListener('click',()=>{
  ascending=!ascending;chooseSort(order,false);
 });
 function rawSize(delta){
  fontSize=Math.max(8,Math.min(14,fontSize+delta));
  document.getElementById('live-terminal-screen').style.fontSize=fontSize+'px';
 }
 document.getElementById('live-smaller').onclick=()=>rawSize(-1);
 document.getElementById('live-bigger').onclick=()=>rawSize(1);
 document.getElementById('live-sort').value=order;
 showMode();connect();
}
