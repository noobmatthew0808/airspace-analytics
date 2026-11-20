"""Read-only status and local Aerodrome last-seen history for the personal flight log.

Local receiver + read-only Aerodrome sightings take priority. Global registration
lookup rotates among configured providers with strict per-provider freshness,
backoff and one bounded lookup per cycle. Never writes to Google Sheets.
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

from . import alerts, adsbfi, adsblol, flyitaly, data, live_details, flights_routes, flights_history

_CACHE_LOCK=threading.Lock()
# Keep the original adsb.fi cache shape for existing callers and regressions.
_REMOTE={'updated':0.,'aircraft':[],'error':None}
_OTHER_REMOTE={
    'FlyItalyADSB':{'updated':0.,'aircraft':[],'error':None},
    'adsb.lol':{'updated':0.,'aircraft':[],'error':None},
}
_ROTATION={'at':0.,'cursor':0,'retry_until':{}}
MAX_BYTES=1_750_000
MAX_REGS=80
MIN_REMOTE_PERIOD=35
MAX_CACHED_AGE=40
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


def _lookup_provider(regs,provider='adsb.fi',key='',opener=None):
    """Bounded global registration lookup; all endpoints verified from official docs.

    One call for adsb.fi and adsb.lol; FlyItaly uses batches of at most 50.
    No credentials are included in URLs, errors or responses.
    """
    if opener is None:opener=build_opener(ProxyHandler({}),_NoRedirect()).open
    codes=list(dict.fromkeys(str(r).strip().upper() for r in regs
        if re.fullmatch(r'[A-Z0-9-]{2,16}',str(r).strip().upper())))[:MAX_REGS]
    if not codes:return []
    configurations={
        'adsb.fi':('https://opendata.adsb.fi/api/v2/registration/',MAX_REGS,{}),
        'adsb.lol':('https://api.adsb.lol/v2/reg/',MAX_REGS,{'X-API-Key':key}),
        'FlyItalyADSB':('https://api.flyitalyadsb.com/v2/reg/',50,{'X-Api-Key':key}),
    }
    if provider not in configurations:raise ValueError('Unknown aircraft source')
    if provider!='adsb.fi' and not key:raise ValueError('API key unavailable')
    prefix,limit,auth=configurations[provider]
    aircraft=[]
    for start in range(0,len(codes),limit):
        batch=codes[start:start+limit]
        address=prefix+','.join(batch)
        if provider=='FlyItalyADSB':
            # Batch endpoint is list-shaped only with at least one comma.
            # ?with=route adds the usual observed route, not today's filed plan.
            if len(batch)==1:address+=','
            address+='?with=route'
        request=Request(address,headers={
            'Accept':'application/json','User-Agent':'AirspaceAnalytics-FlightLog/2',**auth})
        try:
            with opener(request,timeout=6) as response:
                if int(response.headers.get('Content-Length','0') or 0)>MAX_BYTES:
                    raise ValueError('Network aircraft response too large')
                raw=response.read(MAX_BYTES+1)
                if len(raw)>MAX_BYTES:raise ValueError('Network aircraft response too large')
            payload=json.loads(raw)
            if not isinstance(payload,dict) or not isinstance(payload.get('ac'),list):
                raise ValueError('Unexpected aircraft response')
            when=payload.get('now')
            if not isinstance(when,(int,float)) or not math.isfinite(when):
                raise ValueError('Missing network timestamp')
            if when>1e11:when/=1000
            delta=time.time()-when
            if not -10<=delta<=50:raise ValueError('Stale network aircraft response')
            for record in payload['ac'][:500]:
                if not isinstance(record,dict):continue
                p=dict(record)
                for field in ('seen','seen_pos'):
                    v=p.get(field)
                    if isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=120:
                        p[field]=v+max(0,delta)
                    else:p.pop(field,None)
                p['_source']=provider
                aircraft.append(p)
        except HTTPError as error:
            if error.code==404:continue  # valid request; no matching aircraft
            if error.code==429:raise ValueError('API rate limited') from None
            raise ValueError(provider+' HTTP '+str(error.code)) from None
        except (URLError,OSError,TimeoutError):
            raise ValueError(provider+' currently unavailable') from None
        except (json.JSONDecodeError,UnicodeDecodeError):
            raise ValueError('Invalid aircraft response from '+provider) from None
    return aircraft


def _lookup_network(regs,opener=None):
    """Backwards-compatible keyless adsb.fi lookup for callers and tests."""
    return _lookup_provider(regs,'adsb.fi',opener=opener)


def _configured_keys():
    """Read existing Alerts configuration; never expose key material to client."""
    try:
        with alerts._lock,alerts.connect() as db:
            return {'FlyItalyADSB':alerts._flyitaly_key(db),
                    'adsb.lol':alerts._adsblol_key(db)}
    except (OSError,ValueError):
        return {'FlyItalyADSB':'','adsb.lol':''}


def _local_last_seen(registrations):
    """Most recent *own receiver* Aerodrome sighting and ICAO per registration.

    One read-only, bounded batch query. Remote aircraft never populate this.
    """
    keys=list(dict.fromkeys(normal_reg(x) for x in registrations if normal_reg(x)))
    if not keys:return {}
    output={}
    try:
        with closing(data.connection()) as db:
            rows=db.execute(
                "SELECT icao,registration,last_seen_at FROM seen_aircraft "
                "WHERE UPPER(REPLACE(REPLACE(TRIM(registration),'-',''),' ','')) IN ("+
                ','.join('?' for _ in keys)+") ORDER BY last_seen_at DESC LIMIT 250",
                keys).fetchall()
        for row in rows:
            name=normal_reg(row['registration'])
            icao=str(row['icao'] or '').strip().lower()
            stamp=row['last_seen_at']
            if name in keys and name not in output and re.fullmatch(r'[a-f0-9]{6}',icao):
                if isinstance(stamp,(int,float)) and 0<stamp<=time.time()+120:
                    output[name]={'hex':icao,'last_seen_at':int(stamp)}
    except (OSError,ValueError,TypeError,Exception):
        return {}  # Aerodrome may be temporarily updating; optional only
    return output


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
    if not targets:
        return {'aircraft':{},'checked_at':int(time.time())}

    # All local data is independent of external API quotas.
    local=_local_planes()
    local_history=_local_last_seen(registrations)
    others=[dict(p,_source=p.get('_network_source') or 'Backup API')
            for p in adsbfi.aircraft()+adsblol.aircraft()+flyitaly.aircraft()
            if isinstance(p,dict)]

    # The already-running alert workers poll geographically (near Polegate).
    # This registration-specific lookup handles other airports worldwide.
    configured=_configured_keys() if network_fetch is _lookup_network else {}
    provider_keys={'adsb.fi':'',**{k:v for k,v in configured.items() if v}}
    with _CACHE_LOCK:
        now=time.monotonic()
        if network_fetch is _lookup_network:
            if not _ROTATION['at'] or now-_ROTATION['at']>=MIN_REMOTE_PERIOD:
                eligible=[key for key in ('adsb.fi','FlyItalyADSB','adsb.lol')
                          if key in provider_keys and now>=_ROTATION['retry_until'].get(key,0)]
                if eligible:
                    provider=eligible[_ROTATION['cursor']%len(eligible)]
                    _ROTATION['cursor']+=1
                    _ROTATION['at']=now
                    selected=_REMOTE if provider=='adsb.fi' else _OTHER_REMOTE[provider]
                    selected['updated']=now
                    try:
                        selected['aircraft']=_lookup_provider(registrations,provider,provider_keys[provider])
                        selected['error']=None
                    except (OSError,ValueError) as error:
                        selected.update(aircraft=[],error=str(error)[:110])
                        # Back off failed provider instead of burning its quota.
                        _ROTATION['retry_until'][provider]=time.monotonic()+(
                            900 if 'rate limit' in str(error).lower() else 150)
        elif not _REMOTE['updated'] or now-_REMOTE['updated']>=MIN_REMOTE_PERIOD:
            # Keep old injection point for deterministic offline regressions.
            _REMOTE['updated']=now
            try:_REMOTE.update(aircraft=network_fetch(registrations),error=None)
            except (OSError,ValueError) as error:
                _REMOTE.update(aircraft=[],error=str(error)[:110])

        # Age *every* provider's cached aircraft. Each plane must be freshly
        # detected even if its provider was last used in another rotation slot.
        remote=[]
        for provider,stored in [('adsb.fi',_REMOTE),*_OTHER_REMOTE.items()]:
            elapsed=max(0.,time.monotonic()-stored['updated'])
            if stored['updated']<=0 or elapsed>MAX_CACHED_AGE:continue
            for source in stored['aircraft']:
                plane=dict(source)
                for field in ('seen','seen_pos'):
                    age=plane.get(field)
                    if isinstance(age,(int,float)) and math.isfinite(age):
                        plane[field]=age+elapsed
                plane.setdefault('_source',provider)
                remote.append(plane)

    seen={}
    for plane in remote+others+local:
        if not _active(plane):continue
        reg=normal_reg(plane.get('r',''))
        if reg in targets:seen[reg]=_prefer(seen.get(reg),plane)
    calls=[str(p.get('flight') or '').strip().upper() for p in seen.values()]
    route_map=_routes([c for c in calls if re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',c)])
    # The normal Aerodrome route_cache is fast but often lacks the current
    # callsign. Queue a separate, position-aware adsb.lol route lookup.
    # Never wait for HTTP here: a route response is shown on later refreshes.
    missing_routes=[]
    for plane in seen.values():
        flight=str(plane.get('flight') or '').strip().upper()
        if not flight or route_map.get(flight):continue
        if not isinstance(plane.get('lat'),(int,float)) or not isinstance(plane.get('lon'),(int,float)):
            continue
        age=plane.get('seen_pos')
        if not isinstance(age,(int,float)) or age<0 or age>30:continue
        missing_routes.append({'callsign':flight,'lat':plane['lat'],'lon':plane['lon']})
    plausible_routes=flights_routes.cached_routes(missing_routes)
    route_map.update(plausible_routes)
    # Observed usual callsign routes are a fallback, *not* a confirmation.
    usual_routes={}
    for item in remote+others+local:
        if not isinstance(item,dict):continue
        reg=normal_reg(item.get('r',''))
        if reg not in targets:continue
        route_info=item.get('route')
        if not isinstance(route_info,dict) or not item.get('flight'):continue
        orig=str(route_info.get('from_iata') or '').strip().upper()
        dest=str(route_info.get('to_iata') or '').strip().upper()
        if re.fullmatch(r'[A-Z]{3}',orig) and re.fullmatch(r'[A-Z]{3}',dest) and orig!=dest:
            usual_routes[str(item['flight']).strip().upper()]=orig+'–'+dest
    history_key=configured.get('FlyItalyADSB','') if isinstance(configured,dict) else ''
    unknown_regs=[reg for key,reg in targets.items() if key not in seen]
    if history_key and unknown_regs:
        flights_history.schedule(unknown_regs,history_key)
    output={}
    for key,registration in targets.items():
        history=local_history.get(key,{})
        plane=seen.get(key)
        result={'status':'N/A','route':'','route_confidence':'','source':'','hex':'',
                'at_airport':'','last_landed_at':None,
                'local_hex':history.get('hex',''),
                'local_last_seen_at':history.get('last_seen_at')}
        if plane is None:
            recent=flights_history.cached(registration)
            if recent:
                result.update(status='Last landed '+recent['airport'],
                              source='FlyItalyADSB observed history',
                              last_landed_at=recent['time'],
                              at_airport=recent['airport'])
            output[registration]=result
            continue
        flight=str(plane.get('flight') or '').strip().upper()
        route=route_map.get(flight,'')
        confidence='plausible' if flight in plausible_routes else ('cached' if route else '')
        if not route and flight in usual_routes:
            route=usual_routes[flight]
            confidence='usual'
        altitude=plane.get('alt_baro')
        airport=''
        status='N/A'
        if altitude=='ground':
            airport=airport_for_ground(plane) or ''
            status='At '+airport if airport else 'Ground'
        else:
            speed=plane.get('gs')
            high=isinstance(altitude,(int,float)) and altitude>=2000
            moving=isinstance(speed,(int,float)) and speed>=80
            if high or moving:
                status=('Flying '+route if confidence!='usual' else 'Flying · likely '+route) if route else 'Flying'
        hexcode=str(plane.get('hex') or '').lower().strip()
        if not re.fullmatch(r'[a-f0-9]{6}',hexcode):hexcode=''
        result.update(status=status,route=route if status.startswith('Flying') else '',
                      route_confidence=confidence if status.startswith('Flying') else '',
                      source=str(plane.get('_source',''))[:30],hex=hexcode,
                      at_airport=airport,callsign=flight,
                      updated_seconds_ago=plane.get('seen'))
        output[registration]=result
    return {'aircraft':output,'checked_at':int(time.time())}
