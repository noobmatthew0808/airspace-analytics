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
const defaults={metric:'flights',period:'rolling',bucket:'auto',category:'all',type:'all',airline:'all',icao:'all',amount:7,unit:'days',start:'',end:'',chart:'line',theme:'dark',comparison:'previous',offset:1,other_start:'',other_end:'',typeViz:'bars',airlineViz:'bars',operatorScope:'airline'};
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
const savedViewsKey='airspace-analytics-views-v1';
// A previously paired browser stays paired across reloads without showing a
// password box each time. The updater's server-side token check remains active.
// Built-in launcher entries are deliberately independent of the analytics UI.
// Relative ports use the hostname currently serving the dashboard (also works via Tailscale).
const defaultLinks=[
 {id:'adsb-im',name:'ADSB.im',group:'stats',sub:'Receiver dashboard',port:'1099',path:'/',icon:'radar',brand:'AD',logoDomain:'adsb.im',tone:'teal'},
 {id:'skystats',name:'SkyStats',group:'stats',sub:'Receiver statistics',port:'5173',path:'/',icon:'chart',brand:'SK',logoDomain:'skystats.adsb.sixtopia.net',tone:'violet'},
 {id:'tar1090',name:'tar1090 map',group:'stats',sub:'Live aircraft map',port:'1099',path:'/map/',icon:'plane',brand:'1090',tone:'blue'},
 {id:'aerodrome',name:'Aerodrome',group:'stats',sub:'Aircraft history and live stats',port:'8000',path:'/',icon:'radar',brand:'AE',tone:'teal'},
 {id:'dozzle',name:'Dozzle',group:'stats',sub:'Container logs',port:'1094',path:'/',icon:'terminal',brand:'DZ',logoDomain:'dozzle.dev',tone:'amber'},
 {id:'fr24',name:'Flightradar24',group:'feeders',sub:'Local feeder status',port:'8754',path:'/',icon:'radar',brand:'24',logoDomain:'flightradar24.com',tone:'gold'},
 {id:'airnav',name:'AirNav Radar',group:'feeders',sub:'EXTRPI737643',url:'https://www.airnavradar.com/stations/EXTRPI737643',icon:'radar',brand:'AN',logoDomain:'airnavradar.com',tone:'green'},
 {id:'flightdeck',name:'FlightDeck',group:'feeders',sub:'Feeder account',url:'https://www.tryflightdeck.com/map/account/feeder',icon:'plane',brand:'FD',logoDomain:'tryflightdeck.com',tone:'sky'},
 {id:'planefinder',name:'Plane Finder',group:'feeders',sub:'Receiver statistics',port:'30053',path:'/stats.html',extraLabel:'Feeder map',extraUrl:'',extraPort:'30053',extraPath:'/map.html',icon:'plane',brand:'PF',logoDomain:'planefinder.net',tone:'blue'},
 {id:'adsbx',name:'ADS-B Exchange',group:'feeders',sub:'Feeder status',url:'https://www.adsbexchange.com/myip/',extraLabel:'Feeder map',extraUrl:'https://globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2',icon:'plane',brand:'AX',logoDomain:'adsbexchange.com',tone:'green'},
 {id:'flightaware',name:'FlightAware',group:'feeders',sub:'Local feeder status',port:'1093',path:'/',icon:'plane',brand:'FA',logoDomain:'flightaware.com',tone:'navy'}
];
const linksKey='airspace-analytics-links';
const linksMigration='airspace-links-v19';
function migrateLinks(){
 if(localStorage.getItem(linksMigration))return;
 try {
  const existing=JSON.parse(localStorage.getItem(linksKey));
  if(Array.isArray(existing)){
   // Keep genuine user-added links, without letting older defaults overwrite the new ports.
   const builtIn=/^(adsb\.im|aerodrome|skystats|aircraft map|receiver graphs|dozzle|flightradar24|airnav radar|flightdeck|plane finder|ads-b exchange|flightaware|tar1090 map)$/i;
   const custom=existing.filter(x=>x&&typeof x.name==='string'&&!builtIn.test(x.name.trim()))
     .map(x=>({...x,group:x.group==='feeders'?'feeders':'stats'}));
   localStorage.setItem(linksKey,JSON.stringify([...defaultLinks,...custom]));
  }else localStorage.setItem(linksKey,JSON.stringify(defaultLinks));
 }catch{localStorage.setItem(linksKey,JSON.stringify(defaultLinks))}
 localStorage.setItem(linksMigration,'1');
}
// Repair built-in links exactly once after the v1.9 launcher change.
// Preserve user-created shortcuts rather than wiping all local preferences.
function restoreV193Launcher(){
 const marker='airspace-links-v193-repaired';
 if(localStorage.getItem(marker))return;
 try{
  const previous=JSON.parse(localStorage.getItem(linksKey)||'null');
  const defaultIds=new Set(defaultLinks.map(x=>x.id));
  const defaultNames=new Set(defaultLinks.map(x=>x.name.toLowerCase()));
  const legacyNames=new Set(['aircraft map','receiver graphs','airspace analytics']);
  const added=Array.isArray(previous)?previous.filter(x=>x&&typeof x.name==='string'&&!defaultIds.has(x.id)&&!defaultNames.has(x.name.trim().toLowerCase())&&!legacyNames.has(x.name.trim().toLowerCase())):[];
  localStorage.setItem(linksKey,JSON.stringify([...defaultLinks,...added]));
 }catch{localStorage.setItem(linksKey,JSON.stringify(defaultLinks));}
 localStorage.setItem(marker,'1');
}
function getLinks(){try{migrateLinks();restoreV193Launcher();const x=JSON.parse(localStorage.getItem(linksKey));return Array.isArray(x)?x:defaultLinks}catch{return defaultLinks}}
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
const pages=[['explore','Traffic','chart'],['database','Database','database'],['settings','Settings','settings']];
const names={home:'Launcher',...Object.fromEntries(pages.map(x=>[x[0],x[1]]))};
let currentPage='home',currentChart='line',currentAnalytics=null,latestOverview=null,healthInfo=null,activeTimer=null,renderId=0;
const zoomHistory=[];
// One-time migration: old v1.5 range preferences should not replace the new yearly entry point.
if(!localStorage.getItem('airspace-v16-started')){
 Object.assign(state,{period:'all',bucket:'year',metric:'flights',type:'all',airline:'all',category:'all',icao:'all',chart:'bar',filtersEnabled:false,heatScope:'follow'});
 localStorage.setItem('airspace-v16-started','1');persist();
}
if(state.filtersEnabled===undefined)state.filtersEnabled=false;
if(!['year','month'].includes(state.heatScope))state.heatScope='year';

function setTheme(theme){document.documentElement.dataset.theme=theme||'dark';state.theme=theme;persist()}
setTheme(state.theme);

function shell(){
 $('#app').innerHTML=`<div class="overlay" id="overlay"></div><div class="layout">
   <aside class="sidebar" id="sidebar" aria-hidden="true"><span id="sidebarDot"></span><span id="sidebarTitle"></span><span id="sidebarDetail"></span><span class="versionValue"></span></aside>
   <div class="workspace"><header class="topbar streamlined-topbar">
     <div class="topbar-left">
       <a class="top-icon-link" href="/" title="Home launcher" aria-label="Home">${icon('grid',19)}</a>
       <a class="top-nav-link" href="/analytics#explore" data-page="explore">Traffic</a>
       <strong id="topTitle" class="sr-only">Traffic</strong>
     </div>
     <div class="top-actions">
       <span class="sr-only"><span id="topDot"></span><span id="topStatus"></span></span>
       <a class="top-icon-link top-settings" href="/analytics#settings" data-page="settings" title="Settings" aria-label="Settings">${icon('settings',20)}</a>
     </div>
   </header><main class="content" id="page" aria-live="polite"></main></div>
 </div><div class="toast-wrap" id="toasts" role="status" aria-live="polite"></div>`;
 $('#overlay').onclick=()=>setMenu(false);
}
function nav([id,title,ic]){return `<a class="nav-link" href="#${id}" data-page="${id}">${icon(ic)}<span>${title}</span></a>`}
function setMenu(open){$('#sidebar').classList.toggle('open',open);$('#overlay').classList.toggle('show',open)}
function toast(){/* Quiet personal dashboard: no transient notification overlays. */}
function setStatus(h){healthInfo=h;const good=h?.fresh===true;const msg=good?'Aerodrome connected':h?.ok?'Data may be delayed':'Database unavailable';for(const id of ['sidebarDot','topDot']){$('#'+id).classList.toggle('good',good);$('#'+id).classList.toggle('bad',!!h&&!good)}$('#sidebarTitle').textContent=msg;$('#topStatus').textContent=good?'Data updating':'Check data';$('#sidebarDetail').textContent=h?.last_sighting?`Latest observation: ${when(h.last_sighting)}`:'Read-only historical data connection';}
async function api(path,params={}){const url=new URL(path,location.origin);Object.entries(params).forEach(([k,v])=>{if(v!==null&&v!==undefined&&v!=='')url.searchParams.set(k,String(v))});const res=await fetch(url,{cache:'no-store'});let d;try{d=await res.json()}catch{throw Error('The local website is unavailable.')};if(!res.ok)throw Error(d.error||'Request failed');return d}
const timerDate=(d)=>d?d:new Date().toISOString().slice(0,16);
function title(eyebrow,heading,subtitle='',accessory=''){return `<div class="page-heading"><div><h1 class="page-title">${esc(heading)}</h1>${subtitle&&currentPage!=='explore'?`<p class="page-subtitle">${subtitle}</p>`:''}</div>${accessory}</div>`}
function stat(label,value,meta,ic='chart'){return `<article class="stat-card"><div class="stat-label"><span>${esc(label)}</span><span class="stat-icon">${icon(ic)}</span></div><div class="stat-value">${value}</div><div class="stat-meta">${meta}</div></article>`}
function section(h,sub='',right=''){return `<div class="section-heading"><div><h2>${h}</h2>${sub?`<p>${sub}</p>`:''}</div>${right}</div>`}
const primaryAnalytics={name:'Airspace Analytics',id:'analytics',sub:'Explore your aircraft history',group:'stats',icon:'chart',brand:'AA',logoSrc:'/favicon.svg',tone:'aqua'};
function branding(it){
 const initials=String(it.brand||it.name?.replace(/[^a-zA-Z0-9]/g,'').slice(0,2)||'↗').slice(0,4).toUpperCase();
 const domain=String(it.logoDomain||'').trim();
 const logo=/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(domain)?`<img src="https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128" alt="" loading="lazy" decoding="async" onerror="this.remove()">`:'';
 const selfLogo=/^\/[a-z0-9/_-]+\.svg$/i.test(it.logoSrc||'')?`<img src="${esc(it.logoSrc)}" alt="" loading="lazy" onerror="this.remove()">`:'';
 const officialLogo=it.id==='aerodrome'?'<img src="/brand/aerodrome.svg" alt="" loading="lazy" onerror="this.remove()">':
   it.id==='skystats'?'<img src="https://raw.githubusercontent.com/tomcarman/skystats/main/docs/logo/logo_icon.png" alt="" loading="lazy" decoding="async" onerror="this.remove()">':'';
 return `<span class="launcher-link-icon brand-${esc(it.tone||'teal')}" aria-hidden="true">${officialLogo||selfLogo||logo}<span class="brand-fallback">${esc(initials)}</span></span>`;
}
function launcherEntry(it,primary=false){
 const destination=primary?'/analytics#explore':hrefFor(it);
 const secondary=!primary&&it.extraLabel?hrefFor({url:it.extraUrl||'',port:it.extraPort||it.port,path:it.extraPath||'/' }):null;
 return `<div class="launcher-card ${primary?'launcher-primary':''} ${!destination?'disabled':''}">
   <a class="launcher-card-main" ${destination?`href="${esc(destination)}" ${primary?'':'target="_blank" rel="noopener noreferrer"'}`:'aria-disabled="true"'}>
     ${branding(it)}<span class="launcher-link-text"><strong>${esc(it.name)}</strong><small>${esc(it.sub||'Open website')}</small></span><span class="launcher-link-arrow">${icon(primary?'chevron':'external',16)}</span>
   </a>${secondary?`<a class="launcher-sub-link" href="${esc(secondary)}" target="_blank" rel="noopener noreferrer">${icon('map',14)} ${esc(it.extraLabel)} ${icon('external',12)}</a>`:''}
 </div>`;
}
function launcherGroup(heading,items,primary=false){return `<section class="launcher-section"><h2>${esc(heading)}</h2><div class="launcher-list">${primary?launcherEntry(primaryAnalytics,true):''}${items.map(it=>launcherEntry(it)).join('')}</div></section>`}
function hrefFor(link){const host=location.hostname;const proto=location.protocol==='https:'?'https:':'http:';const path=String(link.path||'/');if(link.url){try{const u=new URL(link.url);if(!['http:','https:'].includes(u.protocol))return null;return u.href}catch{return null}}
 if(link.port===''||link.port===null||link.port===undefined)return null;
 const port=link.port?':'+link.port:'';
 return `${proto}//${host}${port}${path.startsWith('/')?path:'/'+path}`;
}
async function renderHome(){
 const configured=getLinks();
 $('#page').innerHTML=`<div class="launcher-screen"><header class="launcher-header"><div class="launcher-brand"><span class="launcher-brand-icon">${icon('radar',23)}</span><div><h1>Airspace</h1><span>Your receiver tools</span></div></div><a class="launcher-settings" href="/analytics#settings" title="Manage links" aria-label="Settings">${icon('settings',19)}</a></header>
 ${launcherGroup('View Stats',configured.filter(x=>x.group!=='feeders'),true)}
 ${launcherGroup('Feeder Website Status',configured.filter(x=>x.group==='feeders'))}
 <footer class="launcher-footer"><span><i class="dot" id="launcherDot"></i><span id="launcherStatus">Checking Aerodrome</span></span><a href="/analytics#settings">Manage shortcuts</a></footer></div>`;
 // Inline image onerror attributes are blocked by the CSP. Detect
 // genuine image loads so failed favicon requests retain the initials.
 $('.launcher-link-icon img').forEach(image=>{
  const ready=()=>image.parentElement?.classList.add('has-logo');
  const failed=()=>image.remove();
  image.addEventListener('load',ready,{once:true});
  image.addEventListener('error',failed,{once:true});
  if(image.complete){if(image.naturalWidth>0)ready();else failed();}
 });
 try{const h=await api('/api/health');if(currentPage!=='home')return;const dot=$('#launcherDot');if(dot)dot.classList.toggle('good',h.fresh===true);$('#launcherStatus').textContent=h.fresh?'Aerodrome connected':h.ok?'Aerodrome history available':'Database unavailable';setStatus(h)}catch{if($('#launcherStatus'))$('#launcherStatus').textContent='Status unavailable'}
}
function queryArgs(groupOverride){return {period:state.period,metric:state.metric,bucket:groupOverride||state.bucket,
 category:state.category,type:state.type,airline:state.airline,icao:state.icao,
 amount:state.amount,unit:state.unit,start:state.start,end:state.end}}
function field(label,element){return `<label class="field"><span>${esc(label)}</span>${element}</label>`}
const groups=[['auto','Automatic'],['hour','Hourly'],['day','Daily'],['week','Weekly'],['month','Monthly'],['year','Yearly'],['weekday','Average weekday'],['hour_of_day','Average hour'],['month_of_year','Average month']];
const opts=(options,chosen)=>options.map(([val,text])=>`<option value="${esc(val)}" ${chosen===val?'selected':''}>${esc(text)}</option>`).join('');
function metrics(){return `<div class="segmented" role="group" aria-label="Measurement">${[['flights','Visits'],['aircraft','Aircraft'],['observations','Samples']].map(([k,v])=>`<button data-metric="${k}" class="${state.metric===k?'on':''}" type="button">${v}</button>`).join('')}</div>`}
function rangeMode(){return ['rolling','custom','all'].includes(state.period)?state.period:'rolling'}
function initialDates(){
 const now=new Date();const prev=new Date(now.getTime()-7*86400000);
 return [ukDatetime(prev.toISOString()),ukDatetime(now.toISOString())];
}
function controls(extra=false){
 const mode=rangeMode(),[fallbackStart,fallbackEnd]=initialDates();
 return `<div class="control-card compact-controls">
  <div class="metric-toolbar"><div class="metric-toolbar-left">${metrics()}</div></div>
  <div class="range-layout">
   <div class="range-picker" role="group" aria-label="Time period">
    <button class="range-choice ${mode==='rolling'?'selected':''}" type="button" data-range-mode="rolling">Last</button>
    <button class="range-choice ${mode==='custom'?'selected':''}" type="button" data-range-mode="custom">Dates</button>
    <button class="range-choice ${mode==='all'?'selected':''}" type="button" data-range-mode="all">All time</button>
   </div>
   <input type="hidden" id="period" value="${esc(mode)}">
   <div class="range-inputs ${mode==='rolling'?'':'hidden'}" id="rollingBox">
    ${field('Duration',`<input type="number" inputmode="numeric" id="amount" min="1" max="100000" value="${esc(state.amount)}" aria-label="Number of units">`)}
    ${field('Unit',`<select id="unit">${opts([['minutes','Minutes'],['hours','Hours'],['days','Days'],['weeks','Weeks'],['months','Months'],['years','Years']],state.unit)}</select>`)}
   </div>
   <div class="range-inputs date-inputs ${mode==='custom'?'':'hidden'}" id="customBox">
    ${field('From · UK time',`<input type="datetime-local" id="customStart" value="${esc(state.start||fallbackStart)}">`)}
    ${field('To · UK time',`<input type="datetime-local" id="customEnd" value="${esc(state.end||fallbackEnd)}">`)}
   </div>
   <div class="range-group">${field('Group by',`<select id="bucket">${opts(groups,state.bucket)}</select>`)}</div>
   <button class="btn primary compact-apply" id="applyFilters" type="button">Show</button>
  </div>
  <details class="advanced-panel" id="advancedPanel" ${state.category!=='all'||state.type!=='all'||state.airline!=='all'||state.icao!=='all'?'open':''}><summary>${icon('layers',16)} Filters ${[state.category,state.type,state.airline,state.icao].filter(x=>x!=='all').length?'<span class="filter-dot">Active</span>':''}</summary><div class="advanced-grid">
   ${field('Aviation',`<select id="category">${opts([['all','All aviation'],['commercial','Commercial'],['general_aviation','General aviation'],['military','Military'],['helicopter','Helicopters'],['unknown','Unknown']],state.category)}</select>`)}
   ${field('Aircraft type',`<select id="aircraftType"><option value="all">All types</option></select>`)}
   ${field('Airline / operator',`<select id="airline"><option value="all">All operators</option></select>`)}
   ${field('ICAO address',`<input id="icao" placeholder="All aircraft" value="${esc(state.icao==='all'?'':state.icao)}" spellcheck="false" maxlength="12">`)}
   <button class="btn" id="resetFilters" type="button">Clear filters</button>
  </div></details>
  ${extra?'<div class="compact-save"><button class="btn small" id="saveView" type="button">'+icon('bookmark',15)+' Save view</button></div>':''}
 </div>`;
}
function collectControls(){
 state.period=$('#period')?.value||state.period;
 state.bucket=$('#bucket')?.value||state.bucket;
 state.category=$('#category')?.value||state.category;
 state.amount=Number($('#amount')?.value||state.amount);
 state.unit=$('#unit')?.value||state.unit;
 state.start=$('#customStart')?.value||state.start;
 state.end=$('#customEnd')?.value||state.end;
 state.type=$('#aircraftType')?.value||state.type;
 state.airline=$('#airline')?.value||state.airline;
 state.icao=($('#icao')?.value||'').trim().toLowerCase()||'all';
 persist();
}
function initControls(refresh,extra=false){
 $$('[data-metric]').forEach(b=>b.onclick=()=>{collectControls();state.metric=b.dataset.metric;persist();refresh()});
 $$('[data-range-mode]').forEach(b=>b.onclick=()=>{
   collectControls();state.period=b.dataset.rangeMode;
   const [start,end]=initialDates();
   if(state.period==='custom'){state.start=state.start||start;state.end=state.end||end;}
   persist();refresh();
 });
 $('#bucket').onchange=()=>{collectControls();refresh()};
 $('#amount').onchange=()=>{collectControls();refresh()};
 $('#unit').onchange=()=>{collectControls();refresh()};
 $$('#customStart,#customEnd').forEach(x=>x.onchange=()=>{collectControls();if(state.start&&state.end)refresh()});
 $('#applyFilters').onclick=()=>{collectControls();refresh()};
 $('#resetFilters').onclick=()=>{
   const metric=state.metric,period=state.period,amount=state.amount,unit=state.unit,start=state.start,end=state.end,bucket=state.bucket;
   Object.assign(state,{...defaults,metric,period,amount,unit,start,end,bucket});zoomHistory.length=0;persist();refresh()
 };
 if(extra&&$('#saveView'))$('#saveView').onclick=()=>{
  collectControls();const name=prompt('Name this view:');if(!name)return;
  let views=[];try{views=JSON.parse(localStorage.getItem(savedViewsKey))||[]}catch{}
  views=[...views.filter(v=>v.name!==name),{name:name.slice(0,50),query:queryArgs(),saved:Date.now()}].slice(-20);
  localStorage.setItem(savedViewsKey,JSON.stringify(views));toast('View saved');renderSavedViews();
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
function renderChart(series,kind='line',{height=305,mini=false,color='aqua',everyHour=false,axisGroup=''}={}){
 if(!series?.length||series.every(s=>s.value===null||s.value===undefined))return `<div class="chart-empty">No observations in this period.</div>`;
 const desktopMain=window.innerWidth>=1050 && height===305 && axisGroup!=='hour_of_day';
 const n=series.length,W=desktopMain?1120:720,H=desktopMain?248:height,L=55,R=14,T=19,B=49;
 const plotW=W-L-R,plotH=H-T-B;
 const max=Math.max(1,...series.map(s=>Number(s.value)||0));
 // Keep sparse series anchored at the LEFT of the timeline rather than
 // centring a lone year/month as if it filled the whole calendar.
 const guideSlots={year:8,month:12,week:6,day:7,hour:24,hour_of_day:24};
 const slot=plotW/Math.max(n,guideSlots[axisGroup]||n);
 const x=i=>L+slot*(i+.5);
 const y=value=>T+plotH-(Math.max(0,Number(value)||0)/max)*(plotH-9);
 const stroke=({aqua:'var(--aqua)',blue:'var(--blue)',pink:'var(--pink)'})[color]||'var(--aqua)';
 const ticks=Array.from({length:5},(_,i)=>max*i/4);
 let shape='';
 if(kind==='bar'){
   const bw=Math.max(1.2,Math.min(31,slot*.72));
   shape=series.map((s,i)=>s.value==null?'':`<rect class="chart-bar" data-index="${i}" x="${x(i)-bw/2}" y="${y(s.value)}" width="${bw}" height="${Math.max(0,T+plotH-y(s.value))}" rx="${Math.min(2.8,bw/4)}" style="fill:${stroke}"/>`).join('');
 }else{
   const coords=series.map((s,i)=>s.value==null?null:[x(i),y(s.value)]);
   // Gentle, monotone-in-x cubic joins keep peaks truthful without jagged corners.
   let previous=null;
   const path=coords.map(pt=>{if(!pt){previous=null;return ''}if(!previous){previous=pt;return `M${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`;}
    const m=(previous[0]+pt[0])/2;
    const segment=`C${m.toFixed(1)} ${previous[1].toFixed(1)} ${m.toFixed(1)} ${pt[1].toFixed(1)} ${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`;
    previous=pt;return segment;
   }).join(' ');
   shape=`<path class="chart-line" d="${path}" style="stroke:${stroke}"/>`;
   if(n<=80)shape+=coords.map((pt,i)=>pt?`<circle class="chart-point" data-index="${i}" cx="${pt[0]}" cy="${pt[1]}" r="3.3" style="fill:${stroke}"/>`:'').join('');
 }
 const hourTick=s=>{const m=String(s.label).match(/(\d{1,2}):(\d{2})/);return m?m[1].padStart(2,'0'):String(s.label).slice(0,2)};
 const everyTick=everyHour&&n<=25;
 const labels=Math.min(n,mini?10:14),skip=everyTick?1:Math.max(1,Math.ceil(n/labels));
 const axis=series.map((s,i)=>{
   if(i%skip!==0&&i!==n-1)return '';
   const text=everyHour?hourTick(s):axisGroup==='month'?new Date(s.key+'-01T12:00:00Z').toLocaleDateString('en-GB',{month:'short'}):axisGroup==='week'?new Date(s.key+'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short'}):axisGroup==='day'?new Date(s.key+'T12:00:00Z').toLocaleDateString('en-GB',{weekday:'short',day:'numeric'}):short(s.label,11);
   return `<text class="chart-axis ${everyHour?'hour-axis':''}" text-anchor="middle" x="${x(i)}" y="${H-15}">${esc(text)}</text>`;
 }).join('');
 return `<div class="chart-shell"><div class="chart-scroll"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Interactive traffic chart with ${n} intervals, scaled to screen width" preserveAspectRatio="xMidYMid meet">
 ${ticks.map(t=>`<line class="chart-gridline" x1="${L}" x2="${W-R}" y1="${y(t)}" y2="${y(t)}"/><text class="chart-axis" x="${L-9}" y="${y(t)+4}" text-anchor="end">${fmt(t,0)}</text>`).join('')}
 ${axis}${shape}
 ${series.map((s,i)=>`<rect class="chart-hit" data-index="${i}" x="${L+slot*i}" y="${T}" width="${slot}" height="${plotH}"/>`).join('')}
 </svg></div><div class="chart-tooltip hidden" role="status"></div></div>`;
}
function hookChart(container,series,group,drill=true){if(!container||!series)return;const tip=$('.chart-tooltip',container);const wrap=$('.chart-shell',container);if(!tip||!wrap)return;
 $$('.chart-hit',container).forEach(hit=>{
  const index=+hit.dataset.index;
  hit.addEventListener('pointermove',ev=>{
    if(ev.pointerType==='touch')return;
    const s=series[index];tip.innerHTML=`${esc(s.label)}<strong>${s.value===null||s.value===undefined?'—':fmt(s.value,2)}</strong>${s.samples?`<span class="muted">${s.samples} occurrences</span>`:''}`;
    tip.classList.remove('hidden');const box=wrap.getBoundingClientRect();tip.style.left=Math.min(box.width-155,Math.max(0,ev.clientX-box.left+8))+'px';tip.style.top=Math.max(45,ev.clientY-box.top)+'px';
  });
  hit.addEventListener('pointerleave',()=>tip.classList.add('hidden'));
  if(!drill)hit.addEventListener('click',()=>{
    const s=series[index];
    tip.innerHTML=`${esc(s.label)}<strong>${s.value==null?'—':fmt(s.value,2)}</strong>`;
    tip.classList.remove('hidden');
    const area=wrap.getBoundingClientRect(),point=hit.getBoundingClientRect();
    tip.style.left=Math.max(0,Math.min(area.width-142,point.left-area.left))+'px';
    tip.style.top=Math.max(42,point.top-area.top+25)+'px';
  });
  if(drill&&['year','month','week','day','hour'].includes(group))hit.addEventListener('click',()=>drillInto(series[index],group));
 });
}
function ukDatetime(iso){const d=new Date(iso);return d.toLocaleString('sv-SE',{timeZone:'Europe/London'}).replace(' ','T').slice(0,16)}
function drillInto(point,group){
 const key=point.key;let from,to,next;
 if(group==='year'){from=`${key}-01-01T00:00`;to=`${(+key+1)}-01-01T00:00`;next='month'}
 else if(group==='month'){const [y,m]=key.split('-').map(Number);from=`${key}-01T00:00`;to=m===12?`${y+1}-01-01T00:00`:`${y}-${String(m+1).padStart(2,'0')}-01T00:00`;next='week'}
 else if(group==='week'){from=key+'T00:00';const x=new Date(key+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+7);to=x.toISOString().slice(0,10)+'T00:00';if(state.period==='custom'){if(from<state.start)from=state.start;if(to>state.end)to=state.end;}next='day'}
 else if(group==='day'){from=key+'T00:00';const x=new Date(key+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+1);to=x.toISOString().slice(0,10)+'T00:00';next='hour'}
 else if(group==='hour'){from=ukDatetime(key);const x=new Date(Date.parse(key)+3600*1000);to=ukDatetime(x.toISOString());next='hour'}
 if(from&&to){delete state.heatYear;delete state.heatMonth;zoomHistory.push({period:state.period,start:state.start,end:state.end,bucket:state.bucket,amount:state.amount,unit:state.unit});state.period='custom';state.start=from;state.end=to;state.bucket=next;persist();location.hash='#explore';if(currentPage==='explore')renderExplore();}
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
function bindBreakdowns(){ $$('[data-filter]').forEach(el=>el.onclick=()=>{const f=el.dataset.filter,value=el.dataset.value;if(!['type','airline','category'].includes(f))return;if(f==='airline'&&value.toLowerCase().startsWith('unknown'))return;state.filtersEnabled=true;state[f]=value;persist();renderExplore();toast('Filter applied',`${value} — click Reset to clear.`)}) }
function summaryFor(a){const unit={flights:'estimated visits',aircraft:'unique aircraft',observations:'observation records'}[a.metric];
 return `<div class="summary-row"><div class="summary-item"><span>Period total</span><strong>${fmt(a.total)}</strong></div><div class="summary-item"><span>${a.aggregation_label}</span><strong>${fmt(a.average,2)}</strong></div><div class="summary-item"><span>Highest bucket</span><strong>${fmt(a.peak,2)}</strong></div><div class="summary-item"><span>Distinct aircraft</span><strong>${fmt(a.unique_aircraft)}</strong></div></div>`;
}
// Simple progressive timeline: all years → months → weeks → days → hours.
function resetTimeline(){delete state.heatYear;delete state.heatMonth;zoomHistory.length=0;Object.assign(state,{period:'all',bucket:'year',start:'',end:'',amount:7,unit:'days',metric:'flights',category:'all',type:'all',airline:'all',icao:'all'});persist();}
function periodHeading(data){
 const localDate=d=>new Date(String(d).slice(0,10)+'T12:00:00Z');
 const locale=(d,o)=>localDate(d).toLocaleDateString('en-GB',o);
 const sd=state.start||new Date(data.start*1000).toISOString().slice(0,10);
 if(!state.filtersEnabled&&state.period==='all')return 'All recorded years';
 if(state.bucket==='month')return locale(sd,{year:'numeric'});
 if(state.bucket==='week')return locale(sd,{month:'long',year:'numeric'});
 if(state.bucket==='day')return `Week of ${locale(sd,{day:'numeric',month:'long',year:'numeric'})}`;
 if(state.bucket==='hour')return locale(sd,{weekday:'long',day:'numeric',month:'long',year:'numeric'});
 if(state.period==='all')return 'All recorded years';
 const end=new Date((data.end-1)*1000).toLocaleDateString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',year:'numeric'});
 const from=new Date(data.start*1000).toLocaleDateString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',year:'numeric'});
 return from===end?from:`${from} – ${end}`;
}
function applyFilterState(){
 if(!state.filtersEnabled)Object.assign(state,{metric:'flights',category:'all',type:'all',airline:'all',icao:'all'});
}
function drawCurrentChart(){
 if(!currentAnalytics)return;
 $('#exploreChart').innerHTML=renderChart(currentAnalytics.series,state.chart||'bar',{everyHour:currentAnalytics.bucket==='hour',axisGroup:currentAnalytics.bucket});
 hookChart($('#exploreChart'),currentAnalytics.series,currentAnalytics.bucket);
 $$('#lineSwitch,#barSwitch').forEach(b=>b.classList.toggle('selected',b.id===(state.chart==='line'?'lineSwitch':'barSwitch')));
}
function latestSelection(a,scope){
 // Construct UK calendar windows; local time strings are interpreted by the backend.
 const dt=new Date((a.end-1)*1000).toLocaleString('sv-SE',{timeZone:'Europe/London'}).slice(0,10);
 const [yr,mo,day]=dt.split('-').map(Number);
 const pad=n=>String(n).padStart(2,'0');
 const date=(y,m,d)=>`${y}-${pad(m)}-${pad(d)}`;
 let start,end;
 if(scope==='year'){start=`${yr}-01-01`;end=`${yr+1}-01-01`;}
 else if(scope==='month'){start=date(yr,mo,1);end=mo===12?date(yr+1,1,1):date(yr,mo+1,1);}
 else if(scope==='week'){
  const noon=new Date(dt+'T12:00:00Z');const dow=(noon.getUTCDay()+6)%7;
  noon.setUTCDate(noon.getUTCDate()-dow);start=noon.toISOString().slice(0,10);
  noon.setUTCDate(noon.getUTCDate()+7);end=noon.toISOString().slice(0,10);
 }else{
  start=dt;const noon=new Date(dt+'T12:00:00Z');noon.setUTCDate(noon.getUTCDate()+1);end=noon.toISOString().slice(0,10);
 }
 return {period:'custom',start:start+'T00:00',end:end+'T00:00'};
}
let patternsRequestId=0;
async function fillPatterns(rid,a){
 const run=++patternsRequestId;
 const metric=state.filtersEnabled?state.metric:'flights';
 const filters={metric,category:state.filtersEnabled?state.category:'all',type:state.filtersEnabled?state.type:'all',airline:state.filtersEnabled?state.airline:'all',icao:state.filtersEnabled?state.icao:'all'};
 const renderStats=async()=>{
   const all=await api('/api/patterns',{...filters,period:'all'});
   if(rid!==renderId||run!==patternsRequestId)return;
   $('#weekdayPattern').innerHTML=renderWeekBars(all.weekday,true);
   $('#hourPattern').innerHTML=renderChart(all.hourly,'bar',{height:230,everyHour:true,axisGroup:'hour_of_day'});
   hookChart($('#hourPattern'),all.hourly,'hour_of_day',false);
 };
 const renderCalendar=async()=>{
   // When the timeline is zoomed to a calendar year/month, follow that selection.
   // Otherwise default to the most recent recorded year, never an empty future year.
   const tail=new Date((Math.max(a.start,a.end-1))*1000).toLocaleDateString('sv-SE',{timeZone:'Europe/London'});
   const selected=(state.period==='custom'&&state.start?state.start.slice(0,7):tail.slice(0,7));
   const year=state.heatYear||Number(selected.slice(0,4));
   const month=state.heatMonth||Number(selected.slice(5,7));
   const mode=state.heatMonth?'month':'year';
   const pad=n=>String(n).padStart(2,'0');
   const from=mode==='year'?`${year}-01-01T00:00`:`${year}-${pad(month)}-01T00:00`;
   const to=mode==='year'?`${year+1}-01-01T00:00`:(month===12?`${year+1}-01-01T00:00`:`${year}-${pad(month+1)}-01T00:00`);
   // Future months have no observations. The API caps future end dates;
   // avoid requesting a window whose start is already beyond that cap.
   const nowUK=new Date().toLocaleString('sv-SE',{timeZone:'Europe/London'}).replace(' ','T');
   let response={series:[]};
   if(from<nowUK){
    try{response=await api('/api/analytics',{...filters,period:'custom',start:from,end:to,bucket:'day'});}
    catch(e){if(!String(e.message||e).includes('Start must be before end'))throw e;}
   }
   if(rid!==renderId||run!==patternsRequestId)return;
   $('#heatmap').innerHTML=window.AirspaceCalendar.render(response.series,{level:mode,year,month,metric});
   $('#heatmapRange').textContent='';
   $$('[data-heat-month]',$('#heatmap')).forEach(button=>button.onclick=()=>{
     const [y,m]=button.dataset.heatMonth.split('-').map(Number);
     state.heatYear=y;state.heatMonth=m;state.heatScope='month';persist();
     $('#heatmap').innerHTML=loading();
     renderCalendar().catch(e=>$('#heatmap').innerHTML=safeError(e));
   });
   const back=$('[data-heat-back]',$('#heatmap'));
   if(back)back.onclick=()=>{
     delete state.heatMonth;state.heatScope='year';persist();
     $('#heatmap').innerHTML=loading();
     renderCalendar().catch(e=>$('#heatmap').innerHTML=safeError(e));
   };
 };
 try{await renderStats();await renderCalendar();}
 catch(e){if(rid!==renderId||run!==patternsRequestId)return;
  for(const id of ['weekdayPattern','hourPattern','heatmap']){const el=$('#'+id);if(el&&el.innerHTML.includes('spinner'))el.innerHTML=`<div class="empty">${esc(e.message)}</div>`;}
 }
}

async function renderExplore(){const rid=++renderId;currentAnalytics=null;applyFilterState();
 $('#page').innerHTML=title('','Traffic')+`
 <details class="foldout traffic-filter-panel" id="trafficFilterPanel"><summary><span>${icon('layers',17)} Traffic filters <small id="filterModeLabel">${state.filtersEnabled?'On':'Off'}</small></span>${icon('chevron',17)}</summary>
  <div class="traffic-filter-actions"><button class="btn small ${state.filtersEnabled?'primary':''}" id="filtersToggle" type="button">Filters ${state.filtersEnabled?'on':'off'}</button><button class="btn small" id="filtersReset" type="button">Reset</button></div>
  <div class="${state.filtersEnabled?'':'filters-disabled'}" id="filtersBody">${controls(false)}</div>
 </details>
 <section class="main-chart-panel"><div class="main-chart-head"><div><div id="chartPeriod" class="chart-period">Loading period…</div><h2 id="chartLabel">Estimated flight visits</h2><div id="chartMeta" class="muted tiny">Loading…</div></div>
 <div class="chart-tools"><button class="btn small ${zoomHistory.length?'':'hidden'}" id="zoomBack" type="button">${icon('chevron',13)} Zoom out</button><button class="btn small" id="zoomReset" type="button">All years</button><span class="chart-toggle"><button class="btn small" id="barSwitch" type="button">Bars</button><button class="btn small" id="lineSwitch" type="button">Line</button></span></div></div>
 <div id="exploreStats" class="compact-stats">${loading()}</div>
 <div id="exploreChart" class="chart-frame">${loading()}</div>
 <div class="chart-foot"><span id="pointCount">—</span><span>Tap a bar or point to see the next level</span></div></section>
 <details class="foldout" id="breakdownDetails" open><summary><span>${icon('layers',18)} Breakdowns <small>Category · aircraft type · operator</small></span>${icon('chevron',17)}</summary><div class="breakdown-head"><button class="btn small" id="breakdownVizSwitch" type="button">${state.typeViz==='pie'?'Show bars':'Show pies'}</button></div>
 <div class="grid-three breakdown-grid"><div class="panel"><h3 class="panel-title">Aviation category</h3><div id="categoryDonut">${loading()}</div></div><div class="panel"><h3 class="panel-title">Aircraft types</h3><div id="typeBars">${loading()}</div></div><div class="panel"><select id="operatorScope" class="breakdown-scope" aria-label="Operator breakdown">${opts([['airline','Airlines · commercial'],['operator','Operators · all']],state.operatorScope||'airline')}</select><div id="airlineBars">${loading()}</div></div></div></details>
 <div class="panel pattern-section"><div class="panel-top"><h3 class="panel-title">Activity calendar</h3></div><div id="heatmapRange" class="muted tiny"></div><div id="heatmap">${loading()}</div></div>
 <div class="pattern-subgrid"><div class="panel"><h3 class="panel-title">Average by weekday <small class="muted">· all time</small></h3><div id="weekdayPattern">${loading()}</div></div><div class="panel"><h3 class="panel-title">Average by hour <small class="muted">· all time</small></h3><div id="hourPattern">${loading()}</div></div></div>`;
 initControls(()=>{if(state.filtersEnabled){zoomHistory.length=0;renderExplore()}},false);populateFilters();
 $('#filtersToggle').onclick=()=>{state.filtersEnabled=!state.filtersEnabled;if(!state.filtersEnabled)resetTimeline();persist();renderExplore();};
 $('#filtersReset').onclick=()=>{state.filtersEnabled=false;resetTimeline();renderExplore()};
 $('#lineSwitch').onclick=()=>{state.chart='line';persist();drawCurrentChart()};
 $('#barSwitch').onclick=()=>{state.chart='bar';persist();drawCurrentChart()};
 $('#zoomBack').onclick=()=>{const prev=zoomHistory.pop();if(prev){Object.assign(state,prev);persist();renderExplore()}};
 $('#zoomReset').onclick=()=>{resetTimeline();renderExplore()};
 try{
  const a=await api('/api/analytics',queryArgs());if(rid!==renderId)return;
  currentAnalytics=a;fillFilterOptions(a);
  $('#exploreStats').innerHTML=`<div class="mini-stat"><span>Period total</span><strong>${fmt(a.total)}</strong></div><div class="mini-stat"><span>${esc(a.aggregation_label)}</span><strong>${fmt(a.average,2)}</strong></div><div class="mini-stat"><span>Peak interval</span><strong>${fmt(a.peak,2)}</strong></div><div class="mini-stat"><span>Unique aircraft</span><strong>${fmt(a.unique_aircraft)}</strong></div>`;
  $('#chartLabel').textContent={flights:'Estimated flight visits',aircraft:'Unique aircraft',observations:'Recorded observations'}[a.metric];
  $('#chartPeriod').textContent=periodHeading(a);
  $('#chartMeta').textContent=`Grouped by ${a.bucket==='hour'?'hour':a.bucket==='day'?'day':a.bucket==='week'?'week':a.bucket==='month'?'month':'year'}`;
  $('#pointCount').textContent=`${a.series.length} intervals`;
  drawCurrentChart();
  function showBreakdowns(){
   const pie=state.typeViz==='pie';
   $('#categoryDonut').innerHTML=pie?donut(a.breakdowns.category):breakdownList(a.breakdowns.category,'category','aqua');
   $('#typeBars').innerHTML=pie?donut(a.breakdowns.type):breakdownList(a.breakdowns.type,'type','blue');
   const op=a.breakdowns[state.operatorScope||'airline']||a.breakdowns.airline;
   $('#airlineBars').innerHTML=pie?donut(op):breakdownList(op,'airline','pink');
   $('#breakdownVizSwitch').textContent=pie?'Show bars':'Show pies';bindBreakdowns();
  }
  $('#breakdownVizSwitch').onclick=()=>{state.typeViz=state.typeViz==='pie'?'bars':'pie';persist();showBreakdowns()};
  $('#operatorScope').onchange=()=>{state.operatorScope=$('#operatorScope').value;persist();showBreakdowns()};showBreakdowns();
  fillPatterns(rid,a);
 }catch(e){if(rid!==renderId)return;$('#exploreStats').innerHTML='';$('#exploreChart').innerHTML=safeError(e);}
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
function renderHeatmap(cells,onlyWeekday=null){if(!cells?.length)return '<div class="empty">No hourly observations.</div>';
 const max=Math.max(1,...cells.map(x=>Number(x.value)||0)),colorScale=v=>{
  if(v===null||v===undefined)return 'var(--panel2)';const f=Math.max(0,Math.min(1,Math.pow(v/max,.65)));return `hsl(${Math.round(224-67*f)} 89% ${Math.round(15+44*f)}%)`;
 };
 const cols=[...Array(24)].map((_,h)=>`<div class="heat-label">${h%3===0?String(h).padStart(2,'0'):''}</div>`).join('');
 const weekdays=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
 return `<div class="heat-outer"><div class="heatmap"><span></span>${cols}${weekdays.map((d,wd)=>onlyWeekday!==null&&wd!==onlyWeekday?'':`<span class="heat-day">${d}</span>${cells.filter(x=>x.weekday===wd).map(x=>`<div class="heat-cell" tabindex="0" title="${d} ${String(x.hour).padStart(2,'0')}:00 — ${x.samples?`avg ${fmt(x.value,2)}, ${x.samples} recorded hours`:'No samples'}" style="background:${colorScale(x.value)}"></div>`).join('')}`).join('')}</div></div><div class="heat-legend"><span>Less busy</span>${[.08,.24,.43,.65,.85].map(x=>`<i style="background:hsl(${Math.round(224-67*x)} 89% ${Math.round(15+44*x)}%)"></i>`).join('')}<span>More busy</span></div>`;
}
async function renderPatterns(){const rid=++renderId;
 $('#page').innerHTML=title('','Patterns')+
 controls(false)+`<div class="panel"><div class="panel-top"><div><h2 class="panel-title">Day × hour heatmap</h2></div></div><div id="heatmap">${loading()}</div></div>
 
 <div class="pattern-subgrid"><div class="panel"><h3 class="panel-title">Average by weekday</h3><div id="weekdayPattern">${loading()}</div></div>
 <div class="panel"><h3 class="panel-title">Average by hour</h3><div id="hourPattern">${loading()}</div></div></div>
`;
 initControls(renderPatterns);populateFilters();
 try{const a=await api('/api/patterns',queryArgs());if(rid!==renderId)return;
 $('#heatmap').innerHTML=renderHeatmap(a.heatmap);
 $('#weekdayPattern').innerHTML=renderWeekBars(a.weekday,true);
 $('#hourPattern').innerHTML=renderChart(a.hourly,'bar',{height:230,everyHour:true});hookChart($('#hourPattern'),a.hourly,'hour_of_day',false);
 }catch(e){if(rid!==renderId)return;['heatmap','weekdayPattern','hourPattern'].forEach(x=>$('#'+x).innerHTML=safeError(e))}
}
function comparisonFields(){return `<div class="secondary-controls" style="margin:0 0 16px;border:none;padding:0">
 ${field('Compare against',`<select id="comparison">${opts([['previous','An earlier equivalent period'],['year_ago','Same dates last year'],['custom','Another custom date range']],state.comparison)}</select>`)}
 <label class="field" id="offsetField"><span>Periods back</span><input id="offset" type="number" min="1" max="100" step="1" value="${esc(state.offset)}"></label>
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
 $('#page').innerHTML=title('','Compare periods')+`<div class="analytics-tabs"><a href="#explore">Traffic</a><a href="#patterns">Patterns</a><a class="selected" href="#compare">Compare</a></div>`+
 controls(false)+`<div class="control-card">${comparisonFields()}<button class="btn primary" id="runComparison">${icon('compare')} Compare periods</button></div>
 <div id="compareResults">${loading()}</div>`;
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
   ${section('Traffic comparison')}
   <div class="panel">${overlayChart(d.left,d.right)}</div>
   ${section('Averages')}
   <div class="grid-two"><div class="panel"><h3 class="panel-title">Selected period</h3>${summaryFor(d.left)}</div><div class="panel"><h3 class="panel-title">Comparison period</h3>${summaryFor(d.right)}</div></div>`;
 }catch(e){if(rid===renderId)$('#compareResults').innerHTML=safeError(e)}
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
 $('#page').innerHTML=title('','Database','','<a class="btn small" href="#settings">← Settings</a>')+
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
function settingsLinks(){return `<div class="shortcut-list" id="shortcutList">${getLinks().map((it,i)=>`<div class="shortcut-edit-row" data-linkindex="${i}"><div class="shortcut-edit-main">${field('Name',`<input class="link-name" value="${esc(it.name)}" maxlength="50">`)}${field('Group',`<select class="link-group">${opts([['stats','View Stats'],['feeders','Feeder Status']],it.group||'stats')}</select>`)}${field('Port',`<input class="link-port" value="${esc(it.port??'')}" placeholder="5173" inputmode="numeric">`)}${field('Full URL (optional)',`<input class="link-url" value="${esc(it.url||'')}" placeholder="https://…">`)}${field('Path',`<input class="link-path" value="${esc(it.path||'/')}" placeholder="/">`)}${field('Logo website',`<input class="link-logo-domain" value="${esc(it.logoDomain||'')}" placeholder="flightaware.com">`)}</div>
 <details class="shortcut-extras"><summary>Optional second link</summary><div class="shortcut-edit-main">${field('Button label',`<input class="link-extra-label" value="${esc(it.extraLabel||'')}" placeholder="Feeder map">`)}${field('Port',`<input class="link-extra-port" value="${esc(it.extraPort||'')}" inputmode="numeric" placeholder="30053">`)}${field('Full URL',`<input class="link-extra-url" value="${esc(it.extraUrl||'')}" placeholder="https://…">`)}${field('Path',`<input class="link-extra-path" value="${esc(it.extraPath||'/')}" placeholder="/map.html">`)}</div></details>
 <div class="shortcut-edit-actions"><button class="btn small" data-reorder="up" data-pos="${i}" title="Move up" ${i===0?'disabled':''}>↑</button><button class="btn small" data-reorder="down" data-pos="${i}" title="Move down" ${i===getLinks().length-1?'disabled':''}>↓</button><button class="btn small danger" data-remove="${i}" title="Remove shortcut">Remove</button></div></div>`).join('')}</div>
 <div class="setting-actions shortcut-actions"><button class="btn" id="addLink" type="button">${icon('plus',15)} Add link</button><button class="btn primary" id="saveLinks" type="button">Save links</button><button class="btn" id="restoreLinks" type="button">Restore defaults</button></div>`}
function collectSettingsLinks(){const original=getLinks();return $$('[data-linkindex]').map(el=>{
 const idx=Number(el.dataset.linkindex),port=$('.link-port',el).value.trim(),path=$('.link-path',el).value.trim()||'/',url=$('.link-url',el).value.trim();
 const extraPort=$('.link-extra-port',el).value.trim(),extraUrl=$('.link-extra-url',el).value.trim(),logoDomain=$('.link-logo-domain',el).value.trim();
 for(const value of [port,extraPort])if(value&&(!/^\d{1,5}$/.test(value)||Number(value)<1||Number(value)>65535))throw Error('Port must be 1–65535');
 for(const value of [url,extraUrl])if(value&&!/^https?:\/\//i.test(value))throw Error('URLs must begin with http:// or https://');
 if(logoDomain&&!/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(logoDomain))throw Error('Logo domain should look like flightaware.com');
 return {...original[idx],name:$('.link-name',el).value.trim().slice(0,50)||'New link',group:$('.link-group',el).value,sub:original[idx]?.sub||'Application shortcut',port,path,url,logoDomain,extraLabel:$('.link-extra-label',el).value.trim().slice(0,32),extraPort,extraUrl,extraPath:$('.link-extra-path',el).value.trim()||'/',icon:original[idx]?.icon||'external'};
})}
function updateBox(){return `<div class="auth-box">
  <div class="status-row" style="margin-bottom:9px"><i class="dot" id="updateDot"></i><strong id="updateHeading">Checking GitHub…</strong></div>
  <div class="tiny muted break-word" id="updateDetails"></div>
  <div class="setting-actions"><button class="btn" id="checkUpdates">${icon('refresh')} Check GitHub</button><button class="btn primary" id="applyUpdate">Update now</button><button class="btn" id="rollbackUpdate">Restore previous</button></div>
  <div class="tiny muted" id="updateProgress"></div>
 </div>`}
async function renderSettings(){const rid=++renderId;
 $('#page').innerHTML=title('','Settings')+
 `<div class="panel">${settingsRow('Appearance','Choose a theme and your preferred default measurement.',
   `<div class="settings-entry">${field('Colour theme',`<select id="settingTheme">${opts([['dark','Dark / midnight'],['light','Light / cloud']],state.theme)}</select>`)}${field('Default measurement',`<select id="settingMetric">${opts([['flights','Estimated flights'],['aircraft','Unique aircraft'],['observations','Observations']],state.metric)}</select>`)}</div><button class="btn primary" id="saveAppearance" style="margin-top:13px">Save preferences</button>`)}
 ${settingsRow('Launcher links','The Analytics link always comes first. Add, remove and reorder the other links.',settingsLinks())}
 ${settingsRow('GitHub updates','',updateBox())}
  ${settingsRow('Aerodrome database','',`<div id="databaseInfo">${loading()}</div>`)}
  ${settingsRow('Database explorer','',`<a class="btn primary" href="/analytics#database">${icon('database',16)} Open database →</a>`)}
 </div>`;
 $('#saveAppearance').onclick=()=>{setTheme($('#settingTheme').value);state.metric=$('#settingMetric').value;persist();toast('Preferences saved')};
 function saveLinks(){try{putLinks(collectSettingsLinks());toast('Launcher links saved');return true}catch(e){toast('Invalid link',e.message,true);return false}}
 $('#saveLinks').onclick=()=>saveLinks();
 $('#addLink').onclick=()=>{if(!saveLinks())return;const xs=getLinks();xs.push({name:'New link',group:'stats',sub:'Application shortcut',port:'',path:'/',url:'',icon:'external'});putLinks(xs);renderSettings()};
 $('#restoreLinks').onclick=()=>{putLinks(defaultLinks);toast('Default links restored');renderSettings()};
 $$('[data-remove]').forEach(b=>b.onclick=()=>{if(!saveLinks())return;const xs=getLinks();xs.splice(+b.dataset.remove,1);putLinks(xs);renderSettings()});
 $$('[data-reorder]').forEach(b=>b.onclick=()=>{if(!saveLinks())return;const xs=getLinks(),i=+b.dataset.pos,j=i+(b.dataset.reorder==='up'?-1:1);if(j<0||j>=xs.length)return;[xs[i],xs[j]]=[xs[j],xs[i]];putLinks(xs);renderSettings()});
 $('#checkUpdates').onclick=async()=>{
  $('#updateDetails').textContent='Checking GitHub…';try{const d=await api('/api/update/check',{refresh:1});setUpdateInfo(d)}catch(e){$('#updateDetails').textContent=e.message}
 };
 $('#applyUpdate').onclick=()=>launchUpdate('apply');
 $('#rollbackUpdate').onclick=()=>launchUpdate('rollback');
 async function launchUpdate(mode){
  if(!confirm(mode==='rollback'?'Restore the previous working website version and restart only this service?':'Download the latest code from your configured GitHub repository and restart only this website?'))return;
  $('#updateProgress').textContent='Starting the updater…';
  try{const res=await fetch('/api/update/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
   const d=await res.json();if(!res.ok){throw Error(d.error||'Update request failed');}
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
async function loadPage(){const fallback=location.pathname==='/analytics'?'explore':'home';const hash=(location.hash||'#'+fallback).slice(1).split('?')[0];currentPage=hash==='patterns'?'explore':names[hash]?hash:fallback;renderId++;document.body.classList.toggle('launcher-mode',currentPage==='home');document.title=(currentPage==='home'?'Airspace · Launcher':names[currentPage]+' · Airspace Analytics');
 $$('.top-nav-link,.top-settings').forEach(el=>el.classList.toggle('active',el.dataset.page===currentPage||(currentPage==='database'&&el.dataset.page==='settings')));
 $('#topTitle').textContent=names[currentPage];setMenu(false);
 window.scrollTo({top:0,behavior:'instant'});
 const routes={home:renderHome,explore:renderExplore,database:renderDatabase,settings:renderSettings};
 try{await routes[currentPage]()}catch(e){$('#page').innerHTML=safeError(e)}
}
async function refreshStatus(){try{const h=await api('/api/health');setStatus(h)}catch{setStatus(null)}}
function boot(){shell();window.addEventListener('hashchange',loadPage);loadPage();refreshStatus();api('/api/config').then(d=>$$('.versionValue').forEach(x=>x.textContent='v'+d.version)).catch(()=>{});activeTimer=setInterval(refreshStatus,60000)}
boot();
