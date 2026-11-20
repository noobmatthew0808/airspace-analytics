"""Read-only, best-effort live status for registrations in the personal flight log.

Uses (1) this antenna's existing readsb JSON, (2) already cached network
aircraft data and (3) one bounded adsb.fi registration batch at most every
90 seconds. No tracker API can write to Google Sheets or delay flight log CRUD.
"""
from __future__ import annotations

from contextlib import closing
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from . import alerts, adsbfi, adsblol, flyitaly, data, live_details

_CACHE_LOCK=threading.Lock()
_REMOTE={'updated':0.,'aircraft':[],'error':None}
MAX_BYTES=1_750_000
MAX_REGS=80
MIN_REMOTE_PERIOD=90
AIRPORT_FILE=Path('/opt/aerodrome/static/airports.json')
# Airport reference fallback for common UK airports when Aerodrome isn't mounted.
COMMON_AIRPORTS=(
    ('LGW',51.1481,-0.1903),('LHR',51.4700,-0.4543),
    ('STN',51.8850,0.2350),('LTN',51.8747,-0.3683),
    ('LCY',51.5053,0.0553),('SOU',50.9503,-1.3568),
    ('BHX',52.4539,-1.7480),('MAN',53.3537,-2.2750),
    ('BRS',51.3827,-2.7191),('EMA',52.8311,-1.3281),
)


def current_registration(value):
    raw=str(value or '').strip()
    m=re.search(r'\(([^()]*)\)\s*$',raw)
    return (m.group(1) if m else raw).strip()


def normal_reg(value):
    return re.sub('[^A-Z0-9]','',current_registration(value).upper())


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


def _lookup_network(regs,opener=None):
    """Provider's documented public /v2/registration endpoint; 1 batch call."""
    if opener is None:opener=build_opener(ProxyHandler({}),_NoRedirect()).open
    # Use only reasonable, encoded registration values and never a raw URL from UI.
    codes=[str(r).strip().upper() for r in regs if re.fullmatch(r'[A-Z0-9-]{2,16}',str(r).strip().upper())]
    if not codes:return []
    url='https://opendata.adsb.fi/api/v2/registration/'+','.join(codes[:MAX_REGS])
    request=Request(url,headers={'Accept':'application/json',
                                  'User-Agent':'AirspaceAnalytics-FlightLog/1'})
    try:
        with opener(request,timeout=6) as response:
            if int(response.headers.get('Content-Length','0') or 0)>MAX_BYTES:
                raise ValueError('Network response too large')
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError('Network response too large')
        response=json.loads(raw)
        if not isinstance(response,dict) or not isinstance(response.get('ac'),list):
            raise ValueError('Unexpected network aircraft response')
        when=response.get('now')
        if not isinstance(when,(int,float)) or not math.isfinite(when):
            raise ValueError('No snapshot timestamp')
        if when>1e11:when/=1000
        delta=time.time()-when
        if delta>50 or delta<-10:raise ValueError('Old network snapshot')
        planes=[]
        for aircraft in response['ac'][:500]:
            if not isinstance(aircraft,dict):continue
            plane=dict(aircraft)
            for agefield in ('seen','seen_pos'):
                v=plane.get(agefield)
                if isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=120:
                    plane[agefield]=v+max(0,delta)
                else:plane.pop(agefield,None)
            plane['_source']='adsb.fi'
            planes.append(plane)
        return planes
    except HTTPError as error:
        # Not-found means nobody in this batch is currently broadcasting.
        if error.code==404:return []
        raise ValueError(f'adsb.fi HTTP {error.code}') from None
    except (URLError,OSError,TimeoutError):
        raise ValueError('Network aircraft positions unavailable') from None
    except (json.JSONDecodeError,UnicodeDecodeError):
        raise ValueError('Invalid network aircraft data') from None


@lru_cache(maxsize=1)
def _airport_positions():
    choices=list(COMMON_AIRPORTS)
    try:
        source=json.loads(AIRPORT_FILE.read_text(encoding='utf-8'))
        rows=source.get('airports',[]) if isinstance(source,dict) else []
        for entry in rows:
            if not isinstance(entry,list) or len(entry)<8:continue
            code=str(entry[7] or entry[0] or '').strip().upper()
            if not re.fullmatch(r'[A-Z]{3}',code):continue
            # Aerodrome's compact OurAirports rows store lat/lon after ICAO.
            try:lat=float(entry[1]);lon=float(entry[2])
            except (ValueError,TypeError):continue
            if -90<=lat<=90 and -180<=lon<=180:
                choices.append((code,lat,lon))
    except (OSError,ValueError,TypeError):
        pass
    return choices


def _km(a,b,c,d):
    a,b,c,d=map(math.radians,(a,b,c,d))
    v=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 12742*math.asin(min(1,math.sqrt(max(0,v))))


def airport_for_ground(plane):
    """Only assert an airport when a current GROUND position is very close."""
    age=plane.get('seen_pos',999)
    if not isinstance(age,(int,float)) or age<0 or age>35:return None
    try:lat=float(plane['lat']);lon=float(plane['lon'])
    except (ValueError,TypeError,KeyError):return None
    if not (-90<=lat<=90 and -180<=lon<=180):return None
    speed=plane.get('gs')
    if isinstance(speed,(int,float)) and speed>45:return None
    closest=None
    for code,alat,alon in _airport_positions():
        if abs(lat-alat)>0.05 or abs(lon-alon)>0.08:continue
        dist=_km(lat,lon,alat,alon)
        if dist<=2.0 and (closest is None or dist<closest[0]):
            closest=(dist,code)
    return closest[1] if closest else None


def _routes(calls):
    if not calls:return {}
    calls=list(dict.fromkeys(calls))[:MAX_REGS]
    try:
        with closing(data.connection()) as db:
            rows=db.execute(
                'SELECT callsign,origin_icao,dest_icao FROM route_cache WHERE callsign IN ('+
                ','.join('?' for _ in calls)+')',calls).fetchall()
        return {str(item['callsign']).upper():
                live_details._route(item['origin_icao'],item['dest_icao'])
                for item in rows}
    except Exception:
        return {}


def _local_planes():
    """Direct existing readsb feed; never require Docker socket access."""
    try:
        raw=alerts._get_json('http://127.0.0.1:1090/data/aircraft.json')
        now=raw.get('now') if isinstance(raw,dict) else None
        if not isinstance(now,(float,int)) or abs(time.time()-now)>20:return []
        return [dict(a,_source='Your antenna') for a in raw.get('aircraft',[])[:2500]
                if isinstance(a,dict)]
    except (OSError,ValueError,TypeError,KeyError):
        return []


def _active(p):
    age=p.get('seen')
    return isinstance(age,(int,float)) and math.isfinite(age) and 0<=age<=30


def _prefer(current,other):
    if current is None:return other
    # Prefer current local reception over remote when both are fresh.
    if other.get('_source')=='Your antenna' and current.get('_source')!='Your antenna':
        return other
    return current


def snapshot(value='',network_fetch=_lookup_network):
    tokens=[str(v).strip().upper() for v in str(value).split(',') if v.strip()]
    if len(tokens)>MAX_REGS or len(value)>2000:
        raise ValueError('Too many registrations for a status lookup')
    registrations=[]
    for token in tokens:
        if not re.fullmatch(r'[A-Z0-9-]{2,16}',token):
            raise ValueError('Invalid registration')
        if token not in registrations:registrations.append(token)
    targets={normal_reg(x):x for x in registrations}
    if not targets:return {'aircraft':{},'source':'Local receiver + adsb.fi','checked_at':int(time.time())}

    local=_local_planes()
    others=[dict(p,_source=p.get('_network_source') or 'Backup API')
            for p in adsbfi.aircraft()+adsblol.aircraft()+flyitaly.aircraft()
            if isinstance(p,dict)]
    # One registration batch per 90s maximum across all visitors.
    with _CACHE_LOCK:
        now=time.monotonic()
        if now-_REMOTE['updated']>=MIN_REMOTE_PERIOD:
            _REMOTE['updated']=now  # even errors cause backoff
            try:
                _REMOTE['aircraft']=network_fetch(registrations)
                _REMOTE['error']=None
            except (OSError,ValueError) as error:
                _REMOTE['aircraft']=[]
                _REMOTE['error']=str(error)[:150]
        remote=[dict(p) for p in _REMOTE['aircraft']]
        error=_REMOTE['error']
    seen={}
    for plane in remote+others+local:
        if not _active(plane):continue
        reg=normal_reg(plane.get('r',''))
        if reg in targets:seen[reg]=_prefer(seen.get(reg),plane)
    calls=[str(p.get('flight') or '').strip().upper() for p in seen.values()]
    route_map=_routes([c for c in calls if re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',c)])
    output={}
    for key,registration in targets.items():
        plane=seen.get(key)
        if plane is None:
            output[registration]={'status':'N/A','route':'','source':'','hex':'','at_airport':''}
            continue
        flight=str(plane.get('flight') or '').strip().upper()
        route=route_map.get(flight,'')
        altitude=plane.get('alt_baro')
        status='N/A'
        airport=''
        if altitude=='ground':
            airport=airport_for_ground(plane) or ''
            status='At '+airport if airport else 'Ground'
        else:
            gs=plane.get('gs')
            pos_age=plane.get('seen_pos')
            fresh_position=isinstance(pos_age,(int,float)) and 0<=pos_age<=35
            has_altitude=isinstance(altitude,(int,float)) and altitude>=2000
            moving=isinstance(gs,(int,float)) and gs>=80
            if fresh_position and (has_altitude or moving):
                status='Flying '+route if route else 'Flying'
            elif has_altitude or moving:
                status='Flying '+route if route else 'Flying'
        hexcode=str(plane.get('hex') or '').lower().strip()
        if not re.fullmatch(r'[a-f0-9]{6}',hexcode):hexcode=''
        output[registration]={'status':status,'route':route if status.startswith('Flying') else '',
            'source':str(plane.get('_source',''))[:30],'hex':hexcode,
            'at_airport':airport,'callsign':flight,'updated_seconds_ago':plane.get('seen')}
    return {'aircraft':output,'source':'Your antenna + available network APIs',
            'checked_at':int(time.time()),
            **({'warning':error} if error else {})}
