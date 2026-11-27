/* Independent Alerts UI — no Traffic or Live ADS-B changes. */
const ae=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const at=n=>n==null?'Any':Number(n).toLocaleString('en-GB');
const whenAlert=n=>new Date(n*1000).toLocaleString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
const fields=[['type','Aircraft type'],['registration','Registration'],['callsign','Callsign'],['hex','ICAO hex'],['operator','Operator'],['military','Military']];
const providers=[
 {id:'flyitaly',name:'FlyItalyADSB',url:'https://api.flyitalyadsb.com/v2',hint:'Live positions and military metadata; check your feeder perk in My API.'},
 {id:'adsblol',name:'adsb.lol',url:'https://api.adsb.lol/v2',hint:'Enter your free feeder API key when eligible. The separate route lookup remains automatic.'},
 {id:'avioadsb',name:'AvioADSB',url:'https://avioadsb.org/v1',hint:'Claim your feeding station and create a contributor key on avioadsb.org/dashboard.'},
 {id:'adsbiq',name:'ADSBiq',url:'https://api.adsbiq.com/v2/all',hint:'Enable ADSBiq in ADSB.im, claim your station at adsbiq.com/join and copy your dashboard API key.'},
 {id:'adsbfi',name:'adsb.fi',url:'https://opendata.adsb.fi/api',hint:'Free public API; worldwide snapshot access uses your feeder IP.',keyless:true},
 {id:'airplaneslive',name:'airplanes.live',keyless:true,url:'https://api.airplanes.live/v2/reg/',hint:'Test from your feeder network to enable registration and nearby aircraft lookups.'},
 {id:'adsbhub',name:'ADSBHub',keyless:true,url:'tcp://data.adsbhub.org:5002',hint:'Set your public Data Access IP and SBS/30003 format, then test to activate the shared read-only stream.'},
 {id:'opensky',name:'OpenSky Network',oauth:true,url:'https://opensky-network.org/api/states/all',hint:'Create an OAuth API client on the OpenSky account page. Written permission for automated live use is required.'},
 {id:'planetrack',name:'PlaneTrack',url:'https://planetrack.ai/v1',hint:'Create a free key at planetrack.ai. Data: PlaneTrack.ai; contains information from the Mictronics aircraft database under ODC Attribution License. Free tier 2,000 credits/month; shared snapshots at most every 6 hours, history at most daily. Test checks the balance before live use.'},
 {id:'mapflights',name:'map.flights',url:'https://map.flights/api/v1',hint:'Feeder key: regional live data, observed routes and landing history. Poll 10s, up to 250 km around saved antenna; respects 1,000 daily non-live requests.'},
 {id:'flyoverhead',name:'Fly Overhead',url:'https://flyoverhead.com/api/public/aircraft/bounds',hint:'Free key: regional bounds endpoint, 65s polling to stay below 2,000 requests/day. Test checks compatible observed aircraft format. Route endpoint not verified.'}
];
let alertsData=null,alertsTimer=null,editingRule=null,alertsBusy=false;
const pendingProviders=new Set();
const providerMessages={};
function providerFeedback(id,message,error=false){
 providerMessages[id]={message,error,until:Date.now()+8000};
 const el=document.querySelector('#provider-result-'+id);
 if(el){el.textContent=message;el.className='alert-provider-result'+(error?' is-error':' is-good');}
}
function providerIcon(state){
 const paths={verified:'<circle cx="12" cy="12" r="10" fill="currentColor" stroke="none"/><path d="m7 12 3 3 7-7" stroke="var(--panel)" stroke-width="2.8"/>',
 saved:'<circle cx="12" cy="12" r="10"/><path d="m7 12 3 3 7-7"/>',
 missing:'<circle cx="12" cy="12" r="10"/><path d="m8 8 8 8m0-8-8 8"/>',
 key:'<circle cx="16" cy="8" r="5"/><path d="m12.5 11.5-9 9H2v-4l3-3h3v-3l4-4"/>',
 keyless:'<path d="m3 3 18 18M12 4a5 5 0 0 1 7 7m-9 2-7 7H2v-4l3-3h3l1-1"/>',
 pending:'<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>'};
 return '<svg class="alert-api-icon '+state+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths[state]+'</svg>';
}
function providerIcons(keyless,state){
 return '<span class="alert-api-icons" aria-hidden="true">'+providerIcon(keyless?'keyless':'key')+providerIcon(state)+'</span>';
}
async function alertApi(path,body){
 const opts=body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'};
 const response=await fetch(path,opts);
 const data=await response.json().catch(()=>({error:'Invalid server response'}));
 if(!response.ok)throw Error(data.error||'Request failed');
 return data;
}
function feedback(message,error=false){
 const node=document.querySelector('#alertFeedback');
 if(node){node.textContent=message;node.className='alert-feedback'+(error?' alert-fail':'');}
}
function ruleCard(r){
 const source=r.use_flyitaly?' · Backup APIs':' · Local only';
 return '<article class="alert-rule"><div class="alert-rule-main"><div class="alert-rule-title"><strong>'+ae(r.label)+'</strong><span class="alert-tag">'+at(r.active||0)+' active</span></div>'+
  '<div class="alert-rule-meta">'+ae(r.field==='military'?'Military':r.field+': '+r.pattern)+' · '+at(r.max_km)+' km · '+at(r.min_ft)+'–'+at(r.max_ft)+' ft'+source+'</div></div>'+
  '<div class="alert-rule-actions"><label class="alert-switch"><input type="checkbox" data-toggle="'+r.id+'" '+(r.enabled?'checked':'')+' aria-label="Enable alert"><span>On</span></label>'+
  '<button class="btn small" type="button" data-edit="'+r.id+'">Edit</button></div></article>';
}
function eventCard(e){
 return '<div class="alert-event"><div><strong>'+ae(e.rule_label)+'</strong> <span class="muted">'+ae(e.callsign||e.registration||e.hex)+'</span>'+
  '<div class="alert-event-meta">'+ae(e.aircraft_type||'Unknown')+' · '+ae(e.hex.toUpperCase())+' · '+at(e.distance_km)+' km · '+at(e.altitude_ft)+' ft'+(e.source!=='local'?' · '+ae(e.source):'')+'</div></div>'+
  '<div class="alert-event-time">'+whenAlert(e.created)+'<div>'+ae(e.delivery)+'</div></div></div>';
}
function providerCard(p,d){
 const info=d[p.id]||{},saved=!!info.key_set,test=d.provider_tests?.[p.id],local=providerMessages[p.id]?.until>Date.now()?providerMessages[p.id]:null;
 const verified=test?test.ok:!!(info.connected||info.last_success&&!info.error);
 const failed=test?test.ok===false:!!info.error;
 const state=failed||(!p.keyless&&!saved)?'missing':verified?'verified':p.keyless?'pending':'saved';
 const subtitle=p.keyless?(failed?'No key required · Test failed':verified?'No key required · Verified':(['airplaneslive','adsbhub'].includes(p.id)?'No key required · Test to activate':'No key required')):
  !saved?'No key saved':failed?'Connection failed':verified?'Verified':'Key saved · Not tested';
 const message=local?.message||test?.message||(info.error?'Connection failed: '+info.error:info.last_success?'Last successful connection: '+whenAlert(info.last_success):'');
 const error=local?local.error:failed;
 const usage=d.provider_usage?.[p.id];
 const background=usage?'<p class="alert-provider-note">Background: '+ae(usage.error?'Last attempt failed — '+usage.error:usage.last_attempt_seconds_ago==null?'Awaiting data':('Last attempt '+usage.last_attempt_seconds_ago+'s ago'))+(usage.matching_aircraft!=null?' · '+at(usage.matching_aircraft)+' tracked matches':'')+(usage.nearby_aircraft!=null?' · '+at(usage.nearby_aircraft)+' nearby matches':'')+(usage.retry_seconds>0?' · Next eligible in '+at(usage.retry_seconds)+'s':'')+'</p>':'';
 const result='<div id="provider-result-'+p.id+'" role="status" class="alert-provider-result'+(message?(error?' is-error':' is-good'):'')+'">'+ae(message)+(test?.at&&!local?' · '+ae(whenAlert(test.at)):'')+'</div>';
 return '<details class="foldout alert-config alert-provider" id="alert-'+p.id+'"><summary class="alert-api-summary">'+providerIcons(p.keyless,state)+'<span><strong>'+ae(p.name)+'</strong><small>'+ae(subtitle)+'</small></span></summary>'+
  '<form class="alert-config-content alert-provider-form" data-provider="'+p.id+'" autocomplete="off">'+
  '<div class="alert-provider-endpoint"><span>API endpoint</span><code>'+ae(p.url)+'</code></div>'+
  '<p class="alert-provider-note">'+ae(p.hint)+'</p>'+
  (p.oauth?'<label class="alert-field">OAuth client ID<input name="client_id" autocomplete="off" placeholder="Client ID"></label><label class="alert-clear"><input name="permission" type="checkbox"> I have written permission for automated OpenSky use</label>':'')+
  (p.keyless?'':'<label class="alert-field alert-wide">'+(p.oauth?'OAuth client secret':'API key')+' <small>'+(saved?'Key saved on server. Enter a replacement only if needed.':'Paste your API key.')+'</small>'+
  '<span class="alert-secret-row"><input name="key" type="password" autocomplete="new-password" placeholder="'+(saved?'Key saved — enter replacement':'Paste API key')+'"><button type="button" class="btn small" data-showkey="'+p.id+'">Show</button></span></label>')+
  '<div class="alert-editor-buttons">'+(p.keyless?'':'<button class="btn primary" type="submit">Save key</button>')+
  '<button class="btn small" type="button" '+(p.id==='adsbfi'?'id="alertAdsbfiTest" ':'')+'data-test-provider="'+p.id+'">Test connection</button>'+
  (p.keyless?'':'<button class="btn small alert-delete" type="button" data-remove-provider="'+p.id+'" '+(saved?'':'disabled')+'>Remove key</button>')+'</div>'+
  result+background+(p.id==='mapflights'?'<p class="alert-provider-note">Data: map.flights. Flight data (c) map.flights, adsb.fi; attribution required. Contains information from Mictronics Aircraft Database, which is made available under the ODC Attribution License (ODC-BY 1.0). Contains information from plane-alert-db (sdr-enthusiasts), which is made available under the Open Database License (ODbL 1.0).</p>':'')+
  (info.monthly_used!=null?'<p class="alert-provider-note">'+(p.id==='planetrack'?'Credits ':'Requests ')+ae(info.monthly_used)+'/'+ae(info.monthly_quota||'?')+'</p>':'')+
  '</form></details>';
}
function renderAlertPageContents(){
 const host=document.querySelector('#page');if(!host||!alertsData)return;
 const wasOpen=new Set([...host.querySelectorAll('details[open]')].map(x=>x.id).filter(Boolean));
 const d=alertsData,receiver=d.receiver||{},healthy=receiver.time&&!receiver.error&&Date.now()/1000-receiver.time<20;
 host.innerHTML='<div class="alert-page">'+
  '<div class="page-heading"><h1 class="page-title">Alerts</h1><button class="btn small" id="alertAdd" type="button">+ Add rule</button></div>'+
  '<div class="alert-status"><span class="alert-status-dot '+(healthy?'online':'')+'"></span>'+
  (healthy?at(receiver.aircraft)+(receiver.source?.startsWith('Aerodrome')?' aircraft seen (30s)':' aircraft')+' · Receiver connected'+(receiver.lat!=null?' · Antenna set':'')+
   (receiver.source?.startsWith('Aerodrome')?' · Aerodrome backup':''):'Receiver unavailable'+(receiver.error?' · '+ae(receiver.error):''))+'</div>'+
  '<div id="alertEditor"></div><div id="alertFeedback" role="status" class="alert-feedback"></div>'+
  '<section class="alert-rules">'+(d.rules.length?d.rules.map(ruleCard).join(''):'<div class="alert-empty">No rules configured yet.</div>')+'</section>'+
  '<details class="foldout alert-root-config" id="alertAllConfig"><summary><span>Configuration &amp; Logs <small>Notifications · Receiver · History</small></span></summary>'+
  '<div class="alert-config-stack">'+
  '<a class="btn small alert-api-settings-link" href="/analytics#settings">API settings</a>'+
  '<details class="foldout alert-config" id="alertNtfy"><summary><span>Notifications <small>'+(d.ntfy.topic?'Configured':'Not configured')+'</small></span></summary>'+
  '<form id="alertNtfyForm" class="alert-config-content"><div class="alert-form-grid">'+
  '<label class="alert-field">ntfy server<input name="server" type="url" required value="'+ae(d.ntfy.server)+'"></label>'+
  '<label class="alert-field">Topic<input name="topic" maxlength="80" value="'+ae(d.ntfy.topic)+'" placeholder="ntfy topic"></label>'+
  '<label class="alert-field alert-wide">Access token <small>'+(d.ntfy.token_set?'Saved — blank to keep':'Optional')+'</small><input name="token" type="password" autocomplete="off" placeholder="Leave blank to keep existing token"></label>'+
  '</div><div class="alert-editor-buttons"><button class="btn primary" type="submit">Save notifications</button><button class="btn small" type="button" id="alertTest">Send test</button>'+
  (d.ntfy.token_set?'<label class="alert-clear"><input type="checkbox" id="clearNtfyToken"> Clear token</label>':'')+'</div>'+
  '<p class="alert-provider-note">Send test publishes a priority 3 message. It confirms ntfy accepts it; check the iPhone lock screen for push delivery.</p>'+
  '</form></details>'+
  '<details class="foldout alert-config" id="alertReceiver"><summary><span>Receiver <small>'+(receiver.lat!=null&&receiver.lon!=null?'Antenna located':'Optional setup')+'</small></span></summary>'+
  '<form id="alertReceiverForm" class="alert-config-content"><div class="alert-form-grid">'+
  '<label class="alert-field alert-wide">Aircraft feed URL <small>Leave blank for automatic localhost and LAN detection</small><input name="url" type="url" value="'+ae(d.receiver_settings?.url||'')+'" placeholder="http://'+ae(location.hostname)+':1090/data/aircraft.json"></label>'+
  '<label class="alert-field">Antenna latitude<input name="lat" type="number" min="-90" max="90" step="any" value="'+ae(d.receiver_settings?.lat??'')+'" placeholder="Automatic"></label>'+
  '<label class="alert-field">Antenna longitude<input name="lon" type="number" min="-180" max="180" step="any" value="'+ae(d.receiver_settings?.lon??'')+'" placeholder="Automatic"></label>'+
  '</div><div class="alert-editor-buttons"><button class="btn primary" type="submit">Save receiver</button><button class="btn small" type="button" id="alertReceiverCheck">Test connection</button></div>'+
  '<p class="alert-provider-note">Test connection checks the local feed, number of aircraft and antenna coordinates. It does not create an alert.</p>'+
  '</form></details>'+
  '<details class="foldout alert-history" id="alertHistory"><summary><span>Recent alerts <small>'+d.events.length+' shown</small></span></summary>'+
  '<div class="alert-events">'+(d.events.length?d.events.slice(0,60).map(eventCard).join(''):'<div class="alert-empty">No alerts yet.</div>')+'</div></details>'+
  '</div></details></div>';
 bindAlerts();
 for(const id of wasOpen){const item=document.getElementById(id);if(item&&item.tagName==='DETAILS')item.open=true;}
 if(editingRule)editAlert(editingRule);
}
function editAlert(rule){
 editingRule=rule||{};
 const r=editingRule,node=document.querySelector('#alertEditor');
 if(!node)return;
 node.innerHTML='<form id="alertEditorForm" class="alert-editor alert-editor-compact">'+
  '<div class="alert-editor-heading"><strong>'+(r.id?'Edit alert':'New alert')+'</strong><button class="btn small" type="button" id="alertCancel">Cancel</button></div>'+
  '<div class="alert-compact-top">'+
  '<label class="alert-field">Name<input name="label" maxlength="50" required value="'+ae(r.label||'')+'" placeholder="Military nearby"></label>'+
  '<label class="alert-field">Match by<select name="field" id="alertField">'+fields.map(f=>'<option value="'+f[0]+'" '+(r.field===f[0]?'selected':'')+'>'+f[1]+'</option>').join('')+'</select></label>'+
  '</div>'+
  '<label class="alert-field alert-compact-pattern" id="alertPatternHolder">Codes / pattern<input name="pattern" maxlength="1800" required value="'+ae(r.pattern||'')+'" placeholder="A388, G-*, BAW*"></label>'+
  '<div class="alert-compact-limits">'+
  '<label class="alert-field">Distance (km)<input name="max_km" type="number" step="0.1" min="0.1" max="1000" value="'+ae(r.max_km??'')+'" placeholder="Any"></label>'+
  '<label class="alert-field">Min alt (ft)<input name="min_ft" type="number" min="-2000" max="70000" step="100" value="'+ae(r.min_ft??'')+'" placeholder="Any"></label>'+
  '<label class="alert-field">Max alt (ft)<input name="max_ft" type="number" min="-2000" max="70000" step="100" value="'+ae(r.max_ft??'')+'" placeholder="Any"></label>'+
  '</div>'+
  '<label class="alert-compact-backup"><input name="backup_apis" type="checkbox" '+(r.use_flyitaly?'checked':'')+'><strong>Backup APIs</strong></label>'+
  '<p class="alert-compact-note">Off: your antenna only. On: antenna + live API data. A distance limit enables nearby network detections.</p>'+
  '<div class="alert-editor-buttons"><button type="submit" class="btn primary">Save</button>'+
  (r.id?'<button type="button" class="btn small alert-delete" id="alertDelete">Delete</button>':'')+'</div></form>';
 const form=node.querySelector('form'),match=form.elements.field,pattern=form.elements.pattern;
 const sync=()=>{pattern.disabled=match.value==='military';pattern.required=!pattern.disabled;
  document.querySelector('#alertPatternHolder').hidden=pattern.disabled};
 match.onchange=sync;sync();
 document.querySelector('#alertCancel').onclick=()=>{editingRule=null;node.innerHTML='';};
 form.onsubmit=async e=>{
  e.preventDefault();if(alertsBusy)return;
  alertsBusy=true;
  try{
   const obj=Object.fromEntries(new FormData(form));
   obj.backup_apis=form.elements.backup_apis.checked;
   obj.enabled=r.enabled??1;if(r.id)obj.id=r.id;
   await alertApi('/api/alerts/rule',obj);
   editingRule=null;await refreshAlerts();feedback('Alert saved.');
  }catch(err){feedback(err.message,true)}finally{alertsBusy=false;}
 };
 if(r.id)document.querySelector('#alertDelete').onclick=async()=>{
  if(!confirm('Delete this alert rule?'))return;
  try{await alertApi('/api/alerts/delete',{id:r.id});editingRule=null;await refreshAlerts();feedback('Alert deleted.');}
  catch(err){feedback(err.message,true);}
 };
}
function bindAlerts(){
 document.querySelector('#alertAdd').onclick=()=>editAlert(null);
 document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>editAlert(alertsData.rules.find(r=>r.id===Number(b.dataset.edit))));
 document.querySelectorAll('[data-toggle]').forEach(b=>b.onchange=async()=>{
  const r=alertsData.rules.find(x=>x.id===Number(b.dataset.toggle));
  if(!r)return;
  try{await alertApi('/api/alerts/rule',{...r,enabled:b.checked});await refreshAlerts();}
  catch(err){b.checked=!b.checked;feedback(err.message,true);}
 });
 const receiver=document.querySelector('#alertReceiverForm');
 receiver.onsubmit=async e=>{
  e.preventDefault();
  try{
   await alertApi('/api/alerts/receiver',Object.fromEntries(new FormData(receiver)));
   await refreshAlerts();document.getElementById('alertAllConfig').open=true;
   document.getElementById('alertReceiver').open=true;feedback('Receiver settings saved.');
  }catch(err){feedback(err.message,true);}
 };
 document.querySelector('#alertReceiverCheck').onclick=async()=>{
  try{
   const result=await alertApi('/api/alerts/receiver/check',{});
   feedback(result.aircraft+' aircraft'+(result.coordinates_available?' · antenna coordinates available':' · antenna position missing')+
   (result.source?' · '+result.source:''));
  }catch(err){feedback(err.message,true);}
 };
 const ntfy=document.querySelector('#alertNtfyForm');
 ntfy.onsubmit=async e=>{
  e.preventDefault();const obj=Object.fromEntries(new FormData(ntfy));
  if(!obj.token&&!document.querySelector('#clearNtfyToken')?.checked)delete obj.token;
  try{await alertApi('/api/alerts/ntfy',obj);await refreshAlerts();
   document.getElementById('alertAllConfig').open=true;
   document.getElementById('alertNtfy').open=true;feedback('Notification settings saved.');
  }catch(err){feedback(err.message,true);}
 };
 document.querySelector('#alertTest').onclick=async()=>{
  try{await alertApi('/api/alerts/test',{});feedback('ntfy accepted the priority 3 test. Check your iPhone lock screen for push delivery.');}
  catch(err){feedback(err.message,true);}
 };
}
async function refreshAlerts(){alertsData=await alertApi('/api/alerts');if(location.hash==='#alerts')renderAlertPageContents();}
export async function renderAlertsPage(){
 if(alertsTimer)clearTimeout(alertsTimer);editingRule=null;
 const host=document.querySelector('#page');if(!host)return;
 host.innerHTML='<div class="loading">Loading alerts…</div>';
 try{await refreshAlerts()}catch(err){host.innerHTML='<div class="notice error-note">'+ae(err.message)+'</div>';return;}
 const poll=async()=>{
  if(location.hash!=='#alerts')return;
  try{
   if(!pendingProviders.size&&!document.querySelector('#alertEditorForm')&&!document.querySelector('.alert-config-stack :focus-within')&&![...document.querySelectorAll('.alert-provider-form input[name="key"]')].some(el=>el.value)&&!document.querySelector('.alert-provider-form input[name="client_id"]')?.value&&!document.querySelector('.alert-provider-form input[name="permission"]')?.checked){
    await refreshAlerts();
   }
  }catch{}
  alertsTimer=setTimeout(poll,10000);
 };
 alertsTimer=setTimeout(poll,10000);
}

// The existing provider cards and controls now live in Settings, using the
// original endpoints and persisted verification state unchanged.
let settingsProviderData=null;
function settingsProviderMarkup(d){return   '<details class="foldout alert-config" id="alertApis"><summary><span>ADS-B providers <small>Flights · Backup alerts</small></span></summary>'+
  '<div class="alert-config-stack alert-nested">'+
  '<p class="alert-explainer">Configured sources share live aircraft data for Flights and opted-in backup alerts. Each has its own limits and connection test. Receiver-only data and rules are unchanged.</p>'+
  '<div class="alert-api-legend"><span>'+providerIcon('key')+' Key required</span><span>'+providerIcon('keyless')+' Keyless</span><span>'+providerIcon('verified')+' Verified</span><span>'+providerIcon('saved')+' Key saved</span><span>'+providerIcon('missing')+' Missing / failed</span><span>'+providerIcon('pending')+' Not verified</span></div>'+
  providers.map(p=>providerCard(p,d)).join('')+
  '</div></details>';
}
async function refreshSettingsProviders(host){
 const d=await alertApi('/api/alerts');
 if(!host.isConnected||location.hash!=='#settings')return;
 settingsProviderData=d;
 const open=[...host.querySelectorAll('details[open]')].map(x=>x.id);
 // Keep unsaved text in other provider forms when a card is tested.
 const drafts=[...host.querySelectorAll('.alert-provider-form')].map(form=>({id:form.dataset.provider,key:form.elements.key?.value||'',client:form.elements.client_id?.value||'',permission:!!form.elements.permission?.checked}));
 host.innerHTML=settingsProviderMarkup(d);
 for(const id of open){const el=document.getElementById(id);if(el)el.open=true;}
 bindSettingsProviders(host);
 for(const draft of drafts){const form=host.querySelector('.alert-provider-form[data-provider="'+draft.id+'"]');if(!form)continue;if(form.elements.key)form.elements.key.value=draft.key;if(form.elements.client_id)form.elements.client_id.value=draft.client;if(form.elements.permission)form.elements.permission.checked=draft.permission;}
}
function bindSettingsProviders(host){
 host.querySelectorAll('.alert-provider-form').forEach(form=>{
  const id=form.dataset.provider;
  const keepOpen=()=>['alertAllConfig','alertApis','alert-'+id].forEach(k=>{const el=document.getElementById(k);if(el)el.open=true;});
  const act=async(work,message)=>{
   if(pendingProviders.size)return;
   pendingProviders.add(id);
   form.querySelectorAll('button').forEach(b=>b.disabled=true);
   providerFeedback(id,'Working…');
   try{
    const result=await work();
    providerFeedback(id,message(result));
    await refreshSettingsProviders(host);keepOpen();
   }catch(err){
    providerFeedback(id,err.message,true);
    try{await refreshSettingsProviders(host);keepOpen()}catch{}
   }finally{
    pendingProviders.delete(id);
    const active=host.querySelector('.alert-provider-form[data-provider="'+id+'"]');
    if(active){active.querySelectorAll('button').forEach(b=>b.disabled=false);const remove=active.querySelector('[data-remove-provider]');if(remove)remove.disabled=!settingsProviderData?.[id]?.key_set;}
   }
  };
  form.onsubmit=e=>{
   e.preventDefault();const key=form.elements.key?.value.trim();
   if(!key){providerFeedback(id,'Enter an API key first.',true);return;}
   act(()=>alertApi('/api/alerts/'+id,{key,...(id==='opensky'?{client_id:form.elements.client_id.value.trim(),permission:form.elements.permission.checked}:{})} ),()=>{form.elements.key.value='';return 'Key saved. Test connection to verify.'});
  };
  const show=form.querySelector('[data-showkey]');
  if(show)show.onclick=()=>{const input=form.elements.key;input.type=input.type==='password'?'text':'password';show.textContent=input.type==='password'?'Show':'Hide';};
  form.querySelector('[data-test-provider]').onclick=()=>act(()=>alertApi('/api/alerts/'+id+'/check',{}),result=>'Connection successful'+(result.plan?' · '+result.plan:'')+(result.aircraft!=null?' · '+at(result.aircraft)+' aircraft':''));
  const remove=form.querySelector('[data-remove-provider]');
  if(remove)remove.onclick=()=>{if(confirm('Remove this saved API key from the laptop?'))act(()=>alertApi('/api/alerts/'+id,{clear:true}),()=> 'Key removed.');};
 });

}
export function mountSettingsProviders(host){
 if(!host)return;
 host.innerHTML='<details class="foldout" id="alertApis"><summary>ADS-B providers</summary><div class="alert-config-content muted tiny">Open to load API settings.</div></details>';
 host.querySelector('details').addEventListener('toggle',async e=>{if(!e.target.open)return;try{await refreshSettingsProviders(host)}catch(err){if(host.isConnected)host.querySelector('.alert-config-content').textContent=err.message;}});
}
export {providerIcons,providerIcon};
