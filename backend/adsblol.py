"""Optional adsb.lol network aircraft cache.

Official API: https://api.adsb.lol/v2 with X-API-Key.
Geographic query distance is nautical miles, unlike our website (kilometres).
Feeds and alert matching remain fully independent from this poller.
"""
from __future__ import annotations

import json
import math
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen, build_opener, ProxyHandler, HTTPRedirectHandler

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def _private_open(request, timeout=5):
    """Fixed HTTPS provider only; never forward API keys after redirects."""
    return build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)

BASE = 'https://api.adsb.lol/v2'
MAX_BYTES = 2_000_000
MAX_AGE = 85  # 30-second polls and short network interruptions
_lock = threading.Lock()
_state = dict(aircraft=[],last_success=None,last_error=None,last_count=0,
              requests=0,retry_after=0)

def clear():
    with _lock:
        _state.update(aircraft=[],last_success=None,last_error=None,last_count=0,retry_after=0)

def status(key_set=False):
    with _lock:
        return {'key_set':bool(key_set),'connected':bool(_state['last_success'] and
                time.time()-_state['last_success']<MAX_AGE),
                'last_success':_state['last_success'],'error':_state['last_error'],
                'aircraft':_state['last_count'],'requests_session':_state['requests'],
                'retry_after':_state['retry_after'] if _state['retry_after']>time.time() else None}

def fetch(key,lat,lon,radius_km,opener=None):
    if opener is None:opener=_private_open
    if not isinstance(key,str) or not key.strip():
        raise ValueError('adsb.lol feeder key is not saved')
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (lat,lon,radius_km)):
        raise ValueError('Antenna coordinates are required')
    if not (-90<=lat<=90 and -180<=lon<=180 and .1<=radius_km<=500):
        raise ValueError('Invalid coordinates or radius')
    with _lock:
        if time.time() < _state['retry_after']:
            raise ValueError('adsb.lol rate limit: retry later')
    # adsb.lol's /dist/ expects nautical miles. Round up for complete km coverage.
    radius_nm=math.ceil(radius_km/1.852)
    url=f'{BASE}/lat/{lat:.7f}/lon/{lon:.7f}/dist/{radius_nm}'
    req=Request(url,headers={'X-API-Key':key,
        'User-Agent':'AirspaceAnalytics-Alerts/1','Accept':'application/json'})
    try:
        with opener(req,timeout=5) as resp:
            if int(resp.headers.get('Content-Length','0') or 0)>MAX_BYTES:
                raise ValueError('adsb.lol response too large')
            raw=resp.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('adsb.lol response too large')
        obj=json.loads(raw)
        if not isinstance(obj,dict) or not isinstance(obj.get('ac'),list):
            raise ValueError('Invalid adsb.lol aircraft response')
        now=time.time()
        source_now=obj.get('now')
        if not isinstance(source_now,(int,float)) or not math.isfinite(source_now):
            raise ValueError('Missing network timestamp')
        if source_now>1e11:source_now/=1000  # readsb v2 often uses milliseconds
        if source_now<now-40 or source_now>now+10:
            raise ValueError('Stale adsb.lol response')
        elapsed=max(0,now-source_now)
        planes=[]
        for src in obj['ac'][:3000]:
            if not isinstance(src,dict):continue
            p=dict(src)
            for field in ('seen','seen_pos'):
                age=p.get(field)
                if isinstance(age,(int,float)) and math.isfinite(age) and 0<=age<=80:
                    p[field]=age+elapsed
                else:p.pop(field,None)
            p['_network_source']='adsb.lol'
            planes.append(p)
        with _lock:
            _state.update(aircraft=planes,last_success=now,last_error=None,
                          last_count=len(planes),requests=_state['requests']+1,retry_after=0)
        return status(key_set=True)
    except (OSError,ValueError,TypeError) as exc:
        if isinstance(exc,HTTPError):
            msg=f'adsb.lol HTTP {exc.code}'
            if exc.code==429:
                try:delay=min(900,max(30,int(exc.headers.get('Retry-After','60'))))
                except (ValueError,TypeError):delay=60
                with _lock:_state['retry_after']=time.time()+delay
        elif isinstance(exc,URLError):msg='adsb.lol connection failed'
        else:msg=str(exc)[:120]
        with _lock:_state['last_error']=msg
        raise ValueError(msg) from None

def aircraft():
    with _lock:
        saved=_state['last_success']
        if not saved or time.time()-saved>=MAX_AGE:return []
        delta=max(0,time.time()-saved)
        planes=[dict(p) for p in _state['aircraft']]
    for p in planes:
        for field in ('seen','seen_pos'):
            age=p.get(field)
            if isinstance(age,(int,float)) and math.isfinite(age):p[field]=age+delta
            else:p.pop(field,None)
    return planes
