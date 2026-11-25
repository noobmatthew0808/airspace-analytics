"""adsb.fi public geographic aircraft feed; no API key is needed.

Uses official v3 geographic API, not the legacy v2 positional endpoint.
Contributor-only /v2/snapshot access is automatically granted by source IP.
This poller does not request or download the global snapshot.
"""
from __future__ import annotations
from . import api_budget
import json
import math
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

BASE='https://opendata.adsb.fi/api'
MAX_BYTES=2_000_000
MAX_AGE=110
_lock=threading.Lock()
_state={'aircraft':[],'last_success':None,'error':None,'aircraft_count':0,
        'requests_session':0,'retry_after':0.0}

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None

def _open(request,timeout=5):
    return build_opener(ProxyHandler({}),_NoRedirect()).open(request,timeout=timeout)

def discard_aircraft():
    """No eligible rule: disable cached network matches, keep connection status."""
    with _lock:_state['aircraft']=[]

def status():
    with _lock:
        last=_state['last_success']
        return {'key_required':False,'key_set':False,
                'connected':bool(last and time.time()-last<MAX_AGE),
                'last_success':last,'error':_state['error'],
                'aircraft':_state['aircraft_count'],
                'requests_session':_state['requests_session'],
                'retry_after':_state['retry_after'] if _state['retry_after']>time.time() else None}

def fetch(lat,lon,radius_km,opener=None):
    """At most one local geographic request each caller-controlled 60s cycle."""
    if opener is None:opener=lambda req,timeout:api_budget.open_request('adsb.fi',_open,req,timeout)
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (lat,lon,radius_km)):
        raise ValueError('Set antenna coordinates in Receiver configuration')
    if not (-90<=lat<=90 and -180<=lon<=180 and .1<=radius_km<=450):
        raise ValueError('Invalid antenna location or radius')
    with _lock:
        if time.time()<_state['retry_after']:
            raise ValueError('adsb.fi rate limit: retry later')
    radius_nm=math.ceil(radius_km/1.852)
    url=f'{BASE}/v3/lat/{lat:.7f}/lon/{lon:.7f}/dist/{radius_nm}'
    request=Request(url,headers={'User-Agent':'AirspaceAnalytics-Alerts/1',
                                 'Accept':'application/json'})
    try:
        with opener(request,timeout=5) as response:
            if int(response.headers.get('Content-Length','0') or 0)>MAX_BYTES:
                raise ValueError('adsb.fi response too large')
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('adsb.fi response too large')
        payload=json.loads(raw)
        if not isinstance(payload,dict) or not isinstance(payload.get('ac'),list):
            raise ValueError('Invalid adsb.fi v3 aircraft response')
        now=time.time()
        age=payload.get('now')
        if not isinstance(age,(float,int)) or not math.isfinite(age):
            raise ValueError('adsb.fi response has no timestamp')
        if age>1e11:age/=1000  # v3 may use epoch milliseconds.
        if age<now-45 or age>now+10:
            raise ValueError('Stale adsb.fi response')
        elapsed=max(0,now-age)
        planes=[]
        for src in payload['ac'][:3000]:
            if not isinstance(src,dict):continue
            p=dict(src)
            for field in ('seen','seen_pos'):
                v=p.get(field)
                if isinstance(v,(float,int)) and math.isfinite(v) and 0<=v<=90:
                    p[field]=v+elapsed
                else:p.pop(field,None)
            p['_network_source']='adsb.fi'
            planes.append(p)
        with _lock:
            _state.update(aircraft=planes,last_success=now,error=None,
                          aircraft_count=len(planes),retry_after=0,
                          requests_session=_state['requests_session']+1)
        return status()
    except (OSError,ValueError,TypeError) as exc:
        if isinstance(exc,HTTPError):
            error=f'adsb.fi HTTP {exc.code}'
            if exc.code==429:
                with _lock:_state['retry_after']=time.time()+120
        elif isinstance(exc,URLError):
            error='adsb.fi connection failed'
        else:error=str(exc)[:120]
        with _lock:_state['error']=error
        raise ValueError(error) from None

def aircraft():
    """Age positional data between polls and do not retain stale aircraft."""
    with _lock:
        last=_state['last_success']
        if not last or time.time()-last>=MAX_AGE:return []
        elapsed=max(0,time.time()-last)
        planes=[dict(p) for p in _state['aircraft']]
    for p in planes:
        for field in ('seen','seen_pos'):
            v=p.get(field)
            if isinstance(v,(float,int)) and math.isfinite(v):
                p[field]=v+elapsed
            else:p.pop(field,None)
    return planes
