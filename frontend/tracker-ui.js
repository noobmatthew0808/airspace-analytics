/* Personal flight tracker. No flight log writes. */
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={flightbyte:'FlightByte',aviationstack:'Aviationstack',airlabs:'AirLabs',aerodatabox:'AeroDataBox',mapflights:'map.flights',weather:'Aviation Weather Center'};
const labels={dep_gate:'Departure gate',arr_gate:'Arrival gate',dep_terminal:'Departure terminal',arr_terminal:'Arrival terminal',belt:'Baggage carousel',status:'Flight status',registration:'Aircraft registration',checkin:'Check-in desks',dep_est:'Departure time',arr_est:'Arrival time'};
const name=s=>names[s]||names[String(s).replace(/-(dep|arr)$/,'')]||s;
const dateLabel=d=>String(d||'').split('-').reverse().join('/');
const clock=t=>String(t||'').match(/T(\d\d:\d\d)/)?.[1]||'—';
const time=t=>new Date(t*1000).toLocaleString('en-GB',{timeZone:'Europe/London',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
async function api(path,body){
 const res=await fetch('/api/tracker'+path,{cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
 const d=await res.json();if(!res.ok)throw Error(d.error||'Request failed');return d;
}
let generation=0,timer=null,host=null,updating=false;
const val=(t,k)=>t.fields?.[k]?.value||'';
const source=(t,k)=>t.fields?.[k]?`<small title="Last received ${esc(time(t.fields[k].at))} UK">${esc(name(t.fields[k].source))} · ${esc(time(t.fields[k].at))}</small>`:'<small>Not reported</small>';
const status=t=>!t.active?'Paused / completed':val(t,'status')||'Awaiting flight data';
const field=(t,k,label)=>`<div class="ft-fact"><span>${label}</span><strong>${esc(val(t,k)||'—')}</strong>${source(t,k)}</div>`;
function tripMarkup(t){
 const v=k=>val(t,k);
 const timing=(pre,airport)=>`<div class="ft-airport"><span>${pre==='dep'?'DEPARTURE':'ARRIVAL'}</span><strong>${esc(airport)}</strong><b>${clock(v(pre+'_actual')||v(pre+'_est')||v(pre+'_scheduled'))}</b><small>${v(pre+'_actual')?'Actual':v(pre+'_est')?'Updated':'Scheduled'} · airport local</small>${v(pre+'_scheduled')&&v(pre+'_est')&&clock(v(pre+'_scheduled'))!==clock(v(pre+'_est'))?`<small>Scheduled ${clock(v(pre+'_scheduled'))}</small>`:''}${source(t,v(pre+'_actual')?pre+'_actual':v(pre+'_est')?pre+'_est':pre+'_scheduled')}</div>`;
 return `<article class="ft-trip" data-trip="${esc(t.id)}"><header class="ft-trip-head"><div><span class="ft-eyebrow">${esc(dateLabel(t.date))}</span><h2>${esc(t.flight)}</h2></div><span class="ft-status">${esc(status(t))}</span></header>
 <div class="ft-route">${timing('dep',t.origin)}<div class="ft-route-line"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 16l9-3V5l2-2 2 2v8l7 3v2l-7-1v4l-2 1-2-1v-4l-9 1z"/></svg></div>${timing('arr',t.destination)}</div>
 <div class="ft-facts">${field(t,'dep_terminal','Terminal')}${field(t,'dep_gate','Departure gate')}${field(t,'belt','Baggage belt')}${field(t,'arr_terminal','Arrival terminal')}${field(t,'arr_gate','Arrival gate')}${field(t,'checkin','Check-in')}</div>
 <div class="ft-airframe"><div><span class="ft-eyebrow">ASSIGNED AIRCRAFT</span><strong>${esc(v('registration')||'Not assigned')}</strong><small>${esc([v('aircraft_type'),v('callsign')].filter(Boolean).join(' · '))}</small>${source(t,'registration')}</div>${v('registration')&&/^[A-Z0-9-]{2,16}$/.test(v('registration'))?`<a class="btn small" href="https://www.flightradar24.com/data/aircraft/${encodeURIComponent(v('registration').toLowerCase())}" target="_blank" rel="noopener noreferrer">Aircraft history ↗</a>`:''}</div>
 ${t.live?`<div class="ft-live"><b>${esc(t.live.status)}</b><small> · ${esc(t.live.source)} · ${esc(time(t.live.last_observed_at))} UK</small></div>`:''}
 <details class="ft-detail" data-section="timeline" open><summary>Flight timeline <span>${t.events.length}</span></summary>${t.events.length?`<div class="ft-timeline">${t.events.map(e=>`<div><i></i><section><strong>${esc(labels[e.field]||e.field)} · ${esc(e.value)}</strong><small>${esc(time(e.at))} UK · ${esc(name(e.source))}${e.delivery==='sent'?' · Notified':e.delivery==='failed'?' · Notification failed':''}</small></section></div>`).join('')}</div>`:'<p class="muted">Flight changes will appear here as they are reported.</p>'}</details>
 <details class="ft-detail" data-section="weather"><summary>Airport weather</summary><div class="ft-weather">${['dep','arr'].map((k,i)=>`<div><b>${esc(i?t.destination:t.origin)}</b><p>${esc(v(k+'_weather')||'No METAR available yet')}</p>${source(t,k+'_weather')}</div>`).join('')}</div></details>
 <details class="ft-detail" data-section="acars"><summary>Live ACARS <span>${(t.messages||[]).length}</span></summary>${!t.acars?'<p class="muted">Enable ACARS below to collect messages for this flight.</p>':(t.messages||[]).length?`<div class="ft-messages">${t.messages.map(m=>`<div><small>${esc(time(m.timestamp))} UK · ${esc(m.protocol||'ACARS')} · ${esc(m.flight||m.reg||'')}</small><p>${esc(m.text)}</p></div>`).join('')}</div>`:'<p class="muted">Waiting for a matched aircraft or callsign and available datalink messages.</p>'}</details>
 <details class="ft-detail" data-section="sources"><summary>Data sources</summary>${t.sources.length?t.sources.map(s=>`<div class="ft-source"><b>${esc(name(s.provider))}</b><small>${esc(s.note)}</small></div>`).join(''):'<p class="muted">Waiting for the background worker.</p>'}<p class="tiny muted">Data: map.flights. Flight data (c) map.flights, adsb.fi; attribution required. Contains information from Mictronics Aircraft Database under ODC Attribution License (ODC-BY 1.0) and plane-alert-db (sdr-enthusiasts) under ODbL 1.0.</p></details>
 <footer class="ft-controls"><label><input type="checkbox" data-opt="notify" ${t.notify?'checked':''}> Push alerts</label><label><input type="checkbox" data-opt="acars" ${t.acars?'checked':''}> ACARS</label><button class="btn small" data-action="${t.active?'pause':'resume'}">${t.active?'Pause':'Resume'}</button><button class="btn small" data-action="delete">Remove</button></footer></article>`;
}
function renderData(d){
 if(!host)return;
 const list=host.querySelector('.ft-list'),suggest=host.querySelector('.ft-suggestions');
 const details=new Map([...list.querySelectorAll('[data-trip]')].map(el=>[el.dataset.trip,[...el.querySelectorAll('details[open]')].map(x=>x.dataset.section)]));
 list.innerHTML=d.trips.length?d.trips.map(tripMarkup).join(''):'<div class="ft-empty"><h3>No tracked flights yet</h3><p>Add your next journey above. Monitoring runs on your server even when you close the website.</p></div>';
 for(const el of list.querySelectorAll('[data-trip]')){
  if(details.has(el.dataset.trip))for(const detail of el.querySelectorAll('details'))detail.open=details.get(el.dataset.trip).includes(detail.dataset.section);
  const id=el.dataset.trip;
  for(const b of el.querySelectorAll('[data-action]'))b.onclick=async()=>{if(b.dataset.action==='delete'&&!confirm('Remove this tracked flight? Your Flights log will not change.'))return;await action({action:b.dataset.action,id});};
  for(const b of el.querySelectorAll('[data-opt]'))b.onchange=()=>action({action:'options',id,notify:el.querySelector('[data-opt=notify]').checked,acars:el.querySelector('[data-opt=acars]').checked});
 }
 suggest.innerHTML=d.suggestions.length?`<span class="ft-eyebrow">SUGGESTED FROM YOUR FLIGHTS LOG</span>${d.suggestions.map((s,i)=>`<div class="ft-suggestion"><div><strong>${esc(s.flight)} <span>${esc(s.origin)} → ${esc(s.destination)}</span></strong><small>${esc(dateLabel(s.date))}</small></div><button class="btn small" data-suggestion="${i}">+ Track</button></div>`).join('')}`:'';
 suggest.hidden=!d.suggestions.length;
 for(const b of suggest.querySelectorAll('[data-suggestion]'))b.onclick=()=>{const s=d.suggestions[Number(b.dataset.suggestion)],form=host.querySelector('form');for(const k of ['flight','date','origin','destination'])form.elements[k].value=s[k];form.elements.arrival_date.value='';host.querySelector('.ft-add').open=true;form.elements.flight.focus();};
 host.querySelector('.ft-count').textContent=d.trips.filter(t=>t.active).length+' active';
}
async function refresh(g=generation){if(updating)return;updating=true;try{const d=await api('');if(g===generation&&host?.isConnected)renderData(d)}catch(e){if(g===generation&&host)host.querySelector('.ft-feedback').textContent=e.message}finally{updating=false}}
async function action(data){if(!host)return;const root=host;try{await api('/action',data);if(root===host){root.querySelector('.ft-feedback').textContent='Saved';await refresh()}}catch(e){if(root===host)root.querySelector('.ft-feedback').textContent=e.message}}
export function stopTrackerPage(){generation++;if(timer)clearInterval(timer);timer=null;host=null;}
export async function renderTrackerPage(){
 stopTrackerPage();const g=generation;const page=document.querySelector('#page');
 page.innerHTML=`<div class="ft-page"><header class="ft-heading"><div><span class="ft-eyebrow">YOUR NEXT JOURNEY</span><h1>Flight Tracker</h1><p>Live flight updates, gates, baggage and aircraft.</p></div><span class="ft-count">Loading</span></header>
 <div class="ft-suggestions" hidden></div>
 <details class="ft-add" open><summary><b>+ Track a flight</b><span>Flight number and travel date</span></summary>
 <form class="ft-form"><label>Flight number<input name="flight" placeholder="BA123" required maxlength="8"></label><label>Departure date<input name="date" type="date" required></label><label>From (IATA)<input name="origin" placeholder="LGW" required maxlength="3"></label><label>To (IATA)<input name="destination" placeholder="BTS" required maxlength="3"></label><label>Arrival date (optional)<input name="arrival_date" type="date"></label><div class="ft-form-options"><label><input type="checkbox" name="notify" checked> Push notifications</label><label><input type="checkbox" name="acars" checked> Live ACARS</label></div><button class="btn primary" type="submit">Start tracking</button></form></details>
 <p class="ft-feedback" role="status"></p><div class="ft-list"></div><p class="tiny muted">Flight data is best effort. Confirm gates, boarding and baggage with airport displays. Unreported fields stay blank. <a href="#settings">Manage APIs</a></p></div>`;
 host=page.querySelector('.ft-page');
 const form=host.querySelector('form');form.elements.date.value=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 form.onsubmit=async e=>{e.preventDefault();const root=host,b=form.querySelector('button');b.disabled=true;try{const d=Object.fromEntries(new FormData(form));d.notify=form.elements.notify.checked;d.acars=form.elements.acars.checked;await api('/action',{...d,action:'add'});if(root===host){root.querySelector('.ft-feedback').textContent='Flight added. Background monitoring started.';root.querySelector('.ft-add').open=false;await refresh(g)}}catch(err){if(root===host)root.querySelector('.ft-feedback').textContent=err.message}finally{b.disabled=false}};
 await refresh(g);if(g===generation)timer=setInterval(()=>refresh(g),10000);
}
export async function mountTrackerSettings(root){
 if(!root)return;
 try{const d=await api('/settings');if(!root.isConnected)return;
 root.innerHTML=`<details class="foldout"><summary>Flight Tracker providers</summary><p class="tiny muted">Free allowances only. Keys remain on the server. Connection results appear in each tracked flight's Data sources after a lookup. Existing map.flights credentials and keyless weather are reused.</p>${Object.entries(d).map(([p,s])=>`<details class="ft-provider" data-provider="${p}"><summary><b>${esc(s.name)}</b> <small>${s.key_set?'Key saved':'No key saved'} · ${s.used}/${s.limit} requests (rolling 31 days)</small></summary><form><label>API key<input type="password" name="key" autocomplete="off" placeholder="${s.key_set?'Saved — enter replacement':'Enter key'}"></label>${p==='aerodatabox'?'<label><input name="credit_only" type="checkbox"> I use earned feeder credits only, without paid billing.</label>':''}<div><button type="submit" class="btn small">Save key</button> <button type="button" data-clear class="btn small">Remove key</button></div><p role="status" class="tiny muted"></p></form></details>`).join('')}</details>`;
 for(const el of root.querySelectorAll('[data-provider]')){
  const form=el.querySelector('form'),p=el.dataset.provider,notice=form.querySelector('[role=status]');
  async function save(clear){try{await api('/key',{provider:p,clear,key:form.elements.key.value,credit_only:form.elements.credit_only?.checked===true});form.elements.key.value='';notice.textContent=clear?'Key removed':'Key saved; the next eligible tracked-flight lookup will test it.';el.querySelector('summary small').textContent=clear?'No key saved':'Key saved'}catch(e){notice.textContent=e.message}}
  form.onsubmit=e=>{e.preventDefault();save(false)};form.querySelector('[data-clear]').onclick=()=>{if(confirm('Remove this API key?'))save(true)};
 }
 }catch(e){root.textContent=e.message}
}
