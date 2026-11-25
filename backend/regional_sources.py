"""Read-only nearby coverage shared by backup alerts and Flights.
No remote aircraft are written to the receiver or Aerodrome database.
"""
from __future__ import annotations
import math
import threading
import time
from . import api_budget, extra_flight_sources as extra

_lock=threading.RLock()
_region=None
_cache={}
_next={}
_errors={}
_busy=set()
_enabled=set()

def valid(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def nearby(p,region):
    if not region:return False
    lat,lon,radius=region
    a,b=p.get('lat'),p.get('lon')
    if not valid(a) or not valid(b) or not -90<=a<=90 or not -180<=b<=180:return False
    # Haversine, including antimeridian wrap.
    dlat=math.radians(a-lat)
    dlon=math.radians(b-lon)
    h=math.sin(dlat/2)**2+math.cos(math.radians(lat))*math.cos(math.radians(a))*math.sin(dlon/2)**2
    return 12742*math.asin(math.sqrt(min(1,max(0,h))))<=radius

def region():
    with _lock:return _region

def publish(name,planes,area=None):
    now=time.monotonic()
    with _lock:
        if area is None:area=_region
        if not area or area!=_region or name not in _enabled:return
        _cache[name]=(now,[dict(p,_network_source=name) for p in planes if nearby(p,area)][:3000])
        _errors.pop(name,None)

def aircraft():
    now=time.monotonic()
    with _lock:
        out=[]
        for name,(stamp,planes) in _cache.items():
            if name not in _enabled or now-stamp>120:continue
            for p in planes:
                q=dict(p)
                for k in ('seen','seen_pos'):
                    if valid(q.get(k)):q[k]+=max(0,now-stamp)
                if q.get('seen',999)<=120:out.append(q)
        enabled='ADSBHub' in _enabled
    if enabled:out.extend(extra.hub_nearby())
    return out

def _json_planes(payload):
    now=time.time()
    if not isinstance(payload,dict) or not isinstance(payload.get('ac'),list) or not valid(payload.get('now')):
        raise ValueError('Invalid aircraft snapshot')
    stamp=payload['now']
    if stamp>1e11:stamp/=1000
    if not -10<=now-stamp<=50:raise ValueError('Stale aircraft snapshot')
    result=[]
    for src in payload['ac']:
        if not isinstance(src,dict):continue
        p=dict(src)
        for k in ('seen','seen_pos'):
            if valid(p.get(k)) and 0<=p[k]<=120:p[k]+=max(0,now-stamp)
            else:p.pop(k,None)
        result.append(p)
    return result

def _fetch(name,area,key):
    lat,lon,radius=area
    nm=math.ceil(radius/1.852)
    if name=='AvioADSB':
        url=f'https://avioadsb.org/v1/point/{lat:.6f}/{lon:.6f}/{min(nm,250)}'
        auth={'X-API-Key':key}
    elif name=='ADSBiq':
        url=f'https://api.adsbiq.com/v2/lat/{lat:.6f}/lon/{lon:.6f}/dist/{nm}'
        auth={'Authorization':'Bearer '+key}
    elif name=='airplanes.live':
        url=f'https://api.airplanes.live/v2/point/{lat:.6f}/{lon:.6f}/{nm}'
        auth={}
    else:raise ValueError('Unknown regional provider')
    return _json_planes(extra._json(url,auth,provider=name))

def configure(area,keys,verified):
    """Called independently of receiver matching; only cache reads in the alert loop."""
    global _region,_enabled
    names={n for n in ('AvioADSB','ADSBiq') if keys.get(n)}
    if verified.get('airplaneslive',{}).get('ok'):names.add('airplanes.live')
    if verified.get('adsbhub',{}).get('ok'):names.add('ADSBHub')
    # OpenSky region may be used only with written authorization.
    if keys.get('OpenSky Network') and verified.get('opensky',{}).get('ok'):names.add('OpenSky Network')
    with _lock:
        if area!=_region:_cache.clear()
        _region=area
        _enabled=names if area else set()
        for name in list(_cache):
            if name not in _enabled:del _cache[name]
        now=time.monotonic()
        extra.set_region(area,'ADSBHub' in _enabled)
        if not area:return
        for name,delay in [('AvioADSB',900),('ADSBiq',300),('airplanes.live',240),('OpenSky Network',240)]:
            if name not in _enabled or name in _busy or now<_next.get(name,0) or api_budget.remaining(name)>0:continue
            if name in _cache and now-_cache[name][0]<45:continue
            _next[name]=now+delay
            _busy.add(name)
            def worker(n=name,a=area,k=keys.get(name)):
                try:
                    planes=extra.opensky_region(k,a) if n=='OpenSky Network' else _fetch(n,a,k)
                    publish(n,planes,a)
                except (ValueError,OSError) as err:
                    with _lock:_errors[n]=str(err)[:120]
                finally:
                    with _lock:_busy.discard(n)
            threading.Thread(target=worker,daemon=True,name='airspace-region-'+name).start()

def health():
    with _lock:
        now=time.monotonic()
        return {name:{'nearby_aircraft':len(_cache.get(name,(0,[]))[1]),
                      'last_attempt_seconds_ago':round(max(0,now-_cache[name][0])) if name in _cache else None,
                      'error':_errors.get(name),'retry_seconds':round(api_budget.remaining(name))}
                for name in sorted(_enabled)}
