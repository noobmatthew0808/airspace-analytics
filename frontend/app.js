/* Airspace Analytics: dependency-free, responsive client for Aerodrome's read-only API. */
const $ = (q, root=document)=>root.querySelector(q);
const $$ = (q, root=document)=>[...root.querySelectorAll(q)];
const NL = '\n';
const esc = s => String(s??'').replace(/[&<>"']/g, x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const fmt = (n,d=0)=>Number(n||0).toLocaleString('en-GB',{maximumFractionDigits:d});
const pct=(a,b)=>b?`${fmt(a/b*100,1)}%`:'—';
const when=(ts,opts={})=>ts?new Date(ts*1000).toLocaleString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',...opts}):'Not recorded';
const bytes=n=>!n?'0 B':n<1024**2?`${fmt(n/1024,0)} KB`:n<1024**3?`${fmt(n/1024**2,1)} MB`:`${fmt(n/1024**3,2)} GB`;
const short=(t,n=35)=>String(t??'—').length>n?String(t).slice(0,n-1)+'…':String(t??'—');
const loading=(label='Analysing your receiver history…')=>`<div class="loading"><span class="spinner"></span>${esc(label)}</div>`;
const safeError=e=>`<div class="notice error-note"><strong>Couldn't load this view.</strong> ${esc(e.message||e)} <a class="btn small" href="#home">Return home</a></div>`;
const key='airspace-analytics-prefs-v1';
const defaults={metric:'flights',period:'all',bucket:'auto',category:'all',type:'all',airline:'all',icao:'all',amount:7,unit:'days',start:'',end:'',chart:'bar',theme:'dark',breakdownViz:'bars',operatorScope:'airline'};
const state={...defaults,...readPrefs()};
// Convert old preset preferences to the new single duration picker. A preset
// never reappears as a confusing legacy dropdown after an update.
if(!['rolling','custom','all'].includes(state.period)){
 const previous={last_24h:[24,'hours'],last_7d:[7,'days'],last_30d:[30,'days'],last_90d:[90,'days'],last_365d:[365,'days']};
 const chosen=previous[state.period]||[7,'days'];
 state.period='rolling';state.amount=chosen[0];state.unit=chosen[1];
 try{localStorage.setItem(key,JSON.stringify(state))}catch{}
}

function readPrefs(){try {return JSON.parse(localStorage.getItem(key))||{}}catch{return {}}}
function persist(){localStorage.setItem(key,JSON.stringify(state))}
// A previously paired browser stays paired across reloads without showing a
// password box each time. The updater's server-side token check remains active.
const pairedUpdaterKey='airspace-updater-pairing';
try {
 const old=sessionStorage.getItem('airspace-token');
 if(old&&!localStorage.getItem(pairedUpdaterKey))localStorage.setItem(pairedUpdaterKey,old);
} catch {}

const defaultLinks=[
  {name:'ADSB.im',sub:'Receiver controls',path:'/',color:'aqua',icon:'radar'},
  {name:'Aerodrome',sub:'History & records',port:'8000',path:'/',color:'blue',icon:'plane'},
  {name:'SkyStats',sub:'Flight statistics',port:'5173',path:'/',color:'pink',icon:'chart'},
  {name:'Aircraft map',sub:'Readsb live map',port:'1099',path:'/',color:'aqua',icon:'map'},
  {name:'Receiver graphs',sub:'Signal & coverage',port:'1094',path:'/',color:'orange',icon:'activity'},
  {name:'Dozzle',sub:'Container logs',port:'',path:'/',color:'blue',icon:'terminal'}
];
function getLinks(){try{const x=JSON.parse(localStorage.getItem('airspace-analytics-links'));return Array.isArray(x)?x:defaultLinks}catch{return defaultLinks}}
function putLinks(links){localStorage.setItem('airspace-analytics-links',JSON.stringify(links))}
function icon(name,size=18){
 const paths={
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.4"/><rect x="14" y="3" width="7" height="7" rx="1.4"/><rect x="3" y="14" width="7" height="7" rx="1.4"/><rect x="14" y="14" width="7" height="7" rx="1.4"/>',
  radar:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12l7-7"/><circle cx="16" cy="8" r="1" fill="currentColor"/>',
  chart:'<path d="M3 3v18h18"/><path d="m6 16 5-6 4 3 5-8"/>',
  activity:'<path d="M2 12h4l3-8 5 16 3-8h5"/>',
  layers:'<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M4 10h16M10 4v16"/>',
  compare:'<path d="M3 5h8v14H3zM13 5h8v14h-8z"/><path d="m6 13 2-3 2 2m5 2 2-4 2 1"/>',
  plane:'<path d="M21 3 3 10l7 3 3 7 8-17ZM10 13l5-5"/>',
  database:'<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
  settings:'<path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/><circle cx="12" cy="12" r="5"/>',
  external:'<path d="M13 5h6v6m0-6-9 9"/><path d="M19 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4"/>',
  chevron:'<path d="m9 18 6-6-6-6"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
  search:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
  menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
  refresh:'<path d="M20 12a8 8 0 0 1-14 5M4 12A8 8 0 0 1 18 7M4 17v-5h5m6-5h5V2"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  bookmark:'<path d="M5 3h14v18l-7-4-7 4V3Z"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  bars:'<path d="M5 20v-9m7 9V4m7 16v-6"/>',
  list:'<path d="M4 6h16M4 12h16M4 18h16"/>',
  eye:'<path d="M2 12c2.5-4 5.8-6 10-6s7.5 2 10 6c-2.5 4-5.8 6-10 6S4.5 16 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  upload:'<path d="M12 16V4m-5 5 5-5 5 5M4 18v3h16v-3"/>',
  map:'<path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5ZM9 3v16m6-14v16"/>',
  terminal:'<rect x="2" y="3" width="20" height="18" rx="2"/><path d="m6 8 4 4-4 4m6 0h6"/>',
  shield:'<path d="m12 2 9 4v6c0 5-4 9-9 10-5-1-9-5-9-10V6l9-4Z"/><path d="m8 12 3 3 5-6"/>',
  alert:'<path d="M12 3 2 21h20L12 3Zm0 6v5m0 3v1"/>',
  moon:'<path d="M20 15A8 8 0 0 1 9 4 8 8 0 1 0 20 15Z"/>',
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M19 5l-2 2M7 17l-2 2"/>'
 };
 return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.grid}</svg>`;
}
const pages=[['explore','Traffic','chart'],['aircraft','Aircraft','plane'],['database','Database','database'],['settings','Settings','settings']];
const names={home:'Launcher',...Object.fromEntries(pages.map(x=>[x[0],x[1]]))};
let currentPage='home',currentChart='line',currentAnalytics=null,latestOverview=null,healthInfo=null,activeTimer=null,renderId=0;
const zoomHistory=[];
let drill={level:'year',mode:'all',start:'',end:'',amount:7,unit:'days',trail:[]};
let firstRecordedLocal=null;
function setTheme(theme){document.documentElement.dataset.theme=theme||'dark';state.theme=theme;persist()}
setTheme(state.theme);

function shell(){
 $('#app').innerHTML=`<div class="overlay" id="overlay"></div><div class="layout">
   <aside class="sidebar" id="sidebar">
     <a class="brand" href="/" aria-label="Open launcher"><span class="logo">${icon('radar',21)}</span><span><strong>Airspace</strong><small>Analytics</small></span></a>
     <nav class="nav-list" aria-label="Analytics sections">${pages.map(nav).join('')}</nav>
     
     <div class="sidebar-bottom"><div class="sidebar-status"><div class="status-row"><i class="dot" id="sidebarDot"></i><strong class="status-label" id="sidebarTitle">Checking data source</strong></div><p id="sidebarDetail">Aerodrome</p></div><div class="version"><span class="versionValue">v1.4.0</span> · Local database</div></div>
   </aside>
   <div class="workspace"><header class="topbar"><div class="topbar-left"><button class="icon-button mobile-menu" id="mobileMenu" aria-label="Open menu">${icon('menu')}</button><a class="top-back" href="/">${icon('grid',16)} <span>Launcher</span></a><span class="top-separator">/</span><strong id="topTitle">Explore</strong></div><div class="top-actions"><span class="top-live"><i class="dot" id="topDot"></i><span id="topStatus">Connecting</span></span><button class="icon-button" id="themeButton" title="Toggle dark/light mode" aria-label="Toggle theme">${icon('sun')}</button></div></header>
   <main class="content" id="page" aria-live="polite"></main></div>
 </div>
 <nav class="mobile-tabbar" id="mobileTabs"><a href="/" data-page="home">${icon('grid',20)}<span>Home</span></a>${[['explore','Traffic','chart'],['aircraft','Aircraft','plane'],['database','Database','database'],['settings','Settings','settings']].map(([id,label,ic])=>`<a href="#${id}" data-page="${id}">${icon(ic,20)}<span>${label}</span></a>`).join('')}</nav>
 <div class="toast-wrap" id="toasts" role="status" aria-live="polite"></div>`;
 $('#mobileMenu').onclick=()=>setMenu(true);
 $('#overlay').onclick=()=>setMenu(false);
 $('#themeButton').onclick=()=>setTheme(state.theme==='dark'?'light':'dark');
}
function nav([id,title,ic]){return `<a class="nav-link" href="#${id}" data-page="${id}">${icon(ic)}<span>${title}</span></a>`}
function setMenu(open){$('#sidebar').classList.toggle('open',open);$('#overlay').classList.toggle('show',open)}
function toast(title,msg='',bad=false){const x=document.createElement('div');x.className='toast'+(bad?' bad':'');x.innerHTML=`<strong>${esc(title)}</strong>${esc(msg)}`;$('#toasts').append(x);setTimeout(()=>x.remove(),5200)}
function setStatus(h){healthInfo=h;const good=h?.fresh===true;const msg=good?'Aerodrome connected':h?.ok?'Data may be delayed':'Database unavailable';for(const id of ['sidebarDot','topDot']){$('#'+id).classList.toggle('good',good);$('#'+id).classList.toggle('bad',!!h&&!good)}$('#sidebarTitle').textContent=msg;$('#topStatus').textContent=good?'Data updating':'Check data';$('#sidebarDetail').textContent=h?.last_sighting?`Latest observation: ${when(h.last_sighting)}`:'Read-only historical data connection';}
async function api(path,params={}){const url=new URL(path,location.origin);Object.entries(params).forEach(([k,v])=>{if(v!==null&&v!==undefined&&v!=='')url.searchParams.set(k,String(v))});const res=await fetch(url,{cache:'no-store'});let d;try{d=await res.json()}catch{throw Error('The local website is unavailable.')};if(!res.ok)throw Error(d.error||'Request failed');return d}
const timerDate=(d)=>d?d:new Date().toISOString().slice(0,16);
function title(eyebrow,heading,subtitle='',accessory=''){return `<div class="page-heading"><div><h1 class="page-title">${esc(heading)}</h1>${subtitle&&currentPage!=='explore'?`<p class="page-subtitle">${subtitle}</p>`:''}</div>${accessory}</div>`}
function stat(label,value,meta,ic='chart'){return `<article class="stat-card"><div class="stat-label"><span>${esc(label)}</span><span class="stat-icon">${icon(ic)}</span></div><div class="stat-value">${value}</div><div class="stat-meta">${meta}</div></article>`}
function section(h,sub='',right=''){return `<div class="section-heading"><div><h2>${h}</h2>${sub?`<p>${sub}</p>`:''}</div>${right}</div>`}
function links(){return getLinks().map((it,i)=>{const destination=hrefFor(it);return `<${destination?'a':'div'} class="launcher-link ${destination?'':'disabled'}" ${destination?`href="${esc(destination)}" target="_blank" rel="noopener noreferrer"`:''}>
  <span class="launcher-link-icon">${icon(it.icon||'external',19)}</span><span class="launcher-link-text"><strong>${esc(it.name)}</strong><small>${esc(destination?it.sub||'Open application':'Set a port or URL in Settings')}</small></span><span class="launcher-link-arrow">${destination?icon('external',16):'—'}</span></${destination?'a':'div'}>`}).join('')}
function hrefFor(link){const host=location.hostname;const proto=location.protocol==='https:'?'https:':'http:';const path=String(link.path||'/');if(link.url){try{const u=new URL(link.url);if(!['http:','https:'].includes(u.protocol))return null;return u.href}catch{return null}}
 if(link.port===''||link.port===null)return null;
 const port=link.port?':'+link.port:'';
 return `${proto}//${host}${port}${path.startsWith('/')?path:'/'+path}`;
}
async function renderHome(){
 $('#page').innerHTML=`<div class="launcher-screen"><header class="launcher-header"><div class="launcher-brand"><span class="launcher-brand-icon">${icon('radar',24)}</span><div><h1>Airspace</h1><span>Application launcher</span></div></div><a class="launcher-settings" href="/analytics#settings" title="Edit links in Settings" aria-label="Settings">${icon('settings',19)}</a></header>
 <div class="launcher-list"><a class="launcher-link launcher-primary" href="/analytics#explore"><span class="launcher-link-icon">${icon('chart',20)}</span><span class="launcher-link-text"><strong>Airspace Analytics</strong><small>Aircraft history and patterns</small></span><span class="launcher-link-arrow">${icon('chevron',18)}</span></a>${links()}</div>
 <footer class="launcher-footer"><span><i class="dot" id="launcherDot"></i><span id="launcherStatus">Checking Aerodrome</span></span><a href="/analytics#settings">Manage shortcuts</a></footer></div>`;
 try{const h=await api('/api/health');if(currentPage!=='home')return;const dot=$('#launcherDot');if(dot)dot.classList.toggle('good',h.fresh===true);$('#launcherStatus').textContent=h.fresh?'Aerodrome connected':h.ok?'Aerodrome history available':'Database unavailable';setStatus(h)}catch{if($('#launcherStatus'))$('#launcherStatus').textContent='Status unavailable'}
}
function field(label,element){return `<label class="field"><span>${esc(label)}</span>${element}</label>`}

const opts=(options,chosen)=>options.map(([value,label])=>`<option value="${esc(value)}" ${value===chosen?'selected':''}>${esc(label)}</option>`).join('');
function metrics(){return `<div class="segmented" role="group" aria-label="Measurement">${[['flights','Estimated visits'],['aircraft','Aircraft'],['observations','Observations']].map(([k,v])=>`<button data-metric="${k}" class="${state.metric===k?'on':''}" type="button">${v}</button>`).join('')}</div>`}
function initialDates(){const now=new Date(),previous=new Date(now.getTime()-7*86400000);return [ukDatetime(previous.toISOString()),ukDatetime(now.toISOString())]}
function rangeMode(){return ['rolling','custom','all'].includes(drill.mode)?drill.mode:'all'}
function queryArgs(){return {period:drill.mode,bucket:drill.level,metric:state.metric,category:state.category,type:state.type,airline:state.airline,icao:state.icao,amount:drill.amount,unit:drill.unit,start:drill.start,end:drill.end}}
function rangeControls(){
 const mode=rangeMode(),[fstart,fend]=initialDates();
 return `<details class="traffic-options" id="trafficOptions"><summary>${icon('settings',15)} Range & filters</summary><div class="traffic-options-body">
 <div class="range-picker" role="group" aria-label="Time range">
 ${[['all','All history'],['rolling','Last…'],['custom','From / to']].map(([k,v])=>`<button type="button" data-range-mode="${k}" class="range-choice ${mode===k?'selected':''}">${v}</button>`).join('')}
 </div>
 <div class="range-inputs ${mode==='rolling'?'':'hidden'}" id="rollingBox">
 ${field('Number',`<input type="number" inputmode="numeric" min="1" max="100000" id="amount" value="${esc(drill.amount)}">`)}
 ${field('Unit',`<select id="unit">${opts([['minutes','Minutes'],['hours','Hours'],['days','Days'],['weeks','Weeks'],['months','Months'],['years','Years']],drill.unit)}</select>`)}
 </div>
 <div class="range-inputs ${mode==='custom'?'':'hidden'}" id="customBox">
 ${field('From · UK time',`<input type="datetime-local" id="customStart" value="${esc(drill.start||fstart)}">`)}
 ${field('To · UK time',`<input type="datetime-local" id="customEnd" value="${esc(drill.end||fend)}">`)}
 </div>
 <div class="traffic-filter-grid">
 ${field('Aviation',`<select id="category">${opts([['all','All aviation'],['commercial','Commercial'],['general_aviation','General aviation'],['military','Military'],['helicopter','Helicopters'],['unknown','Unknown']],state.category)}</select>`)}
 ${field('Aircraft type',`<select id="aircraftType"><option value="all">All types</option></select>`)}
 ${field('Airline / operator',`<select id="airline"><option value="all">All operators</option></select>`)}
 ${field('ICAO',`<input id="icao" spellcheck="false" placeholder="All aircraft" value="${esc(state.icao==='all'?'':state.icao)}" maxlength="12">`)}
 </div><div class="traffic-filter-actions"><button class="btn primary" type="button" id="trafficApply">Apply</button><button class="btn small" type="button" id="clearFilters">Clear filters</button></div>
 </div></details>`;
}
function nextRootLevel(mode,amount,unit,start,end){
 if(mode==='all')return 'year';
 let seconds=86400*365;
 if(mode==='rolling')seconds=amount*({minutes:60,hours:3600,days:86400,weeks:604800,months:2629800,years:31557600}[unit]||86400);
 if(mode==='custom')seconds=(Date.parse(end+':00Z')-Date.parse(start+':00Z'))/1000;
 if(seconds<=72*3600)return 'hour';
 if(seconds<=90*86400)return 'day';
 if(seconds<=3*365*86400)return 'month';
 return 'year';
}
function bindRangeControls(){
 $$('[data-range-mode]').forEach(b=>b.onclick=()=>{
  $$('[data-range-mode]').forEach(el=>el.classList.toggle('selected',el===b));
  $('#rollingBox').classList.toggle('hidden',b.dataset.rangeMode!=='rolling');
  $('#customBox').classList.toggle('hidden',b.dataset.rangeMode!=='custom');
 });
 $('#trafficApply').onclick=()=>{
  const mode=$('[data-range-mode].selected')?.dataset.rangeMode||'all';
  const amount=Number($('#amount').value),unit=$('#unit').value;
  const start=$('#customStart').value,end=$('#customEnd').value;
  if(mode==='rolling'&&(!Number.isInteger(amount)||amount<1||amount>100000)){toast('Enter a valid duration','Use a whole number between 1 and 100000.',true);return}
  if(mode==='custom'&&(!start||!end||Date.parse(start+':00Z')>=Date.parse(end+':00Z'))){toast('Check the dates','End must be later than start.',true);return}
  state.category=$('#category').value;state.type=$('#aircraftType').value;state.airline=$('#airline').value;
  state.icao=$('#icao').value.trim().toLowerCase()||'all';persist();
  zoomHistory.length=0;
  drill={level:nextRootLevel(mode,amount,unit,start,end),mode,start:mode==='custom'?start:'',end:mode==='custom'?end:'',amount,unit,trail:[]};
  renderExplore();
 };
 $('#clearFilters').onclick=()=>{state.category='all';state.type='all';state.airline='all';state.icao='all';persist();renderExplore()};
}
let cachedGlobalFilters=null;
async function populateFilters(){
 try{
  if(!cachedGlobalFilters)cachedGlobalFilters=await api('/api/filters');
  fillFilterOptions(null);
 }catch(e){console.warn('Optional filter choices unavailable:',e.message)}
}
function fillFilterOptions(result){
 const type=$('#aircraftType'),air=$('#airline');if(!type||!air)return;
 const types=[['all','All aircraft types'],...((cachedGlobalFilters?.types||result?.breakdowns?.type?.map(x=>x.name)||[])).map(x=>[x,x])];
 const airlines=[['all','All airlines'],...((cachedGlobalFilters?.airlines||result?.breakdowns?.airline?.map(x=>x.name)||[])).map(x=>[x,x])];
 if(state.type!=='all'&&!types.some(x=>x[0]===state.type))types.push([state.type,state.type]);
 if(state.airline!=='all'&&!airlines.some(x=>x[0]===state.airline))airlines.push([state.airline,state.airline]);
 type.innerHTML=opts(types,state.type);air.innerHTML=opts(airlines,state.airline);
}
function hourTick(s){
 const value=String(s.key||'');
 if(/^\d{4}-\d{2}-\d{2}T\d{2}:00Z$/.test(value)){
   return new Date(value.slice(0,-1)+':00Z').toLocaleTimeString('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit',hour12:false});
 }
 return String(s.label).match(/\b\d{2}:\d{2}\b/)?.[0]||s.label;
}
function shortAxisLabel(s,kind,hourAxis){
 if(hourAxis)return hourTick(s);
 const k=String(s.key||'');
 if(kind==='day'&&/^\d{4}-\d{2}-\d{2}$/.test(k))return `${Number(k.slice(8))} ${new Date(k+'T12:00:00Z').toLocaleString('en-GB',{month:'short',timeZone:'UTC'})}`;
 if(kind==='month'&&/^\d{4}-\d{2}$/.test(k))return new Date(k+'-12T12:00:00Z').toLocaleString('en-GB',{month:'short',timeZone:'UTC'});
 if(kind==='week'&&/^\d{4}-\d{2}-\d{2}$/.test(k))return new Date(k+'T12:00:00Z').toLocaleString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'});
 return short(s.label,14);
}
function renderChart(series,kind='line',{height=315,mini=false,color='aqua',hourAxis=false,bucket=''}={}){
 if(!series?.length||series.every(x=>x.value===null||x.value===undefined||!Number(x.value)))return `<div class="chart-empty">No observations in this period. Try another range.</div>`;
 const n=series.length;const width=hourAxis?Math.max(720, n*47+90):Math.max(mini?630:730,Math.min(20000,(kind==='bar'?n*34:n*24)+80));
 const W=width,H=height,L=mini?45:56,R=18,T=18,B=mini?36:46;
 const plotW=W-L-R,plotH=H-T-B, max=Math.max(1,...series.map(x=>Number(x.value)||0));
 const x=i=>L+(n===1?plotW/2:plotW*i/(n-1));
 const y=v=>T+plotH-(Number(v||0)/max)*(plotH-10);
 const ticks=Array.from({length:5},(_,i)=>max*i/4);
 const palette={aqua:'var(--aqua)',blue:'var(--blue)',pink:'var(--pink)'};
 const stroke=palette[color]||palette.aqua;
 let shape='';
 if(kind==='bar'){
   const barWidth=Math.max(3,Math.min(33,plotW/Math.max(1,n)*.72));
   shape=series.map((s,i)=>s.value===null||s.value===undefined?'':`<rect class="chart-bar" data-index="${i}" x="${x(i)-barWidth/2}" y="${y(s.value)}" width="${barWidth}" height="${Math.max(0,T+plotH-y(s.value))}" rx="${Math.min(3,barWidth/4)}" style="fill:${stroke}"/>`).join('');
 }else{
   const coords=series.map((s,i)=>s.value===null||s.value===undefined?null:[x(i),y(s.value)]);
   let inSegment=false;const path=coords.map(pt=>{if(!pt){inSegment=false;return ''}const command=inSegment?'L':'M';inSegment=true;return `${command}${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`}).join(' ');
   shape=`<path class="chart-area" d="${path} L${x(n-1)} ${T+plotH} L${x(0)} ${T+plotH} Z"/><path class="chart-line" d="${path}" style="stroke:${stroke}"/>`;
   if(n<80)shape+=coords.map((pt,i)=>pt?`<circle class="chart-point"  data-index="${i}" cx="${pt[0]}" cy="${pt[1]}" r="3.5" style="fill:${stroke}"/>`:'').join('');
 }
 const labels=hourAxis?n:Math.min(n,mini?6:(n<=32?n:10)),skip=Math.max(1,Math.ceil(n/labels));
 return `<div class="chart-shell"><div class="chart-scroll"><svg style="min-width:${hourAxis?W:Math.min(W,730)}px" viewBox="0 0 ${W} ${H}" role="img" aria-label="Interactive chart with ${n} time buckets">
   <defs><linearGradient id="chartfade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#31dfc1" stop-opacity=".28"/><stop offset="1" stop-color="#31dfc1" stop-opacity="0"/></linearGradient></defs>
   ${ticks.map(t=>`<line class="chart-gridline" x1="${L}" x2="${W-R}" y1="${y(t)}" y2="${y(t)}"/><text class="chart-axis" x="${L-9}" y="${y(t)+3}" text-anchor="end">${fmt(t,max<10?1:0)}</text>`).join('')}
   ${series.map((s,i)=>i%skip===0||i===n-1?`<text class="chart-axis" text-anchor="middle" x="${x(i)}" y="${H-12}">${esc(mini?short(s.label,9):shortAxisLabel(s,bucket,hourAxis))}</text>`:'').join('')}
   ${shape}${series.map((s,i)=>`<rect class="chart-hit" data-index="${i}" x="${Math.max(L,x(i)-plotW/Math.max(n,1)/2)}" y="${T}" width="${Math.max(5,plotW/Math.max(n,1))}" height="${plotH}"/>`).join('')}
   </svg></div><div class="chart-tooltip hidden" role="status"></div></div>`;
}
function hookChart(container,series,group,drill=true){if(!container||!series)return;const tip=$('.chart-tooltip',container);const wrap=$('.chart-shell',container);if(!tip||!wrap)return;
 $$('.chart-hit',container).forEach(hit=>{
  const index=+hit.dataset.index;
  hit.addEventListener('pointermove',ev=>{
    const s=series[index];tip.innerHTML=`${esc(s.label)}<strong>${s.value===null||s.value===undefined?'—':fmt(s.value,2)}</strong>${s.samples?`<span class="muted">${s.samples} occurrences</span>`:''}`;
    tip.classList.remove('hidden');const box=wrap.getBoundingClientRect();tip.style.left=Math.min(box.width-155,Math.max(0,ev.clientX-box.left+8))+'px';tip.style.top=Math.max(45,ev.clientY-box.top)+'px';
  });
  hit.addEventListener('pointerleave',()=>tip.classList.add('hidden'));
  if(drill&&['year','month','week','day','hour'].includes(group))hit.addEventListener('click',()=>drillInto(series[index],group));
 });
}
function ukDatetime(iso){const d=new Date(iso);return d.toLocaleString('sv-SE',{timeZone:'Europe/London'}).replace(' ','T').slice(0,16)}
function drillInto(point,group){
 if(!['year','month','week','day'].includes(group))return;
 const key=String(point.key);let from,to,next,label;
 if(group==='year'){
  from=`${key}-01-01T00:00`;to=`${Number(key)+1}-01-01T00:00`;next='month';label=key;
  if(firstRecordedLocal&&from<firstRecordedLocal)from=firstRecordedLocal;
 }else if(group==='month'){
  const [y,m]=key.split('-').map(Number);
  from=`${key}-01T00:00`;to=m===12?`${y+1}-01-01T00:00`:`${y}-${String(m+1).padStart(2,'0')}-01T00:00`;
  next='week';label=new Date(`${key}-12T12:00:00Z`).toLocaleDateString('en-GB',{month:'long',year:'numeric',timeZone:'UTC'});
 }else if(group==='week'){
  const x=new Date(key+'T12:00:00Z'),z=new Date(x);
  z.setUTCDate(z.getUTCDate()+7);from=key+'T00:00';to=z.toISOString().slice(0,10)+'T00:00';next='day';
  const last=new Date(x);last.setUTCDate(last.getUTCDate()+6);
  label=`${x.toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'})} – ${last.toLocaleDateString('en-GB',{day:'numeric',month:'short',timeZone:'UTC'})}`;
 }else{
  const x=new Date(key+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+1);
  from=key+'T00:00';to=x.toISOString().slice(0,10)+'T00:00';next='hour';
  label=new Date(key+'T12:00:00Z').toLocaleDateString('en-GB',{weekday:'short',day:'numeric',month:'long',year:'numeric',timeZone:'UTC'});
 }
 // A week straddling two months displays only the days within the selected month.
 // This keeps the chart, heatmap and averages tied to one exact period.
 if(drill.mode==='custom'&&drill.start&&drill.end){
  if(from<drill.start)from=drill.start;
  if(to>drill.end)to=drill.end;
 }
 if(from>=to)return;
 zoomHistory.push({...drill,trail:[...drill.trail]});
 drill={...drill,mode:'custom',level:next,start:from,end:to,trail:[...drill.trail,label]};
 renderExplore();window.scrollTo({top:0,behavior:'instant'});
}
function categoryName(n){return ({general_aviation:'General aviation',commercial:'Commercial',military:'Military',helicopter:'Helicopters',unknown:'Unknown',other:'Other'})[n]||n}
function donut(items,pretty=false){if(!items?.length)return `<div class="empty">No breakdown available.</div>`;
 const top=items.slice(0,5),total=items.reduce((a,x)=>a+Number(x.value),0);
 if(total<=0)return '<div class="empty">No classifications available for this selection.</div>';
 const colors=['#31dfc1','#6795ff','#cb8efa','#f1b970','#e37d92','#52647d'];let at=0;
 const portions=top.map((s,i)=>{const p=s.value/total*100;const segment=`${colors[i]} ${at.toFixed(2)}% ${(at+p).toFixed(2)}%`;at+=p;return segment});
 if(at<100)portions.push(`${colors[5]} ${at.toFixed(2)}% 100%`);
 return `<div class="donut-layout"><div class="donut" style="background:conic-gradient(${portions.join(',')})"><div class="donut-center"><strong>${fmt(total)}</strong><span>${esc(state.metric)}</span></div></div>
 <div class="legend">${top.map((x,i)=>`<div class="legend-row"><span title="${esc(x.name)}"><i class="legend-swatch" style="background:${colors[i]}"></i>${esc(short(pretty?categoryName(x.name):x.name,21))}</span><strong>${pct(x.value,total)}</strong></div>`).join('')}${top.length<items.length?`<div class="legend-row"><span><i class="legend-swatch" style="background:${colors[5]}"></i>Other</span><strong>${pct(total-top.reduce((a,x)=>a+x.value,0),total)}</strong></div>`:''}</div></div>`;
}
function breakdownList(items,field,color='aqua'){
 if(!items?.length)return '<div class="empty">No information available for this period.</div>';
 const top=items.slice(0,10),max=top[0].value||1;
 return `<div class="breakdown-list">${top.map(s=>`<div class="breakdown-row" title="Filter by ${esc(s.name)}" data-filter="${esc(field)}" data-value="${esc(s.name)}"><div><div class="breakdown-name">${esc(field==='category'?categoryName(s.name):s.name)}</div><div class="bar-track"><div class="bar-fill ${color==='aqua'?'':color}" style="width:${Math.max(0,s.value/max*100)}%"></div></div></div><strong class="breakdown-value">${fmt(s.value)}</strong></div>`).join('')}</div>`;
}
function bindBreakdowns(){ $$('[data-filter]').forEach(el=>el.onclick=()=>{const f=el.dataset.filter,value=el.dataset.value;if(!['type','airline','category'].includes(f))return;if(f==='airline'&&value.toLowerCase().startsWith('unknown'))return;state[f]=value;persist();renderExplore();toast('Filter applied',`${value} — click Reset to clear.`)}) }
function summaryFor(a){const unit={flights:'estimated visits',aircraft:'unique aircraft',observations:'observation records'}[a.metric];
 return `<div class="summary-row"><div class="summary-item"><span>Period total</span><strong>${fmt(a.total)}</strong></div><div class="summary-item"><span>${a.aggregation_label}</span><strong>${fmt(a.average,2)}</strong></div><div class="summary-item"><span>Highest bucket</span><strong>${fmt(a.peak,2)}</strong></div><div class="summary-item"><span>Distinct aircraft</span><strong>${fmt(a.unique_aircraft)}</strong></div></div>`;
}
function currentSelection(){
 const names={year:'Years',month:'Months',week:'Weeks',day:'Days',hour:'Hours'};
 return `${names[drill.level]} · ${drill.trail.length?drill.trail.join(' / '):drill.mode==='all'?'All recorded history':drill.mode==='rolling'?`Last ${drill.amount} ${drill.unit}`:'Custom dates'}`;
}
function drillCrumbs(){
 const labels=['All years',...drill.trail];
 return labels.map((label,i)=>`<button type="button" data-crumb="${i}" class="${i===labels.length-1?'current':''}">${esc(label)}</button>`).join('<span aria-hidden="true">›</span>');
}
function drawCurrentChart(){
 if(!currentAnalytics)return;
 const isHour=currentAnalytics.bucket==='hour';
 $('#exploreChart').innerHTML=renderChart(currentAnalytics.series,state.chart||'bar',{hourAxis:isHour,bucket:currentAnalytics.bucket});
 hookChart($('#exploreChart'),currentAnalytics.series,currentAnalytics.bucket);
 $('#lineSwitch').classList.toggle('on',state.chart==='line');
 $('#barSwitch').classList.toggle('on',state.chart!=='line');
}
async function renderExplore(){
 const rid=++renderId;currentAnalytics=null;
 $('#page').innerHTML=`<div class="traffic-view">
 <header class="traffic-header"><div class="traffic-left"><h1>Traffic</h1><nav class="drill-crumbs" id="drillCrumbs" aria-label="Selected dates">${drillCrumbs()}</nav></div>
 <div class="traffic-header-actions">${metrics()}<button class="btn small" id="zoomBack" ${zoomHistory.length?'':'disabled'} type="button">${icon('chevron',14)} Zoom out</button></div></header>
 ${rangeControls()}
 <section class="main-chart-panel"><div class="main-chart-head"><div><h2 id="chartLabel">Estimated flight visits</h2><div class="traffic-selected" id="chartMeta">${esc(currentSelection())}</div></div>
 <div class="chart-tools"><div class="chart-toggle"><button class="btn small" id="barSwitch" type="button">Bars</button><button class="btn small" id="lineSwitch" type="button">Line</button></div></div></div>
 <div id="exploreStats" class="compact-stats">${loading()}</div>
 <div id="exploreChart" class="chart-frame">${loading()}</div>
 <div class="chart-foot"><span id="pointCount"></span><span id="chartHelp">Select a bar or point to zoom in</span></div></section>
 <section class="breakdown-section"><div class="breakdown-heading"><h2>Breakdown</h2><button class="btn small" id="allVizSwitch" type="button">${state.breakdownViz==='pie'?'Show bars':'Show pies'}</button></div>
 <div class="grid-three breakdown-grid"><div class="panel"><h3 class="panel-title">Aviation category</h3><div id="categoryDonut">${loading()}</div></div>
 <div class="panel"><h3 class="panel-title">Aircraft types</h3><div id="typeBars">${loading()}</div></div>
 <div class="panel"><div class="panel-top"><select id="operatorScope" class="breakdown-scope" aria-label="Operator breakdown">${opts([['airline','Commercial airlines'],['operator','All operators']],state.operatorScope||'airline')}</select></div><div id="airlineBars">${loading()}</div></div></div></section>

 <div class="pattern-panel panel"><div class="panel-top"><h2 class="panel-title">Hourly activity</h2><span class="tiny muted" id="patternRange">${esc(currentSelection())}</span></div><div id="heatmap">${loading()}</div></div>
 <div class="pattern-subgrid"><section class="panel"><h3 class="panel-title">Average by weekday</h3><div id="weekdayPattern">${loading()}</div></section><section class="panel"><h3 class="panel-title">Average by hour</h3><div id="hourPattern">${loading()}</div></section></div>
 </div>`;
 bindRangeControls();populateFilters();
 $$('[data-metric]').forEach(b=>b.onclick=()=>{state.metric=b.dataset.metric;persist();renderExplore()});
 $('#lineSwitch').onclick=()=>{state.chart='line';persist();drawCurrentChart()};
 $('#barSwitch').onclick=()=>{state.chart='bar';persist();drawCurrentChart()};
 $('#zoomBack').onclick=()=>{const prev=zoomHistory.pop();if(prev){drill=prev;renderExplore()}};
 $$('[data-crumb]').forEach(b=>b.onclick=()=>{const index=+b.dataset.crumb;if(index>=drill.trail.length)return;
  if(index===0){zoomHistory.length=0;drill={level:'year',mode:'all',start:'',end:'',amount:7,unit:'days',trail:[]}}
  else {const previous=zoomHistory[index];if(previous){drill={...previous,trail:[...previous.trail]};zoomHistory.length=index}}
  renderExplore();
 });
 $('#allVizSwitch').onclick=()=>{state.breakdownViz=state.breakdownViz==='pie'?'bars':'pie';persist();drawBreakdowns()};
 $('#operatorScope').onchange=()=>{state.operatorScope=$('#operatorScope').value;persist();drawBreakdowns()};
 function drawBreakdowns(){
  if(!currentAnalytics)return;
  const a=currentAnalytics, pie=state.breakdownViz==='pie';
  $('#categoryDonut').innerHTML=pie?donut(a.breakdowns.category,true):breakdownList(a.breakdowns.category,'category','aqua');
  $('#typeBars').innerHTML=pie?donut(a.breakdowns.type):breakdownList(a.breakdowns.type,'type','blue');
  const scope=a.breakdowns[state.operatorScope||'airline']||a.breakdowns.airline;
  $('#airlineBars').innerHTML=pie?donut(scope):breakdownList(scope,'airline','pink');
  $('#allVizSwitch').textContent=pie?'Show bars':'Show pies';bindBreakdowns();
 }
 try{
  const a=await api('/api/analytics',queryArgs());if(rid!==renderId)return;
  if(drill.mode==='all'&&drill.level==='year'&&a.start)firstRecordedLocal=ukDatetime(new Date(a.start*1000).toISOString());
  currentAnalytics=a;fillFilterOptions(a);
  $('#exploreStats').innerHTML=`<div class="mini-stat"><span>Total</span><strong>${fmt(a.total)}</strong></div><div class="mini-stat"><span>Average per interval</span><strong>${fmt(a.average,2)}</strong></div><div class="mini-stat"><span>Highest interval</span><strong>${fmt(a.peak,2)}</strong></div><div class="mini-stat"><span>Unique aircraft</span><strong>${fmt(a.unique_aircraft)}</strong></div>`;
  $('#chartLabel').textContent={flights:'Estimated flight visits',aircraft:'Unique aircraft',observations:'Recorded observations'}[a.metric];
  $('#chartMeta').textContent=`${currentSelection()} · ${when(a.start)} – ${when(a.end)}`;
  $('#patternRange').textContent=`${when(a.start)} – ${when(a.end)}`;
  $('#pointCount').textContent=`${a.series.length} ${drill.level==='hour'?'hours':drill.level==='day'?'days':drill.level==='week'?'weeks':drill.level==='month'?'months':'years'}`;
  $('#chartHelp').textContent=drill.level==='hour'?'Every recorded hour · UK local time':'Select a bar or point to zoom in';
  drawCurrentChart();drawBreakdowns();
  // Pattern query is serial after analytics because both use Aerodrome's
  // bounded read-only semaphore; parallel queries could reject one another.
  try{
   const patterns=await api('/api/patterns',queryArgs());if(rid!==renderId)return;
   const single=drill.level==='hour'&&drill.mode==='custom'&&drill.start?.slice(0,10)===new Date(Date.parse(drill.end+':00Z')-60000).toISOString().slice(0,10);
   $('#heatmap').innerHTML=renderHeatmap(patterns.heatmap,single?drill.start.slice(0,10):null);
   $('#weekdayPattern').innerHTML=renderWeekBars(patterns.weekday,true);
   $('#hourPattern').innerHTML=renderChart(patterns.hourly,'bar',{height:205,hourAxis:true});
   hookChart($('#hourPattern'),patterns.hourly,'hour_of_day',false);
  }catch(e){if(rid!==renderId)return;['heatmap','weekdayPattern','hourPattern'].forEach(id=>$('#'+id).innerHTML=`<div class="empty">${esc(e.message)}</div>`)}
 }catch(e){if(rid!==renderId)return;$('#exploreStats').innerHTML='';$('#exploreChart').innerHTML=safeError(e);['heatmap','weekdayPattern','hourPattern','categoryDonut','typeBars','airlineBars'].forEach(id=>$('#'+id).innerHTML='')}
}
function renderWeekBars(series,shortLabels=false){if(!series?.length)return '<div class="empty">No data available.</div>';
 const observed=series.filter(x=>x.samples>0&&x.value!==null);
 if(!observed.length)return '<div class="empty">No recorded days in this range.</div>';
 const max=Math.max(...observed.map(x=>x.value),1);
 return `<div class="pattern-bars">${series.map(s=>{
  const has=s.samples>0&&s.value!==null;
  return `<div class="pattern-col" title="${esc(s.label)}: ${has?fmt(s.value,2)+' average from '+s.samples+' recorded day(s)':'No recorded days'}"><strong class="tiny muted">${has?fmt(s.value,1):'—'}</strong><div class="pattern-bar ${has?'':'missing'}" style="height:${has?Math.max(2,150*s.value/max):2}px"></div><small>${esc(shortLabels?String(s.label).slice(0,3):s.label)}</small></div>`;
 }).join('')}</div>`;
}
function renderHeatmap(cells,singleDate=null){
 if(!cells?.length)return '<div class="empty">No hourly records.</div>';
 const max=Math.max(1,...cells.filter(x=>x.samples).map(x=>x.value||0));
 const dimension={flights:'visits',aircraft:'aircraft',observations:'samples'}[state.metric]||'traffic';
 const weekdays=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
 const selectedWeekday=singleDate?(new Date(singleDate+'T12:00:00Z').getUTCDay()+6)%7:null;
 const rows=selectedWeekday===null?[0,1,2,3,4,5,6]:[selectedWeekday];
 const map=new Map(cells.map(c=>[`${c.weekday}-${c.hour}`,c]));
 const format=v=>v===null||v===undefined?'var(--panel2)':`rgba(98,229,208,${(.13+.83*Math.pow(Math.max(0,v)/max,.7)).toFixed(3)})`;
 return `<div class="heat-outer"><div class="heatmap compact-heatmap"><span></span>${Array.from({length:24},(_,h)=>`<span class="heat-label">${String(h).padStart(2,'0')}</span>`).join('')}
 ${rows.map(wd=>`<span class="heat-day">${weekdays[wd]}</span>${Array.from({length:24},(_,hour)=>{
  const x=map.get(`${wd}-${hour}`),has=x?.samples>0;
  const detail=has?`${fmt(x.value,2)} average · ${x.samples} recorded ${x.samples===1?'hour':'hours'}`:'No recorded samples';
  return `<span class="heat-cell" role="img" tabindex="0" aria-label="${weekdays[wd]} ${String(hour).padStart(2,'0')}:00 — ${detail}" title="${weekdays[wd]} ${String(hour).padStart(2,'0')}:00 — ${detail}" style="background:${format(has?x.value:null)}"></span>`;
 }).join('')}`).join('')}</div></div><div class="heat-legend"><span>Fewer ${dimension}</span>${[.15,.3,.5,.7,.95].map(op=>`<i style="background:rgba(98,229,208,${op})"></i>`).join('')}<span>More ${dimension}</span></div>`;
}
async function renderAircraft(){const rid=++renderId;
 $('#page').innerHTML=title('','Aircraft')+
 `<div class="control-card"><div class="secondary-controls" style="border:0;padding:0;margin:0;align-items:center">${field('Search aircraft',`<input id="aircraftQuery" placeholder="e.g. A388, EZY, 4CA123" autocomplete="off" style="min-width:240px">`)}<button class="btn primary" id="aircraftGo">${icon('search')} Search</button></div></div>
 <div class="panel"><div class="panel-top"><div><h3 class="panel-title">Aircraft registry</h3><p class="panel-subtitle">Searches Aerodrome's previously detected aircraft</p></div><span class="chip aqua" id="aircraftCount">—</span></div><div id="aircraftList">${loading()}</div></div><div id="aircraftDetail"></div>`;
 let activeSearch=0;
 const search=async()=>{const seq=++activeSearch;const q=$('#aircraftQuery').value;$('#aircraftList').innerHTML=loading('Searching aircraft…');
  try{const d=await api('/api/aircraft',{q,limit:60});if(rid!==renderId||seq!==activeSearch)return;
   $('#aircraftCount').textContent=`${d.items.length} results`;
   $('#aircraftList').innerHTML=d.items.length?`<div class="table-wrap"><table><thead><tr><th>ICAO hex</th><th>Callsign</th><th>Type</th><th>Category</th><th>Operator</th><th>Last recorded</th></tr></thead><tbody>${d.items.map(it=>`<tr class="aircraft-row" data-icao="${esc(it.icao)}"><td class="mono">${esc(it.icao)}</td><td>${esc(it.last_callsign||'—')}</td><td>${esc(it.aircraft_type||'—')}</td><td>${esc(it.category||'—')}</td><td>${esc(short(it.operator,28))}</td><td>${when(it.last_seen_at)}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No matching aircraft yet.</div>';
   $$('.aircraft-row').forEach(row=>row.onclick=()=>showAircraft(row.dataset.icao));
  }catch(e){if(rid===renderId)$('#aircraftList').innerHTML=safeError(e)}};
 $('#aircraftGo').onclick=search;$('#aircraftQuery').addEventListener('keydown',e=>{if(e.key==='Enter')search()});await search();
}
async function showAircraft(icao){const target=$('#aircraftDetail');if(!target)return;target.innerHTML=`${section('Aircraft details')}<div class="panel">${loading()}</div>`;
 try{const d=await api('/api/aircraft/'+encodeURIComponent(icao));if(!$('#aircraftDetail'))return;
 const x=d.aircraft;
 target.innerHTML=`${section('Aircraft '+esc(icao),'Historical metadata and latest retained observations.')}
 <div class="panel"><div class="detail-grid">${[['Registration',x.registration||'Unavailable'],['Type',x.aircraft_type||'Unknown'],['Description',x.aircraft_type_desc||'Unknown'],['Operator',x.operator||'Unknown'],['Category',x.category||'Unknown'],['Country',x.country||'Unknown'],['First detected',when(x.first_seen_at)],['Last detected',when(x.last_seen_at)],['Observations',fmt(x.sighting_count)]].map(([k,v])=>`<div class="detail-item"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('')}</div></div>
 ${section('Recent sightings')}
 <div class="panel"><div class="table-wrap"><table><thead><tr><th>Recorded</th><th>Callsign</th><th>Latitude</th><th>Longitude</th><th>Altitude</th><th>Speed</th><th>Squawk</th></tr></thead><tbody>${d.sightings.map(s=>`<tr><td>${when(s.seen_at)}</td><td>${esc(s.callsign||'—')}</td><td>${esc(s.lat??'—')}</td><td>${esc(s.lon??'—')}</td><td>${esc(s.altitude??'—')}</td><td>${esc(s.speed??'—')}</td><td>${esc(s.squawk??'—')}</td></tr>`).join('')}</tbody></table></div></div>`;
 target.scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){target.innerHTML=safeError(e)}
}
let dbPage=1;
async function renderDatabase(){const rid=++renderId;
 $('#page').innerHTML=title('','Database')+
 `<div class="control-card"><div class="secondary-controls" style="border:0;margin:0;padding:0">
 ${field('Database table',`<select id="dbTable"><option>Loading tables…</option></select>`)}
 ${field('Search ICAO / callsign / operator',`<input type="search" id="dbSearch" placeholder="Optional filter">`)}
 <button class="btn primary" id="dbApply">${icon('search')} Search</button><button class="btn" id="dbExport">${icon('download')} Export CSV</button>
 </div></div>
 <div class="panel"><div class="panel-top"><div><h3 class="panel-title" id="dbTitle">Stored observations</h3></div><span class="chip" id="dbPageInfo">—</span></div><div id="dbResults">${loading()}</div>
 <div class="table-pager"><span class="muted tiny" id="dbCaption">Read-only query</span><div class="setting-actions"><button class="btn small" id="dbPrev">← Previous</button><button class="btn small" id="dbNext">Next →</button></div></div></div>`;
 try{const d=await api('/api/database/tables');if(rid!==renderId)return;
 $('#dbTable').innerHTML=opts(d.tables.map(x=>[x.name,x.name.replaceAll('_',' ')]),'all_sightings');
 const load=async()=>{
  const name=$('#dbTable').value,q=$('#dbSearch').value;$('#dbResults').innerHTML=loading();
  try{const t=await api('/api/database/rows',{table:name,page:dbPage,limit:30,q});if(rid!==renderId)return;
   $('#dbTitle').textContent=name.replaceAll('_',' ');$('#dbPageInfo').textContent=`Page ${t.page}`;
   $('#dbPrev').disabled=dbPage===1;$('#dbNext').disabled=!t.has_more;
   $('#dbCaption').textContent=`${t.rows.length} records on this page · ${t.columns.length} columns`;
   $('#dbResults').innerHTML=t.rows.length?`<div class="table-wrap"><table><thead><tr>${t.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${t.rows.map(r=>`<tr>${t.columns.map(c=>`<td title="${esc(r[c])}">${esc(r[c]??'—')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:'<div class="empty">No records found for this search.</div>';
  }catch(e){if(rid===renderId)$('#dbResults').innerHTML=safeError(e)}
 };
 $('#dbApply').onclick=()=>{dbPage=1;load()};$('#dbTable').onchange=()=>{dbPage=1;load()};$('#dbSearch').onkeydown=e=>{if(e.key==='Enter'){dbPage=1;load()}};
 $('#dbPrev').onclick=()=>{dbPage=Math.max(1,dbPage-1);load()};$('#dbNext').onclick=()=>{dbPage++;load()};
 $('#dbExport').onclick=()=>{const u=new URL('/api/database/export',location.origin);u.searchParams.set('table',$('#dbTable').value);u.searchParams.set('q',$('#dbSearch').value);window.location.href=u.toString()};
 dbPage=1;await load();
 }catch(e){if(rid===renderId)$('#dbResults').innerHTML=safeError(e)}
}
function settingsRow(title,desc,body){return `<div class="settings-group"><div><h3>${title}</h3><p>${desc}</p></div><div>${body}</div></div>`}
function settingsLinks(){return `<div class="shortcut-list" id="shortcutList">${getLinks().map((it,i)=>`<div class="shortcut-edit-row" data-linkindex="${i}"><div class="shortcut-edit-main">${field('Name',`<input class="link-name" value="${esc(it.name)}" maxlength="50">`)}${field('Port',`<input class="link-port" value="${esc(it.port??'')}" placeholder="e.g. 5173" inputmode="numeric">`)}${field('Full URL (optional)',`<input class="link-url" value="${esc(it.url||'')}" placeholder="http://…">`)}${field('Path',`<input class="link-path" value="${esc(it.path||'/')}" placeholder="/">`)}</div><div class="shortcut-edit-actions"><button class="btn small" data-reorder="up" data-pos="${i}" title="Move up" ${i===0?'disabled':''}>↑</button><button class="btn small" data-reorder="down" data-pos="${i}" title="Move down" ${i===getLinks().length-1?'disabled':''}>↓</button><button class="btn small danger" data-remove="${i}" title="Remove shortcut">Remove</button></div></div>`).join('')}</div>
 <div class="setting-actions shortcut-actions"><button class="btn" id="addLink" type="button">${icon('plus',15)} Add link</button><button class="btn primary" id="saveLinks" type="button">Save links</button><button class="btn" id="restoreLinks" type="button">Restore defaults</button></div>`}
function collectSettingsLinks(){const original=getLinks();return $$('[data-linkindex]').map(el=>{
 const idx=Number(el.dataset.linkindex),port=$('.link-port',el).value.trim(),path=$('.link-path',el).value.trim()||'/',url=$('.link-url',el).value.trim();
 if(port&&!/^\d{1,5}$/.test(port))throw Error('Ports must be numeric');
 if(port&&(Number(port)<1||Number(port)>65535))throw Error('Port must be 1–65535');
 if(url&&!/^https?:\/\//i.test(url))throw Error('URLs must begin with http:// or https://');
 return {...original[idx],name:$('.link-name',el).value.trim().slice(0,50)||'New link',sub:original[idx]?.sub||'Application shortcut',port,path,url,icon:original[idx]?.icon||'external'};
})}
function updaterToken(){
 try{return localStorage.getItem(pairedUpdaterKey)||sessionStorage.getItem('airspace-token')||''}catch{return ''}
}
function updateBox(){return `<div class="auth-box">
  <div class="status-row" style="margin-bottom:9px"><i class="dot" id="updateDot"></i><strong id="updateHeading">Checking GitHub…</strong></div>
  <div class="tiny muted break-word" id="updateDetails"></div>
  <div class="setting-actions"><button class="btn" id="checkUpdates">${icon('refresh')} Check GitHub</button><button class="btn primary" id="applyUpdate">Update now</button><button class="btn" id="rollbackUpdate">Restore previous</button></div>
  <div class="tiny muted" id="updateProgress"></div>
  <details class="advanced-panel updater-pair" id="updaterPairing"><summary>Connect updates on this browser</summary>
   <div class="settings-entry">${field('Pairing code',`<input type="password" id="updateToken" autocomplete="off" placeholder="Only needed on a new browser">`)}
   <button class="btn" type="button" id="saveUpdatePair">Connect</button></div></details>
 </div>`}
async function renderSettings(){const rid=++renderId;
 $('#page').innerHTML=title('','Settings')+
 `<div class="panel">${settingsRow('Appearance','Choose a theme and your preferred default measurement.',
   `<div class="settings-entry">${field('Colour theme',`<select id="settingTheme">${opts([['dark','Dark / midnight'],['light','Light / cloud']],state.theme)}</select>`)}${field('Default measurement',`<select id="settingMetric">${opts([['flights','Estimated flights'],['aircraft','Unique aircraft'],['observations','Observations']],state.metric)}</select>`)}</div><button class="btn primary" id="saveAppearance" style="margin-top:13px">Save preferences</button>`)}
 ${settingsRow('Launcher links','The Analytics link always comes first. Add, remove and reorder the other links.',settingsLinks())}
 ${settingsRow('GitHub updates','',updateBox())}
 ${settingsRow('Aerodrome database','',`<div id="databaseInfo">${loading()}</div>`)}

 </div>`;
 $('#saveAppearance').onclick=()=>{setTheme($('#settingTheme').value);state.metric=$('#settingMetric').value;persist();toast('Preferences saved')};
 function saveLinks(){try{putLinks(collectSettingsLinks());toast('Launcher links saved');return true}catch(e){toast('Invalid link',e.message,true);return false}}
 $('#saveLinks').onclick=()=>saveLinks();
 $('#addLink').onclick=()=>{if(!saveLinks())return;const xs=getLinks();xs.push({name:'New link',sub:'Application shortcut',port:'',path:'/',url:'',icon:'external'});putLinks(xs);renderSettings()};
 $('#restoreLinks').onclick=()=>{putLinks(defaultLinks);toast('Default links restored');renderSettings()};
 $$('[data-remove]').forEach(b=>b.onclick=()=>{if(!saveLinks())return;const xs=getLinks();xs.splice(+b.dataset.remove,1);putLinks(xs);renderSettings()});
 $$('[data-reorder]').forEach(b=>b.onclick=()=>{if(!saveLinks())return;const xs=getLinks(),i=+b.dataset.pos,j=i+(b.dataset.reorder==='up'?-1:1);if(j<0||j>=xs.length)return;[xs[i],xs[j]]=[xs[j],xs[i]];putLinks(xs);renderSettings()});
 $('#saveUpdatePair').onclick=()=>{
   const value=$('#updateToken').value.trim();if(!value)return;
   localStorage.setItem(pairedUpdaterKey,value);sessionStorage.setItem('airspace-token',value);
   $('#updateToken').value='';$('#updaterPairing').open=false;toast('Updater connected');
 };
 $('#checkUpdates').onclick=async()=>{
  $('#updateDetails').textContent='Checking GitHub…';try{const d=await api('/api/update/check',{refresh:1});setUpdateInfo(d)}catch(e){$('#updateDetails').textContent=e.message}
 };
 $('#applyUpdate').onclick=()=>launchUpdate('apply');
 $('#rollbackUpdate').onclick=()=>launchUpdate('rollback');
 async function launchUpdate(mode){
  const token=updaterToken();
  if(!token){$('#updaterPairing').open=true;toast('Connect updates once','Use your existing pairing code for this browser.');return}
  if(!confirm(mode==='rollback'?'Restore the previous working website version and restart only this service?':'Download the latest code from your configured GitHub repository and restart only this website?'))return;
  $('#updateProgress').textContent='Starting the updater…';
  try{const res=await fetch('/api/update/'+mode,{method:'POST',headers:{'X-Update-Token':token,'Content-Type':'application/json'},body:'{}'});
   const d=await res.json();if(!res.ok){if(res.status===403)$('#updaterPairing').open=true;throw Error(d.error||'Update request failed');}
   toast(mode==='rollback'?'Rollback requested':'Update requested','The updater will restart only the Airspace Analytics service.');
   let attempts=0;
   const poll=async()=>{if(!$('#updateProgress'))return;attempts++;
    try{const status=await api('/api/update/status');$('#updateProgress').textContent=`${status.state.toUpperCase()}: ${status.detail}`;
      if(['failed','current'].includes(status.state)){clearInterval(timer);if(status.state==='failed')toast('Update failed',status.detail,true)}
      if(status.state==='success'){clearInterval(timer);setTimeout(()=>location.reload(),2500)}
    }catch{}if(attempts>90)clearInterval(timer)};
   const timer=setInterval(poll,2000);poll();
  }catch(e){toast('Update failed to start',e.message,true);$('#updateProgress').textContent=e.message}
 }
 try{const [d,u,s]=await Promise.all([api('/api/health'),api('/api/update/check'),api('/api/update/status')]);if(rid!==renderId)return;
  $('#databaseInfo').innerHTML=`<div class="detail-grid">${[
   ['Database',d.db_path],['Current size',bytes(d.db_size_bytes)],['Oldest observation',when(d.first_sighting)],
   ['Most recent',when(d.last_sighting)],['Observations',fmt(d.raw_observations)],['Unique aircraft',fmt(d.total_aircraft)]
  ].map(([k,v])=>`<div class="detail-item"><small>${esc(k)}</small><strong class="break-word">${esc(v)}</strong></div>`).join('')}</div>`;
  setUpdateInfo(u);$('#updateProgress').textContent=s.state==='idle'?'':`${s.state}: ${s.detail}`;
 }catch(e){if(rid===renderId)$('#databaseInfo').innerHTML=safeError(e)}
}
function setUpdateInfo(d){if(!$('#updateDetails'))return;
 $('#updateHeading').textContent=d.available?'New version available':d.configured?'Repository is up to date':'GitHub unavailable';
 $('#updateDot').classList.toggle('good',d.configured&&!d.available);$('#updateDot').classList.toggle('bad',!!d.error);
 $('#updateDetails').innerHTML=`<div class="detail-grid">${[['Version',d.version],['Installed',d.local_sha||'—'],['GitHub',d.remote_sha||'—']].map(([k,v])=>`<div class="detail-item"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('')}</div>
 ${d.error?`<p style="color:var(--orange)">${esc(d.error)}</p>`:''}`;
}
async function loadPage(){const fallback=location.pathname==='/analytics'?'explore':'home';const hash=(location.hash||'#'+fallback).slice(1).split('?')[0];currentPage=['patterns','compare'].includes(hash)?'explore':(names[hash]?hash:fallback);renderId++;document.body.classList.toggle('launcher-mode',currentPage==='home');document.title=(currentPage==='home'?'Airspace · Launcher':names[currentPage]+' · Airspace Analytics');
 $$('.nav-link,.mobile-tabbar a').forEach(el=>el.classList.toggle('active',el.dataset.page===currentPage));
 $('#topTitle').textContent=names[currentPage];setMenu(false);
 window.scrollTo({top:0,behavior:'instant'});
 const routes={home:renderHome,explore:renderExplore,aircraft:renderAircraft,database:renderDatabase,settings:renderSettings};
 try{await routes[currentPage]()}catch(e){$('#page').innerHTML=safeError(e)}
}
async function refreshStatus(){try{const h=await api('/api/health');setStatus(h)}catch{setStatus(null)}}
function boot(){shell();window.addEventListener('hashchange',loadPage);loadPage();refreshStatus();api('/api/config').then(d=>$$('.versionValue').forEach(x=>x.textContent='v'+d.version)).catch(()=>{});activeTimer=setInterval(refreshStatus,60000)}
boot();
