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
function redraw(){
 drawPending=0;
 const node=document.getElementById('live-terminal-screen');
 if(node)node.textContent=grid.map(row=>row.join('').replace(/ +$/,'')).join('\n').replace(/\n+$/,'')||'Waiting for viewadsb…';
}
export function stopLiveTerminal(){
 if(source){source.close();source=null;}
 if(drawPending){cancelAnimationFrame(drawPending);drawPending=0;}
}
export function renderLiveTerminal(){
 stopLiveTerminal();reset();
 document.getElementById('page').innerHTML=
 '<div class="page-heading"><div><h1 class="page-title">Live ADS-B terminal</h1>'+
 '<p class="page-subtitle">The actual Ultrafeeder viewadsb terminal, mirrored directly. Refreshes whenever viewadsb redraws (about every 500 ms).</p></div></div>'+
 '<section class="live-terminal-panel"><div class="live-terminal-top"><span class="live-terminal-led" id="live-terminal-led"></span>'+
 '<strong>ultrafeeder / viewadsb</strong><span id="live-terminal-state">Connecting…</span></div>'+
 '<div class="live-terminal-scroll" role="region" aria-label="Live aircraft terminal" tabindex="0">'+
 '<pre class="live-terminal-screen" id="live-terminal-screen">Connecting to local terminal…</pre></div></section>'+
 '<p class="live-terminal-note">This displays the real read-only terminal rather than a slower copy of aircraft.json. Scroll horizontally on mobile for all columns. The normal viewadsb terminal does not include flight routes.</p>';
 const label=document.getElementById('live-terminal-state'),led=document.getElementById('live-terminal-led');
 const feed=new EventSource('/api/live/terminal');source=feed;
 feed.onopen=()=>{if(source!==feed)return;label.textContent='Connected';led.classList.add('active');};
 feed.onmessage=event=>{if(source!==feed)return;try{ingest(JSON.parse(event.data));if(!drawPending)drawPending=requestAnimationFrame(redraw);}catch{label.textContent='Invalid terminal output';}};
 feed.addEventListener('stopped',event=>{
  if(source!==feed)return;
  feed.close();source=null;led.classList.remove('active');
  let d={};try{d=JSON.parse(event.data);}catch{}
  label.textContent=d.error||'Terminal exited — check Docker permissions';
 });
 feed.onerror=()=>{if(source!==feed)return;led.classList.remove('active');label.textContent='Disconnected — reconnecting';};
}
