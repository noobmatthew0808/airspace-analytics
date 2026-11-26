"""Read-only, bounded datalink search. No receiver changes or credentials in URLs."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from . import alerts, api_budget

PROVIDERS=('avio','vdliq','airframes','drama')
NAMES={'avio':'AvioADSB','vdliq':'vdlIQ','airframes':'Airframes.io','drama':'ACARS Drama'}
URLS={'avio':'https://avioadsb.org/v1/acars','vdliq':'https://api.adsbiq.com/v2/messages',
      'airframes':'https://api.airframes.io/v1','drama':'https://api.jumpseat.acarsdrama.com/v1/messages/search'}
BUDGET_NAMES={'avio':'AvioADSB','vdliq':'ADSBiq'}
INTERVAL={'avio':180,'vdliq':300,'airframes':60,'drama':120}
MAX_BYTES=4_000_000
MAX_ROWS=500
MAX_SESSIONS=5
_lock=threading.RLock()
_sessions={}
_busy=set()
_next={}
_started=False
_test_busy=set()

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _open(req,timeout=12):
    return build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=timeout)

def _stamp(value):
    try:
        if isinstance(value,(float,int)) and not isinstance(value,bool):
            value=float(value)
            if value>1e11:value/=1000
        elif isinstance(value,str):
            d=datetime.fromisoformat(value.replace('Z','+00:00'))
            value=d.replace(tzinfo=timezone.utc).timestamp() if d.tzinfo is None else d.timestamp()
        else:return None
        return value if math.isfinite(value) and value>0 else None
    except (ValueError,OverflowError,TypeError):return None

def _iso(t):
    return datetime.fromtimestamp(t,timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')

def ident(value):
    return re.sub(r'[^A-Z0-9]','',str(value or '').upper())

def flight_ident(value):
    s=ident(value)
    m=re.fullmatch(r'([A-Z0-9]{2,3}?)(\d+)([A-Z]?)',s)
    return m[1]+str(int(m[2]))+m[3] if m else s

def _query(data):
    raw=str(data.get('query','')).strip().upper()
    kind=data.get('kind','auto')
    if not re.fullmatch(r'[A-Z0-9-]{2,16}',raw):raise ValueError('Enter a registration, flight number or callsign')
    if kind=='auto':
        kind='hex' if re.fullmatch(r'[0-9A-F]{6}',raw) and any(x.isdigit() for x in raw) else 'reg' if '-' in raw or re.fullmatch(r'N[0-9][A-Z0-9]{0,5}',raw) else 'flight'
    if kind not in ('reg','flight','hex') or kind=='hex' and not re.fullmatch(r'[0-9A-F]{6}',raw):raise ValueError('Invalid search type')
    try:hours=int(data.get('hours',12))
    except (TypeError,ValueError):raise ValueError('Invalid history duration')
    if hours not in (1,3,6,12,24):raise ValueError('Choose 1, 3, 6, 12 or 24 hours')
    return raw,kind,hours

def _key(c,name):
    if name=='avio':return alerts._avio_key(c)
    row=c.execute('SELECT value FROM config WHERE key=?',('acars_key_'+name,)).fetchone()
    key=row['value'] if row else ''
    return key or (alerts._adsbiq_key(c) if name=='vdliq' else '')

def _fingerprint(key):
    return hashlib.sha256(key.encode()).hexdigest()

def settings():
    result={}
    with alerts._lock,alerts.connect() as c:
        for p in PROVIDERS:
            k=_key(c,p)
            row=c.execute('SELECT value FROM config WHERE key=?',('acars_test_'+p,)).fetchone()
            try:t=json.loads(row['value']) if row else {}
            except (TypeError,ValueError):t={}
            if t.get('fingerprint')!=_fingerprint(k):t={}
            custom=c.execute('SELECT value FROM config WHERE key=?',('acars_key_'+p,)).fetchone()
            result[p]={'key_set':bool(k),'custom_key':bool(custom and custom['value']),
                       'reused_key':bool(k and (p=='avio' or p=='vdliq' and not custom)),
                       'test':{x:t[x] for x in ('ok','at','message') if x in t}}
        public,_=alerts.notifier(c)
    return {'providers':result,'ntfy_configured':bool(public['topic'])}

def save_key(p,data):
    if p not in ('vdliq','airframes','drama'):raise ValueError('Use the existing AvioADSB key in ADS-B settings')
    key='' if data.get('clear') else str(data.get('key','')).strip()
    if not data.get('clear') and (not key or len(key)>512 or not re.fullmatch(r'[\x21-\x7e]+',key)):raise ValueError('Enter a valid API key')
    with alerts._lock,alerts.connect() as c:
        if key:c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',('acars_key_'+p,key))
        else:c.execute('DELETE FROM config WHERE key=?',('acars_key_'+p,))
        c.execute('DELETE FROM config WHERE key=?',('acars_test_'+p,))
    return {'ok':True}

def _request(p,path='',params=None,key='',opener=None):
    url=URLS[p]+path
    if params:url+='?'+urlencode(params)
    headers={'Accept':'application/json','User-Agent':'AirspaceAnalytics-Flights/4'}
    if key:headers['X-API-Key' if p=='avio' else 'Authorization']=key if p=='avio' else 'Bearer '+key
    req=Request(url,headers=headers)
    try:
        open_call=opener or _open
        if opener is None and p in BUDGET_NAMES:
            base=open_call
            open_call=lambda r,timeout:api_budget.open_request(BUDGET_NAMES[p],base,r,timeout)
        with open_call(req,timeout=12) as response:
            raw=response.read(MAX_BYTES+1)
            headers=getattr(response,'headers',{}) or {}
            if len(raw)>MAX_BYTES:raise ValueError('Response too large')
            if p=='avio' and opener is None:
                try:
                    remaining=int(headers.get('X-RateLimit-Remaining','99999'))
                    if remaining<(min(500,max(5,int(headers.get('X-RateLimit-Limit','10000' if key else '100'))//10))):
                        reset=float(headers.get('X-RateLimit-Reset','86400'))
                        with _lock:_next[p]=max(_next.get(p,0),time.monotonic()+max(60,min(reset,2678400)))
                except (ValueError,TypeError):pass
            return json.loads(raw)
    except HTTPError as e:
        if e.code==429:
            try:wait=max(INTERVAL[p],float(e.headers.get('Retry-After','900')))
            except (TypeError,ValueError,AttributeError):wait=900
            with _lock:_next[p]=max(_next.get(p,0),time.monotonic()+wait)
        raise ValueError('HTTP '+str(e.code)) from None
    except (URLError,OSError,UnicodeError,json.JSONDecodeError):raise ValueError('Network or invalid JSON response') from None

def _rows(p,payload):
    rows=payload if p=='airframes' and isinstance(payload,list) else payload.get('items' if p=='drama' else 'messages') if isinstance(payload,dict) else None
    if not isinstance(rows,list):raise ValueError('Unexpected message response format')
    return rows

def _normal(p,row):
    if not isinstance(row,dict):return None
    aircraft=row.get('airframe') if isinstance(row.get('airframe'),dict) else {}
    raw_time=row.get('timestamp')
    stamp=_stamp(raw_time)
    if stamp is None:return None
    text=row.get('cleanedText') if p=='drama' else row.get('text')
    if not isinstance(text,str) or not text.strip():return None
    # Strip controls except line breaks; display as text, never HTML.
    text=''.join(ch for ch in text if ch in '\n\t' or ord(ch)>=32).strip()[:4000]
    if not text:return None
    reg=str(row.get('tail') or row.get('registration') or aircraft.get('tail') or '').strip().upper()[:20]
    adsb=row.get('adsb') if isinstance(row.get('adsb'),dict) else {}
    flight=str(row.get('flightNumber') or (row.get('flight') if isinstance(row.get('flight'),str) else '') or '').strip().upper()[:20]
    hexcode=str(row.get('hex') or row.get('icaoHex') or aircraft.get('icao') or '').lower()
    if not re.fullmatch(r'[0-9a-f]{6}',hexcode):hexcode=''
    endpoints=[str(row.get(x,'')).lower() for x in ('fromHex','toHex')]
    protocol=str(row.get('type') or row.get('sourceType') or row.get('protocol') or '').upper()
    if protocol in ('VDL','VDLM2','VDL MODE 2'):protocol='VDL2'
    return {'timestamp':stamp,'reg':reg,'flight':flight,'hex':hexcode,'endpoints':endpoints,
            'callsign':str(adsb.get('flight') or '').strip().upper()[:20],
            'protocol':protocol[:20],'label':str(row.get('label') or '')[:12],
            'text':text,'direction':str(row.get('direction') or row.get('linkDirection') or '')[:20],
            'sources':[p],'id':str(row.get('uuid') or row.get('id') or '')[:100],
            'source_ids':{p:str(row.get('uuid') or row.get('id') or '')[:100]},
            'sequence':str(row.get('msgNum') or row.get('msgno') or row.get('messageNumber') or '')[:20]}

def _match(row,raw,kind,aliases=()):
    if kind=='reg':return ident(row['reg'])==ident(raw)
    if kind=='hex':return raw.lower() in [row['hex'],*row['endpoints']]
    return flight_ident(row['flight'])==flight_ident(raw) or flight_ident(row.get('callsign'))==flight_ident(raw) or (row['flight'] and flight_ident(row['flight']) in aliases)

def _identity(raw,kind):
    if kind=='reg':return {'reg':raw,'hex':'','aliases':[]}
    if kind=='hex':return {'reg':'','hex':raw.lower(),'aliases':[]}
    # Current local decoder/cached flight-log results, no external request here.
    from . import flights_live,flights_cache
    candidates=[]
    try:candidates+=flights_live._local_planes()
    except (OSError,ValueError):pass
    try:
        # The background cache's public data is keyed by registration.
        with flights_cache._lock:
            saved=flights_cache._entries.copy()
        for reg,item in saved.items():
            if isinstance(item,dict) and (item.get('last_observed_at') or 0)>=time.time()-120:
                candidates.append({'r':reg,'flight':item.get('callsign'),'hex':item.get('hex'),'seen':0})
    except (AttributeError,TypeError,ValueError):pass
    matches=[p for p in candidates if isinstance(p,dict) and flight_ident(p.get('flight'))==flight_ident(raw) and isinstance(p.get('seen'),(float,int)) and 0<=p['seen']<=120]
    ids={(str(p.get('r') or '').strip().upper(),str(p.get('hex') or '').lower()) for p in matches}
    ids={i for i in ids if i[0] or re.fullmatch(r'[a-f0-9]{6}',i[1])}
    if len(ids)==1:
        r,h=next(iter(ids));return {'reg':r,'hex':h if re.fullmatch(r'[a-f0-9]{6}',h) else '','aliases':[]}
    return {'reg':'','hex':'','aliases':[]}

def fetch(p,raw,kind,since,until,key,identity,history=True,opener=None):
    """Return exact matches plus limitations. No broad archived firehose requests."""
    params={'limit':100}
    reg=identity.get('reg','')
    hx=identity.get('hex','')
    note=''
    if p=='avio':
        field={'reg':'tail','flight':'flight','hex':'hex'}[kind]
        value=raw
        if kind=='flight' and (hx or reg):field,value=('hex',hx) if hx else ('tail',reg)
        params.update({field:value,'limit':50 if not key else 500})
        payload=_request(p,params=params,key=key,opener=opener)
        if since<until-3600:note='Provider retains only the latest hour.'
    elif p=='vdliq':
        if hx:path='/hex/'+quote(hx,safe='')
        elif reg:path='/tail/'+quote(reg,safe='')
        else:
            # No documented callsign archive filter. A bounded recent window
            # can still find exact flight identifiers, never scan global history.
            path='/recent'
            note='No resolved airframe; searching bounded recent messages only. Search by registration for full history.'
        params.update(since=int(since),until=int(until),limit=500)
        if history and path!='/recent':params['history']=1
        payload=_request(p,path,params,key,opener)
    elif p=='airframes':
        if not key:raise ValueError('Airframes feeder API key required')
        if not hx and reg:
            airframe=_request(p,'/airframes/tail/'+quote(reg,safe=''),key=key,opener=opener)
            if isinstance(airframe,dict) and ident(airframe.get('tail'))==ident(reg):
                hx=str(airframe.get('icao') or '').lower()
                if re.fullmatch(r'[a-f0-9]{6}',hx):identity['hex']=hx
        if not re.fullmatch(r'[a-f0-9]{6}',hx):
            return [],'Airframe ICAO unknown; search by registration or hex to query Airframes.'
        params.update(icao=hx,since=_iso(since),until=_iso(until),aircraft='civil')
        payload=_request(p,'/messages',params,key,opener)
    else:
        if not key:raise ValueError('ACARS Drama feeder Jumpseat key required')
        if kind=='hex':
            if not reg:return [],'Registration needed for ACARS Drama.'
            field='registration';value=reg
        elif kind=='flight' and reg:field,value='registration',reg
        else:field='registration' if kind=='reg' else 'flightNumber';value=raw
        params.update({field:value,'source':'all','from':_iso(since),'to':_iso(until),'limit':500})
        payload=_request(p,params=params,key=key,opener=opener)
    rows=_rows(p,payload)
    cap=params['limit']
    if p=='airframes' and history:
        # Bounded archive pagination using the documented descending ID cursor.
        page=rows
        for _ in range(4):
            if len(page)<100:break
            cursor=page[-1].get('id') if isinstance(page[-1],dict) else None
            if not cursor or cursor==params.get('before_id'):break
            params['before_id']=cursor
            try:page=_rows(p,_request(p,'/messages',params,key,opener))
            except ValueError:break
            rows=rows+page
        cap=MAX_ROWS
    if len(rows)>=cap or (p=='airframes' and len(rows)>=100 and len(page if history else rows)>=100) or isinstance(payload,dict) and payload.get('truncated'):
        note=(note+' ' if note else '')+'Result limit reached; history may be incomplete.'
    result=[]
    for row in rows[:cap]:
        item=_normal(p,row)
        if not item or not since<=item['timestamp']<=until+10:continue
        if _match(item,raw,kind,identity.get('aliases',[])):
            item['match']='exact';result.append(item)
        elif kind in ('flight','reg') and ((hx and hx in [item['hex'],*item['endpoints']]) or (reg and item['reg'] and ident(reg)==ident(item['reg']))):
            if kind=='reg' and item['reg'] and ident(item['reg'])!=ident(reg):continue
            if not item['reg'] and reg:item['reg']=reg
            item['match']='linked airframe' if kind=='flight' else 'exact';result.append(item)
    return result,note

def _duplicate(a,b):
    # Keep separate transmissions; merge same message heard by multiple feeds.
    shared=set(a['sources'])&set(b['sources'])
    if any(a.get('source_ids',{}).get(p) and a['source_ids'][p]==b.get('source_ids',{}).get(p) for p in shared):return True
    if abs(a['timestamp']-b['timestamp'])>12:return False
    if not a['text'] or ' '.join(a['text'].split())!=' '.join(b['text'].split()):return False
    same=(a['hex'] and a['hex']==b['hex']) or (a['reg'] and ident(a['reg'])==ident(b['reg'])) or (a['flight'] and flight_ident(a['flight'])==flight_ident(b['flight']))
    if not same or a['label'] and b['label'] and a['label']!=b['label']:return False
    if a['sequence'] and b['sequence'] and a['sequence']!=b['sequence']:return False
    return not shared or (abs(a['timestamp']-b['timestamp'])<1 and not any(a.get('source_ids',{}).get(p) and b.get('source_ids',{}).get(p) for p in shared))

def _prune(s,now):
    # Provider's one-hour retention is respected for Avio-only observations.
    s['messages']=[m for m in s['messages'] if m['timestamp']>=s['since'] and
                   (now-m['timestamp']<=3600 or any(p!='avio' for p in m['sources']))][:MAX_ROWS]

def _merge(s,rows,now):
    fresh=[]
    for m in sorted(rows,key=lambda r:r['timestamp']):
        old=next((x for x in s['messages'] if _duplicate(x,m)),None)
        if old:
            old['sources']=sorted(set(old['sources']+m['sources']))
            old.setdefault('source_ids',{}).update(m.get('source_ids',{}))
            if m.get('match')=='exact':old['match']='exact'
            for field in ('reg','flight','hex','label','protocol','direction'):
                if not old[field]:old[field]=m[field]
        else:
            s['messages'].append(m)
            fresh.append(m)
    s['messages'].sort(key=lambda r:r['timestamp'],reverse=True)
    _prune(s,now)
    return fresh

def _public(s):
    return {'id':s['id'],'query':s['query'],'kind':s['kind'],'hours':s['hours'],
            'since':s['since'],'tracking_until':s['tracking_until'],'notify_count':s['notify_count'],
            'notify_error':s['notify_error'],'identity':dict(s['identity']),
            'messages':[{k:v for k,v in m.items() if k not in ('source_ids','endpoints')} for m in s['messages']],
            'providers':{p:dict(x) for p,x in s['providers'].items()}}

def _clean_sessions(now):
    for id,s in list(_sessions.items()):
        if max(s['touched']+120,s['tracking_until'])<now:
            del _sessions[id]

def search(data):
    raw,kind,hours=_query(data)
    now=time.time()
    identity=_identity(raw,kind)
    with _lock:
        _clean_sessions(now)
        for s in _sessions.values():
            if (s['query'],s['kind'],s['hours'])==(raw,kind,hours):
                s['touched']=now
                return _public(s)
        if len(_sessions)>=MAX_SESSIONS:raise ValueError('Too many active searches; stop a tracking session first')
        id=secrets.token_hex(12)
        s={'id':id,'query':raw,'kind':kind,'hours':hours,'since':now-hours*3600,
           'touched':now,'tracking_until':0,'tracking_start':0,'notify_count':0,'notify_error':'',
           'identity':identity,'messages':[],'providers':{p:{'state':'Waiting','next':0,'last':0,'note':''} for p in PROVIDERS}}
        _sessions[id]=s
        return _public(s)

def read(id=''):
    with _lock:
        _clean_sessions(time.time())
        if id:
            s=_sessions.get(id)
            if not s:raise ValueError('Search expired; press Send again')
            s['touched']=time.time()
            _prune(s,time.time())
            return _public(s)
        return {'tracking':[{k:s[k] for k in ('id','query','kind','hours','tracking_until','notify_count','notify_error')} for s in _sessions.values() if s['tracking_until']>time.time()]}

def stop(data):
    with _lock:
        _sessions.pop(str(data.get('id','')),None)
    return {'ok':True}


def track(data):
    id=str(data.get('id',''))
    duration=data.get('duration',0)
    if not isinstance(duration,int) or isinstance(duration,bool) or duration not in (0,1,2,3,6,12,24):
        raise ValueError('Choose a tracking duration')
    if duration:
        with alerts._lock,alerts.connect() as c:
            public,_=alerts.notifier(c)
        if not public['topic']:raise ValueError('Configure ntfy under Alerts first')
    with _lock:
        s=_sessions.get(id)
        if not s:raise ValueError('Search expired; press Send again')
        now=time.time()
        s['tracking_until']=now+duration*3600 if duration else 0
        s['tracking_start']=(s['tracking_start'] or now) if duration else 0
        s['touched']=now
        if not duration:s['pending_notifications']=[]
        return _public(s)

def _notify(s,rows,opener=None):
    # Opt-in only, private configured topic. Notify new observations, not
    # historical backfill. Limit each request and never publish credentials.
    with alerts._lock,alerts.connect() as c:public,token=alerts.notifier(c)
    if not public['topic']:return
    for item in rows:
        with _lock:
            if _sessions.get(s['id']) is not s or not s['tracking_start'] or not s['tracking_start']<=item['timestamp']<=s['tracking_until'] or time.time()>s['tracking_until']:continue
        headers={'Title':'ACARS '+s['query'],'Priority':'3','Content-Type':'text/plain; charset=utf-8','Cache':'no'}
        if token:headers['Authorization']='Bearer '+token
        body=(item['reg']+' '+item['flight']+' · '+item['protocol']+' '+item['label']).strip()+'\n'+item['text']
        try:
            with (opener or _open)(Request(public['server']+'/'+public['topic'],data=body[:3000].encode(),headers=headers,method='POST'),timeout=5) as response:
                if not 200<=response.status<300:raise OSError('ntfy did not accept message')
            with _lock:s['notify_count']+=1;s['notify_error']=''
        except (OSError,ValueError,URLError):
            with _lock:s['notify_error']='ntfy delivery failed; message remains visible in ACARS'

def _available(p,key):
    return bool(key) or p in ('avio','vdliq')

def test(p):
    if p not in PROVIDERS:raise ValueError('Unknown datalink source')
    with alerts._lock,alerts.connect() as c:key=_key(c,p)
    if not _available(p,key):raise ValueError('Save the API key first')
    with _lock:
        now=time.monotonic()
        if p in _busy or p in _test_busy or now<_next.get(p,0):raise ValueError('Provider is cooling down; try later')
        _test_busy.add(p);_next[p]=now+(900 if p=='avio' and not key else INTERVAL[p])
    try:
        if p=='avio':payload=_request(p,params={'limit':1},key=key)
        elif p=='vdliq':payload=_request(p,'/recent',{'limit':1},key)
        elif p=='airframes':payload=_request(p,'/messages',{'limit':1,'since':_iso(time.time()-60),'aircraft':'civil'},key)
        else:payload=_request(p,params={'source':'messages','limit':1,'from':_iso(time.time()-60)},key=key)
        rows=_rows(p,payload)
        ok=True;message='Connection successful · message endpoint verified'
    except ValueError as e:
        ok=False;message=str(e)[:100]
    finally:
        with _lock:_test_busy.discard(p)
    if 'cooldown' not in message and 'rate limited' not in message and 'HTTP 429' not in message:
        with alerts._lock,alerts.connect() as c:
            if _key(c,p)==key:
                c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',('acars_test_'+p,json.dumps({'fingerprint':_fingerprint(key),'ok':ok,'message':message,'at':int(time.time())})))
    if not ok:raise ValueError(message)
    return {'ok':True,'message':message,'count':len(rows)}

def _work(p,s,key):
    try:
        now=time.time()
        with _lock:
            first=not s['providers'][p]['last']
            since=s['since'] if first else max(s['since'],s['providers'][p]['last']-600)
            identity=dict(s['identity'])
        # Try current identity again when a flight is first acquired.
        if s['kind']=='flight' and not (identity.get('hex') or identity.get('reg')):
            identity=_identity(s['query'],s['kind'])
        # The datalink flight identifier often differs from the ATC callsign.
        # One bounded documented Avio aircraft lookup can resolve the airframe;
        # the next scheduled datalink query uses that registration/hex.
        if not first and p=='avio' and s['kind']=='flight' and not (identity.get('hex') or identity.get('reg')) and s['providers'][p].get('resolved_attempt',0)<now-900:
            with _lock:s['providers'][p]['resolved_attempt']=now
            try:
                from . import flights_live
                headers={'Accept':'application/json','User-Agent':'AirspaceAnalytics-Flights/4'}
                if key:headers['X-API-Key']=key
                req=Request('https://avioadsb.org/v1/callsign/'+quote(s['query'],safe=''),headers=headers)
                with api_budget.open_request('AvioADSB',_open,req,timeout=8) as resp:
                    raw=resp.read(600001)
                if len(raw)>600000:raise ValueError('Identity response too large')
                payload=json.loads(raw)
                candidates=[x for x in payload.get('ac',[]) if isinstance(x,dict) and flight_ident(x.get('flight'))==flight_ident(s['query']) and flights_live._active(x)]
                pairs={(str(x.get('r') or '').upper(),str(x.get('hex') or '').lower()) for x in candidates}
                if len(pairs)==1:
                    r,h=next(iter(pairs))
                    with _lock:
                        if r:s['identity']['reg']=r
                        if re.fullmatch(r'[a-f0-9]{6}',h):s['identity']['hex']=h
                        s['providers'][p].update(state='Checking',note='Airframe resolved; datalink lookup follows at next interval.')
                    return
            except (OSError,ValueError,TypeError,AttributeError):pass
            # Never bypass the shared provider cooldown with a second request.
            if api_budget.remaining('AvioADSB')>0:return
        with _lock:
            if s['providers'][p].get('identity')!=(identity.get('reg'),identity.get('hex')):
                first=True;since=s['since']
        rows,note=fetch(p,s['query'],s['kind'],since,now,key,identity,first)
        with _lock:
            if _sessions.get(s['id']) is not s:return
            for k in ('reg','hex'):
                if identity.get(k) and not s['identity'].get(k):s['identity'][k]=identity[k]
            # Exact flight-number matches can establish a unique current airframe.
            if s['kind']=='flight':
                recent=[m for m in rows if now-m['timestamp']<3600 and m['reg']]
                regs={m['reg'] for m in recent}
                if len(regs)==1 and not s['identity'].get('reg'):
                    s['identity']['reg']=next(iter(regs))
                    h={m['hex'] for m in recent if m['hex']}
                    if len(h)==1:s['identity']['hex']=next(iter(h))
            fresh=_merge(s,rows,now)
            # A missing identity is not a successful archive search.
            state='Limited' if note.startswith(('Airframe ICAO unknown','Registration needed','No resolved airframe')) else 'Connected'
            s['providers'][p].update(state=state,last=now,note=note,identity=(identity.get('reg'),identity.get('hex')))
        # Delivery is separate from fetching, so slow notifications cannot block data sources.
        with _lock:
            if s['tracking_start'] and time.time()<s['tracking_until']:
                q=s.setdefault('pending_notifications',[])
                q.extend(m for m in fresh if s['tracking_start']<=m['timestamp']<=s['tracking_until'])
                if len(q)>MAX_ROWS:s['notify_error']='Notification queue full; older messages remain visible in ACARS';del q[MAX_ROWS:]
    except (ValueError,OSError,TypeError,KeyError) as e:
        message=str(e)
        safe=re.search(r'HTTP \d{3}|rate limited|Network or invalid JSON response|Unexpected message response format|Response too large|API key required',message)
        with _lock:s['providers'][p].update(state='Unavailable',note=safe.group(0) if safe else 'Provider lookup failed')
    finally:
        with _lock:_busy.discard(p)

def tick():
    now=time.time();mono=time.monotonic()
    with alerts._lock,alerts.connect() as c:keys={p:_key(c,p) for p in PROVIDERS}
    with _lock:
        _clean_sessions(now)
        for p in PROVIDERS:
            if not _available(p,keys[p]):
                for s in _sessions.values():s['providers'][p].update(state='Key required',note='Configure in Settings → APIs')
                continue
            if p in _busy or p in _test_busy or mono<_next.get(p,0):continue
            if p in BUDGET_NAMES and api_budget.remaining(BUDGET_NAMES[p])>0:continue
            due=[s for s in _sessions.values() if s['providers'][p]['next']<=mono]
            if not due:continue
            s=min(due,key=lambda x:x['providers'][p]['next'])
            delay=900 if p=='avio' and not keys[p] else INTERVAL[p]
            _next[p]=mono+delay
            s['providers'][p].update(state='Checking',next=mono+delay)
            _busy.add(p)
            threading.Thread(target=_work,args=(p,s,keys[p]),daemon=True,name='airspace-acars-'+p).start()

def start():
    global _started
    with _lock:
        if _started:return
        _started=True
    def loop():
        while True:
            try:tick()
            except Exception:pass
            time.sleep(5)
    threading.Thread(target=loop,daemon=True,name='airspace-acars').start()
    def deliver():
        while True:
            try:
                with _lock:
                    active=next((s for s in _sessions.values() if s['tracking_until']>time.time() and s.get('pending_notifications')),None)
                    item=active['pending_notifications'].pop(0) if active else None
                if active:_notify(active,[item])
            except Exception:pass
            time.sleep(1)
    threading.Thread(target=deliver,daemon=True,name='airspace-acars-notify').start()
