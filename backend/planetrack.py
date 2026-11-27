"""Optional PlaneTrack REST adapter. One shared bounded cache; no continuous polling.
Data: PlaneTrack.ai. Personal use. Aircraft reference includes Mictronics (ODC-BY).
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from . import api_budget

NAME='PlaneTrack'
BASE='https://planetrack.ai/v1'
LIVE_INTERVAL=6*3600
HISTORY_INTERVAL=24*3600
WINDOW=15
RESERVE=100
_lock=threading.RLock()
_identity=''
_next_live=0.
_next_history=0.
_busy=False
_planes=[]
_stamp=0.
_routes={}
_state={}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fingerprint(key):
    return hashlib.sha256(key.encode()).hexdigest() if key else ''

def reset():
    global _identity,_next_live,_next_history,_planes,_stamp,_routes,_state
    with _lock:
        _identity='';_next_live=0.;_next_history=0.;_planes=[];_stamp=0.;_routes={};_state={}

def _number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _time(v):
    if not isinstance(v,str):return None
    try:
        d=datetime.fromisoformat(v.replace('Z','+00:00'))
        return d.timestamp() if d.tzinfo else None
    except (ValueError,OverflowError):return None

def _open(request,timeout=10):
    return build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=timeout)

def _request(path,key,opener=None):
    if not key:raise ValueError('Save your PlaneTrack key first')
    request=Request(BASE+path,headers={'X-API-Key':key,'Accept':'application/json','User-Agent':'AirspaceAnalytics/1'})
    if opener is None:opener=lambda req,timeout:api_budget.open_request(NAME,_open,req,timeout)
    try:
        with opener(request,timeout=12) as response:
            raw=response.read(12_000_001)
        if len(raw)>12_000_000:raise ValueError('PlaneTrack response too large')
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError('Invalid PlaneTrack response')
        return value
    except HTTPError as e:
        if e.code==402:raise ValueError('PlaneTrack credits exhausted') from None
        raise ValueError('PlaneTrack HTTP '+str(e.code)) from None
    except (URLError,OSError,TypeError,UnicodeError,json.JSONDecodeError):
        raise ValueError('PlaneTrack unavailable or invalid response') from None

def _usage(key,opener=None):
    result=_request('/usage',key,opener)
    quota,remaining=result.get('monthly_credits'),result.get('credits_remaining')
    if not _number(quota) or not _number(remaining) or not 0<=remaining<=quota:
        raise ValueError('Invalid PlaneTrack credit balance')
    return {'tier':str(result.get('tier','unknown'))[:30],
            'monthly_quota':int(quota),'monthly_used':int(quota-remaining),
            'credits_remaining':int(remaining)}

def test(key,opener=None):
    info=_usage(key,opener)
    with _lock:
        if _identity in ('',fingerprint(key)):_state.update(info)
    return {'ok':True,'plan':info['tier']+' · '+str(info['credits_remaining'])+' credits left (balance verified)'}

def parse_live(payload,now=None):
    now=time.time() if now is None else now
    meta=payload.get('meta')
    stamp=_time(meta.get('generated_at')) if isinstance(meta,dict) else None
    rows=payload.get('aircraft')
    if stamp is None or not -10<=now-stamp<=40 or not isinstance(rows,list):
        raise ValueError('Stale or invalid PlaneTrack snapshot')
    result=[]
    for row in rows[:20000]:
        if not isinstance(row,dict):continue
        h=str(row.get('icao24') or '').lower()
        last=_time(row.get('last_seen'))
        if not re.fullmatch(r'[0-9a-f]{6}',h) or last is None or not -10<=now-last<=60:continue
        # The API supplies grid time, not independent per-position message age.
        # Conservatively include the requested observation window.
        age=max(0,now-last,now-stamp)+WINDOW
        p={'hex':h,'seen':age,'_source':NAME,'_network_source':NAME}
        for source,target,pattern in [('registration','r',r'[A-Z0-9-]{2,16}'),('callsign','flight',r'[A-Z0-9]{1,8}'),('type','t',r'[A-Z0-9]{2,4}'),('squawk','squawk',r'[0-7]{4}')]:
            v=str(row.get(source) or '').strip().upper()
            if re.fullmatch(pattern,v):p[target]=v
        if row.get('on_ground') is True:p['alt_baro']='ground'
        elif _number(row.get('altitude')) and -1500<=row['altitude']<=100000:p['alt_baro']=row['altitude']
        if _number(row.get('velocity')) and 0<=row['velocity']<=2000:p['gs']=row['velocity']
        if _number(row.get('heading')) and 0<=row['heading']<=360:p['track']=row['heading']
        if all(_number(row.get(k)) for k in ('lat','lon')) and -90<=row['lat']<=90 and -180<=row['lon']<=180:
            p.update(lat=row['lat'],lon=row['lon'],seen_pos=age)
        result.append(p)
    return result

def parse_history(payload,call,now=None):
    """Consistent previous completed flights only, not today's confirmed route."""
    now=time.time() if now is None else now
    rows=payload.get('flights')
    if not isinstance(rows,list):return None
    routes=set()
    for row in rows[:20]:
        if not isinstance(row,dict) or str(row.get('callsign','')).strip().upper()!=call:continue
        stamp=_time(row.get('arrival_time'))
        if stamp is None or not 0<=now-stamp<=7*86400:continue
        dep,arr=row.get('departure'),row.get('arrival')
        if not isinstance(dep,dict) or not isinstance(arr,dict):continue
        a,b=(str(v.get('airport') or '').strip().upper() for v in (dep,arr))
        if re.fullmatch(r'[A-Z]{3,4}',a) and re.fullmatch(r'[A-Z]{3,4}',b) and a!=b:routes.add((a,b))
    return next(iter(routes)) if len(routes)==1 else None

def _worker(key,identity,kind,call=None):
    global _busy,_planes,_stamp
    try:
        info=_usage(key)
        with _lock:
            if _identity!=identity:return
            _state.update(info)
        cost=10 if kind=='live' else 20
        if info['credits_remaining']<cost+RESERVE:raise ValueError('PlaneTrack credit reserve reached')
        # The usage call is free but still obey the documented request rate.
        time.sleep(2.1)
        if kind=='live':
            value=_request('/live?window_secs=15&limit=20000',key)
            planes=parse_live(value)
        else:
            value=_request('/flights/'+call+'/history?days=7&limit=10',key)
            route=parse_history(value,call)
        with _lock:
            if _identity!=identity:return
            meta=value.get('meta',{})
            remaining=meta.get('credits_remaining') if isinstance(meta,dict) else None
            if _number(remaining) and 0<=remaining<=info['monthly_quota']:
                _state.update(credits_remaining=int(remaining),monthly_used=info['monthly_quota']-int(remaining))
            if kind=='live':_planes=planes;_stamp=time.monotonic()
            else:_routes[call]=(time.monotonic()+86400,route)
            _state.update(error=None,last_success=time.time())
    except (OSError,ValueError,TypeError) as e:
        with _lock:
            if _identity==identity:_state['error']=str(e).replace(key,'[redacted]')[:120]
    finally:
        with _lock:_busy=False

def _schedule(key,kind,call=None):
    global _identity,_next_live,_next_history,_busy,_planes,_stamp,_routes,_state
    if not key:return
    identity=fingerprint(key)
    with _lock:
        if _identity!=identity:
            _identity=identity;_next_live=0.;_next_history=0.;_planes=[];_stamp=0.;_routes={};_state={}
        now=time.monotonic()
        if _busy or now<(_next_live if kind=='live' else _next_history) or api_budget.remaining(NAME)>0:return
        if kind=='live':_next_live=now+LIVE_INTERVAL
        else:_next_history=now+HISTORY_INTERVAL
        _busy=True
        _state['last_attempt']=time.time()
        threading.Thread(target=_worker,args=(key,identity,kind,call),daemon=True,name='airspace-planetrack').start()

def ensure_live(key):
    _schedule(key,'live')

def cached(identity):
    if not identity:return []
    with _lock:
        if identity!=_identity or not _stamp:return []
        elapsed=max(0,time.monotonic()-_stamp)
        if elapsed>120:return []
        result=[]
        for src in _planes:
            p=dict(src)
            for field in ('seen','seen_pos'):
                if field in p:p[field]+=elapsed
            if p['seen']<=120:result.append(p)
        return result

def usual_routes(key,calls):
    if not key:return {}
    valid=list(dict.fromkeys(c for c in calls if re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',c)))
    with _lock:
        if fingerprint(key)!=_identity:return {}
        now=time.monotonic()
        result={c:_routes[c][1] for c in valid if c in _routes and _routes[c][0]>now and _routes[c][1]}
        missing=[c for c in valid if c not in _routes or _routes[c][0]<=now]
    if missing:_schedule(key,'history',missing[0])
    return result

def status():
    with _lock:
        now=time.time()
        info=dict(_state)
        if 'last_attempt' in info:info['last_attempt_seconds_ago']=round(max(0,now-info.pop('last_attempt')))
        info['retry_seconds']=round(max(0,_next_live-time.monotonic(),api_budget.remaining(NAME)))
        info['matching_aircraft']=0
        return info
