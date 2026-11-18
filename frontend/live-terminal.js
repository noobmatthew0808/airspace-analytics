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

/* RAW: render the actual v1.10.10 terminal screen without any alteration.
   NICE: table uses that same stream, plus existing optional metadata.
   Both streams close when the Live page is not in view. */
const COLUMNS=[
 ['hex','Hex ID',7.6],['flight','Callsign',10],['registration','Reg',7.2],
 ['route','Route',11.8],['type','Type',6.6],['squawk','Squawk',6.7],
 ['alt','Alt. (ft)',8],['speed','Spd. (kt)',7],['distance','Dist. (nmi)',9.5],
 ['messages','Messages',7.9],['seen','Seen',5.4],['rssi','RSSI',6.2],
 ['source','Source',6.1]
];
const NUMERIC=new Set(['alt','speed','distance','messages','seen','rssi','squawk']);
let view='nice',aircraft=[],metadata={},sortKey=null,sortAsc=true;
let metadataTimer=null,metadataRequest=null,fetching=false,lastMetadata=0,permissionDenied=false;
let rawLastWidth=0,rawObserver=null,ignoreTapClickUntil=0;
const esc=v=>String(v??'').replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
function parseLine(line){
 const part=(a,b)=>line.slice(a,b).trim();
 const hex=part(0,7).replace(/^~/,'').toUpperCase();
 if(!/^[0-9A-F]{6}$/.test(hex)||line.length<48)return null;
 return {hex,mode:part(8,12),squawk:part(14,18),flight:part(20,28),
  alt:part(29,35),speed:part(36,40),heading:part(42,45),
  posA:part(47,54),posB:part(55,63),rssi:part(64,69),
  messages:part(70,75),seen:part(78,83)};
}
function extractAircraft(){
 // Consume exactly the same terminal frame that is visible in Raw.
 const rows=new Map();
 for(const line of grid){
  const row=parseLine(line.join(''));
  if(!row)continue;
  const existing=rows.get(row.hex);
  if(!existing||Number(row.seen||999)<=Number(existing.seen||999))rows.set(row.hex,row);
 }
 return [...rows.values()];
}
function enrich(raw){
 const data=metadata[raw.hex]||{};
 const km=Number(data.distance_km);
 const nmi=data.distance_km!==undefined&&data.distance_km!==null&&Number.isFinite(km)
   ?(km/1.852).toFixed(1):'';
 return {
  hex:raw.hex,flight:raw.flight,registration:data.registration||'',
  route:data.route||'',type:data.aircraft_type||'',squawk:raw.squawk,
  alt:raw.alt,speed:raw.speed,distance:nmi,
  messages:raw.messages,seen:raw.seen,rssi:raw.rssi,source:data.source||''
 };
}
function sortPlanes(rows,key=sortKey,ascending=sortAsc){
 if(!key)return [...rows];
 const direction=ascending?1:-1;
 return [...rows].sort((left,right)=>{
  const a=String(left[key]??'').trim(),b=String(right[key]??'').trim();
  // Missing values always appear after known values.
  if(!a||!b)return !a&&!b?left.hex.localeCompare(right.hex):!a?1:-1;
  let c;
  if(NUMERIC.has(key)){
   const n=Number(a),m=Number(b);
   c=Number.isFinite(n)&&Number.isFinite(m)?n-m:a.localeCompare(b,undefined,{numeric:true});
  }else c=a.localeCompare(b,undefined,{numeric:true});
  return direction*c||left.hex.localeCompare(right.hex);
 });
}
function value(v){return String(v??'').trim()?esc(v):'—';}
function updateTableHead(){
 const head=document.getElementById('live-nice-head');
 if(!head)return;
 head.innerHTML='<tr>'+COLUMNS.map(([key,title])=>
  '<th scope="col" data-field="'+key+'" data-sort="'+key+'" aria-sort="'+
  (sortKey===key?(sortAsc?'ascending':'descending'):'none')+'">'+
  '<button type="button" class="live-head-button'+(sortKey===key?' chosen':'')+
  '" data-sort="'+key+'" title="Sort by '+esc(title)+'" aria-label="Sort by '+esc(title)+
  (sortKey===key?(sortAsc?', ascending':', descending'):'')+'">'+esc(title)+
  (sortKey===key?(sortAsc?' ↑':' ↓'):'')+'</button></th>').join('')+'</tr>';
}
function updateTableRows(){
 const tbody=document.getElementById('live-nice-rows');
 const count=document.getElementById('live-nice-count');
 if(count)count.textContent=aircraft.length+' aircraft';
 if(!tbody)return;
 const ordered=sortPlanes(aircraft.map(enrich));
 tbody.innerHTML=ordered.length?ordered.map(a=>
  '<tr>'+COLUMNS.map(([key])=>
  '<td data-field="'+key+'" title="'+esc(a[key]||'')+'">'+value(a[key])+'</td>').join('')+'</tr>'
 ).join(''):'<tr><td colspan="13" class="live-nice-empty">Waiting for aircraft…</td></tr>';
}
function chooseSort(key){
 if(!COLUMNS.some(([name])=>name===key))return;
 if(sortKey===key)sortAsc=!sortAsc;
 else{sortKey=key;sortAsc=true;}
 updateTableHead();updateTableRows();
}
function fitRawToScreen(){
 // Keep the REAL untouched PTY text; only scale its font to the container.
 // Need the full 132-column screen? On narrow phones this becomes tiny,
 // but unlike clipping or reflowing it does not lose or misalign any fields.
 const pre=document.getElementById('live-terminal-screen');
 const wrap=document.querySelector('#live-raw .live-terminal-scroll');
 if(!pre||!wrap||view!=='raw')return;
 const width=wrap.clientWidth;
 if(width<20)return;
 pre.style.fontSize='12px';
 // scrollWidth measures the ENTIRE monospace line, even when clipped.
 const content=pre.scrollWidth;
 const ratio=Math.min(1,Math.max(0.1,(width-3)/Math.max(content,1)));
 const size=12*ratio;
 pre.style.fontSize=size.toFixed(2)+'px';
 rawLastWidth=width;
}
function rawRedraw(){
 // Original v1.10.10 frame renderer, including cursor movement and spaces.
 const node=document.getElementById('live-terminal-screen');
 if(node)node.textContent=grid.map(row=>row.join('').replace(/ +$/,'')).join('\n').replace(/\n+$/,'')||'Waiting for viewadsb…';
 fitRawToScreen();
}
function redraw(){
 drawPending=0;
 if(view==='raw'){rawRedraw();return;}
 aircraft=extractAircraft();updateTableRows();
 if(aircraft.length&&Date.now()-lastMetadata>7000&&!fetching)refreshMetadata();
}
function stopMetadata(){
 if(metadataTimer){clearInterval(metadataTimer);metadataTimer=null;}
 if(metadataRequest){metadataRequest.abort();metadataRequest=null;}
 fetching=false;
}
export function stopLiveTerminal(){
 if(source){source.close();source=null;}
 if(drawPending){cancelAnimationFrame(drawPending);drawPending=0;}
 if(rawObserver){rawObserver.disconnect();rawObserver=null;}
 stopMetadata();
}
async function refreshMetadata(){
 if(view!=='nice'||fetching||document.hidden||!aircraft.length||!document.getElementById('live-root'))return;
 fetching=true;lastMetadata=Date.now();
 const controller=new AbortController();metadataRequest=controller;
 const ids=aircraft.slice(0,100).map(a=>a.hex+':'+a.flight).join(',');
 try{
  const response=await fetch('/api/live/details?items='+encodeURIComponent(ids),{
   cache:'no-store',signal:controller.signal
  });
  if(!response.ok)throw Error('Metadata unavailable');
  const data=await response.json();
  if(metadataRequest!==controller)return;
  metadata=data.aircraft||{};
  updateTableRows();
 }catch(error){
  // Extra lookups must never interrupt the real viewadsb feed.
  if(error.name!=='AbortError')console.warn('Live aircraft details unavailable');
 }finally{
  if(metadataRequest===controller)metadataRequest=null;
  fetching=false;
 }
}
function status(message,active=false){
 const label=document.getElementById('live-terminal-state');
 const led=document.getElementById('live-terminal-led');
 if(label)label.textContent=message;
 const nice=document.getElementById('live-nice-state');
 if(nice)nice.textContent=message;
 if(led)led.classList.toggle('active',active);
}
function switchView(mode){
 if(mode!== 'raw'&&mode!=='nice')return;
 view=mode;
 const root=document.getElementById('live-root');
 if(!root)return;
 root.dataset.view=view;
 root.querySelectorAll('[data-view]').forEach(button=>{
  const active=button.dataset.view===view;
  button.classList.toggle('selected',active);
  button.setAttribute('aria-pressed',String(active));
 });
 try{localStorage.setItem('airspace-live-preferred-ui',view);}catch{}
 if(view==='raw'){
  if(metadataRequest){metadataRequest.abort();metadataRequest=null;fetching=false;}
  rawRedraw();
 }else{
  aircraft=extractAircraft();
  updateTableHead();updateTableRows();refreshMetadata();
 }
}
function connect(){
 if(source||document.hidden||!document.getElementById('live-root'))return;
 reset();aircraft=[];metadata={};permissionDenied=false;lastMetadata=0;
 rawRedraw();updateTableRows();status('Connecting…');
 const feed=new EventSource('/api/live/terminal');source=feed;
 feed.onopen=()=>{if(feed===source)status('Connected',true);};
 feed.onmessage=event=>{
  if(feed!==source)return;
  try{
   const chunk=JSON.parse(event.data);
   if(typeof chunk!=='string')return;
   if(/permission denied/i.test(chunk)&&/docker/i.test(chunk)){
    permissionDenied=true;status('Docker permission denied');
   }
   ingest(chunk);
   if(!drawPending)drawPending=requestAnimationFrame(redraw);
  }catch{status('Invalid terminal data');}
 };
 feed.addEventListener('stopped',event=>{
  if(feed!==source)return;
  feed.close();source=null;stopMetadata();
  let message={};try{message=JSON.parse(event.data);}catch{}
  status(permissionDenied?'Docker permission denied — check Linux permissions':message.error||'Terminal exited');
 });
 feed.onerror=()=>{if(feed===source)status('Disconnected — reconnecting');};
 metadataTimer=setInterval(refreshMetadata,8000);
}
document.addEventListener('visibilitychange',()=>{
 if(!document.getElementById('live-root'))return;
 if(document.hidden){stopLiveTerminal();status('Paused — tab hidden');}
 else connect();
});
export function renderLiveTerminal(){
 stopLiveTerminal();reset();aircraft=[];metadata={};sortKey=null;sortAsc=true;
 try{view=localStorage.getItem('airspace-live-preferred-ui')==='raw'?'raw':'nice';}
 catch{view='nice';}
 document.getElementById('page').innerHTML=
 '<div id="live-root" data-view="'+view+'">'+
 '<div class="live-page-title"><h1 class="page-title">Live ADS-B</h1>'+
 '<div class="live-switch" role="group" aria-label="Live aircraft display">'+
 '<button type="button" data-view="raw">Raw UI</button>'+
 '<button type="button" data-view="nice">Pretty UI</button></div></div>'+
 '<section id="live-raw" class="live-terminal-panel">'+
 '<div class="live-terminal-top"><span class="live-terminal-led" id="live-terminal-led"></span>'+
 '<strong>ultrafeeder / viewadsb</strong><span id="live-terminal-state">Connecting…</span></div>'+
 '<div class="live-terminal-scroll" role="region" aria-label="Original viewadsb terminal" tabindex="0">'+
 '<pre id="live-terminal-screen" class="live-terminal-screen">Connecting to local terminal…</pre></div></section>'+
 '<section id="live-nice" class="live-nice-panel">'+
 '<div class="live-nice-top"><span id="live-nice-count">0 aircraft</span><span id="live-nice-state">Connecting…</span></div>'+
 '<div class="live-nice-table-wrap" role="region" aria-label="Live aircraft table">'+
 '<table class="live-nice-table"><colgroup>'+
 COLUMNS.map(([key,,percent])=>'<col data-col="'+key+'" style="width:'+percent+'%">').join('')+
 '</colgroup><thead id="live-nice-head"></thead><tbody id="live-nice-rows"></tbody></table></div>'+
 '</section></div>';
 document.getElementById('live-root').addEventListener('click',event=>{
  const mode=event.target.closest('[data-view]');
  if(mode){switchView(mode.dataset.view);return;}
 });
 const root=document.getElementById('live-root');
 root.querySelectorAll('[data-view]').forEach(button=>{
  const active=button.dataset.view===view;
  button.classList.toggle('selected',active);
  button.setAttribute('aria-pressed',String(active));
 });
 // Make the whole header cell a hit target; react on pointer release for
 // iOS Safari where tiny buttons and live DOM updates can swallow the click.
 const tableHead=document.getElementById('live-nice-head');
 tableHead.addEventListener('pointerup',event=>{
  if(event.pointerType==='mouse')return;
  const heading=event.target.closest('th[data-sort]');
  if(!heading)return;
  event.preventDefault();
  ignoreTapClickUntil=Date.now()+600;
  chooseSort(heading.dataset.sort);
 });
 tableHead.addEventListener('click',event=>{
  if(Date.now()<ignoreTapClickUntil)return;
  const heading=event.target.closest('th[data-sort]');
  if(heading)chooseSort(heading.dataset.sort);
 });
 // The original raw output is untouched; scale only its rendering to the
 // current screen width, including device rotation.
 const wrap=document.querySelector('#live-raw .live-terminal-scroll');
 if(typeof ResizeObserver==='function'){
  rawObserver=new ResizeObserver(()=>{if(view==='raw')fitRawToScreen();});
  rawObserver.observe(wrap);
 }
 updateTableHead();updateTableRows();
 connect();
}
