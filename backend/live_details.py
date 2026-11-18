"""On-demand aircraft enrichment for the live view (no second history DB).

The half-second display remains the real viewadsb stream. This module only
adds slowly changing readsb/Aerodrome metadata when a browser requests it.
"""
from __future__ import annotations

from contextlib import closing
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from threading import Lock, BoundedSemaphore
from urllib.parse import quote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.parse import urlsplit
import json
import re
import time
import subprocess

from . import data, alerts

_HEX = re.compile(r'^[0-9A-F]{6}$')
_CALL = re.compile(r'^[A-Z0-9]{2,8}$')
_LIVE_URLS = (
    'http://127.0.0.1:1099/map/data/aircraft.json',
    'http://127.0.0.1:1099/data/aircraft.json',
)
_RECEIVER_URLS = (
    'http://127.0.0.1:1099/map/data/receiver.json',
    'http://127.0.0.1:1099/data/receiver.json',
)
_ROUTE_CACHE = {}
_ROUTE_LOCK = Lock()
_ROUTE_SLOT = BoundedSemaphore(1)
_FEED_LAST_GOOD = None
_DB_ROOT_CACHE = {}
_DB_SHARD_CACHE = {}
_TAR_ROUTE_CACHE = {}
_CACHE_LOCK = Lock()
_TAR_ROUTE_SLOT = BoundedSemaphore(1)
_ROUTE_API_RETRY_AFTER = 0
# Used only if the preinstalled Aerodrome airports list is unavailable.
_COMMON_IATA = {
    'EGKK':'LGW','EGLL':'LHR','EGSS':'STN','EGGW':'LTN','EGCC':'MAN',
    'EGBB':'BHX','EGPH':'EDI','EGPF':'GLA','EGLC':'LCY','EGNX':'EMA',
    'EGGD':'BRS','EGHI':'SOU','EGHH':'BOH','EGNM':'LBA','EGAA':'BFS',
    'EGAC':'BHD','EGGP':'LPL','EGNT':'NCL','EGTE':'EXT','EGJJ':'JER',
    'EGJB':'GCI','EGFF':'CWL','EGPK':'PIK','EGPD':'ABZ','EGPE':'INV',
    'EIDW':'DUB','EICK':'ORK','EINN':'SNN','EIKN':'NOC',
    'LEMD':'MAD','LEBL':'BCN','LEPA':'PMI','LEMG':'AGP','LEAL':'ALC',
    'LEVC':'VLC','LEIB':'IBZ','GCLP':'LPA','GCTS':'TFS','GCXO':'TFN',
    'GCRR':'ACE','GCFV':'FUE','LPPT':'LIS','LPPR':'OPO','LPFR':'FAO',
    'LFPG':'CDG','LFPO':'ORY','LFPB':'LBG','LFML':'MRS','LFLL':'LYS',
    'LFMN':'NCE','LFSB':'BSL','EDDF':'FRA','EDDM':'MUC','EDDB':'BER',
    'EDDH':'HAM','EDDL':'DUS','EDDK':'CGN','EDDS':'STR','EDDP':'LEJ',
    'EHAM':'AMS','EHRD':'RTM','EHEH':'EIN','EBBR':'BRU','EBLG':'LGG',
    'LSZH':'ZRH','LSGG':'GVA','LOWW':'VIE','LKPR':'PRG','LZIB':'BTS',
    'LHBP':'BUD','EPWA':'WAW','EPKK':'KRK','EDDW':'BRE','LIRF':'FCO',
    'LIMC':'MXP','LIME':'BGY','LIPZ':'VCE','LIRN':'NAP','LGAV':'ATH',
    'LGTS':'SKG','LTAC':'ESB','LTFM':'IST','SAEZ':'EZE','KJFK':'JFK',
    'KEWR':'EWR','KLAX':'LAX','KSFO':'SFO','KORD':'ORD','KATL':'ATL',
    'KDFW':'DFW','KDEN':'DEN','KBOS':'BOS','KMIA':'MIA','CYYZ':'YYZ',
    'OMDB':'DXB','OTHH':'DOH','WSSS':'SIN','VHHH':'HKG','RJTT':'HND',
}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None

def _json(url, timeout=0.7):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url, headers={'User-Agent':'AirspaceAnalytics-Live/1'}),
                     timeout=timeout) as response:
        if int(response.headers.get('Content-Length', '0') or 0) > 1_500_000:
            raise ValueError('Data response too large')
        content = response.read(1_500_001)
    if len(content) > 1_500_000:
        raise ValueError('Data response too large')
    return json.loads(content)

@lru_cache(maxsize=1)
def _airports():
    # Aerodrome already ships OurAirports with BOTH ICAO and IATA; no
    # downloads, no added Python packages, and no stored copy required.
    codes = dict(_COMMON_IATA)
    for path in (Path('/opt/aerodrome/static/airports.json'),):
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            for entry in raw.get('airports', []):
                if len(entry) > 7:
                    icao, iata = str(entry[0]).upper(), str(entry[7]).upper()
                    if re.fullmatch(r'[A-Z0-9]{4}', icao) and re.fullmatch(r'[A-Z]{3}', iata):
                        codes[icao] = iata
            break
        except (OSError, TypeError, ValueError, KeyError):
            continue
    return codes

def _iata(code):
    code = str(code or '').strip().upper()
    if re.fullmatch(r'[A-Z]{3}', code):
        return code
    return _airports().get(code, '')

def _route(origin, destination):
    departure, arrival = _iata(origin), _iata(destination)
    if departure and arrival and departure != arrival:
        return departure + ' – ' + arrival
    return ''

def _km(lat1, lon1, lat2, lon2):
    a, b, c, d = map(radians, (lat1, lon1, lat2, lon2))
    hav = sin((c-a)/2)**2 + cos(a)*cos(c)*sin((d-b)/2)**2
    return round(12742.0*asin(min(1.0, sqrt(max(0.0, hav)))), 1)

def parse_items(value):
    items=[]
    for entry in str(value or '').split(',')[:100]:
        part=entry.strip().upper().split(':',1)
        hexcode=part[0].lstrip('~')
        callsign=part[1] if len(part)==2 else ''
        if not _HEX.fullmatch(hexcode):
            continue
        if callsign and not _CALL.fullmatch(callsign):
            callsign=''
        items.append((hexcode, callsign))
    return list(dict.fromkeys(items))

def _candidate_feeds():
    """Use the same local receiver discovery as Alerts, not loopback only.

    Ultrafeeder/tar1090 may be exposed on the host's Wi-Fi IP, while its
    port does not listen on 127.0.0.1. Never probe arbitrary remote hosts.
    """
    candidates=[]
    try:
        config=alerts.snapshot().get('receiver_settings',{})
        configured=config.get('url')
        if configured:candidates.append(configured)
    except (OSError,ValueError,TypeError):pass
    if _FEED_LAST_GOOD:candidates.append(_FEED_LAST_GOOD)
    try:
        urls=alerts._receiver_candidates(alerts._local_addresses())
        candidates.extend(urls)
    except (OSError,ValueError,TypeError,AttributeError):
        candidates.extend(_LIVE_URLS)
    return tuple(dict.fromkeys(candidates))

def _docker_json(filename):
    """Read readsb's current JSON directly from the already-running Ultrafeeder.

    Raw viewadsb already has working permission to this same Docker container.
    The filename is fixed; no shell, new container, restart or user input.
    """
    if filename not in ('aircraft.json', 'receiver.json'):
        raise ValueError('Unsupported readsb JSON file')
    try:
        process=subprocess.run(
            ('docker','exec','ultrafeeder','cat','/run/readsb/'+filename),
            capture_output=True,timeout=1.5,check=False)
        if process.returncode or len(process.stdout)>1_500_000:
            return {}
        result=json.loads(process.stdout)
        return result if isinstance(result,dict) else {}
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return {}


def _valid_aircraft_snapshot(value):
    if not (isinstance(value,dict) and isinstance(value.get('aircraft'),list)):
        return False
    stamp=value.get('now')
    # readsb writes a UNIX timestamp. Never serve an old disk snapshot.
    return not isinstance(stamp,(float,int)) or abs(time.time()-stamp)<=30


def _readsb():
    """Use the same Ultrafeeder decoder as the working Raw terminal first."""
    global _FEED_LAST_GOOD
    # This removes dependency on which 1099/map proxy paths the user runs.
    direct=_docker_json('aircraft.json')
    if _valid_aircraft_snapshot(direct):
        return direct
    for url in _candidate_feeds():
        # The Alerts URL validator ensures same-host HTTP feeds only.
        try:
            if not alerts._receiver_url_allowed(url,alerts._local_addresses()):
                continue
            obj=_json(url,timeout=0.55)
            if not _valid_aircraft_snapshot(obj):
                continue
            _FEED_LAST_GOOD=url
            return obj
        except (ValueError,OSError,KeyError,TypeError,AttributeError):
            continue
    _FEED_LAST_GOOD=None
    return {}

def _tar_db_roots():
    """Find tar1090's actual db2 asset directory on same-host HTTP only.

    tar1090's index.html uses databaseFolder = db2 (not db).
    Keep the old db root as a compatibility fallback for custom installs.
    """
    roots=[]
    # Prefer the known /map/ tar1090 proxy over unrelated loopback ports.
    # This matters where Docker exposes the map only on the host LAN IP.
    urls=sorted(_candidate_feeds(),key=lambda u:
        (0 if '/map/' in u else 1,
         0 if ':1099/' in u else 1,
         0 if urlsplit(u).hostname not in ('localhost','127.0.0.1') else 1))
    for url in urls:
        try:
            if not alerts._receiver_url_allowed(url,alerts._local_addresses()):
                continue
            parsed=urlsplit(url)
            path=parsed.path
            if '/data/aircraft.json' in path:
                base=path.split('/data/aircraft.json')[0]
            else:
                base=path.rsplit('/aircraft.json',1)[0]
            origin=parsed.scheme+'://'+parsed.netloc
            # If aircraft.json is at /data/, tar1090 may still live at /map/.
            prefixes=(base,base+'/map') if base in ('','/') else (base,)
            for prefix in prefixes:
                root=origin+prefix.rstrip('/')
                roots.extend((root+'/db2',root+'/db'))
        except (ValueError,TypeError):
            continue
    return tuple(dict.fromkeys(roots))[:12]


def _shard(root,prefix,budget):
    """One static JSON shard; very small time and request budget per viewer."""
    key=(root,prefix)
    now=time.monotonic()
    with _CACHE_LOCK:
        cached=_DB_SHARD_CACHE.get(key)
    if cached and cached[0]>now:return cached[1]
    if budget[0]<=0:return None
    budget[0]-=1
    try:
        # root was generated from a validated LOCAL aircraft.json URL.
        content=_json(root+'/'+prefix+'.js',timeout=0.45)
        if not isinstance(content,dict):content=None
        ttl=3600 if content is not None else 120
    except (OSError,TypeError,ValueError):content=None;ttl=120
    with _CACHE_LOCK:
        if len(_DB_SHARD_CACHE)>1200:_DB_SHARD_CACHE.clear()
        _DB_SHARD_CACHE[key]=(time.monotonic()+ttl,content)
    return content

def _tar_aircraft_db(hexes):
    """Use tar1090's bundled registration/type database where readsb lacks them.

    tar1090 dbloader.js recursively looks up 4.js, 40.js, 408.js, etc.
    Its leaf entries are arrays [registration, aircraft_type, flags, ...].
    """
    found={}
    # HTTP db2 metadata is independent of how readsb JSON was read.
    # Even when Docker supplies aircraft.json, tar1090 serves db2 locally.
    roots=_tar_db_roots()
    if not roots:return found
    budget=[40]  # limit on-demand requests, never bulk-sync a new DB
    for hexcode in hexes:
        for root in roots:
            prefix=hexcode[:1]
            for index in range(1,7):
                shard=_shard(root,prefix,budget)
                if shard is None:break
                remainder=hexcode[index:]
                value=shard.get(remainder)
                if isinstance(value,list):
                    reg=value[0] if len(value)>0 else None
                    typ=value[1] if len(value)>1 else None
                    found[hexcode]={'registration':str(reg or ''),
                                    'aircraft_type':str(typ or '')}
                    break
                next_prefix=hexcode[:index+1]
                if index>=6 or next_prefix not in shard.get('children',[]):
                    break
                prefix=next_prefix
            if hexcode in found:break
    return found

def _batch_tar_routes(items,current):
    """Optional, bounded use of tar1090's existing routeset format.

    Routes aren't ADS-B. The local Aerodrome route cache is preferred; this
    optional online lookup only fills genuinely missing routes, never blocks
    Raw output, and never writes another aircraft database.
    """
    global _TAR_ROUTE_CACHE, _ROUTE_API_RETRY_AFTER
    now=time.monotonic()
    if now<_ROUTE_API_RETRY_AFTER:return {}
    missing=[]
    results={}
    for hexcode,callsign in items:
        if not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',callsign):continue
        cached=_TAR_ROUTE_CACHE.get(callsign)
        if cached and cached[0]>now:
            if cached[1]:results[callsign]=cached[1]
            continue
        plane=current.get(hexcode,{})
        request={'callsign':callsign}
        try:
            if plane.get('lat') is not None and plane.get('lon') is not None:
                request.update(lat=float(plane['lat']),lng=float(plane['lon']))
            elif float(plane.get('messages',plane.get('messages_total',0)))<100:
                continue
        except (TypeError,ValueError):continue
        missing.append(request)
        if len(missing)>=40:break
    if not missing or not _TAR_ROUTE_SLOT.acquire(blocking=False):return results
    try:
        # This is the same schema as tar1090's routeDoLookup, no credentials.
        # If internet is unavailable, simply keep the local cache / blanks.
        payload=json.dumps({'planes':missing}).encode('utf-8')
        request=Request('https://api.adsb.lol/api/0/routeset',data=payload,
                        headers={'Content-Type':'application/json',
                                 'User-Agent':'AirspaceAnalytics-Live/1'},
                        method='POST')
        opener=build_opener(ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=1.8) as stream:
            if int(stream.headers.get('Content-Length','0') or 0)>250_000:raise ValueError('Oversized route response')
            raw=stream.read(250_001)
        if len(raw)>250_000:raise ValueError('Oversized route response')
        response=json.loads(raw)
        if not isinstance(response,list):return results
        _ROUTE_API_RETRY_AFTER=0
        # Treat omitted callsigns as short-term misses, so the site doesn't
        # send the same empty query every eight seconds.
        with _CACHE_LOCK:
            for item in missing:
                _TAR_ROUTE_CACHE[item['callsign']]=(time.monotonic()+900,'')
        for entry in response:
            if not isinstance(entry,dict):continue
            cs=str(entry.get('callsign') or '').strip().upper()
            if cs not in {x['callsign'] for x in missing}:continue
            route=''
            ports=entry.get('_airports')
            if entry.get('plausible') is not False and isinstance(ports,list) and len(ports)>=2:
                first,last=ports[0],ports[-1]
                if isinstance(first,dict) and isinstance(last,dict):
                    route=_route(first.get('iata') or first.get('icao'),
                                 last.get('iata') or last.get('icao'))
            results[cs]=route
            with _CACHE_LOCK:
                if len(_TAR_ROUTE_CACHE)>1000:_TAR_ROUTE_CACHE.clear()
                _TAR_ROUTE_CACHE[cs]=(time.monotonic()+(21600 if route else 900),route)
    except (OSError,ValueError,TypeError):
        # Back off on internet loss; never retry on each eight-second refresh.
        _ROUTE_API_RETRY_AFTER=time.monotonic()+120
    finally:
        _TAR_ROUTE_SLOT.release()
    return results

def _receiver_position(feed=None):
    """Prefer configured antenna coordinates; otherwise reuse tar1090 receiver.json."""
    try:
        config=alerts.snapshot().get('receiver_settings',{})
        lat,lon=config.get('lat'),config.get('lon')
        if lat is not None and lon is not None:
            lat,lon=float(lat),float(lon)
            if -90<=lat<=90 and -180<=lon<=180:return lat,lon
    except (ValueError,TypeError,OSError):pass
    if isinstance(feed,dict):
        try:
            lat,lon=float(feed['lat']),float(feed['lon'])
            if -90<=lat<=90 and -180<=lon<=180:return lat,lon
        except (TypeError,ValueError,KeyError):pass
    receiver=_docker_json('receiver.json')
    try:
        lat,lon=float(receiver['lat']),float(receiver['lon'])
        if -90<=lat<=90 and -180<=lon<=180:return lat,lon
    except (KeyError,TypeError,ValueError):pass
    urls=list(_RECEIVER_URLS)
    if _FEED_LAST_GOOD and _FEED_LAST_GOOD.endswith('/aircraft.json'):
        urls.insert(0,_FEED_LAST_GOOD[:-len('/aircraft.json')]+'/receiver.json')
    for url in dict.fromkeys(urls):
        try:
            if not alerts._receiver_url_allowed(url.replace('receiver.json','aircraft.json'),alerts._local_addresses()):
                continue
            obj=_json(url,timeout=0.4)
            lat,lon=float(obj.get('lat',obj.get('latitude'))),float(obj.get('lon',obj.get('longitude')))
            if -90<=lat<=90 and -180<=lon<=180:return lat,lon
        except (ValueError,TypeError,OSError,AttributeError):continue
    return None,None

def _lookup_from_aerodrome(callsign):
    """Use Aerodrome's *existing* cached route resolver when its DB lacks a hit.

    Only airline-like callsigns, bounded calls/timeouts, never arbitrary URL.
    Aerodrome may maintain its own route_cache; this site never writes it.
    """
    if not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',callsign):
        return ''
    now=time.monotonic()
    with _ROUTE_LOCK:
        known=_ROUTE_CACHE.get(callsign)
        if known and known[0]>now:return known[1]
        if not _ROUTE_SLOT.acquire(blocking=False):return ''
        # Mark the attempt now so overlapping browsers don't repeat it.
        _ROUTE_CACHE[callsign]=(now+1800,'')
        if len(_ROUTE_CACHE)>600:
            _ROUTE_CACHE.clear()
            _ROUTE_CACHE[callsign]=(now+1800,'')
    try:
        url='http://127.0.0.1:8000/api/callsign/'+quote(callsign,safe='')+'/route'
        response=_json(url,timeout=1.5)
        result=_route(response.get('origin_icao'),response.get('dest_icao')) if response.get('found') else ''
        with _ROUTE_LOCK:
            _ROUTE_CACHE[callsign]=(time.monotonic()+(21600 if result else 1800),result)
        return result
    except (ValueError,TypeError,OSError,AttributeError):
        return ''
    finally:
        _ROUTE_SLOT.release()

def _source_name(value):
    """readsb aircraft.json position source, separate from aircraft model ('t')."""
    code = str(value or '').lower().strip()
    if code.startswith('adsb'): return 'ADS-B'
    if code.startswith('mlat'): return 'MLAT'
    if code.startswith('mode_s'): return 'Mode S'
    if code.startswith('tisb'): return 'TIS-B'
    if code.startswith('adsr'): return 'ADS-R'
    if code in ('other', 'unknown'): return ''
    return ''


def details(query):
    items=parse_items(query.get('items',''))
    if not items:
        return {'aircraft':{}}
    hexes=list(dict.fromkeys(hexcode for hexcode,_ in items))
    calls=list(dict.fromkeys(call for _,call in items if call))
    planes={code:{} for code in hexes}
    known_routes={}
    error=None
    try:
        with closing(data.connection()) as db:
            h=','.join('?' for _ in hexes)
            for row in db.execute('SELECT icao,registration,country,aircraft_type '
                                  'FROM seen_aircraft WHERE UPPER(icao) IN ('+h+')',hexes):
                entry=planes.get(str(row['icao']).upper())
                if entry is not None:
                    entry.update(registration=row['registration'] or '',
                                 country=row['country'] or '',aircraft_type=row['aircraft_type'] or '')
            if calls:
                h=','.join('?' for _ in calls)
                for row in db.execute('SELECT callsign,origin_icao,dest_icao '
                                      'FROM route_cache WHERE callsign IN ('+h+')',calls):
                    candidate=_route(row['origin_icao'],row['dest_icao'])
                    if candidate:
                        known_routes[str(row['callsign']).upper()]=candidate
    except (OSError,ValueError,TypeError,Exception) as exc:
        # Optional enrichment must never make the real terminal fail.
        error='Local aircraft metadata unavailable'

    feed=_readsb()
    current={str(a.get('hex','')).upper().lstrip('~'):a for a in feed.get('aircraft',[])
             if isinstance(a,dict)}
    # tar1090 draws extra registrations/types from its local static db when
    # they aren't embedded in aircraft.json, so apply the same fallback here.
    missing_from_live=[code for code in hexes if
                       not current.get(code,{}).get('r') or not current.get(code,{}).get('t')]
    tar_db=_tar_aircraft_db(missing_from_live) if missing_from_live else {}
    lat,lon=_receiver_position(feed)
    for hexcode,callsign in items:
        plane=planes[hexcode]
        live=current.get(hexcode,{})
        db_entry=tar_db.get(hexcode,{})
        if db_entry.get('registration') and not plane.get('registration'):
            plane['registration']=db_entry['registration']
        if db_entry.get('aircraft_type') and not plane.get('aircraft_type'):
            plane['aircraft_type']=db_entry['aircraft_type']
        if live.get('r'):plane['registration']=str(live['r'])
        if live.get('t'):plane['aircraft_type']=str(live['t'])
        # Source is supplied by readsb, not by the flight-route resolver.
        source=_source_name(live.get('type'))
        if source:plane['source']=source
        if lat is not None and lon is not None:
            try:
                plat,plon=live['lat'],live['lon']
                plane['distance_km']=_km(lat,lon,float(plat),float(plon))
            except (KeyError,ValueError,TypeError):pass
        if callsign:
            plane['route']=known_routes.get(callsign,'')
    # Batch lookup the same route source tar1090 uses, only for missing
    # aircraft routes; Aerodrome cached values still take precedence.
    unresolved=[(hexcode,cs) for hexcode,cs in items if cs and not planes[hexcode].get('route')]
    tar_routes=_batch_tar_routes(unresolved,current)
    for hexcode,callsign in unresolved:
        if tar_routes.get(callsign):planes[hexcode]['route']=tar_routes[callsign]

    # Resolve at most two new callsigns per *slow* metadata request.
    # Flight routes are not ADS-B transmissions and may be unavailable.
    count=0
    for hexcode,callsign in items:
        if count>=2:break
        plane=planes[hexcode]
        if callsign and not plane.get('route') and re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',callsign):
            plane['route']=_lookup_from_aerodrome(callsign)
            count+=1
    result={'aircraft':planes,
            'metadata_status':{
                'receiver_aircraft':len(current),
                'matched_receiver_aircraft':sum(1 for code in hexes if code in current),
                'tar1090_db_matches':len(tar_db),
                'receiver_location_available':lat is not None and lon is not None}}
    if error:result['warning']=error
    return result
