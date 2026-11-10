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
const defaults={metric:'flights',period:'last_7d',bucket:'auto',category:'all',type:'all',airline:'all',icao:'all',amount:46,unit:'hours',start:'',end:'',chart:'line',theme:'dark',comparison:'previous',offset:1,other_start:'',other_end:'',typeViz:'bars',airlineViz:'bars'};
const state={...defaults,...readPrefs()};
function readPrefs(){try {return JSON.parse(localStorage.getItem(key))||{}}catch{return {}}}
function persist(){localStorage.setItem(key,JSON.stringify(state))}
const savedViewsKey='airspace-analytics-views-v1';
const defaultLinks=[
  {name:'ADSB.im',sub:'Receiver controls',path:'/',color:'aqua',icon:'radar'},
  {name:'Aerodrome',sub:'History & records',port:'8000',path:'/',color:'blue',icon:'plane'},
  {name:'SkyStats',sub:'Flight statistics',port:'5173',path:'/',color:'pink',icon:'chart'},
  {name:'Aircraft map',sub:'Readsb live map',port:'1099',path:'/',color:'aqua',icon:'map'},
  {name:'Receiver graphs',sub:'Signal & coverage',port:'1094',path:'/',color:'orange',icon:'activity'},
  {name:'Dozzle',sub:'Container logs',port:'',path:'/',color:'blue',icon:'terminal'}
];
function getLinks(){try{const x=JSON.parse(localStorage.getItem('airspace-analytics-links'));return Array.isArray(x)&&x.length?x:defaultLinks}catch{return defaultLinks}}
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
const pages=[['home','Overview','grid'],['explore','Explore data','chart'],['patterns','Patterns','activity'],['compare','Compare periods','compare'],['aircraft','Aircraft','plane'],['database','Raw database','database'],['settings','Settings & updates','settings']];
const names=Object.fromEntries(pages.map(x=>[x[0],x[1]]));
let currentPage='home',currentChart='line',currentAnalytics=null,latestOverview=null,healthInfo=null,activeTimer=null,renderId=0;
function setTheme(theme){document.documentElement.dataset.theme=theme||'dark';state.theme=theme;persist()}
setTheme(state.theme);

function shell(){
 $('#app').innerHTML=`<div class="overlay" id="overlay"></div><div class="layout">
   <aside class="sidebar" id="sidebar">
     <a class="brand" href="#home" aria-label="Airspace Analytics homepage"><span class="logo">${icon('radar',24)}</span><span><strong>Airspace</strong><small>Analytics</small></span></a>
     <div class="nav-caption">Workspace</div><nav class="nav-list">${pages.slice(0,5).map(nav).join('')}</nav>
     <div class="nav-section"><div class="nav-caption">Tools</div><nav class="nav-list">${pages.slice(5).map(nav).join('')}</nav></div>
     <div class="sidebar-bottom"><div class="sidebar-status"><div class="status-row"><i class="dot" id="sidebarDot"></i><strong class="status-label" id="sidebarTitle">Checking data source</strong></div><p id="sidebarDetail">Connecting to Aerodrome…</p></div><div class="version">Local dashboard · <span class="versionValue">v1.1.0</span></div></div>
   </aside>
   <div class="workspace"><header class="topbar"><div style="display:flex;align-items:center;gap:12px"><button class="icon-button mobile-menu" id="mobileMenu" aria-label="Open menu">${icon('menu')}</button><div class="breadcrumbs"><span>Workspace</span><span class="divider">/</span><strong id="topTitle">Overview</strong></div></div><div class="top-actions"><span class="top-live"><i class="dot" id="topDot"></i><span id="topStatus">Connecting</span></span><button class="icon-button" id="themeButton" title="Toggle dark/light mode">${icon('sun')}</button></div></header>
   <main class="content" id="page" aria-live="polite"></main></div>
 </div>
 <nav class="mobile-tabbar" id="mobileTabs">${[['home','Home','grid'],['explore','Explore','chart'],['patterns','Patterns','activity'],['compare','Compare','compare'],['settings','More','menu']].map(([id,title,ic])=>`<a href="#${id}" data-page="${id}">${icon(ic,20)}<span>${title}</span></a>`).join('')}</nav>
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
function title(eyebrow,heading,subtitle,accessory=''){return `<div class="page-heading"><div><div class="page-eyebrow">${esc(eyebrow)}</div><h1 class="page-title">${esc(heading)}</h1><p class="page-subtitle">${subtitle}</p></div>${accessory}</div>`}
function stat(label,value,meta,ic='chart'){return `<article class="stat-card"><div class="stat-label"><span>${esc(label)}</span><span class="stat-icon">${icon(ic)}</span></div><div class="stat-value">${value}</div><div class="stat-meta">${meta}</div></article>`}
function section(h,sub='',right=''){return `<div class="section-heading"><div><h2>${h}</h2>${sub?`<p>${sub}</p>`:''}</div>${right}</div>`}
function links(){return getLinks().map((it,i)=>{const destination=it.port===null?null:hrefFor(it);return `<${destination?'a':'div'} class="launch-card" ${destination?`href="${esc(destination)}" target="_blank" rel="noopener noreferrer"`:''}>
  <span class="launch-icon">${icon(it.icon||'external')}</span><span style="min-width:0"><strong>${esc(it.name)}</strong><small>${esc(destination?it.sub:'Set address in Settings')}</small></span><span class="arrow">${destination?'↗':'·'}</span></${destination?'a':'div'}>`}).join('')}
function hrefFor(link){const host=location.hostname;const proto=location.protocol==='https:'?'https:':'http:';const path=String(link.path||'/');if(link.url){try{const u=new URL(link.url);if(!['http:','https:'].includes(u.protocol))return null;return u.href}catch{return null}}
 if(link.port===''||link.port===null)return null;
 const port=link.port?':'+link.port:'';
 return `${proto}//${host}${port}${path.startsWith('/')?path:'/'+path}`;
}
async function renderHome(){const rid=renderId;$('#page').innerHTML=title('YOUR PRIVATE AIRSPACE','Your airspace, in focus.','One place for your receiver, your history and the patterns hidden inside it.',`<button class="btn" id="reloadHome">${icon('refresh')} Refresh</button>`)+`
 <section class="hero"><div class="hero-content"><span class="eyebrow">YOUR RECEIVER · LIVE INSIGHT</span><h2>Every aircraft tells<br>part of the story.</h2><p>Explore your own ADS-B observations, see changing traffic patterns and open your existing tools in one click.</p><a href="#explore" class="btn">Explore your data ${icon('chevron')}</a></div><div class="hero-stat"><div class="hero-number" id="heroLive">—</div><small>Last sampled count</small></div></section>
 <div class="stat-grid" id="homeStats">${[1,2,3,4].map(()=>stat('Loading','—','Reading database')).join('')}</div>
 ${section('Your applications','All shortcuts use this device’s current hostname, including Tailscale addresses.',`<a class="section-link" href="#settings">Edit shortcuts →</a>`)}
 <div class="launch-grid">${links()}</div>
 ${section('A closer look','Your recent observation pattern and the latest collection status.',`<a class="section-link" href="#explore">Open explorer →</a>`)}
 <div class="grid-two"><div class="panel"><div class="panel-top"><div><h3 class="panel-title">Last 24 hours</h3><p class="panel-subtitle">Hourly observations recorded</p></div><span class="chip aqua">Aerodrome</span></div><div id="homeChart">${loading()}</div></div><div class="panel"><div class="panel-top"><div><h3 class="panel-title">Collection health</h3><p class="panel-subtitle">Read-only database status</p></div>${icon('shield')}</div><div id="homeHealth">${loading()}</div></div></div>
 <div class="foot"><span>Private by design · Data sourced from your own Aerodrome database</span><span>Europe/London time</span></div>`;
 $('#reloadHome').onclick=()=>renderHome();
 try{
   const d=await api('/api/overview');if(rid!==renderId)return;latestOverview=d;setStatus(d);
   $('#heroLive').textContent=d.live_count===null?'—':fmt(d.live_count);
   $('#homeStats').innerHTML=stat('Aircraft today',fmt(d.unique_today),'Unique ICAO identifiers','plane')+stat('Observations today',fmt(d.observations_today),'10-second polling records (approx.)','activity')+stat('Peak concurrent',fmt(d.peak_today),'Highest minute sample today','bars')+stat('Aircraft all time',fmt(d.total_aircraft),'Since monitoring began','radar');
   const projected=d.age_seconds>180?'Receiving may be delayed':'Receiving normally';
   $('#homeHealth').innerHTML=`<div class="summary-row"><div class="summary-item"><span>Last observation</span><strong style="font-size:14px">${esc(when(d.last_sighting))}</strong></div><div class="summary-item"><span>Database size</span><strong>${bytes(d.db_size_bytes)}</strong></div></div><div class="detail-grid" style="grid-template-columns:1fr 1fr"><div class="detail-item"><small>First observation</small><strong>${esc(when(d.first_sighting,{year:undefined}))}</strong></div><div class="detail-item"><small>Observations stored</small><strong>${fmt(d.raw_observations)}</strong></div></div><div class="notice ${d.fresh?'success-note':''}"><strong>${d.fresh?'Data is current':'Possible delay'}.</strong> ${esc(projected)}. A missing observation does not necessarily mean the receiver was offline.</div><a href="#database" class="btn small">${icon('database')} Inspect database</a>`;
 }catch(e){if(rid!==renderId)return;$('#homeStats').innerHTML=safeError(e);$('#homeHealth').innerHTML=safeError(e)}
 try{const a=await api('/api/analytics',{period:'last_24h',metric:'observations',bucket:'hour'});if(rid!==renderId)return;$('#homeChart').innerHTML=renderChart(a.series,'line',{height:255,mini:true});hookChart($('#homeChart'),a.series,'hour');}catch(e){if(rid===renderId)$('#homeChart').innerHTML=safeError(e)}
}
function queryArgs(groupOverride){return {period:state.period,metric:state.metric,bucket:groupOverride||state.bucket,
 category:state.category,type:state.type,airline:state.airline,icao:state.icao,
 amount:state.amount,unit:state.unit,start:state.start,end:state.end}}
function field(label,element){return `<label class="field"><span>${esc(label)}</span>${element}</label>`}
const presets=[['last_24h','Last 24 hours'],['last_46h','Last 46 hours'],['last_7d','Last 7 days'],['last_30d','Last 30 days'],['last_90d','Last 90 days'],['last_365d','Last 365 days'],['today','Today'],['yesterday','Yesterday'],['this_week','This week'],['this_month','This month'],['this_year','This year'],['all','All recorded time'],['rolling','Rolling duration…'],['custom','Custom range…']];
const groups=[['auto','Automatic'],['hour','Per hour'],['day','Per day'],['week','Per week'],['month','Per month'],['year','Per year'],['weekday','Average weekday'],['hour_of_day','Average hour of day'],['month_of_year','Average month of year']];
const opts=(options,chosen)=>options.map(([val,text])=>`<option value="${esc(val)}" ${chosen===val?'selected':''}>${esc(text)}</option>`).join('');
function metrics(){return `<div class="segmented" role="group" aria-label="Measurement">${[['flights','Flights'],['aircraft','Aircraft'],['observations','Observations']].map(([k,v])=>`<button data-metric="${k}" class="${state.metric===k?'on':''}" type="button">${v}</button>`).join('')}</div>`}
function controls(extra=false){return `<div class="control-card"><div class="control-grid">
 ${field('Measurement',metrics())}
 ${field('Time period',`<select id="period">${opts(presets,state.period)}</select>`)}
 ${field('Group by',`<select id="bucket">${opts(groups,state.bucket)}</select>`)}
 ${field('Aviation',`<select id="category">${opts([['all','All aviation'],['commercial','Commercial'],['general_aviation','General aviation'],['military','Military'],['helicopter','Helicopters'],['unknown','Unknown']],state.category)}</select>`)}
 ${field('Aircraft ICAO (optional)',`<input id="icao" placeholder="All aircraft" value="${esc(state.icao==='all'?'':state.icao)}" spellcheck="false" maxlength="12">`)}
 </div><div class="custom-controls ${state.period==='rolling'?'':'hidden'}" id="rollingBox">
 ${field('Last',`<input type="number" id="amount" min="1" max="100000" value="${esc(state.amount)}">`)}
 ${field('Unit',`<select id="unit">${opts([['hours','Hours'],['days','Days'],['weeks','Weeks']],state.unit)}</select>`)}
 </div><div class="custom-controls ${state.period==='custom'?'':'hidden'}" id="customBox">
 ${field('From (UK time)',`<input type="datetime-local" id="customStart" value="${esc(state.start)}">`)}
 ${field('To (UK time)',`<input type="datetime-local" id="customEnd" value="${esc(state.end)}">`)}
 </div><div class="secondary-controls">
 ${field('Aircraft type',`<select id="aircraftType"><option value="all">All aircraft types</option></select>`)}
 ${field('Airline / operator',`<select id="airline"><option value="all">All airlines</option></select>`)}
 <button class="btn primary" id="applyFilters">${icon('chart')} Analyse</button>
 <button class="btn" id="resetFilters">Reset</button>
 ${extra?`<button class="btn" id="saveView">${icon('bookmark')} Save view</button>`:''}
 </div><div class="control-hint">${icon('info',13)} Exact times are recorded in UK local time. Historical analysis uses Aerodrome's hourly summaries.</div></div>`;
}
function collectControls(){state.period=$('#period')?.value||state.period;state.bucket=$('#bucket')?.value||state.bucket;state.category=$('#category')?.value||state.category;state.amount=Number($('#amount')?.value||state.amount);state.unit=$('#unit')?.value||state.unit;state.start=$('#customStart')?.value||state.start;state.end=$('#customEnd')?.value||state.end;state.type=$('#aircraftType')?.value||'all';state.airline=$('#airline')?.value||'all';state.icao=($('#icao')?.value||'').trim().toLowerCase()||'all';persist()}
function initControls(refresh,extra=false){
 $$('[data-metric]').forEach(b=>b.onclick=()=>{collectControls();state.metric=b.dataset.metric;persist();refresh()});
 $('#period').onchange=()=>{const p=$('#period').value;$('#rollingBox').classList.toggle('hidden',p!=='rolling');$('#customBox').classList.toggle('hidden',p!=='custom');};
 $('#applyFilters').onclick=()=>{collectControls();refresh()};
 $('#resetFilters').onclick=()=>{const metric=state.metric;Object.assign(state,{...defaults,metric});persist();refresh()};
 if(extra&&$('#saveView'))$('#saveView').onclick=()=>{
  collectControls();const name=prompt('Name this saved analysis view:');if(!name)return;
  let views=[];try{views=JSON.parse(localStorage.getItem(savedViewsKey))||[]}catch{}
  views=[...views.filter(v=>v.name!==name),{name:name.slice(0,50),query:queryArgs(),saved:Date.now()}].slice(-20);
  localStorage.setItem(savedViewsKey,JSON.stringify(views));toast('View saved', 'Saved in this browser.');renderSavedViews();
 };
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
function renderSavedViews(){const place=$('#savedViews');if(!place)return;let views=[];try{views=JSON.parse(localStorage.getItem(savedViewsKey))||[]}catch{}
 place.innerHTML=views.length?views.map((v,i)=>`<button class="chip aqua" data-view="${i}">${icon('bookmark',12)} ${esc(v.name)}</button>`).join(' '):'<span class="muted tiny">No saved views yet. Save your favourite filters and time groupings.</span>';
 $$('[data-view]',place).forEach(b=>b.onclick=()=>{Object.assign(state,views[+b.dataset.view].query);persist();renderExplore()});
}
function renderChart(series,kind='line',{height=315,mini=false,color='aqua'}={}){
 if(!series?.length||series.every(x=>!Number(x.value)))return `<div class="chart-empty">No observations in this period. Try another range.</div>`;
 const n=series.length;const width=Math.max(mini?630:730, Math.min(20000,(kind==='bar'?n*22:n*12)+80));
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
   shape=series.map((s,i)=>`<rect class="chart-bar" data-index="${i}" x="${x(i)-barWidth/2}" y="${y(s.value)}" width="${barWidth}" height="${Math.max(0,T+plotH-y(s.value))}" rx="${Math.min(3,barWidth/4)}" style="fill:${stroke}"/>`).join('');
 }else{
   const coords=series.map((s,i)=>[x(i),y(s.value)]);
   const path=coords.map(([xx,yy],i)=>`${i===0?'M':'L'}${xx.toFixed(1)} ${yy.toFixed(1)}`).join(' ');
   shape=`<path class="chart-area" d="${path} L${x(n-1)} ${T+plotH} L${x(0)} ${T+plotH} Z"/><path class="chart-line" d="${path}" style="stroke:${stroke}"/>`;
   if(n<80)shape+=coords.map(([xx,yy],i)=>`<circle class="chart-point" data-index="${i}" cx="${xx}" cy="${yy}" r="3.5" style="fill:${stroke}"/>`).join('');
 }
 const labels=Math.min(n,mini?6:8),skip=Math.max(1,Math.ceil(n/labels));
 return `<div class="chart-shell"><div class="chart-scroll"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Interactive chart with ${n} time buckets">
   <defs><linearGradient id="chartfade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#31dfc1" stop-opacity=".28"/><stop offset="1" stop-color="#31dfc1" stop-opacity="0"/></linearGradient></defs>
   ${ticks.map(t=>`<line class="chart-gridline" x1="${L}" x2="${W-R}" y1="${y(t)}" y2="${y(t)}"/><text class="chart-axis" x="${L-9}" y="${y(t)+3}" text-anchor="end">${fmt(t,0)}</text>`).join('')}
   ${series.map((s,i)=>i%skip===0||i===n-1?`<text class="chart-axis" text-anchor="middle" x="${x(i)}" y="${H-12}">${esc(short(s.label,mini?9:14))}</text>`:'').join('')}
   ${shape}${series.map((s,i)=>`<rect class="chart-hit" data-index="${i}" x="${Math.max(L,x(i)-plotW/Math.max(n,1)/2)}" y="${T}" width="${Math.max(5,plotW/Math.max(n,1))}" height="${plotH}"/>`).join('')}
   </svg></div><div class="chart-tooltip hidden" role="status"></div></div>`;
}
function hookChart(container,series,group,drill=true){if(!container||!series)return;const tip=$('.chart-tooltip',container);const wrap=$('.chart-shell',container);if(!tip||!wrap)return;
 $$('.chart-hit',container).forEach(hit=>{
  const index=+hit.dataset.index;
  hit.addEventListener('pointermove',ev=>{
    const s=series[index];tip.innerHTML=`${esc(s.label)}<strong>${fmt(s.value,2)}</strong>${s.samples?`<span class="muted">${s.samples} occurrences</span>`:''}`;
    tip.classList.remove('hidden');const box=wrap.getBoundingClientRect();tip.style.left=Math.min(box.width-155,Math.max(0,ev.clientX-box.left+8))+'px';tip.style.top=Math.max(45,ev.clientY-box.top)+'px';
  });
  hit.addEventListener('pointerleave',()=>tip.classList.add('hidden'));
  if(drill&&['year','month','week','day','hour'].includes(group))hit.addEventListener('click',()=>drillInto(series[index],group));
 });
}
function ukDatetime(iso){const d=new Date(iso);return d.toLocaleString('sv-SE',{timeZone:'Europe/London'}).replace(' ','T').slice(0,16)}
function drillInto(point,group){
 const key=point.key;let from,to,next;
 if(group==='year'){from=`${key}-01-01T00:00`;to=`${(+key+1)}-01-01T00:00`;next='month'}
 else if(group==='month'){const [y,m]=key.split('-').map(Number);from=`${key}-01T00:00`;to=m===12?`${y+1}-01-01T00:00`:`${y}-${String(m+1).padStart(2,'0')}-01T00:00`;next='day'}
 else if(group==='week'){from=key+'T00:00';const x=new Date(key+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+7);to=x.toISOString().slice(0,10)+'T00:00';next='day'}
 else if(group==='day'){from=key+'T00:00';const x=new Date(key+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+1);to=x.toISOString().slice(0,10)+'T00:00';next='hour'}
 else if(group==='hour'){from=ukDatetime(key);const x=new Date(Date.parse(key)+3600*1000);to=ukDatetime(x.toISOString());next='hour'}
 if(from&&to){state.period='custom';state.start=from;state.end=to;state.bucket=next;persist();location.hash='#explore';if(currentPage==='explore')renderExplore();toast('Drilled into '+point.label,'Click Reset to return to your normal time range.');}
}
function donut(items){if(!items?.length)return `<div class="empty">No breakdown available.</div>`;
 const top=items.slice(0,5),total=items.reduce((a,x)=>a+Number(x.value),0);
 if(total<=0)return '<div class="empty">No classifications available for this selection.</div>';
 const colors=['#31dfc1','#6795ff','#cb8efa','#f1b970','#e37d92','#52647d'];let at=0;
 const portions=top.map((s,i)=>{const p=s.value/total*100;const segment=`${colors[i]} ${at.toFixed(2)}% ${(at+p).toFixed(2)}%`;at+=p;return segment});
 if(at<100)portions.push(`${colors[5]} ${at.toFixed(2)}% 100%`);
 return `<div class="donut-layout"><div class="donut" style="background:conic-gradient(${portions.join(',')})"><div class="donut-center"><strong>${fmt(total)}</strong><span>${esc(state.metric)}</span></div></div>
 <div class="legend">${top.map((x,i)=>`<div class="legend-row"><span title="${esc(x.name)}"><i class="legend-swatch" style="background:${colors[i]}"></i>${esc(short(x.name,21))}</span><strong>${pct(x.value,total)}</strong></div>`).join('')}${top.length<items.length?`<div class="legend-row"><span><i class="legend-swatch" style="background:${colors[5]}"></i>Other</span><strong>${pct(total-top.reduce((a,x)=>a+x.value,0),total)}</strong></div>`:''}</div></div>`;
}
function breakdownList(items,field,color='aqua'){
 if(!items?.length)return '<div class="empty">No information available for this period.</div>';
 const top=items.slice(0,10),max=top[0].value||1;
 return `<div class="breakdown-list">${top.map(s=>`<div class="breakdown-row" title="Filter by ${esc(s.name)}" data-filter="${esc(field)}" data-value="${esc(s.name)}"><div><div class="breakdown-name">${esc(s.name)}</div><div class="bar-track"><div class="bar-fill ${color==='aqua'?'':color}" style="width:${Math.max(0,s.value/max*100)}%"></div></div></div><strong class="breakdown-value">${fmt(s.value)}</strong></div>`).join('')}</div>`;
}
function bindBreakdowns(){ $$('[data-filter]').forEach(el=>el.onclick=()=>{const f=el.dataset.filter,value=el.dataset.value;if(!['type','airline','category'].includes(f))return;state[f]=value;persist();renderExplore();toast('Filter applied',`${value} — click Reset to clear.`)}) }
function summaryFor(a){const unit={flights:'estimated visits',aircraft:'unique aircraft',observations:'observation records'}[a.metric];
 return `<div class="summary-row"><div class="summary-item"><span>Period total</span><strong>${fmt(a.total)}</strong><div class="sub">${unit}</div></div><div class="summary-item"><span>${a.aggregation_label}</span><strong>${fmt(a.average,2)}</strong><div class="sub">Average per chart bucket</div></div><div class="summary-item"><span>Highest bucket</span><strong>${fmt(a.peak,2)}</strong><div class="sub">${esc(a.bucket.replaceAll('_',' '))}</div></div><div class="summary-item"><span>Distinct aircraft</span><strong>${fmt(a.unique_aircraft)}</strong><div class="sub">Across the selected period</div></div></div>`;
}
async function renderExplore(){const rid=++renderId;currentAnalytics=null;
 $('#page').innerHTML=title('DEEP ANALYSIS','Explore your data','Choose a measurement, a date range and a grouping. Every chart and breakdown responds to your filters.')+
 controls(true)+`<div id="savedViews" style="display:flex;flex-wrap:wrap;gap:7px;margin:-2px 0 18px"></div><div class="stat-grid" id="exploreStats"></div>
 ${section('Traffic over time','Click a data point to zoom into that year, month, week or day.',`<div class="chart-actions"><button class="btn small" id="lineSwitch">${icon('chart')} Line</button><button class="btn small" id="barSwitch">${icon('bars')} Bars</button></div>`)}
 <div class="panel"><div class="panel-top"><div><h3 class="panel-title" id="chartLabel">Aircraft activity</h3><p class="panel-subtitle" id="chartMeta">Europe/London · Aerodrome hourly rollups</p></div><span class="chip aqua" id="pointCount">—</span></div><div id="exploreChart">${loading()}</div><div class="chart-footer"><span>Hover to inspect · click a point to drill down</span><span>All results reflect your receiver only</span></div></div>
 ${section('What makes up your airspace?','These distributions update with your time period, measurement and filters.')}
 <div class="grid-three"><div class="panel"><div class="panel-top"><div><h3 class="panel-title">Type of aviation</h3><p class="panel-subtitle">Commercial / GA / military / other</p></div></div><div id="categoryDonut">${loading()}</div></div>
 <div class="panel"><div class="panel-top"><div><h3 class="panel-title">Aircraft types</h3><p class="panel-subtitle">Filter by type in bars mode</p></div><button class="btn small" id="typeVizSwitch" type="button">${state.typeViz==='pie'?'Show bars':'Show pie'}</button></div><div id="typeBars">${loading()}</div></div>
 <div class="panel"><div class="panel-top"><div><h3 class="panel-title">Airline / operator</h3><p class="panel-subtitle">Filter by operator in bars mode</p></div><button class="btn small" id="airlineVizSwitch" type="button">${state.airlineViz==='pie'?'Show bars':'Show pie'}</button></div><div id="airlineBars">${loading()}</div></div></div>
 <div class="notice"><strong>Sample coverage:</strong> Your results may be biased if Aerodrome was not running throughout the selected period. Open the chart to see the percentage of expected minute samples. It is an estimate of data availability, not proven receiver uptime.</div>
 <div class="notice"><strong>How numbers are calculated:</strong> “Flights” means estimated separate receiver visits (30-minute gap or callsign change). Hourly rollups can merge short repeat visits; observation counts may include partial boundary hours. “Aircraft” means distinct ICAO identifiers, not flight journeys. Unknown airline/category data is never silently guessed.</div>
 <div class="foot"><span>Analytics drawn from Aerodrome · No duplicated observations</span><span>Times shown in Europe/London</span></div>`;
 initControls(renderExplore,true);renderSavedViews();populateFilters();
 $('#lineSwitch').onclick=()=>{state.chart='line';persist();if(currentAnalytics)drawCurrentChart()};
 $('#barSwitch').onclick=()=>{state.chart='bar';persist();if(currentAnalytics)drawCurrentChart()};
 $('#exploreStats').innerHTML=Array.from({length:4},()=>stat('Loading','—','Working from hourly data')).join('');
 try{
  const a=await api('/api/analytics',queryArgs());if(rid!==renderId)return;
  currentAnalytics=a;fillFilterOptions(a);
  $('#exploreStats').innerHTML=stat('Selected total',fmt(a.total),a.metric==='flights'?'Estimated flight visits':a.metric==='aircraft'?'Unique ICAO identifiers':'Observation records','plane')+
   stat('Average per bucket',fmt(a.average,2),a.aggregation_label,'activity')+
   stat('Busiest bucket',fmt(a.peak,2),`Grouped by ${a.bucket.replaceAll('_',' ')}`,'bars')+
   stat('Unique aircraft',fmt(a.unique_aircraft),'Seen during selection','radar');
  $('#chartLabel').textContent={flights:'Estimated flight visits',aircraft:'Unique aircraft',observations:'Recorded observations'}[a.metric];
  $('#chartMeta').textContent=`${when(a.start)} – ${when(a.end)} · ${a.aggregation_label}`;
  $('#pointCount').textContent=`${a.series.length} points`;
  if(a.coverage){$('#chartMeta').textContent+=` · ${a.coverage.sample_ratio}% minute sample coverage (proxy)`;}
  drawCurrentChart();
  $('#categoryDonut').innerHTML=donut(a.breakdowns.category);
  function showBreakdowns(){
   $('#typeBars').innerHTML=state.typeViz==='pie'?donut(a.breakdowns.type):breakdownList(a.breakdowns.type,'type','blue');
   $('#airlineBars').innerHTML=state.airlineViz==='pie'?donut(a.breakdowns.airline):breakdownList(a.breakdowns.airline,'airline','pink');
   $('#typeVizSwitch').textContent=state.typeViz==='pie'?'Show bars':'Show pie';
   $('#airlineVizSwitch').textContent=state.airlineViz==='pie'?'Show bars':'Show pie';
   bindBreakdowns();
  }
  $('#typeVizSwitch').onclick=()=>{state.typeViz=state.typeViz==='pie'?'bars':'pie';persist();showBreakdowns()};
  $('#airlineVizSwitch').onclick=()=>{state.airlineViz=state.airlineViz==='pie'?'bars':'pie';persist();showBreakdowns()};
  showBreakdowns();
 }catch(e){if(rid!==renderId)return;$('#exploreStats').innerHTML='';$('#exploreChart').innerHTML=safeError(e);['categoryDonut','typeBars','airlineBars'].forEach(id=>$('#'+id).innerHTML='<p class="muted">Not available.</p>')}
}
function drawCurrentChart(){if(!currentAnalytics)return;$('#exploreChart').innerHTML=renderChart(currentAnalytics.series,state.chart||'line');hookChart($('#exploreChart'),currentAnalytics.series,currentAnalytics.bucket);}

function renderWeekBars(series,shortLabels=false){if(!series?.length)return '<div class="empty">No data available.</div>';
 const max=Math.max(...series.map(x=>x.value),1);
 return `<div class="pattern-bars">${series.map((s,i)=>`<div class="pattern-col" title="${esc(s.label)}: ${fmt(s.value,2)} average from ${s.samples} occurrences"><strong class="tiny muted">${fmt(s.value,1)}</strong><div class="pattern-bar" style="height:${Math.max(2,150*s.value/max)}px"></div><small>${esc(shortLabels?String(s.label).slice(0,3):s.label)}</small></div>`).join('')}</div>`;
}
function renderHeatmap(cells){if(!cells?.length)return '<div class="empty">No hourly observations.</div>';
 const max=Math.max(1,...cells.map(x=>x.value)),colorScale=v=>{
  if(!v)return 'var(--panel2)';const f=.12+.85*Math.pow(v/max,.65);return `rgba(49,223,193,${f.toFixed(3)})`;
 };
 const cols=[...Array(24)].map((_,h)=>`<div class="heat-label">${h%3===0?String(h).padStart(2,'0'):''}</div>`).join('');
 const weekdays=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
 return `<div class="heat-outer"><div class="heatmap"><span></span>${cols}${weekdays.map((d,wd)=>`<span class="heat-day">${d}</span>${cells.filter(x=>x.weekday===wd).map(x=>`<div class="heat-cell" tabindex="0" title="${d} ${String(x.hour).padStart(2,'0')}:00 — avg ${fmt(x.value,2)}, ${x.samples} hours" style="background:${colorScale(x.value)}"></div>`).join('')}`).join('')}</div></div><div class="heat-legend"><span>Less busy</span>${[.08,.24,.43,.65,.85].map(x=>`<i style="background:rgba(49,223,193,${x})"></i>`).join('')}<span>More busy</span></div>`;
}
async function renderPatterns(){const rid=++renderId;
 $('#page').innerHTML=title('ACTIVITY PATTERNS','Find your busiest moments','Go beyond total counts. Discover which weekdays and hours consistently bring the most traffic.')+
 controls(false)+`<div class="panel"><div class="panel-top"><div><h2 class="panel-title">Day × hour heatmap</h2><p class="panel-subtitle">Average activity for each weekday/hour combination across your chosen range</p></div><span class="chip aqua">UK local time</span></div><div id="heatmap">${loading()}</div></div>
 ${section('Recurring rhythms','Averages normalised by the number of eligible days or hours, not cumulative totals.')}
 <div class="pattern-subgrid"><div class="panel"><h3 class="panel-title">Average by weekday</h3><p class="panel-subtitle">Mean daily traffic, Monday through Sunday</p><div id="weekdayPattern">${loading()}</div></div>
 <div class="panel"><h3 class="panel-title">Average by hour</h3><p class="panel-subtitle">Mean hourly traffic across all matching dates</p><div id="hourPattern">${loading()}</div></div></div>
 <div class="notice"><strong>Interpretation:</strong> Only complete calendar periods with at least 70% of expected Aerodrome minute samples contribute to recurring averages. Missing history is not interpreted as zero traffic. A blank pattern needs more complete historical data.</div>`;
 initControls(renderPatterns);populateFilters();
 try{const a=await api('/api/patterns',queryArgs());if(rid!==renderId)return;
 $('#heatmap').innerHTML=renderHeatmap(a.heatmap);
 $('#weekdayPattern').innerHTML=renderWeekBars(a.weekday,true);
 $('#hourPattern').innerHTML=renderChart(a.hourly,'bar',{height:225});hookChart($('#hourPattern'),a.hourly,'hour_of_day',false);
 }catch(e){if(rid!==renderId)return;['heatmap','weekdayPattern','hourPattern'].forEach(x=>$('#'+x).innerHTML=safeError(e))}
}
function comparisonFields(){return `<div class="secondary-controls" style="margin:0 0 16px;border:none;padding:0">
 ${field('Compare against',`<select id="comparison">${opts([['previous','An earlier equivalent period'],['year_ago','Same dates last year'],['custom','Another custom date range']],state.comparison)}</select>`)}
 <label class="field" id="offsetField"><span>Periods back</span><select id="offset">${opts([['1','1 period earlier'],['2','2 periods earlier'],['3','3 periods earlier'],['4','4 periods earlier'],['7','7 periods earlier'],['12','12 periods earlier']],String(state.offset))}</select></label>
 </div><div class="custom-controls ${state.comparison==='custom'?'':'hidden'}" id="otherBox" style="margin-bottom:15px">
 ${field('Compare from (UK)',`<input type="datetime-local" id="otherStart" value="${esc(state.other_start)}">`)}
 ${field('Compare to (UK)',`<input type="datetime-local" id="otherEnd" value="${esc(state.other_end)}">`)}
 </div>`;}
function overlayChart(left,right){const A=left?.series||[],B=right?.series||[];
 if(!A.length||!B.length)return '<div class="empty">Not enough data to compare these windows.</div>';
 const n=Math.max(A.length,B.length),W=Math.max(760,Math.min(n*12+80,12000)),H=320,L=57,R=20,T=21,bot=43;
 const ymax=Math.max(1,...A.map(x=>x.value),...B.map(x=>x.value));const xx=i=>L+(n===1?0:i/(n-1)*(W-L-R));const yy=v=>T+(1-v/ymax)*(H-T-bot);
 const pts=a=>a.map((v,i)=>`${i?'L':'M'}${xx(i).toFixed(1)} ${yy(v.value).toFixed(1)}`).join(' ');
 const ticks=Array.from({length:5},(_,i)=>i*ymax/4);
 return `<div class="chart-shell"><div class="chart-scroll"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Comparison of two historical traffic series">
  ${ticks.map(t=>`<line class="chart-gridline" x1="${L}" y1="${yy(t)}" x2="${W-R}" y2="${yy(t)}"/><text class="chart-axis" x="${L-7}" y="${yy(t)+3}" text-anchor="end">${fmt(t)}</text>`).join('')}
  <path d="${pts(A)}" fill="none" stroke="var(--aqua)" stroke-width="2.4"/>
  <path d="${pts(B)}" fill="none" stroke="var(--blue)" stroke-width="2.4" stroke-dasharray="6,4"/>
  ${Array.from({length:6},(_,i)=>`<text x="${L+i*(W-L-R)/5}" y="${H-11}" class="chart-axis" text-anchor="middle">${fmt(i*100/5)}%</text>`).join('')}
 </svg></div></div><div class="chart-footer"><span><i class="legend-swatch" style="background:var(--aqua)"></i>Selected period</span><span><i class="legend-swatch" style="background:var(--blue)"></i>Comparison period</span><span>Horizontal axis = progress through each period</span></div>`;
}
async function renderCompare(){const rid=++renderId;
 $('#page').innerHTML=title('PERIOD COMPARISON','Compare any two periods','Measure changes fairly across days, weeks, months or any two custom time windows.')+
 controls(false)+`<div class="control-card">${comparisonFields()}<button class="btn primary" id="runComparison">${icon('compare')} Compare periods</button></div>
 <div id="compareResults">${loading()}</div><div class="notice"><strong>Fair comparisons:</strong> Today versus yesterday compares equivalent elapsed portions of the day. Calendar weeks/months/years are matched to the equivalent local calendar date where possible. Periods with missing receiver data can be misleading.</div>`;
 initControls(renderCompare);populateFilters();
 if(state.comparison==='year_ago')$('#offsetField').classList.add('hidden');
 $('#comparison').onchange=()=>{const c=$('#comparison').value;$('#offsetField').classList.toggle('hidden',c==='custom'||c==='year_ago');$('#otherBox').classList.toggle('hidden',c!=='custom')};
 $('#runComparison').onclick=()=>{collectControls();state.comparison=$('#comparison').value;state.offset=+($('#offset').value||1);state.other_start=$('#otherStart')?.value||'';state.other_end=$('#otherEnd')?.value||'';persist();renderCompare()};
 try{const args={...queryArgs(),comparison:state.comparison,offset:state.offset,other_start:state.other_start,other_end:state.other_end};
   const d=await api('/api/compare',args);if(rid!==renderId)return;
   const dir=d.difference>0?'positive':d.difference<0?'negative':'',txt=d.change_percent===null?'Insufficient comparable baseline':`${d.change_percent>0?'+':''}${fmt(d.change_percent,1)}% compared`;
   const mx=Math.max(d.left.total,d.right.total,1);
   $('#compareResults').innerHTML=`<div class="comparison-header">
     <div class="compare-period"><span class="tiny muted"><i class="period-color"></i>Selected period</span><div class="big">${fmt(d.left.total)}</div><div class="tiny muted">${when(d.left.start)} – ${when(d.left.end)}</div></div>
     <div class="compare-period other"><span class="tiny muted"><i class="period-color"></i>Comparison period</span><div class="big">${fmt(d.right.total)}</div><div class="tiny muted">${when(d.right.start)} – ${when(d.right.end)}</div></div>
   </div><div class="panel" style="margin-top:16px"><div class="panel-top"><h3 class="panel-title">Difference</h3><span class="chip ${dir==='positive'?'aqua':dir==='negative'?'red':''}">${esc(txt)}</span></div><div class="delta ${dir}" style="font-size:24px;margin:0 0 14px">${d.difference>0?'+':''}${fmt(d.difference)} ${esc(state.metric)}</div>
   <div class="compare-tracks"><span class="muted">Selected</span><div class="compare-track"><div class="compare-fill" style="width:${d.left.total/mx*100}%"></div></div><span class="muted">Comparison</span><div class="compare-track"><div class="compare-fill other" style="width:${d.right.total/mx*100}%"></div></div></div></div>
   ${section('How traffic changed','The lines are aligned by relative progress through each window, not by absolute date.')}
   <div class="panel">${overlayChart(d.left,d.right)}</div>
   <div class="notice"><strong>Availability check:</strong> ${fmt(d.left.coverage.sample_ratio,1)}% minute samples in the selected period versus ${fmt(d.right.coverage.sample_ratio,1)}% in the comparison period. Treat low coverage as a possible data gap.</div>
   ${section('Averages and extremes')}
   <div class="grid-two"><div class="panel"><h3 class="panel-title">Selected period</h3>${summaryFor(d.left)}</div><div class="panel"><h3 class="panel-title">Comparison period</h3>${summaryFor(d.right)}</div></div>`;
 }catch(e){if(rid===renderId)$('#compareResults').innerHTML=safeError(e)}
}
async function renderAircraft(){const rid=++renderId;
 $('#page').innerHTML=title('AIRCRAFT HISTORY','Every aircraft, a history','Search for a registration, callsign, ICAO hex, type or operator. View the exact observations stored by Aerodrome.')+
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
 ${section('Recent raw sightings',`Latest ${d.sightings.length} observations. These are not separate flights.`)}
 <div class="panel"><div class="table-wrap"><table><thead><tr><th>Recorded</th><th>Callsign</th><th>Latitude</th><th>Longitude</th><th>Altitude</th><th>Speed</th><th>Squawk</th></tr></thead><tbody>${d.sightings.map(s=>`<tr><td>${when(s.seen_at)}</td><td>${esc(s.callsign||'—')}</td><td>${esc(s.lat??'—')}</td><td>${esc(s.lon??'—')}</td><td>${esc(s.altitude??'—')}</td><td>${esc(s.speed??'—')}</td><td>${esc(s.squawk??'—')}</td></tr>`).join('')}</tbody></table></div></div>`;
 target.scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){target.innerHTML=safeError(e)}
}
let dbPage=1;
async function renderDatabase(){const rid=++renderId;
 $('#page').innerHTML=title('READ-ONLY DATABASE','Explore the raw data','Inspect real Aerodrome records without changing, deleting or copying its database.',`<span class="chip aqua">${icon('shield',14)} Read-only</span>`)+
 `<div class="control-card"><div class="secondary-controls" style="border:0;margin:0;padding:0">
 ${field('Database table',`<select id="dbTable"><option>Loading tables…</option></select>`)}
 ${field('Search ICAO / callsign / operator',`<input type="search" id="dbSearch" placeholder="Optional filter">`)}
 <button class="btn primary" id="dbApply">${icon('search')} Search</button><button class="btn" id="dbExport">${icon('download')} Export CSV</button>
 </div><div class="control-hint">CSV export is capped at 5,000 matching rows per request, to avoid overloading the receiver. Database tables are whitelisted; arbitrary SQL execution is disabled.</div></div>
 <div class="panel"><div class="panel-top"><div><h3 class="panel-title" id="dbTitle">Stored observations</h3><p class="panel-subtitle">Recent records first. Scroll horizontally for more columns.</p></div><span class="chip" id="dbPageInfo">—</span></div><div id="dbResults">${loading()}</div>
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
function settingsLinks(){return getLinks().map((it,i)=>`<div class="settings-entry" data-linkindex="${i}" style="margin:0 0 12px;padding-bottom:12px;border-bottom:1px solid var(--line)">
  ${field('Shortcut name',`<input class="link-name" value="${esc(it.name)}" maxlength="50">`)}
  ${field('Port (leave blank to disable)',`<input class="link-port" value="${esc(it.port??'')}" placeholder="e.g. 5173" inputmode="numeric">`)}
  ${field('Path',`<input class="link-path" value="${esc(it.path||'/')}" placeholder="/">`)}
  ${field('Optional full URL',`<input class="link-url" value="${esc(it.url||'')}" placeholder="Leave blank to use this device">`)}
 </div>`).join('')}
function updateBox(){return `<div class="auth-box">
  <div class="status-row" style="margin-bottom:12px"><i class="dot" id="updateDot"></i><strong id="updateHeading">Checking installation…</strong></div>
  <div class="tiny muted break-word" id="updateDetails">GitHub update status</div>
  <div style="margin-top:15px;max-width:420px">${field('Update token (shown during initial installation)',`<input type="password" id="updateToken" autocomplete="off" placeholder="Paste update token" value="${esc(sessionStorage.getItem('airspace-token')||'')}">`)}</div>
  <p class="token-note">The token is stored only for this browser tab, not saved to your permanent preferences. Never share it or expose the website directly to the public internet.</p>
  <div class="setting-actions"><button class="btn" id="checkUpdates">${icon('refresh')} Check GitHub</button><button class="btn primary" id="applyUpdate">${icon('download')} Update now</button><button class="btn" id="rollbackUpdate">Restore previous</button></div>
  <div class="tiny muted" id="updateProgress" style="margin-top:14px"></div>
 </div>`}
async function renderSettings(){const rid=++renderId;
 $('#page').innerHTML=title('PREFERENCES & SYSTEM','Settings & updates','Manage your homepage, appearance, saved views and safe GitHub updates—all from the website.')+
 `<div class="panel">${settingsRow('Appearance','Choose a theme and your preferred default measurement.',
   `<div class="settings-entry">${field('Colour theme',`<select id="settingTheme">${opts([['dark','Dark / midnight'],['light','Light / cloud']],state.theme)}</select>`)}${field('Default measurement',`<select id="settingMetric">${opts([['flights','Estimated flights'],['aircraft','Unique aircraft'],['observations','Observations']],state.metric)}</select>`)}</div><button class="btn primary" id="saveAppearance" style="margin-top:13px">Save preferences</button>`)}
 ${settingsRow('Your application shortcuts','These shortcuts open your local ADS-B tools using your current device hostname, including Tailscale.',
   `${settingsLinks()}<button class="btn primary" id="saveLinks">Save shortcuts</button><button class="btn" id="restoreLinks" style="margin-left:9px">Restore defaults</button>`)}
 ${settingsRow('GitHub updates','One-click updates after the initial GitHub checkout and service installation.',updateBox())}
 ${settingsRow('Aerodrome database','Only read operations are allowed. This website does not change retention or feeder configuration.',`<div id="databaseInfo">${loading()}</div>`)}
 ${settingsRow('About this installation','Run as a private local-only website; use Tailscale for remote access.',`<div class="tiny muted">Airspace Analytics <span class="versionValue">v1.1.0</span> · Python stdlib web server · SVG charts · Europe/London.<br>Use GitHub for source-code updates. No cloud database or telemetry is required.</div>`)}
 </div>`;
 $('#saveAppearance').onclick=()=>{setTheme($('#settingTheme').value);state.metric=$('#settingMetric').value;persist();toast('Preferences saved')};
 $('#saveLinks').onclick=()=>{try{let links=getLinks();const vals=$$('[data-linkindex]').map(el=>{
  const idx=+el.dataset.linkindex,port=$('.link-port',el).value.trim();const path=$('.link-path',el).value.trim()||'/';const url=$('.link-url',el).value.trim();
  if(port&&!/^\d{1,5}$/.test(port))throw Error('Ports must be numeric');
  if(port&&(Number(port)<1||Number(port)>65535))throw Error('Port must be 1–65535');
  if(url&&!/^https?:\/\//i.test(url))throw Error('Custom URLs must start with http:// or https://');
  return {...links[idx],name:$('.link-name',el).value.trim().slice(0,50)||links[idx].name,port,path,url};
 });
 putLinks(vals);toast('Shortcuts updated','Your homepage links are ready.')}catch(e){toast('Invalid shortcut',e.message,true)}
 };
 $('#restoreLinks').onclick=()=>{putLinks(defaultLinks);toast('Default shortcuts restored');renderSettings()};
 $('#updateToken').onchange=()=>sessionStorage.setItem('airspace-token',$('#updateToken').value.trim());
 $('#checkUpdates').onclick=async()=>{
  $('#updateDetails').textContent='Checking GitHub…';try{const d=await api('/api/update/check',{refresh:1});setUpdateInfo(d)}catch(e){$('#updateDetails').textContent=e.message}
 };
 $('#applyUpdate').onclick=()=>launchUpdate('apply');
 $('#rollbackUpdate').onclick=()=>launchUpdate('rollback');
 async function launchUpdate(mode){
  const token=$('#updateToken').value.trim();sessionStorage.setItem('airspace-token',token);
  if(!token){toast('Update token required','Paste your private update token to continue.',true);return}
  if(!confirm(mode==='rollback'?'Restore the previous working website version and restart only this service?':'Download the latest code from your configured GitHub repository and restart only this website?'))return;
  $('#updateProgress').textContent='Starting the updater…';
  try{const res=await fetch('/api/update/'+mode,{method:'POST',headers:{'X-Update-Token':token,'Content-Type':'application/json'},body:'{}'});
   const d=await res.json();if(!res.ok)throw Error(d.error||'Update request failed');
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
  ].map(([k,v])=>`<div class="detail-item"><small>${esc(k)}</small><strong class="break-word">${esc(v)}</strong></div>`).join('')}</div><span class="chip ${d.fresh?'aqua':'warn'}">${d.fresh?'Source updating':'Source may be stale'}</span>`;
  setUpdateInfo(u);$('#updateProgress').textContent=`Last updater result: ${s.state} — ${s.detail}`;
 }catch(e){if(rid===renderId)$('#databaseInfo').innerHTML=safeError(e)}
}
function setUpdateInfo(d){if(!$('#updateDetails'))return;
 $('#updateHeading').textContent=d.available?'New version available':d.configured?'Repository is up to date':'GitHub not yet linked';
 $('#updateDot').classList.toggle('good',d.configured&&!d.available);$('#updateDot').classList.toggle('bad',!!d.error);
 $('#updateDetails').innerHTML=`<div class="detail-grid">${[['Installed version',d.version],['Installed commit',d.local_sha||'—'],['Remote commit',d.remote_sha||'—']].map(([k,v])=>`<div class="detail-item"><small>${esc(k)}</small><strong>${esc(v)}</strong></div>`).join('')}</div>
 <span class="break-word tiny">${esc(d.repository||'Clone this project from your GitHub repository to enable in-app updates.')}</span>${d.error?`<p style="color:var(--orange)">${esc(d.error)}</p>`:''}`;
}
async function loadPage(){const hash=(location.hash||'#home').slice(1).split('?')[0];currentPage=names[hash]?hash:'home';renderId++;
 $$('.nav-link,.mobile-tabbar a').forEach(el=>el.classList.toggle('active',el.dataset.page===currentPage));
 $('#topTitle').textContent=names[currentPage];setMenu(false);
 window.scrollTo({top:0,behavior:'instant'});
 const routes={home:renderHome,explore:renderExplore,patterns:renderPatterns,compare:renderCompare,aircraft:renderAircraft,database:renderDatabase,settings:renderSettings};
 try{await routes[currentPage]()}catch(e){$('#page').innerHTML=safeError(e)}
}
async function refreshStatus(){try{const h=await api('/api/health');setStatus(h)}catch{setStatus(null)}}
function boot(){shell();window.addEventListener('hashchange',loadPage);loadPage();refreshStatus();api('/api/config').then(d=>$$('.versionValue').forEach(x=>x.textContent='v'+d.version)).catch(()=>{});activeTimer=setInterval(refreshStatus,60000)}
boot();
