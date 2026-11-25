"""Polite, transient callsign-route enrichment for the Flights tab.

Routes are not ADS-B transmissions. The ADSB.im/tar1090 routeset APIs return
a candidate itinerary and a position-aware plausibility flag. Never write
the lookup to Aerodrome, SheetDB, or the local flight log. All network calls
run in a daemon thread, outside the live aircraft and Google Sheets requests.
"""
from __future__ import annotations

import json
import math
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

SOURCES = ('https://adsb.im/api/0/routeset', 'https://api.adsb.lol/api/0/routeset')
URL = SOURCES[0]
MAX_REQUEST_BYTES = 100_000
MAX_RESPONSE_BYTES = 450_000
MAX_PER_BATCH = 30
MIN_POLL_SECONDS = 180
GOOD_TTL_SECONDS = 30 * 60
MISS_TTL_SECONDS = 5 * 60

_lock=threading.Lock()
_cache={}            # callsign -> (monotonic expiry, IATA route or empty)
_last_request=0.0     # global guard, including failed attempts
_busy=False
_health={'last_check':None,'source':'','matched':0,'errors':[],'last_error':''}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


def _open(request,timeout=4):
    return build_opener(ProxyHandler({}),_NoRedirect()).open(request,timeout=timeout)


def _code(value):
    value=str(value or '').strip().upper()
    return value if re.fullmatch(r'[A-Z]{3}',value) else ''


def parse_routes(payload, requested, unpositioned=()):
    """Return unambiguous 2-airport routes for corresponding callsigns.

    Require plausibility for position-based requests. ADSB.im requests without
    a position may return a usual itinerary, labelled as such by the cache.
    adsb.lol may supply a list of lists (one per plane) or a flat list.
    """
    wanted=set(requested)
    answer={}
    conflicts=set()
    if not isinstance(payload,list):return answer
    records=[]
    for item in payload:
        if isinstance(item,list):records.extend(item)
        elif isinstance(item,dict):records.append(item)
    for entry in records[:100]:
        if not isinstance(entry,dict):continue
        callsign=str(entry.get('callsign') or '').strip().upper()
        if callsign not in wanted or (callsign not in unpositioned and entry.get('plausible') not in (True,1)):
            continue
        path=str(entry.get('_airport_codes_iata') or '').upper()
        parts=path.split('-')
        if len(parts)!=2:
            airports=entry.get('_airports')
            if not isinstance(airports,list) or len(airports)!=2:continue
            parts=[_code(airport.get('iata')) if isinstance(airport,dict) else ''
                   for airport in airports]
        if len(parts)!=2:continue
        orig,dest=(_code(v) for v in parts)
        if orig and dest and orig!=dest:
            value=orig+'–'+dest
            if callsign in answer and answer[callsign]!=value:conflicts.add(callsign)
            answer[callsign]=value
    return {call:route for call,route in answer.items() if call not in conflicts}


def _clean_planes(planes):
    clean=[]
    seen=set()
    for item in planes:
        if not isinstance(item,dict):continue
        call=str(item.get('callsign') or '').strip().upper()
        if not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',call) or call in seen:
            continue
        lat,lon=item.get('lat'),item.get('lon')
        record={'callsign':call}
        if all(isinstance(x,(float,int)) and math.isfinite(x) for x in (lat,lon)) and -90<=lat<=90 and -180<=lon<=180:
            record.update(lat=round(lat,5),lng=round(lon,5))
        elif lat is not None or lon is not None:
            continue
        hexcode=str(item.get('icao') or '').lower()
        if re.fullmatch(r'[0-9a-f]{6}',hexcode):record['icao']=hexcode
        if 'lat' not in record and 'icao' not in record:continue
        clean.append(record)
        seen.add(call)
        if len(clean)>=MAX_PER_BATCH:break
    return clean


def _request_source(clean,url,opener):
    if url not in SOURCES:raise ValueError('Untrusted route API')
    body=json.dumps({'planes':clean},separators=(',',':')).encode()
    if len(body)>MAX_REQUEST_BYTES:raise ValueError('Route batch too large')
    request=Request(url,data=body,method='POST',headers={
        'Content-Type':'application/json','Accept':'application/json',
        'User-Agent':'AirspaceAnalytics-Flights/2'})
    with opener(request,timeout=5) as response:
        if int(response.headers.get('Content-Length','0') or 0)>MAX_RESPONSE_BYTES:
            raise ValueError('Route lookup response too large')
        blob=response.read(MAX_RESPONSE_BYTES+1)
    if len(blob)>MAX_RESPONSE_BYTES:raise ValueError('Route lookup response too large')
    payload=json.loads(blob)
    if not isinstance(payload,list):raise ValueError('Invalid routeset response shape')
    return parse_routes(payload,[p['callsign'] for p in clean],
                        {p['callsign'] for p in clean if 'lat' not in p})


def fetch_routes(planes, opener=None):
    """Try ADSB.im (tar1090 default), then adsb.lol for any missing routes.

    Global requests are throttled by cached_routes; neither endpoint receives
    a key or flight-log personal data.
    """
    if opener is None:opener=_open
    clean=_clean_planes(planes)
    if not clean:return {}
    errors=[]
    combined={}
    used=''
    for url in SOURCES:
        remaining=[p for p in clean if p['callsign'] not in combined and (url==SOURCES[0] or 'lat' in p)]
        if not remaining:continue
        try:
            matched=_request_source(remaining,url,opener)
            if matched:used=url
            combined.update(matched)
        except (HTTPError,URLError,OSError,TimeoutError,ValueError,TypeError) as exc:
            if isinstance(exc,HTTPError):
                errors.append(url.split('/')[2]+': HTTP '+str(exc.code))
            else:
                errors.append(url.split('/')[2]+': unavailable or invalid')
    with _lock:
        _health.update(last_check=time.time(),source=used,matched=len(combined),
                       errors=errors,last_error='; '.join(errors))
    return combined


def health():
    with _lock:return dict(_health)


def cached_routes(planes):
    """Return cached routes and optionally schedule a polite refresh.

    Flight-tab requests are answered immediately; no outgoing HTTP waits.
    """
    global _busy,_last_request
    now=time.monotonic()
    pending=[]
    found={}
    for item in planes:
        if not isinstance(item,dict):continue
        call=str(item.get('callsign') or '').strip().upper()
        if not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',call):continue
        with _lock:
            saved=_cache.get(call)
        if saved and saved[0]>now:
            if saved[1]:found[call]=saved[1]
            if len(saved)>2 and saved[2]=='usual' and item.get('lat') is not None and item.get('lon') is not None and _clean_planes([item]):pending.append(item)
        elif _clean_planes([item]):
            pending.append(item)
    with _lock:
        if pending and not _busy and (not _last_request or now-_last_request>=MIN_POLL_SECONDS):
            _busy=True
            _last_request=now
            batch=pending[:MAX_PER_BATCH]
            threading.Thread(target=_refresh,args=(batch,),daemon=True,
                             name='airspace-flight-routes').start()
    return found


def confidence(call):
    with _lock:
        saved=_cache.get(call)
        return saved[2] if saved and len(saved)>2 else 'plausible'


def _refresh(batch):
    global _busy
    try:
        routes=fetch_routes(batch)
        now=time.monotonic()
        with _lock:
            for aircraft in batch:
                call=str(aircraft.get('callsign') or '').strip().upper()
                route=routes.get(call,'')
                previous=_cache.get(call)
                if not route and previous and previous[0]>now and previous[1]:continue
                _cache[call]=(now+(GOOD_TTL_SECONDS if route else MISS_TTL_SECONDS),route,
                              'plausible' if aircraft.get('lat') is not None and aircraft.get('lon') is not None else 'usual')
    finally:
        with _lock:_busy=False
