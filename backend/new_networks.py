"""Shared optional network adapters. No external data is written to Aerodrome.

map.flights contract: /api/v1/near, /aircraft/{hex}/flights and
/flights/by-callsign/{callsign}; schema cross-checked with pymapflights 0.3.0.
Fly Overhead: documented /api/public/aircraft/bounds; accept only explicitly
fresh, identifiable observed aircraft. No speculative route endpoint.
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
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from . import api_budget

MAP='map.flights'
FLY='Fly Overhead'
BASE={MAP:'https://map.flights/api/v1',FLY:'https://flyoverhead.com/api/public'}
INTERVAL={MAP:10,FLY:65}
MAP_CREDIT='Data: map.flights. Flight data (c) map.flights, adsb.fi; attribution required. Contains information from Mictronics Aircraft Database, which is made available under the ODC Attribution License (ODC-BY 1.0). Contains information from plane-alert-db (sdr-enthusiasts), which is made available under the Open Database License (ODbL 1.0).'
_lock=threading.RLock()
_cache={}
_next={}
_busy=set()
_health={}
_identity={}
_routes={}
_landings={}
_daily={}
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fingerprint(key):
    return hashlib.sha256(key.encode()).hexdigest() if key else ''

def _num(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _stamp(v):
    if _num(v):return v/1000 if v>1e11 else v
    if isinstance(v,str):
        try:
            d=datetime.fromisoformat(v.replace('Z','+00:00'))
            return d.timestamp() if d.tzinfo else None
        except (ValueError,OverflowError):pass
    return None

def _age(v,now):
    t=_stamp(v)
    return max(0,now-t) if t is not None and -10<=now-t<=120 else None

def _ident(v):
    return str(v or '').strip().lower()

def _code(v):
    if isinstance(v,dict):v=v.get('iata') or v.get('icao')
    v=str(v or '').strip().upper()
    return v if re.fullmatch(r'[A-Z]{3,4}',v) else ''

def _route(a,b):
    a,b=_code(a),_code(b)
    return (a,b) if a and b and a!=b else None

def _request(name,path,key,opener=None,live=False):
    if not key or name not in BASE:raise ValueError('API key unavailable')
    ident=fingerprint(key)
    # Guard daily credits even if no headers are returned. Server Retry-After
    # remains authoritative; map live has its own independent quota.
    day=datetime.now(timezone.utc).date().isoformat()
    if not live or name==FLY:
        with _lock:
            bucket=(name,ident,day)
            used=_daily.get(bucket,0)
            if used>=(800 if name==MAP else 1800):raise ValueError(name+' daily request reserve reached')
            _daily[bucket]=used+1
            for b in list(_daily):
                if b[2]!=day:_daily.pop(b,None)
    req=Request(BASE[name]+path,headers={'X-API-Key':key,'Accept':'application/json','User-Agent':'AirspaceAnalytics/1.10.44'})
    if opener is None:
        base=build_opener(ProxyHandler({}),NoRedirect()).open
        # Independent map live and REST buckets; Fly Overhead shares limits.
        scope='map.flights live' if name==MAP and live else name
        opener=lambda request,timeout:api_budget.open_request(scope,base,request,timeout)
    try:
        with opener(req,timeout=8) as response:
            raw=response.read(6_000_001)
            if len(raw)>6_000_000:raise ValueError('Response too large')
            data=json.loads(raw)
            headers=getattr(response,'headers',{})
            remaining=headers.get('X-RateLimit-Remaining') if headers else None
            if remaining is not None and str(remaining).isdigit() and (not live or name==FLY):
                with _lock:
                    if _identity.get(name)==ident:_health.setdefault(name,{})['remaining']=int(remaining)
        if not isinstance(data,dict):raise ValueError('Invalid API response')
        return data
    except HTTPError as e:
        if e.code==404:return None
        raise ValueError(name+' HTTP '+str(e.code)) from None
    except (URLError,OSError,TypeError,UnicodeError,json.JSONDecodeError):
        raise ValueError(name+' unavailable or invalid response') from None

def parse_map(payload,now=None):
    now=time.time() if now is None else now
    if not isinstance(payload,dict) or payload.get('dataDelayReady') is False or payload.get('dataDelayS',0) not in (None,0):
        raise ValueError('map.flights delayed or invalid snapshot')
    delta=_age(payload.get('now'),now)
    rows=payload.get('ac')
    if delta is None or delta>30 or not isinstance(rows,list):raise ValueError('map.flights stale or invalid snapshot')
    out=[]
    for row in rows[:500]:
        if not isinstance(row,dict) or row.get('est') or row.get('gndObj'):continue
        h=_ident(row.get('hex')); age=row.get('ageS')
        if not re.fullmatch(r'[0-9a-f]{6}',h) or not _num(age) or not 0<=age<=120:continue
        lat,lon=row.get('lat'),row.get('lon')
        if not (_num(lat) and _num(lon) and -90<=lat<=90 and -180<=lon<=180):continue
        p={'hex':h,'lat':lat,'lon':lon,'seen':age+delta,'seen_pos':age+delta,'_source':MAP,'_network_source':MAP}
        for source,target in [('registration','r'),('callsign','flight'),('typecode','t'),('category','category')]:
            if isinstance(row.get(source),str):p[target]=row[source].strip().upper()[:16]
        if row.get('onGround') is True:p['alt_baro']='ground'
        elif _num(row.get('altBaro')):p['alt_baro']=row['altBaro']
        if _num(row.get('gs')) and not row.get('gsEst'):p['gs']=row['gs']
        if _num(row.get('track')) and not row.get('trackEst'):p['track']=row['track']
        if row.get('kind')=='mil':p['dbFlags']=1
        route=_route(row.get('origin'),row.get('dest'))
        if route:p['route']={'from':route[0],'to':route[1]}
        out.append(p)
    return out

def parse_fly(payload,now=None):
    """Only accept explicit readsb-compatible timestamps, units and fields.
    Unknown formats fail the test rather than silently fabricating freshness.
    """
    now=time.time() if now is None else now
    if not isinstance(payload,dict):raise ValueError('Fly Overhead invalid response')
    rows=payload.get('ac')
    delta=_age(payload.get('now'),now)
    if not isinstance(rows,list) or delta is None or delta>30:
        raise ValueError('Fly Overhead schema not verified: need timestamped ac array')
    out=[]
    for r in rows[:5000]:
        if not isinstance(r,dict) or not re.fullmatch(r'[0-9a-f]{6}',_ident(r.get('hex'))):continue
        age=r.get('seen')
        if not _num(age) or not 0<=age<=120:continue
        if r.get('estimated') or r.get('est'):continue
        p={k:r[k] for k in ('hex','r','flight','t','alt_baro','gs','lat','lon','track','squawk','dbFlags','category') if k in r}
        p.update(hex=_ident(r['hex']),seen=age+delta,_source=FLY,_network_source=FLY)
        if _num(r.get('seen_pos')) and 0<=r['seen_pos']<=120:p['seen_pos']=r['seen_pos']+delta
        else:p.pop('lat',None);p.pop('lon',None)
        # Route confidence not established by this endpoint.
        route=_route(r.get('route_origin'),r.get('route_dest'))
        if route:p['route']={'from':route[0],'to':route[1]}
        out.append(p)
    return out

def near(name,key,area,opener=None):
    lat,lon,radius=area
    if not all(_num(v) for v in area) or not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('Receiver coordinates required')
    # Conservative margin around the feeder's 300 km circle (station grid may
    # differ from exact receiver coordinates). A 403 never triggers global retry.
    radius=min(250,max(10,radius))
    if name==MAP:
        path=f'/near/{lat:.5f}/{lon:.5f}/{radius:.1f}?limit=500'
        return parse_map(_request(name,path,key,opener,live=True))
    # Bounding box only, no guessed global/registration endpoint.
    radius=min(radius,150)
    dy=radius/111.2;dx=radius/(111.2*max(.2,math.cos(math.radians(lat))))
    path='/aircraft/bounds?'+urlencode({'latMin':max(-90,lat-dy),'lonMin':max(-180,lon-dx),'latMax':min(90,lat+dy),'lonMax':min(180,lon+dx)})
    return parse_fly(_request(name,path,key,opener,live=True))

def test(name,key,area):
    result=near(name,key,(area[0],area[1],15))
    return {'ok':True,'plan':'Fresh regional aircraft endpoint verified','aircraft':len(result)}

def reset(name):
    with _lock:
        _identity.pop(name,None);_cache.pop(name,None);_health.pop(name,None);_next.pop(name,None)
        if name==MAP:_routes.clear();_landings.clear()

def _activate(name,key):
    ident=fingerprint(key)
    if _identity.get(name)!=ident:
        reset(name);_identity[name]=ident
    return ident

def _start(name,scope,key,delay,job):
    ident=_activate(name,key)
    slot=(name,scope)
    now=time.monotonic()
    if slot in _busy or now<_next.get(slot,0):return
    budget='map.flights live' if name==MAP and scope=='live' else name
    if api_budget.remaining(budget)>0:return
    _busy.add(slot);_next[slot]=now+delay
    _health.setdefault(name,{})['last_attempt']=time.time()
    def run():
        try:
            result=job()
            with _lock:
                if _identity.get(name)!=ident:return
                if scope=='live':_cache[name]=(time.monotonic(),result)
                _health.setdefault(name,{}).update(error=None,last_success=time.time())
        except (ValueError,OSError,TypeError) as err:
            with _lock:
                if _identity.get(name)==ident:
                    _health.setdefault(name,{})['error']=str(err).replace(key,'[redacted]')[:150]
                    _next[slot]=max(_next.get(slot,0),time.monotonic()+(300 if '403' in str(err) or '401' in str(err) else 30))
        finally:
            with _lock:_busy.discard(slot)
    threading.Thread(target=run,daemon=True,name='airspace-'+name+'-'+scope).start()

def collect(keys,area):
    if not area:return []
    result=[]
    with _lock:
        for name in BASE:
            key=keys.get(name)
            if not key:continue
            _start(name,'live',key,INTERVAL[name],lambda n=name,k=key:near(n,k,area))
            cached=_cache.get(name)
            if not cached:continue
            stamp,planes=cached;elapsed=max(0,time.monotonic()-stamp)
            for p in planes:
                if p.get('seen',999)+elapsed>120:continue
                q=dict(p,seen=p['seen']+elapsed)
                if _num(q.get('seen_pos')):q['seen_pos']+=elapsed
                result.append(q)
    return result

def parse_current(payload,call,hexcode,now=None):
    now=time.time() if now is None else now
    if not isinstance(payload,dict):return None
    f,l=payload.get('flight'),payload.get('live')
    if not isinstance(f,dict) or not isinstance(l,dict):return None
    if _ident(f.get('hex'))!=hexcode or _ident(l.get('hex'))!=hexcode:return None
    if str(f.get('callsign','')).strip().upper()!=call:return None
    age=_age(l.get('updated'),now)
    if age is None or age>60 or f.get('landingTime'):return None
    return _route(f.get('origin'),f.get('dest'))

def parse_landing(payload,hexcode,reg,now=None):
    now=time.time() if now is None else now
    if not isinstance(payload,dict) or _ident(payload.get('hex'))!=hexcode:return None
    rows=payload.get('flights')
    if not isinstance(rows,list):return None
    found=[]
    normal=lambda s:re.sub('[^A-Z0-9]','',str(s or '').upper())
    for row in rows[:20]:
        if not isinstance(row,dict) or _ident(row.get('hex'))!=hexcode or normal(row.get('registration'))!=normal(reg):continue
        stamp=_stamp(row.get('landingTime'));airport=_code(row.get('dest'))
        if stamp is not None and 0<=now-stamp<=7*86400 and airport:
            found.append({'airport':airport,'time':int(stamp),'source':'map.flights observed history'})
    return max(found,key=lambda r:r['time']) if found else None

def enrich(key,requests,missing):
    """Schedule independent route and landing fallbacks; read only warm caches."""
    if not key:return {},{}
    with _lock:
        ident=_activate(MAP,key)
        now=time.monotonic()
        routes={};landings={}
        for call,h in requests:
            if not re.fullmatch(r'[A-Z0-9]{2,10}',call) or not re.fullmatch(r'[0-9a-f]{6}',h):continue
            token=(call,h)
            item=_routes.get(token)
            if item and item[0]>now:
                if item[1]:routes[token]=item[1]
                continue
            def work(c=call,x=h,t=token):
                val=parse_current(_request(MAP,'/flights/by-callsign/'+c,key),c,x)
                with _lock:
                    if _identity.get(MAP)==ident:_routes[t]=(time.monotonic()+(600 if val else 900),val)
            _start(MAP,'route',key,10,work)
        for reg,h in missing:
            if not re.fullmatch(r'[0-9a-f]{6}',h):continue
            token=(reg,h)
            item=_landings.get(token)
            if item and item[0]>now:
                if item[1]:landings[reg]=item[1]
                continue
            def work(r=reg,x=h,t=token):
                val=parse_landing(_request(MAP,'/aircraft/'+x+'/flights?limit=10',key),x,r)
                with _lock:
                    if _identity.get(MAP)==ident:_landings[t]=(time.monotonic()+(3600 if val else 1800),val)
            _start(MAP,'history',key,60,work)
        return routes,landings

def health():
    with _lock:
        return {n:{**{k:v for k,v in _health.get(n,{}).items() if k!='last_attempt'},
            'last_attempt_seconds_ago':round(max(0,time.time()-_health[n]['last_attempt'])) if _health.get(n,{}).get('last_attempt') else None,
            'retry_seconds':round(max(0,_next.get((n,'live'),0)-time.monotonic())),
            'nearby_aircraft':sum(1 for p in _cache[n][1] if p.get('seen',999)+max(0,time.monotonic()-_cache[n][0])<=120) if n in _cache else 0}
            for n in BASE}
