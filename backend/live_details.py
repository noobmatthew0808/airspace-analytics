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
import json
import re
import time

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

def _readsb():
    for url in _LIVE_URLS:
        try:
            obj=_json(url)
            if isinstance(obj,dict) and isinstance(obj.get('aircraft'),list):
                return obj
        except (ValueError,OSError,KeyError,TypeError):
            continue
    return {}

def _receiver_position():
    try:
        config=alerts.snapshot().get('receiver_settings',{})
        lat,lon=config.get('lat'),config.get('lon')
        if lat is not None and lon is not None:
            lat,lon=float(lat),float(lon)
            if -90<=lat<=90 and -180<=lon<=180:return lat,lon
    except (ValueError,TypeError,OSError):
        pass
    for url in _RECEIVER_URLS:
        try:
            obj=_json(url,timeout=0.4)
            lat,lon=float(obj.get('lat',obj.get('latitude'))),float(obj.get('lon',obj.get('longitude')))
            if -90<=lat<=90 and -180<=lon<=180:return lat,lon
        except (ValueError,TypeError,OSError,AttributeError):
            continue
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
    lat,lon=_receiver_position()
    for hexcode,callsign in items:
        plane=planes[hexcode]
        live=current.get(hexcode,{})
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
    # Resolve at most two new callsigns per *slow* metadata request.
    # Flight routes are not ADS-B transmissions and may be unavailable.
    count=0
    for hexcode,callsign in items:
        if count>=2:break
        plane=planes[hexcode]
        if callsign and not plane.get('route') and re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',callsign):
            plane['route']=_lookup_from_aerodrome(callsign)
            count+=1
    result={'aircraft':planes}
    if error:result['warning']=error
    return result
