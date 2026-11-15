/* Independent Alerts tab: Traffic and chart components are not modified. */
const ae = v => String(v??'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const at = n => n==null?'Any':Number(n).toLocaleString('en-GB');
const whenAlert = n => new Date(n*1000).toLocaleString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
const matchFields = [['type','Aircraft type'],['registration','Registration'],['callsign','Callsign'],['hex','ICAO hex'],['operator','Operator'],['military','Military']];
let alertsData=null, alertsTimer=null, editingRule=null, alertsBusy=false;
async function alertApi(path,body){
 const options=body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'};
 const response=await fetch(path,options);
 const data=await response.json().catch(()=>({error:'Invalid server response'}));
 if(!response.ok)throw Error(data.error||'Alert request failed');
 return data;
}
function notifyInline(message,error=false){
 const node=document.querySelector('#alertFeedback');
 if(node){node.textContent=message;node.className='alert-feedback'+(error?' alert-fail':'');}
}
function alertRule(r){
 return '<article class="alert-rule"><div class="alert-rule-main"><div class="alert-rule-title"><strong>'+ae(r.label)+'</strong><span class="alert-tag">'+at(r.active||0)+' active</span></div>'+
 '<div class="alert-rule-meta">'+ae(r.field==='military'?'Military':r.field+': '+r.pattern)+' · '+at(r.max_km)+' km · '+at(r.min_ft)+'–'+at(r.max_ft)+' ft</div></div>'+
 '<div class="alert-rule-actions"><label class="alert-switch"><input type="checkbox" data-toggle="'+r.id+'" '+(r.enabled?'checked':'')+' aria-label="Enable alert"><span>On</span></label>'+
 '<button class="btn small" type="button" data-edit="'+r.id+'">Edit</button></div></article>';
}
function alertEvent(e){
 return '<div class="alert-event"><div><strong>'+ae(e.rule_label)+'</strong> <span class="muted">'+ae(e.callsign||e.registration||e.hex)+'</span>'+
 '<div class="alert-event-meta">'+ae(e.aircraft_type||'Unknown')+' · '+ae(e.hex.toUpperCase())+' · '+at(e.distance_km)+' km · '+at(e.altitude_ft)+' ft</div></div>'+
 '<div class="alert-event-time">'+whenAlert(e.created)+'<div>'+ae(e.delivery)+'</div></div></div>';
}
function renderAlertPageContents(){
 const host=document.querySelector('#page');if(!host||!alertsData)return;
 const d=alertsData,receiver=d.receiver||{},healthy=receiver.time&&!receiver.error&&Date.now()/1000-receiver.time<20;
 host.innerHTML='<div class="alert-page"><div class="page-heading"><h1 class="page-title">Alerts</h1><button class="btn small" id="alertAdd" type="button">+ Add rule</button></div>'+
 '<div class="alert-status"><span class="alert-status-dot '+(healthy?'online':'')+'"></span>'+(healthy?at(receiver.aircraft)+(receiver.source?.startsWith('Aerodrome')?' aircraft seen (30s)':' aircraft')+' · Receiver connected'+(receiver.lat!=null?' · Antenna set':'')+(receiver.source&&receiver.source.startsWith('Aerodrome')?' · Aerodrome samples':''):'Receiver unavailable'+(receiver.error?' · '+ae(receiver.error):''))+'</div>'+
 '<div id="alertEditor"></div><div id="alertFeedback" role="status" class="alert-feedback"></div>'+
 '<section class="alert-rules">'+(d.rules.length?d.rules.map(alertRule).join(''):'<div class="alert-empty">No rules configured yet.</div>')+'</section>'+
 '<details class="foldout alert-config" id="alertNtfy"><summary><span>Notifications <small>'+(d.ntfy.topic?'Configured':'Not configured')+'</small></span></summary>'+
 '<form id="alertNtfyForm" class="alert-config-content"><div class="alert-form-grid">'+
 '<label class="alert-field">ntfy server<input name="server" type="url" required value="'+ae(d.ntfy.server)+'"></label>'+
 '<label class="alert-field">Topic<input name="topic" maxlength="80" value="'+ae(d.ntfy.topic)+'" placeholder="Existing ntfy topic"></label>'+
 '<label class="alert-field alert-wide">Access token <small>'+(d.ntfy.token_set?'Saved · blank to keep':'Optional')+'</small><input type="password" name="token" autocomplete="off" placeholder="Leave empty to keep saved token"></label>'+
 '<label class="alert-field alert-wide">Home Wi-Fi tar1090 map <small>Opens without VPN when on your home network</small><input type="url" name="map_lan" maxlength="240" value="'+ae(d.ntfy.map_lan||'')+'" placeholder="http://192.168.x.x:1099/map/"></label>'+
 '<label class="alert-field alert-wide">Tailscale tar1090 map <small>Use when connected away from home</small><input type="url" name="map_tailscale" maxlength="240" value="'+ae(d.ntfy.map_tailscale||'')+'" placeholder="http://100.x.x.x:1099/map/"></label>'+
 '<label class="alert-field alert-wide">Tapping an alert opens<select name="tap_route">'+
 '<option value="lan" '+(d.ntfy.tap_route!=='tailscale'?'selected':'')+'>Home Wi-Fi map</option>'+
 '<option value="tailscale" '+(d.ntfy.tap_route==='tailscale'?'selected':'')+'>Tailscale map</option></select><small>Each alert also includes Home Wi-Fi and Tailscale map buttons for the other connection.</small></label>'+
 '</div><div class="alert-editor-buttons"><button class="btn primary" type="submit">Save notifications</button><button class="btn small" type="button" id="alertTest">Send test</button>'+
 (d.ntfy.token_set?'<label class="alert-clear"><input type="checkbox" id="clearNtfyToken"> Clear token</label>':'')+'</div></form></details>'+
 '<details class="foldout alert-config" id="alertReceiver"><summary><span>Receiver setup <small>'+(receiver.lat!=null&&receiver.lon!=null?'Antenna located':'Optional setup')+'</small></span></summary>'+
 '<form id="alertReceiverForm" class="alert-config-content"><div class="alert-form-grid">'+
 '<label class="alert-field alert-wide">Aircraft feed URL <small>Leave blank for automatic localhost and LAN detection</small><input name="url" type="url" value="'+ae(d.receiver_settings?.url||'')+'" placeholder="http://'+ae(location.hostname)+':1099/data/aircraft.json"></label>'+
 '<label class="alert-field">Antenna latitude<input name="lat" type="number" min="-90" max="90" step="any" value="'+ae(d.receiver_settings?.lat??'')+'" placeholder="Automatic"></label>'+
 '<label class="alert-field">Antenna longitude<input name="lon" type="number" min="-180" max="180" step="any" value="'+ae(d.receiver_settings?.lon??'')+'" placeholder="Automatic"></label>'+
 '</div><div class="alert-editor-buttons"><button type="submit" class="btn primary">Save receiver</button><button type="button" class="btn small" id="alertReceiverCheck">Test connection</button></div></form></details>'+
 '<details class="foldout alert-history" id="alertHistory" open><summary><span>Recent alerts <small>'+d.events.length+' shown</small></span></summary>'+
 '<div class="alert-events">'+(d.events.length?d.events.slice(0,30).map(alertEvent).join(''):'<div class="alert-empty">No alerts yet.</div>')+'</div></details></div>';
 bindAlerts();
 if(editingRule)editAlert(editingRule);
}
function editAlert(rule){
 editingRule=rule||{};
 const r=editingRule;
 const node=document.querySelector('#alertEditor');
 const title=r.id?'Edit rule':'New rule';
 node.innerHTML='<form id="alertEditorForm" class="alert-editor"><div class="alert-editor-heading"><strong>'+title+'</strong><button type="button" class="btn small" id="alertCancel">Cancel</button></div>'+
 '<div class="alert-form-grid"><label class="alert-field">Name<input name="label" maxlength="50" required value="'+ae(r.label||'')+'" placeholder="A380 nearby"></label>'+
 '<label class="alert-field">Match by<select name="field" id="alertField">'+matchFields.map(f=>'<option value="'+f[0]+'" '+(r.field===f[0]?'selected':'')+'>'+f[1]+'</option>').join('')+'</select></label>'+
 '<label class="alert-field alert-wide" id="alertPatternHolder">Codes / pattern<input name="pattern" maxlength="1800" required value="'+ae(r.pattern||'')+'" placeholder="A388 or G-* or BAW*"><small>Up to 100 values separated by commas · * is a wildcard</small></label>'+
 '<label class="alert-field">Distance, km<input name="max_km" type="number" step="0.1" min="0.1" max="1000" value="'+ae(r.max_km??'')+'" placeholder="Any"></label>'+
 '<label class="alert-field">Min altitude, ft<input name="min_ft" type="number" min="-2000" max="70000" step="100" value="'+ae(r.min_ft??'')+'" placeholder="Any"></label>'+
 '<label class="alert-field">Max altitude, ft<input name="max_ft" type="number" min="-2000" max="70000" step="100" value="'+ae(r.max_ft??'')+'" placeholder="Any"></label>'+
 '</div><div class="alert-editor-buttons"><button type="submit" class="btn primary">Save rule</button>'+
 (r.id?'<button type="button" id="alertDelete" class="btn small alert-delete">Delete</button>':'')+'</div></form>';
 const form=node.querySelector('form');
 const match=form.elements.field, pattern=form.elements.pattern;
 const syncPattern=()=>{pattern.disabled=match.value==='military';pattern.required=!pattern.disabled;document.querySelector('#alertPatternHolder').hidden=pattern.disabled};
 match.onchange=syncPattern;syncPattern();
 document.querySelector('#alertCancel').onclick=()=>{editingRule=null;node.innerHTML=''};
 form.onsubmit=async e=>{e.preventDefault();if(alertsBusy)return;alertsBusy=true;
  try{const obj=Object.fromEntries(new FormData(form));obj.enabled=r.enabled??1;if(r.id)obj.id=r.id;
      await alertApi('/api/alerts/rule',obj);editingRule=null;await refreshAlerts();notifyInline('Rule saved.')}
  catch(err){notifyInline(err.message,true)}finally{alertsBusy=false}};
 if(r.id)document.querySelector('#alertDelete').onclick=async()=>{
  if(!confirm('Delete this alert rule?'))return;
  try{await alertApi('/api/alerts/delete',{id:r.id});editingRule=null;await refreshAlerts();notifyInline('Rule deleted.')}
  catch(err){notifyInline(err.message,true)}};
}
function bindAlerts(){
 document.querySelector('#alertAdd').onclick=()=>editAlert(null);
 document.querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>editAlert(alertsData.rules.find(r=>r.id===Number(b.dataset.edit))));
 document.querySelectorAll('[data-toggle]').forEach(b=>b.onchange=async()=>{
  const rule=alertsData.rules.find(r=>r.id===Number(b.dataset.toggle));if(!rule)return;
  try{await alertApi('/api/alerts/rule',{...rule,enabled:b.checked});await refreshAlerts();}
  catch(err){b.checked=!b.checked;notifyInline(err.message,true)}
 });
 const recvForm=document.querySelector('#alertReceiverForm');
 recvForm.onsubmit=async e=>{e.preventDefault();try{
   await alertApi('/api/alerts/receiver',Object.fromEntries(new FormData(recvForm)));
   await refreshAlerts();document.querySelector('#alertReceiver').open=true;
   notifyInline('Receiver settings saved.');
  }catch(err){notifyInline(err.message,true)}};
 document.querySelector('#alertReceiverCheck').onclick=async()=>{
  try{const result=await alertApi('/api/alerts/receiver/check',{});
   notifyInline(result.aircraft+(result.source?.startsWith('Aerodrome')?' aircraft seen in last 30 seconds':' aircraft in current snapshot')+(result.coordinates_available?' · antenna position available':' · antenna position missing (distance filters need coordinates)')+(result.source?' · '+result.source:''));}
  catch(err){notifyInline(err.message,true)}};
 const form=document.querySelector('#alertNtfyForm');
 form.onsubmit=async e=>{e.preventDefault();const wasOpen=true;const obj=Object.fromEntries(new FormData(form));
   if(!obj.token&&!document.querySelector('#clearNtfyToken')?.checked)delete obj.token;
   try{await alertApi('/api/alerts/ntfy',obj);await refreshAlerts();document.querySelector('#alertNtfy').open=wasOpen;notifyInline('Notifications saved.')}
   catch(err){notifyInline(err.message,true)}};
 document.querySelector('#alertTest').onclick=async()=>{try{await alertApi('/api/alerts/test',{});notifyInline('ntfy accepted the test notification.')}catch(err){notifyInline(err.message,true)}};
}
async function refreshAlerts(){alertsData=await alertApi('/api/alerts');if(location.hash==='#alerts')renderAlertPageContents()}
export async function renderAlertsPage(){
 if(alertsTimer)clearTimeout(alertsTimer);editingRule=null;
 const host=document.querySelector('#page');if(!host)return;
 host.innerHTML='<div class="loading">Loading alerts…</div>';
 try{await refreshAlerts()}catch(err){host.innerHTML='<div class="notice error-note">'+ae(err.message)+'</div>';return}
 const poll=async()=>{if(location.hash!=='#alerts')return;
  try{if(!document.querySelector('#alertEditorForm')&&!document.querySelector('#alertNtfyForm:focus-within')&&!document.querySelector('#alertReceiverForm:focus-within')){
   const ntfyOpen=document.querySelector('#alertNtfy')?.open;
   const receiverOpen=document.querySelector('#alertReceiver')?.open;
   const historyOpen=document.querySelector('#alertHistory')?.open;
   await refreshAlerts();
   if(ntfyOpen)document.querySelector('#alertNtfy').open=true;
   if(receiverOpen)document.querySelector('#alertReceiver').open=true;
   if(historyOpen===false)document.querySelector('#alertHistory').open=false;
  }}catch{}
  alertsTimer=setTimeout(poll,10000);
 };
 alertsTimer=setTimeout(poll,10000);
}
