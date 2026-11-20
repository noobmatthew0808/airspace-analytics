/* Personal flight log, adapted from the complete user-supplied live-main ZIP.
 * The SheetDB backend, column names, filters and filtered statistics retain
 * the original behaviour. Only the presentation and an optional live column
 * have changed. This module never modifies Traffic, Alerts or Aerodrome.
 */
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const normalizeText = value => String(value ?? '').trim();
const normalizeUpper = value => normalizeText(value).toUpperCase();
const splitPeople = value => String(value ?? '').split(/[\n,;]+/).map(name=>name.trim()).filter(Boolean);
const normalizeWho = value => splitPeople(value).join(', ');
const normalizeRegistration = value => String(value ?? '').toUpperCase().replace(/[^A-Z0-9]/g,'');
const getCurrentRegistration = value => {
 const text=normalizeText(value), match=text.match(/\(([^()]*)\)\s*$/);
 return normalizeText(match?match[1]:text);
};
const normalizeFilterValue=value=>normalizeText(value).toLowerCase();
const normalizeFilterSearch=value=>String(value ?? '').toLowerCase().replace(/[^a-z0-9]/g,'');
const filterMatchesSelected=(value,selectedValues)=>!selectedValues.length||selectedValues.some(item=>normalizeFilterValue(item)===normalizeFilterValue(value));
function parseDate(value){
 if(!value)return null;
 const raw=String(value).trim();
 if(/^\d{4}-\d{2}-\d{2}$/.test(raw)){
  const d=new Date(raw+'T12:00:00');return Number.isNaN(d.getTime())?null:d;
 }
 if(/^\d{2}\/\d{2}\/\d{4}$/.test(raw)){
  const [dd,mm,yyyy]=raw.split('/');
  const d=new Date(yyyy+'-'+mm+'-'+dd+'T12:00:00');
  return Number.isNaN(d.getTime())?null:d;
 }
 const d=new Date(raw);return Number.isNaN(d.getTime())?null:d;
}
const toInputDate=value=>{
 const d=parseDate(value);if(!d)return '';
 return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
};
const niceDate=value=>{
 const d=parseDate(value);
 return d?new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric'}).format(d):normalizeText(value);
};
const uniqueValues=values=>[...new Set(values.map(normalizeText).filter(Boolean))]
 .sort((a,b)=>a.localeCompare(b,undefined,{sensitivity:'base'}));
const yearFromRow=row=>{const d=parseDate(row.date);return d?String(d.getFullYear()):'';};
const uniqueYears=rows=>[...new Set(rows.map(yearFromRow).filter(Boolean))].sort((a,b)=>Number(b)-Number(a));
const uniquePeople=rows=>uniqueValues(rows.flatMap(r=>splitPeople(r.who)));
const normalizeRow=(row={})=>({
 id:normalizeText(row.id),date:normalizeText(row.date),
 from_airport:normalizeText(row.from_airport),to_airport:normalizeText(row.to_airport),
 flight_code:normalizeText(row.flight_code),airline:normalizeText(row.airline),
 airplane:normalizeText(row.airplane),registration:normalizeText(row.registration),
 who:normalizeWho(row.who)
});
const filterDefinitions=[
 {key:'year',label:'Year',options:uniqueYears},
 {key:'airline',label:'Airline',options:rows=>uniqueValues(rows.map(row=>row.airline))},
 {key:'who',label:'Who',options:uniquePeople},
 {key:'from_airport',label:'From',options:rows=>uniqueValues(rows.map(row=>row.from_airport))},
 {key:'to_airport',label:'To',options:rows=>uniqueValues(rows.map(row=>row.to_airport))},
 {key:'airplane',label:'Airplane',options:rows=>uniqueValues(rows.map(row=>row.airplane))},
 {key:'flight_code',label:'Flight',options:rows=>uniqueValues(rows.map(row=>row.flight_code))}
];
const blankFilters=()=>({year:[],airline:[],who:[],from_airport:[],to_airport:[],airplane:[],flight_code:[]});
let allFlights=[],activeFilters=blankFilters(),searchTerm='',filterOpen=null;
let lastLive={},selectedFlightId=null,flightTimer=null,flightsGeneration=0,sheetWarning='',statusRequestNumber=0;
let manageActive=false,manageMode=null;

async function api(url,body){
 const opts={cache:'no-store'};
 if(body!==undefined){
  opts.method='POST';opts.headers={'Content-Type':'application/json'};
  opts.body=JSON.stringify(body);
 }
 const response=await fetch(url,opts);
 let data;
 try{data=await response.json()}catch{throw Error('The local website returned invalid data.');}
 if(!response.ok)throw Error(data.error||'Request failed');
 return data;
}
const sourceRows=()=>allFlights.map(normalizeRow);
const sortedRows=(rows=sourceRows())=>[...rows].sort((a,b)=>
 (parseDate(b.date)?.getTime()||0)-(parseDate(a.date)?.getTime()||0));
const optionsFor=key=>{
 const definition=filterDefinitions.find(x=>x.key===key);
 return definition?definition.options(sourceRows()):[];
};
export function filterFlightRows(rows,filters,query=''){
 const q=normalizeFilterSearch(query);
 const f=filters;
 return sortedRows(rows).filter(row=>{
  const match=(key,value)=>filterMatchesSelected(value,f[key]||[]);
  return match('year',yearFromRow(row))&&match('airline',row.airline)&&
   (!(f.who||[]).length||splitPeople(row.who).some(person=>match('who',person)))&&
   match('from_airport',row.from_airport)&&match('to_airport',row.to_airport)&&
   match('airplane',row.airplane)&&match('flight_code',row.flight_code)&&
   (!q||normalizeRegistration(row.registration).toLowerCase().includes(q));
 });
}
const filteredRows=()=>filterFlightRows(sourceRows(),activeFilters,searchTerm);

const stats=rows=>({
 flights:rows.length,
 regs:new Set(rows.map(r=>normalizeText(r.registration)).filter(Boolean)).size,
 routes:new Set(rows.map(r=>normalizeText(r.from_airport)+'→'+normalizeText(r.to_airport))
       .filter(x=>x!=='→')).size,
 years:new Set(rows.map(yearFromRow).filter(Boolean)).size,
});
export const flightLogTestHelpers={
 normalizeRow,normalizeWho,normalizeRegistration,getCurrentRegistration,
 parseDate,toInputDate,niceDate,yearFromRow,uniqueYears,uniqueValues,
 uniquePeople,blankFilters,stats,filterMatchesSelected
};
// Exposed solely to protect local-last-seen formatting and live-only LGW rules in tests.
export const flightStatusTestHelpers={relativeLocalSeen,isCurrentGatwick};
function updateStats(rows){
 const s=stats(rows);
 for(const [name,value] of Object.entries(s)){
  const element=document.getElementById('flightsStat'+name[0].toUpperCase()+name.slice(1));
  if(element)element.textContent=String(value);
 }
}
function feedback(message,error=false){
 const el=document.getElementById('flightsFeedback');
 if(el){el.textContent=message;el.classList.toggle('error',error);}
}
function currentReg(row){
 return getCurrentRegistration(row.registration);
}
function lgw(text){return /\b(?:LGW|EGKK)\b/i.test(String(text||''));}
function liveFor(row){return lastLive[currentReg(row).toUpperCase()]||{status:'N/A'};}
function isCurrentGatwick(item){
 return String(item.status||'').startsWith('Flying')&&item.route_confidence!=='usual'&&lgw(item.route);
}
function liveGatwick(row){return isCurrentGatwick(liveFor(row));}
function statusBadge(row){
 const item=liveFor(row),status=String(item.status||'N/A');
 const highlight=liveGatwick(row);
 return '<span class="flights-live-chip'+(highlight?' flights-lgw':'')+
  (status==='N/A'?' is-unknown':'')+'" title="'+escapeHtml(item.source?'Live: '+item.source:'No current reliable live position')+
  '" data-live-reg="'+escapeHtml(currentReg(row).toUpperCase())+'">'+escapeHtml(status)+'</span>';
}
function relativeLocalSeen(timestamp,now=Date.now()/1000){
 const then=Number(timestamp);
 if(!Number.isFinite(then)||then<=0)return '';
 const age=Math.max(0,Math.round(now-then));
 if(age<60)return 'Seen just now';
 if(age<3600)return 'Seen '+Math.floor(age/60)+'m ago';
 if(age<86400)return 'Seen '+Math.floor(age/3600)+'h ago';
 if(age<86400*30)return 'Seen '+Math.floor(age/86400)+'d ago';
 if(age<86400*365)return 'Seen '+Math.floor(age/(86400*30))+'mo ago';
 return 'Seen '+Math.floor(age/(86400*365))+'y ago';
}
function localLastSeen(row){
 const item=liveFor(row),stamp=item.local_last_seen_at;
 const label=relativeLocalSeen(stamp),hex=String(item.local_hex||'').toUpperCase();
 if(!label||!/^[0-9A-F]{6}$/.test(hex))return '';
 // This hex and timestamp come exclusively from Aerodrome's own database.
 const url='http://'+location.hostname+':8000/aircraft/'+hex;
 const exact=new Date(Number(stamp)*1000).toLocaleString('en-GB',{timeZone:'Europe/London'});
 return '<a class="flights-local-seen" href="'+escapeHtml(url)+
  '" target="_blank" rel="noopener noreferrer" title="Seen by your antenna: '+escapeHtml(exact)+
  ' · Open Aerodrome aircraft history">'+escapeHtml(label)+'</a>';
}

// Show full Who names on desktop and in details, a short label on phones.
function shortWho(value){
 const names=splitPeople(value);
 if(!names.length)return '—';
 if(names.length===1)return names[0].length>12?names[0].slice(0,11)+'…':names[0];
 return names[0].slice(0,10)+' +'+(names.length-1);
}
function rowHtml(row){
 const reg=currentReg(row),live=liveFor(row),route=normalizeUpper(row.from_airport)+' → '+normalizeUpper(row.to_airport);
 const date=niceDate(row.date),shortDate=date.replace(/(\d{4})$/,(_,year)=>year.slice(-2));
 const fr24='https://www.flightradar24.com/data/aircraft/'+encodeURIComponent(reg);
 const regLink=reg&&!/^no reg$/i.test(reg)?
  '<a class="flights-reg" target="_blank" rel="noopener noreferrer" href="'+escapeHtml(fr24)+'">'+escapeHtml(row.registration)+'</a>':
  '<span class="flights-no-reg">—</span>';
 return '<tr class="flights-row'+(liveGatwick(row)?' flights-highlight':'')+
  (manageMode?' flights-selectable':'')+'" data-flight-id="'+escapeHtml(row.id)+
  '" tabindex="0" role="button" aria-label="'+escapeHtml((manageMode||'View')+' flight '+row.flight_code)+'">'+
  '<td class="flights-cell-date"><span class="flights-desktop-date">'+escapeHtml(date)+
  '</span><span class="flights-mobile-date">'+escapeHtml(shortDate)+'</span></td>'+
  '<td class="flights-cell-route">'+escapeHtml(route)+'</td>'+
  '<td class="flights-cell-code">'+escapeHtml(row.flight_code||'—')+'</td>'+
  '<td class="flights-cell-airline">'+escapeHtml(row.airline||'—')+'</td>'+
  '<td class="flights-cell-aircraft">'+escapeHtml(row.airplane||'—')+'</td>'+
  '<td class="flights-cell-reg"><div class="flights-reg-line">'+regLink+localLastSeen(row)+
  '</div>'+statusBadge(row)+'</td>'+
  '<td class="flights-cell-who" title="'+escapeHtml(row.who||'')+'">'+
  '<span class="flights-who-full">'+escapeHtml(row.who||'—')+'</span>'+
  '<span class="flights-who-short">'+escapeHtml(shortWho(row.who))+'</span></td></tr>';
}
function renderTable(){
 const rows=filteredRows();updateStats(rows);
 const count=document.getElementById('flightsResults');
 if(count)count.textContent=rows.length+' flight'+(rows.length===1?'':'s')+' shown';
 const table=document.getElementById('flightsTableBody');
 if(!table)return;
 table.innerHTML=rows.length?rows.map(rowHtml).join(''):
  '<tr><td colspan="7" class="flights-empty">No matching flights</td></tr>';
 table.querySelectorAll('[data-flight-id]').forEach(element=>{
  const id=element.dataset.flightId;
  const activate=()=>{
   const row=sourceRows().find(item=>item.id===id);
   if(!row)return;
   if(manageMode==='edit'){exitManage();showModal(row);}
   else if(manageMode==='delete'){exitManage();deleteFlight(id);}
   else showFlightDetails(row);
  };
  element.onclick=event=>{
   if(!manageMode&&event.target.closest('a,button'))return;
   if(manageMode)event.preventDefault();
   activate();
  };
  element.onkeydown=event=>{
   if(event.target!==element||!['Enter',' '].includes(event.key))return;
   event.preventDefault();activate();
  };
  element.querySelectorAll('a').forEach(link=>link.onclick=event=>{
   if(!manageMode)return;
   event.preventDefault();event.stopPropagation();activate();
  });
 });
}
function renderManage(){
 const bar=document.getElementById('flightsManageBar');
 const toggle=document.getElementById('flightsManage');
 if(!bar||!toggle)return;
 bar.hidden=!manageActive;toggle.setAttribute('aria-expanded',String(manageActive));
 toggle.classList.toggle('active',manageActive);
 document.getElementById('flightsManageHint').textContent=
  manageMode==='edit'?'Tap a flight to edit':manageMode==='delete'?'Tap a flight to delete':'Choose Edit or Delete';
 for(const mode of ['edit','delete']){
  const button=document.getElementById('flightsManage'+mode[0].toUpperCase()+mode.slice(1));
  button.classList.toggle('active',manageMode===mode);
  button.setAttribute('aria-pressed',String(manageMode===mode));
 }
 renderTable();
}
function exitManage(){manageActive=false;manageMode=null;renderManage();}
function flightDetailsHtml(){
 return '<div class="flights-modal-backdrop" id="flightsDetails" aria-hidden="true">'+
  '<div class="flights-sheet flights-details-sheet" role="dialog" aria-modal="true" aria-labelledby="flightsDetailsTitle">'+
  '<div class="flights-modal-top"><h2 id="flightsDetailsTitle">Flight details</h2>'+
  '<button class="btn small" id="flightsDetailsClose" type="button">Close</button></div>'+
  '<div id="flightsDetailsContent"></div></div></div>';
}
function closeFlightDetails(){
 const modal=document.getElementById('flightsDetails');
 if(modal){modal.classList.remove('show');modal.setAttribute('aria-hidden','true');}
}
function showFlightDetails(row){
 const live=liveFor(row),reg=currentReg(row),hex=String(live.hex||'').toUpperCase();
 const localHex=String(live.local_hex||'').toUpperCase();
 const route=normalizeUpper(row.from_airport)+' → '+normalizeUpper(row.to_airport);
 const links=[];
 if(reg&&!/^no reg$/i.test(reg))links.push(
  '<a class="btn small" target="_blank" rel="noopener noreferrer" href="https://www.flightradar24.com/data/aircraft/'+
  encodeURIComponent(reg)+'">FR24 aircraft history</a>');
 if(/^[0-9A-F]{6}$/.test(localHex))links.push(
  '<a class="btn small" target="_blank" rel="noopener noreferrer" href="http://'+
  location.hostname+':8000/aircraft/'+localHex+'">Aerodrome history</a>');
 if(/^[0-9A-F]{6}$/.test(hex))links.push(
  '<a class="btn small" target="_blank" rel="noopener noreferrer" href="http://'+
  location.hostname+':1099/map/?icao='+hex+'&noIsolation">Live local map</a>');
 document.getElementById('flightsDetailsTitle').textContent=row.flight_code||'Flight details';
 document.getElementById('flightsDetailsContent').innerHTML=
  '<div class="flights-detail-grid">'+
  [['Date',niceDate(row.date)],['Route',route],['Airline',row.airline],
   ['Aircraft',row.airplane],['Registration',row.registration],['Who',row.who],
   ['Live status',live.status||'N/A']].map(([key,value])=>
   '<div><span>'+escapeHtml(key)+'</span><strong>'+escapeHtml(value||'—')+'</strong></div>').join('')+
  '</div><div class="flights-detail-links">'+links.join('')+'</div>';
 const modal=document.getElementById('flightsDetails');
 modal.classList.add('show');modal.setAttribute('aria-hidden','false');
}
function renderFilters(){
 const strip=document.getElementById('flightsFilterStrip');
 if(!strip)return;
 for(const k of Object.keys(activeFilters)){
  const available=optionsFor(k);
  activeFilters[k]=(activeFilters[k]||[]).filter(v=>available.includes(v));
 }
 strip.innerHTML=filterDefinitions.map(config=>{
  const selected=activeFilters[config.key]||[];
  const value=selected.length===0?'All':selected.length===1?selected[0]:selected.length+' selected';
  return '<button type="button" class="flights-filter'+(selected.length?' active':'')+
   '" data-filter="'+escapeHtml(config.key)+'" aria-pressed="'+(selected.length?'true':'false')+'">'+
   '<small>'+escapeHtml(config.label)+'</small><strong>'+escapeHtml(value)+'</strong></button>';
 }).join('');
 strip.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{
  if(filterOpen===b.dataset.filter){closeFilter();return;}
  filterOpen=b.dataset.filter;renderPopover();
 });
}
function closeFilter(){
 filterOpen=null;
 const popover=document.getElementById('flightsFilterPopover');
 if(popover)popover.hidden=true;
}
function renderPopover(){
 const popover=document.getElementById('flightsFilterPopover');
 if(!popover||!filterOpen)return;
 const config=filterDefinitions.find(f=>f.key===filterOpen);
 if(!config){closeFilter();return;}
 const options=optionsFor(filterOpen),selected=activeFilters[filterOpen]||[];
 popover.hidden=false;
 document.getElementById('flightsFilterTitle').textContent=selected.length?
   'Change '+config.label.toLowerCase():'Choose '+config.label.toLowerCase();
 const list=document.getElementById('flightsFilterList');
 list.innerHTML='<button class="flights-filter-option'+(!selected.length?' active':'')+'" data-value="all">All '+escapeHtml(config.label.toLowerCase())+'</button>'+
  options.map(v=>'<button class="flights-filter-option'+(selected.includes(v)?' active':'')+'" data-value="'+escapeHtml(v)+'">'+escapeHtml(v)+'</button>').join('');
 list.querySelectorAll('[data-value]').forEach(button=>button.onclick=()=>{
  const v=button.dataset.value,key=filterOpen,current=activeFilters[key]||[];
  activeFilters[key]=v==='all'?[]:current.includes(v)?current.filter(x=>x!==v):[...current,v];
  renderFilters();renderTable();renderPopover();
 });
}
function clearFilters(){
 searchTerm='';activeFilters=blankFilters();
 const search=document.getElementById('flightsRegSearch');if(search)search.value='';
 closeFilter();renderFilters();renderTable();requestStatuses();
}
async function copyRegs(button){
 // Exact source behaviour: unique current registration, comma-space separated,
 // only for rows passing the current search and multi-select filters.
 const regs=[...new Set(filteredRows().map(currentReg).filter(Boolean))];
 if(!regs.length){feedback('No registrations to copy.');return;}
 const text=regs.join(', ');
 try{await navigator.clipboard.writeText(text);}
 catch{
  const area=document.createElement('textarea');
  area.value=text;area.readOnly=true;area.style.position='fixed';area.style.top='-9999px';
  document.body.appendChild(area);area.select();document.execCommand('copy');area.remove();
 }
 const original=button.textContent;
 button.textContent='Copied!';
 setTimeout(()=>{if(button.isConnected)button.textContent=original;},900);
}
const formFields=[
 ['date','Date','date',''],['registration','Registration','text','G-WUKU'],
 ['from_airport','From airport','text','LGW'],['to_airport','To airport','text','VIE'],
 ['flight_code','Flight code','text','W95776'],['airline','Airline','text','Wizz Air'],
 ['airplane','Airplane','text','A321neo(XLR)'],['who','Who','text','Matthew, Florence']
];
function modalHtml(){
 return '<div class="flights-modal-backdrop" id="flightsModal" aria-hidden="true"><div class="flights-sheet" role="dialog" aria-modal="true" aria-labelledby="flightsModalTitle">'+
 '<div class="flights-modal-top"><h2 id="flightsModalTitle">Add flight</h2><button type="button" class="btn small" id="flightsModalClose">Close</button></div>'+
 '<form id="flightsEditForm"><div class="flights-form-grid">'+formFields.map(([key,label,type,placeholder])=>
  '<label>'+label+'<input id="flightField_'+key+'" type="'+type+'" placeholder="'+escapeHtml(placeholder)+
  '" '+(key==='who'?'':'required')+' autocomplete="off"></label>').join('')+
 '</div><div class="flights-modal-actions"><button type="submit" class="btn primary" id="flightsSave">Save flight</button>'+
 '<button type="button" class="btn small danger" id="flightsDelete" hidden>Delete flight</button></div>'+
 '<p class="flights-form-feedback" id="flightsFormFeedback"></p></form></div></div>';
}
function closeModal(){
 selectedFlightId=null;
 const modal=document.getElementById('flightsModal');
 if(modal){modal.classList.remove('show');modal.setAttribute('aria-hidden','true');}
}
function showModal(row=null){
 selectedFlightId=row?.id||null;
 document.getElementById('flightsModalTitle').textContent=row?'Edit flight':'Add flight';
 const form=document.getElementById('flightsEditForm');form.reset();
 document.getElementById('flightsFormFeedback').textContent='';
 document.getElementById('flightsDelete').hidden=!row;
 for(const [key] of formFields){
  const input=document.getElementById('flightField_'+key);
  input.value=row?(key==='date'?toInputDate(row.date):row[key]||''):'';
 }
 const modal=document.getElementById('flightsModal');
 modal.classList.add('show');modal.setAttribute('aria-hidden','false');
 document.getElementById('flightField_date').focus();
}
async function loadFlights(showLoading=false){
 if(showLoading)feedback('Loading Google Sheets…');
 const d=await api('/api/flights/records');
 allFlights=Array.isArray(d.flights)?d.flights:[];
 sheetWarning=d.cached?d.warning||'SheetDB temporarily unavailable':'';
 closeFilter();renderFilters();renderTable();
 if(sheetWarning)feedback(sheetWarning,true);
 else if(showLoading)feedback('');
 // Aircraft status is strictly optional and must not hold up SheetDB loading.
 requestStatuses().catch(()=>{});
}
function payloadFromForm(){
 const payload={};
 for(const [key] of formFields){
  const input=document.getElementById('flightField_'+key);
  payload[key]=key==='who'?normalizeWho(input.value):
   (['registration','from_airport','to_airport','flight_code'].includes(key)?normalizeUpper(input.value):normalizeText(input.value));
 }
 return payload;
}
async function saveFlight(event){
 event.preventDefault();
 const save=document.getElementById('flightsSave'),status=document.getElementById('flightsFormFeedback');
 save.disabled=true;status.textContent='Saving to Google Sheets…';
 const body={action:selectedFlightId?'update':'create',data:payloadFromForm()};
 if(selectedFlightId)body.id=selectedFlightId;
 try{
  await api('/api/flights/records',body);
  closeModal();await loadFlights();feedback('Flight saved to Google Sheets.');
 }catch(e){status.textContent=e.message||'Could not save flight.';}
 finally{save.disabled=false;}
}
async function deleteFlight(id){
 if(!confirm('Delete this flight from Google Sheets?'))return false;
 try{
  await api('/api/flights/records',{action:'delete',id});
  closeModal();await loadFlights();
  feedback('Flight deleted from Google Sheets.');
  return true;
 }catch(e){feedback(e.message||'Delete failed.',true);return false;}
}
async function requestStatuses(){
 const serial=++statusRequestNumber;
 const rows=filteredRows(),regs=[...new Set(rows.map(currentReg).map(v=>v.toUpperCase())
  .filter(v=>/^[A-Z0-9-]{2,16}$/.test(v)))].slice(0,80);
 if(!regs.length){lastLive={};renderTable();return;}
 const version=flightsGeneration;
 try{
  const response=await api('/api/flights/live?regs='+encodeURIComponent(regs.join(',')));
  if(version!==flightsGeneration||serial!==statusRequestNumber||!document.getElementById('flightsTableBody'))return;
  const aircraft=response.aircraft||{};
  lastLive=aircraft;
  // Only refresh the table, never the search field or open form.
  renderTable();
  const status=document.getElementById('flightsLiveTimestamp');
  if(status){
   const stamp=response.checked_at?new Date(response.checked_at*1000)
    .toLocaleTimeString('en-GB',{timeZone:'Europe/London',hour:'2-digit',minute:'2-digit'}):'';
   status.textContent=response.warning?'Live data temporarily limited':'Live status checked '+stamp;
  }
 }catch(e){
  const status=document.getElementById('flightsLiveTimestamp');
  if(status)status.textContent='Live status temporarily unavailable';
 }
}
function scheduleStatusRefresh(first=false){
 if(flightTimer)clearTimeout(flightTimer);
 // One early refresh lets the asynchronous route lookup populate the
 // flight table without making the initial Google Sheet load wait.
 flightTimer=setTimeout(async()=>{
  if(location.hash==='#flights'&&document.getElementById('flightsTableBody')){
   try{await requestStatuses();}finally{scheduleStatusRefresh(false);}
  }
 },first?12000:35000);
}
export function stopFlightsPage(){
 flightsGeneration++;statusRequestNumber++;manageActive=false;manageMode=null;
 if(flightTimer){clearTimeout(flightTimer);flightTimer=null;}
}
export async function renderFlightsPage(){
 stopFlightsPage();
 const root=document.getElementById('page');
 if(!root)return;
 root.innerHTML='<div class="flights-page">'+
  '<section class="flights-hero"><div class="flights-top"><div>'+
  '<span class="flights-eyebrow">✈ Personal flight tracker</span><h1>My Flight Log</h1>'+
  '<div class="flights-actions"><button type="button" class="btn primary" id="flightsAdd">+ Add flight</button>'+
  '<button type="button" class="btn" id="flightsRefresh">Refresh</button>'+
  '<button type="button" class="btn" id="flightsCopy">Copy Reg’s</button>'+
  '<button type="button" class="btn" id="flightsManage" aria-expanded="false">Manage</button></div></div>'+
  '<div class="flights-stats">'+
  [['Flights','Flights'],['Regs','Regs'],['Routes','Routes'],['Years','Years']].map(([label,key])=>
   '<div class="flights-stat"><strong id="flightsStat'+key+'">0</strong><small>'+label+'</small></div>').join('')+
  '</div></div></section>'+
  '<section class="flights-panel">'+
  '<div class="flights-search-row"><input id="flightsRegSearch" type="search" placeholder="Search registration, e.g. G-WUKU" aria-label="Search registration">'+
  '<button class="btn" id="flightsClear">Clear</button></div>'+
  '<div class="flights-filter-strip" id="flightsFilterStrip"></div>'+
  '<div class="flights-popover" id="flightsFilterPopover" hidden><div class="flights-popover-top">'+
  '<strong id="flightsFilterTitle">Choose a filter</strong><button class="btn small" id="flightsCloseFilter">Close</button></div>'+
  '<div class="flights-popover-list" id="flightsFilterList"></div></div>'+
  '<div id="flightsManageBar" class="flights-manage-bar" hidden>'+
  '<button class="btn small" id="flightsManageEdit" type="button">Edit</button>'+
  '<button class="btn small" id="flightsManageDelete" type="button">Delete</button>'+
  '<span id="flightsManageHint">Choose Edit or Delete</span>'+
  '<button class="btn small" id="flightsManageDone" type="button">Done</button></div>'+
  '</section><section class="flights-list" aria-label="Filtered flights">'+
  '<div class="flights-results-row"><span id="flightsResults">Loading flights…</span></div>'+
  '<p id="flightsFeedback" class="flights-feedback" role="status"></p>'+
  '<div class="flights-table-wrap"><table class="flights-table">'+
  '<colgroup><col class="fc-date"><col class="fc-route"><col class="fc-flight">'+
  '<col class="fc-airline"><col class="fc-aircraft"><col class="fc-reg"><col class="fc-who"></colgroup>'+
  '<thead><tr><th>Date</th><th>Route</th><th>Flight</th>'+
  '<th class="flights-cell-airline">Airline</th><th class="flights-cell-aircraft">Aircraft</th>'+
  '<th>Reg / Live</th><th class="flights-cell-who">Who</th></tr></thead>'+
  '<tbody id="flightsTableBody"><tr><td colspan="7" class="flights-empty">Loading flights…</td></tr></tbody>'+
  '</table></div></section>'+modalHtml()+flightDetailsHtml()+'</div>';
 document.getElementById('flightsAdd').onclick=()=>showModal();
 document.getElementById('flightsManage').onclick=()=>{manageActive=!manageActive;manageMode=null;renderManage();};
 document.getElementById('flightsManageEdit').onclick=()=>{manageActive=true;manageMode='edit';renderManage();};
 document.getElementById('flightsManageDelete').onclick=()=>{manageActive=true;manageMode='delete';renderManage();};
 document.getElementById('flightsManageDone').onclick=exitManage;
 document.getElementById('flightsDetailsClose').onclick=closeFlightDetails;
 document.getElementById('flightsDetails').onclick=event=>{
  if(event.target.id==='flightsDetails')closeFlightDetails();
 };
 document.getElementById('flightsRefresh').onclick=()=>loadFlights(true).catch(e=>feedback(e.message,true));
 document.getElementById('flightsCopy').onclick=e=>copyRegs(e.currentTarget);
 document.getElementById('flightsClear').onclick=clearFilters;
 document.getElementById('flightsRegSearch').oninput=e=>{searchTerm=e.target.value||'';renderTable();requestStatuses();};
 document.getElementById('flightsCloseFilter').onclick=closeFilter;
 document.getElementById('flightsModalClose').onclick=closeModal;
 document.getElementById('flightsModal').onclick=e=>{if(e.target.id==='flightsModal')closeModal();};
 document.getElementById('flightsEditForm').onsubmit=saveFlight;
 document.getElementById('flightsDelete').onclick=()=>{if(selectedFlightId)deleteFlight(selectedFlightId);};
 renderFilters();renderTable();
 try{await loadFlights(true);}
 catch(e){feedback(e.message||'Could not load flights from Google Sheets.',true);}
 scheduleStatusRefresh(true);
}