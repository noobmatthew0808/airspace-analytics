/* Independent Alerts UI — no Traffic or Live ADS-B changes. */
const ae=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const at=n=>n==null?'Any':Number(n).toLocaleString('en-GB');
const whenAlert=n=>new Date(n*1000).toLocaleString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
const fields=[['type','Aircraft type'],['registration','Registration'],['callsign','Callsign'],['hex','ICAO hex'],['operator','Operator'],['military','Military']];
const providers=[
 {id:'flyitaly',name:'FlyItalyADSB',url:'https://api.flyitalyadsb.com/v2',hint:'Live positions and military metadata; check your feeder perk in My API.'},
 {id:'adsblol',name:'adsb.lol',url:'https://api.adsb.lol/v2',hint:'Ready for your feeder key when eligible. No key needed until then.'},
 {id:'adsbfi',name:'adsb.fi',url:'https://opendata.adsb.fi/api',hint:'Free API · no key required.'}
];
let alertsData=null,alertsTimer=null,editingRule=null,alertsBusy=false;
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
 const info=d[p.id]||{},saved=!!info.key_set,connected=!!info.connected;
 if(p.id==='adsbfi'){
  return '<details class="foldout alert-config alert-provider" id="alert-adsbfi"><summary><span>adsb.fi <small>'+
   (connected?'Connected · no key needed':(info.last_success?'Previously tested · no key':(info.error?'Needs attention · no key':'No key required')))+
   '</small></span></summary><div class="alert-config-content">'+
   '<div class="alert-provider-endpoint"><span>API endpoint</span><code>'+ae(p.url)+'</code></div>'+
   '<p class="alert-provider-note">Free public aircraft API. No key to enter. Contributor access uses your feeder IP. <a href="https://adsb.fi/" target="_blank" rel="noopener noreferrer">adsb.fi</a></p>'+
   '<div class="alert-editor-buttons"><button class="btn small primary" id="alertAdsbfiTest" type="button">Test connection</button></div>'+
   (info.last_success?'<p class="alert-provider-note">Last success: '+whenAlert(info.last_success)+' · '+at(info.aircraft)+' aircraft</p>':'')+
   (info.error?'<p class="alert-provider-note">'+ae(info.error)+'</p>':'')+
   '</div></details>';
 }
 const subtitle=saved?(connected?'Live data fresh':(info.error?'Needs attention':(info.last_success?'Key saved · last test succeeded':'Key saved · not tested'))):'No key saved';
 return '<details class="foldout alert-config alert-provider" id="alert-'+p.id+'"><summary><span>'+ae(p.name)+' <small>'+ae(subtitle)+'</small></span></summary>'+
  '<form class="alert-config-content alert-provider-form" data-provider="'+p.id+'" autocomplete="off">'+
  '<div class="alert-provider-endpoint"><span>API endpoint (fixed)</span><code>'+ae(p.url)+'</code></div>'+
  '<label class="alert-field alert-wide">API key <small>'+(saved?'Saved securely on this laptop. Blank means keep the saved key.':'Not saved yet. Paste key and press Save.')+'</small>'+
  '<span class="alert-secret-row"><input name="key" type="password" autocomplete="new-password" placeholder="'+(saved?'Key saved — enter new key to replace':'Paste API key')+'"><button type="button" class="btn small" data-showkey="'+p.id+'">Show</button></span></label>'+
  '<div class="alert-editor-buttons"><button class="btn primary" type="submit">Save key</button>'+
  '<button class="btn small" type="button" data-test-provider="'+p.id+'">Test connection</button>'+
  '<button class="btn small alert-delete" type="button" data-remove-provider="'+p.id+'" '+(saved?'':'disabled')+'>Remove key</button></div>'+
  '<p class="alert-provider-note">'+ae(p.hint)+'</p>'+
  (saved?'<p class="alert-provider-note"><strong>Saved ✓</strong> · '+(connected?'Live data fresh':(info.last_success?'Last API test succeeded':'Connection not tested'))+
  (info.last_success?' · Last success '+whenAlert(info.last_success):'')+
  (info.aircraft!=null?' · '+at(info.aircraft)+' aircraft':'')+
  (info.plan?' · Plan '+ae(info.plan):'')+
  (info.monthly_used?' · Requests '+ae(info.monthly_used)+'/'+ae(info.monthly_quota||'?'):'')+
  (info.error?' · Error '+ae(info.error):'')+'</p>':'')+
  '</form></details>';
}
function renderAlertPageContents(){
 const host=document.querySelector('#page');if(!host||!alertsData)return;
 const wasOpen=new Set([...host.querySelectorAll('details[open]')].map(x=>x.id));
 const d=alertsData,receiver=d.receiver||{},healthy=receiver.time&&!receiver.error&&Date.now()/1000-receiver.time<20;
 host.innerHTML='<div class="alert-page">'+
  '<div class="page-heading"><h1 class="page-title">Alerts</h1><button class="btn small" id="alertAdd" type="button">+ Add rule</button></div>'+
  '<div class="alert-status"><span class="alert-status-dot '+(healthy?'online':'')+'"></span>'+
  (healthy?at(receiver.aircraft)+(receiver.source?.startsWith('Aerodrome')?' aircraft seen (30s)':' aircraft')+' · Receiver connected'+(receiver.lat!=null?' · Antenna set':'')+
   (receiver.source?.startsWith('Aerodrome')?' · Aerodrome backup':''):'Receiver unavailable'+(receiver.error?' · '+ae(receiver.error):''))+'</div>'+
  '<div id="alertEditor"></div><div id="alertFeedback" role="status" class="alert-feedback"></div>'+
  '<section class="alert-rules">'+(d.rules.length?d.rules.map(ruleCard).join(''):'<div class="alert-empty">No rules configured yet.</div>')+'</section>'+
  '<details class="foldout alert-root-config" id="alertAllConfig"><summary><span>Configuration &amp; Logs <small>APIs · Notifications · Receiver · History</small></span></summary>'+
  '<div class="alert-config-stack"><details class="foldout alert-config" id="alertApis"><summary><span>APIs <small>Manage backup sources</small></span></summary>'+
  '<div class="alert-config-stack alert-nested">'+
  '<p class="alert-explainer">APIs only affect rules where Backup APIs is ticked. Your own receiver remains the fastest source.</p>'+
  providers.map(p=>providerCard(p,d)).join('')+'</div></details>'+
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
 document.querySelector('#alertAdsbfiTest').onclick=async()=>{
  try{
   const result=await alertApi('/api/alerts/adsbfi/check',{});
   await refreshAlerts();
   ['alertAllConfig','alertApis','alert-adsbfi'].forEach(k=>{document.getElementById(k).open=true;});
   feedback('adsb.fi connected: '+at(result.aircraft)+' aircraft returned. No key required.');
  }catch(err){feedback('adsb.fi: '+err.message,true);}
 };
 document.querySelectorAll('.alert-provider-form').forEach(form=>{
  const id=form.dataset.provider;
  form.onsubmit=async e=>{
   e.preventDefault();const key=form.elements.key.value.trim();
   if(!key){feedback('Enter an API key before pressing Save, or use Test connection for the saved key.',true);return;}
   try{
    await alertApi('/api/alerts/'+id,{key});
    form.elements.key.value='';await refreshAlerts();
    document.getElementById('alertAllConfig').open=true;
    document.getElementById('alertApis').open=true;
    document.getElementById('alert-'+id).open=true;
    feedback((id==='flyitaly'?'FlyItalyADSB':'adsb.lol')+' key saved privately. Now press Test connection.');
   }catch(err){feedback(err.message,true)}
  };
  form.querySelector('[data-showkey]').onclick=()=>{
   const input=form.elements.key,button=form.querySelector('[data-showkey]');
   input.type=input.type==='password'?'text':'password';
   button.textContent=input.type==='password'?'Show':'Hide';
  };
  form.querySelector('[data-test-provider]').onclick=async()=>{
   try{
    const result=await alertApi('/api/alerts/'+id+'/check',{});
    await refreshAlerts();
    ['alertAllConfig','alertApis','alert-'+id].forEach(k=>{document.getElementById(k).open=true;});
    feedback((id==='flyitaly'?'FlyItalyADSB':'adsb.lol')+' API successful: '+at(result.aircraft)+
     ' aircraft near your antenna'+(result.plan?' · plan '+result.plan:'')+'. This tests API access, not a push notification.');
   }catch(err){feedback('API test failed: '+err.message,true);}
  };
  form.querySelector('[data-remove-provider]').onclick=async()=>{
   if(!confirm('Remove this saved API key from the laptop?'))return;
   try{
    await alertApi('/api/alerts/'+id,{clear:true});
    await refreshAlerts();
    ['alertAllConfig','alertApis','alert-'+id].forEach(k=>{document.getElementById(k).open=true;});
    feedback('API key removed. Local alerts are unaffected.');
   }catch(err){feedback(err.message,true);}
  };
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
   if(!document.querySelector('#alertEditorForm')&&!document.querySelector('.alert-config-stack :focus-within')){
    await refreshAlerts();
   }
  }catch{}
  alertsTimer=setTimeout(poll,10000);
 };
 alertsTimer=setTimeout(poll,10000);
}
