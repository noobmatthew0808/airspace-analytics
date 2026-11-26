/* Independent datalink view; provider credentials remain server-side. */
import {providerIcons} from './alerts-ui.js';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={avio:'AvioADSB',vdliq:'vdlIQ',airframes:'Airframes.io',drama:'ACARS Drama'};
const cfg=[
 {id:'avio',name:names.avio,url:'https://avioadsb.org/docs/protocols/acars',hint:'Uses your existing AvioADSB key from ADS-B providers, or limited anonymous access. ACARS / VDL2 / HFDL, latest hour only.',reuse:true},
 {id:'vdliq',name:names.vdliq,url:'https://www.vdliq.com/api/docs',hint:'Free without ACARS feeding. Uses your saved ADSBiq key by default; no new key needed to try. If authentication fails, choose feeder-IP access below. History is searched by resolved registration or ICAO; free-tier requests are five minutes apart.'},
 {id:'airframes',name:names.airframes,url:'https://docs.airframes.io/api/authentication/',hint:'Free API key for active Airframes datalink feeders after at least seven days. Email api@airframes.io with your station ID. Historical and recent aircraft messages.'},
 {id:'drama',name:names.drama,url:'https://acarsdrama.com/',hint:'Complimentary Jumpseat access for ACARS Drama feeders. Email feeders@acarsdrama.com once feeding, then obtain your Jumpseat API key. No paid subscription is required for eligible feeders.'}
];
async function api(path,body){
 const opts=body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'};
 const r=await fetch(path,opts),d=await r.json().catch(()=>({error:'Invalid server response'}));
 if(!r.ok)throw Error(d.error||'Request failed');
 return d;
}
const time=v=>new Date(v*1000).toLocaleString('en-GB',{timeZone:'Europe/London',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit'});
const opts=(xs,sel)=>xs.map(x=>'<option value="'+x+'" '+(x===sel?'selected':'')+'>'+x+'h</option>').join('');
let timer=null,generation=0,activeId='',last=null,busy=false,signature='',previous={query:'',kind:'auto',hours:12};

function settingsCard(p,d){
 const state=d?.providers?.[p.id]||{},t=state.test||{},keyless=['avio','vdliq'].includes(p.id)&&!state.key_set;
 const status=t.ok===true?'verified':t.ok===false?'missing':state.key_set?'saved':keyless?'pending':'missing';
 const desc=t.ok===true?'Verified':t.ok===false?'Test failed':state.reused_key?'Existing key · Not tested':state.key_set?'Key saved · Not tested':keyless?'Try anonymous / feeder IP access':'No key saved';
 return '<details class="foldout alert-config alert-provider" id="acars-provider-'+p.id+'"><summary class="alert-api-summary">'+providerIcons(keyless,status)+'<span><strong>'+esc(p.name)+'</strong><small>'+esc(desc)+'</small></span></summary>'+
 '<form class="alert-config-content acars-provider-form" data-acars-provider="'+p.id+'" autocomplete="off">'+
 '<p class="alert-provider-note">'+esc(p.hint)+'</p><a class="btn small" href="'+esc(p.url)+'" target="_blank" rel="noopener noreferrer">Setup / documentation</a>'+
 (p.id==='vdliq'?'<div class="alert-editor-buttons"><button type="button" class="btn small" data-auth="existing" '+(state.reused_key?'disabled':'')+'>Use saved ADSBiq key</button><button type="button" class="btn small" data-auth="ip" '+(state.ip_only?'disabled':'')+'>Use feeder IP only</button></div>':'')+
 (p.reuse?'':'<label class="alert-field alert-wide">Optional separate API key <small>'+(state.reused_key?'Existing ADSBiq key in use. Optional replacement for datalink only.':state.key_set?'Saved on server. Enter a replacement only if needed.':'Paste your API key.')+'</small><span class="alert-secret-row"><input name="key" type="password" autocomplete="new-password" placeholder="API key"><button type="button" class="btn small" data-reveal>Show</button></span></label>')+
 '<div class="alert-editor-buttons">'+(p.reuse?'':'<button type="submit" class="btn primary">Save key</button>')+'<button type="button" class="btn small" data-check>Test connection</button>'+
 (!p.reuse&&state.custom_key?'<button type="button" class="btn small alert-delete" data-clear>'+(p.id==='vdliq'?'Use existing ADSBiq key':'Remove key')+'</button>':'')+'</div>'+
 '<div class="alert-provider-result '+(t.ok===true?'is-good':t.ok===false?'is-error':'')+'" role="status">'+esc(t.message||'')+(t.at?' · '+esc(time(t.at)):'')+(state.retry_seconds>0?' · Next request in about '+state.retry_seconds+'s':'')+'</div></form></details>';
}
export function mountAcarsSettings(host){
 if(!host)return;
 const refresh=async(open=[],feedback=null)=>{
  const d=await api('/api/acars/settings');
  if(!host.isConnected)return;
  const drafts=[...host.querySelectorAll('form[data-acars-provider]')].map(f=>[f.dataset.acarsProvider,f.elements.key?.value||'']);
  host.innerHTML='<details class="foldout alert-config" id="acarsProviderSettings"><summary><span>ACARS providers <small>Datalink messages</small></span></summary><div class="alert-config-stack alert-nested"><p class="alert-explainer">Free with your present ADS-B setup: AvioADSB and vdlIQ. No new keys needed initially. Airframes and ACARS Drama require separate eligibility and are hidden unless already configured.</p>'+cfg.filter(p=>['avio','vdliq'].includes(p.id)||d.providers?.[p.id]?.key_set).map(p=>settingsCard(p,d)).join('')+'</div></details>';
  for(const id of open){const el=host.querySelector('#'+id);if(el)el.open=true;}
  let working=false;
  for(const form of host.querySelectorAll('form[data-acars-provider]')){
   const p=form.dataset.acarsProvider;
   const draft=drafts.find(x=>x[0]===p);
   if(draft&&form.elements.key&&(p!==feedback?.id||feedback.error))form.elements.key.value=draft[1];
   const result=form.querySelector('[role=status]');
   if(feedback?.id===p){result.textContent=feedback.text;result.className='alert-provider-result '+(feedback.pending?'':feedback.error?'is-error':'is-good');}
   const action=async(path,payload,msg)=>{
    if(working)return;
    working=true;
    const buttons=[...host.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
    result.textContent='Working…';result.className='alert-provider-result';
    let response;
    try{const value=await api(path,{provider:p,...payload});response={id:p,text:msg(value),error:false,pending:!!value.pending};if(path.endsWith('/key')&&form.elements.key)form.elements.key.value='';}
    catch(e){response={id:p,text:e.message,error:true};}
    try{await refresh([...host.querySelectorAll('details[open]')].map(x=>x.id),response);}
    catch(e){result.textContent=response.text;result.className='alert-provider-result '+(response.error?'is-error':'is-good');}
    finally{working=false;buttons.forEach(b=>b.disabled=false);}
   };
   form.onsubmit=e=>{e.preventDefault();const key=form.elements.key?.value.trim();if(key)action('/api/acars/key',{key},()=> 'Key saved. Test connection to verify.');};
   form.querySelector('[data-check]').onclick=()=>action('/api/acars/check',{},r=>r.message||'Connection successful');
   for(const b of form.querySelectorAll('[data-auth]'))b.onclick=()=>action('/api/acars/key',{mode:b.dataset.auth},()=> 'Authentication mode saved. Test after the current cooldown.');
   const clear=form.querySelector('[data-clear]');if(clear)clear.onclick=()=>{if(confirm('Remove this datalink-specific API key?'))action('/api/acars/key',{clear:true},()=> 'Key removed.');};
   const reveal=form.querySelector('[data-reveal]');if(reveal)reveal.onclick=()=>{const el=form.elements.key;el.type=el.type==='password'?'text':'password';reveal.textContent=el.type==='password'?'Show':'Hide';};
  }
 };
 host.innerHTML='<details class="foldout alert-config" id="acarsProviderSettings"><summary>ACARS providers</summary><div class="alert-config-content muted tiny">Open to load settings.</div></details>';
 host.querySelector('details').addEventListener('toggle',async e=>{if(!e.target.open)return;try{await refresh(['acarsProviderSettings']);}catch(err){if(host.isConnected)host.querySelector('.alert-config-content').textContent=err.message;}});
}
function feedback(text,error=false){
 const el=document.getElementById('acarsFeedback');if(el){el.textContent=text;el.className='acars-feedback'+(error?' acars-error':'');}
}
function renderMessages(s){
 const host=document.getElementById('acarsResults');if(!host)return;
 const selected=s.tracking_until>Date.now()/1000;
 const identity=[s.identity?.reg,s.identity?.hex].filter(Boolean).join(' · ');
 document.getElementById('acarsTrackingState').textContent=selected?'Notifications until '+time(s.tracking_until)+' · '+s.notify_count+' sent': 'Notifications off';
 document.getElementById('acarsTrack').textContent=selected?'Extend tracking':'Track with ntfy';
 document.getElementById('acarsStopTrack').hidden=!selected;
 document.getElementById('acarsTrack').disabled=false;
 document.getElementById('acarsStop').disabled=false;
 document.getElementById('acarsIdentity').textContent=s.kind==='flight'?(identity?'Resolved aircraft: '+identity+' · linked-airframe messages may be from another flight.':'Aircraft not resolved yet. Registration search is more reliable for historical data.'):'';
 const status=document.getElementById('acarsSources');
 status.innerHTML=Object.entries(s.providers||{}).map(([p,x])=>'<div class="acars-source"><span class="acars-dot '+(x.state==='Connected'?'good':x.state==='Unavailable'?'bad':'')+'"></span><div><strong>'+esc(names[p]||p)+'</strong><span>'+esc(x.state)+(x.last?' · '+esc(time(x.last)):'')+(x.matched!=null?' · '+esc(x.matched)+' matches':'')+(x.retry_seconds>0?' · Next in '+esc(x.retry_seconds)+'s':'')+'</span>'+(x.note?'<small>'+esc(x.note)+'</small>':'')+'</div></div>').join('');
 document.getElementById('acarsCount').textContent=s.messages.length+' messages · '+s.query;
 if(s.notify_error)feedback(s.notify_error,true);
 const waiting=Object.values(s.providers||{}).some(p=>['Waiting','Checking','Cooling down'].includes(p.state)&&!p.last);
 const next=JSON.stringify([s.messages,waiting]);
 if(next===signature)return;
 signature=next;
 if(!s.messages.length){host.innerHTML='<div class="acars-empty">'+(waiting?'Waiting for the first provider searches. Open Data sources for cooldowns and connection status.':'No matching messages returned. Check Data sources for coverage, errors and history limits. A different network may have received messages.')+'</div>';return;}
 const open=new Set([...host.querySelectorAll('details[open]')].map(x=>x.dataset.messageKey));
 host.innerHTML=s.messages.map((m,i)=>{
  const id=esc(m.timestamp+'-'+m.id+'-'+m.sources[0]);
  const sources=m.sources.map(p=>names[p]||p).join(' · ');
  return '<details class="acars-message" data-message-key="'+id+'" '+(open.has(m.timestamp+'-'+m.id+'-'+m.sources[0])?'open':'')+'><summary><div class="acars-message-head"><strong>'+esc([m.reg,m.flight].filter(Boolean).join(' · ')||s.query)+'</strong><time>'+esc(time(m.timestamp))+'</time></div><div class="acars-message-meta">'+esc([m.protocol,m.label,sources,m.match==='linked airframe'?'Linked airframe':m.match==='text match'?'Callsign in message text':''].filter(Boolean).join(' · '))+'</div><div class="acars-message-text">'+esc(m.text)+'</div></summary><div class="acars-message-details"><span>Message text</span><pre>'+esc(m.text)+'</pre><div>'+esc([m.direction,m.hex&&'ICAO '+m.hex.toUpperCase(),sources].filter(Boolean).join(' · '))+'</div></div></details>';
 }).join('');
}
async function trackingList(gen){
 const d=await api('/api/acars/session');
 if(gen!==generation)return;
 const host=document.getElementById('acarsActiveTracks');if(!host)return;
 host.innerHTML=(d.tracking||[]).map(s=>'<div class="acars-active-track"><div><strong>'+esc(s.query)+'</strong><small>Until '+esc(time(s.tracking_until))+' · '+s.notify_count+' sent</small></div><button class="btn small" data-resume="'+esc(s.id)+'">View</button><button class="btn small" data-end="'+esc(s.id)+'">Stop</button></div>').join('');
 for(const b of host.querySelectorAll('[data-resume]'))b.onclick=async()=>{try{const s=await api('/api/acars/session?id='+encodeURIComponent(b.dataset.resume));if(gen!==generation)return;activeId=s.id;last=s;signature='';previous={query:s.query,kind:s.kind,hours:s.hours};const form=document.getElementById('acarsSearch');form.elements.query.value=s.query;form.elements.kind.value=s.kind;form.elements.hours.value=s.hours;renderMessages(s);}catch(e){feedback(e.message,true);}};
 for(const b of host.querySelectorAll('[data-end]'))b.onclick=async()=>{try{await api('/api/acars/track',{id:b.dataset.end,duration:0});if(gen===generation)await trackingList(gen);}catch(e){feedback(e.message,true);}};
}
export function stopAcarsPage(){generation++;if(timer)clearTimeout(timer);timer=null;busy=false;}
export async function renderAcarsPage(){
 const gen=++generation,host=document.getElementById('page');if(!host)return;
 signature='';
 host.innerHTML='<div class="acars-page"><div class="page-heading"><h1 class="page-title">ACARS</h1><a href="/analytics#settings" class="btn small">API settings</a></div>'+
 '<section class="panel acars-search-panel"><form id="acarsSearch"><div class="acars-search-grid"><label class="alert-field acars-query">Aircraft or flight<input name="query" maxlength="16" placeholder="e.g. G-WUKU or WZZ580C" value="'+esc(previous.query)+'" required autocapitalize="characters"></label><label class="alert-field">Search by<select name="kind"><option value="auto">Auto</option><option value="reg">Registration</option><option value="flight">Callsign / flight</option><option value="hex">ICAO hex</option></select></label><label class="alert-field">History<select name="hours">'+opts([1,3,6,12,24],previous.hours)+'</select></label><button class="btn primary" type="submit">Send</button></div></form><div id="acarsFeedback" class="acars-feedback" role="status"></div><div id="acarsIdentity" class="muted tiny"></div></section>'+
 '<section class="panel acars-track-panel"><div class="acars-track-title"><strong>Live tracking</strong><span id="acarsTrackingState" class="muted tiny">Notifications off</span></div><div class="acars-track-actions"><label class="alert-field">Notify for<select id="acarsDuration">'+opts([1,2,3,6,12,24],3)+'</select></label><button class="btn primary" id="acarsTrack" disabled>Track with ntfy</button><button class="btn small" id="acarsStopTrack" hidden>Stop notifications</button><button class="btn small" id="acarsStop" disabled>Stop search</button></div><p class="muted tiny">Uses your existing ntfy topic. Only new messages after tracking starts are sent; tracking continues with the browser closed until the selected end time, while the website service is running. Use a private topic.</p><div id="acarsActiveTracks"></div></section>'+
 '<details class="foldout panel acars-source-panel" open><summary>Data sources <small>Connection and coverage</small></summary><div id="acarsSources"><p class="muted tiny">Send a search to check providers.</p></div></details>'+
 '<div class="acars-result-heading"><strong id="acarsCount">Messages</strong><span class="muted tiny">Newest first · UK time</span></div><div id="acarsResults"><div class="acars-empty">Search an aircraft registration or callsign to begin.</div></div>'+
 '<footer class="acars-attribution">Data: <a href="https://avioadsb.org" target="_blank" rel="noopener noreferrer">AvioADSB (CC BY-NC 4.0)</a> · <a href="https://vdliq.com" target="_blank" rel="noopener noreferrer">vdlIQ</a> · <a href="https://airframes.io" target="_blank" rel="noopener noreferrer">Airframes.io and its feeder community</a> · <a href="https://acarsdrama.com" target="_blank" rel="noopener noreferrer">ACARS Drama</a>. Best-effort community data, not for operational use.</footer></div>';
 const form=document.getElementById('acarsSearch');form.elements.kind.value=previous.kind;
 form.onsubmit=async e=>{
  e.preventDefault();if(busy)return;busy=true;const btn=form.querySelector('button[type=submit]');btn.disabled=true;feedback('Searching…');
  try{
   const payload={query:form.elements.query.value.trim().toUpperCase(),kind:form.elements.kind.value,hours:Number(form.elements.hours.value)};
   const s=await api('/api/acars/search',payload);
   if(gen!==generation)return;
   const old=last;
   activeId=s.id;last=s;previous=payload;signature='';renderMessages(s);
   feedback('Live updates enabled; providers check within their individual limits.');
   if(old&&old.id!==s.id&&old.tracking_until<=Date.now()/1000)api('/api/acars/stop',{id:old.id}).catch(()=>{});
  }catch(err){if(gen===generation)feedback(err.message,true);}
  finally{if(gen===generation){busy=false;btn.disabled=false;}}
 };
 document.getElementById('acarsTrack').onclick=async()=>{
  if(!activeId)return;
  const btn=document.getElementById('acarsTrack');btn.disabled=true;
  try{const s=await api('/api/acars/track',{id:activeId,duration:Number(document.getElementById('acarsDuration').value)});if(gen!==generation)return;last=s;renderMessages(s);feedback('Notifications enabled for new messages.');await trackingList(gen);}
  catch(e){if(gen===generation)feedback(e.message,true);}finally{if(gen===generation)btn.disabled=false;}
 };
 document.getElementById('acarsStopTrack').onclick=async()=>{try{const s=await api('/api/acars/track',{id:activeId,duration:0});if(gen!==generation)return;last=s;renderMessages(s);feedback('Notifications stopped.');await trackingList(gen);}catch(e){feedback(e.message,true);}};
 document.getElementById('acarsStop').onclick=async()=>{try{await api('/api/acars/stop',{id:activeId});if(gen!==generation)return;activeId='';last=null;stopAcarsPage();await renderAcarsPage();}catch(e){feedback(e.message,true);}};
 let cycles=0;
 const poll=async()=>{
  if(gen!==generation)return;
  if(activeId&&!busy){
   const id=activeId;
   try{const s=await api('/api/acars/session?id='+encodeURIComponent(id));if(gen===generation&&id===activeId){last=s;renderMessages(s);}}
   catch(e){if(gen===generation&&id===activeId){feedback(e.message,true);if(e.message.includes('expired')){activeId='';last=null;document.getElementById('acarsTrack').disabled=true;document.getElementById('acarsStop').disabled=true;}}}
  }
  if(gen!==generation)return;
  if(cycles++%3===0)try{await trackingList(gen);}catch{}
  if(gen===generation)timer=setTimeout(poll,5000);
 };
 await poll();
}
