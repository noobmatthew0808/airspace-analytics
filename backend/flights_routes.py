"""Polite, transient callsign-route enrichment for the Flights tab.

Routes are not ADS-B transmissions. The public adsb.lol routeset API returns
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

URL = 'https://api.adsb.lol/api/0/routeset'
MAX_REQUEST_BYTES = 100_000
MAX_RESPONSE_BYTES = 450_000
MAX_PER_BATCH = 30
MIN_POLL_SECONDS = 180
GOOD_TTL_SECONDS = 30 * 60
MISS_TTL_SECONDS = 10 * 60

_lock=threading.Lock()
_cache={}            # callsign -> (monotonic expiry, IATA route or empty)
_last_request=0.0     # global guard, including failed attempts
_busy=False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        return None


def _open(request,timeout=4):
    return build_opener(ProxyHandler({}),_NoRedirect()).open(request,timeout=timeout)


def _code(value):
    value=str(value or '').strip().upper()
    return value if re.fullmatch(r'[A-Z]{3}',value) else ''


def parse_routes(payload, requested):
    """Return only plausible 2-airport routes for the corresponding callsigns.

    Unknown, multi-stop, ambiguous or implausible results remain blank.
    adsb.lol may supply a list of lists (one per plane) or a flat list.
    """
    wanted=set(requested)
    answer={}
    if not isinstance(payload,list):return answer
    records=[]
    for item in payload:
        if isinstance(item,list):records.extend(item)
        elif isinstance(item,dict):records.append(item)
    for entry in records[:100]:
        if not isinstance(entry,dict):continue
        callsign=str(entry.get('callsign') or '').strip().upper()
        if callsign not in wanted or entry.get('plausible') not in (True,1):
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
            answer[callsign]=orig+'–'+dest
    return answer


def fetch_routes(planes, opener=None):
    """One bounded batched request; no keys, external redirects or proxies."""
    if opener is None:opener=_open
    clean=[]
    for item in planes:
        if not isinstance(item,dict):continue
        call=str(item.get('callsign') or '').strip().upper()
        if not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',call):
            continue
        lat,lon=item.get('lat'),item.get('lon')
        if not all(isinstance(x,(float,int)) and math.isfinite(x) for x in (lat,lon)):
            continue
        if not (-90<=lat<=90 and -180<=lon<=180):continue
        clean.append({'callsign':call,'lat':round(lat,5),'lng':round(lon,5)})
        if len(clean)>=MAX_PER_BATCH:break
    if not clean:return {}
    body=json.dumps({'planes':clean},separators=(',',':')).encode()
    if len(body)>MAX_REQUEST_BYTES:raise ValueError('Route batch too large')
    request=Request(URL,data=body,method='POST',headers={
        'Content-Type':'application/json','Accept':'application/json',
        'User-Agent':'AirspaceAnalytics-Flights/1'})
    try:
        with opener(request,timeout=4) as response:
            if int(response.headers.get('Content-Length','0') or 0)>MAX_RESPONSE_BYTES:
                raise ValueError('Route lookup response too large')
            blob=response.read(MAX_RESPONSE_BYTES+1)
        if len(blob)>MAX_RESPONSE_BYTES:raise ValueError('Route lookup response too large')
        return parse_routes(json.loads(blob),[p['callsign'] for p in clean])
    except (HTTPError,URLError,OSError,TimeoutError,ValueError,TypeError) as error:
        # Optional lookup: error cannot break Sheets, Alerts or flight status.
        return {}


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
        elif item.get('lat') is not None and item.get('lon') is not None:
            pending.append(item)
    with _lock:
        if pending and not _busy and now-_last_request>=MIN_POLL_SECONDS:
            _busy=True
            _last_request=now
            batch=pending[:MAX_PER_BATCH]
            threading.Thread(target=_refresh,args=(batch,),daemon=True,
                             name='airspace-flight-routes').start()
    return found


def _refresh(batch):
    global _busy
    try:
        routes=fetch_routes(batch)
        now=time.monotonic()
        with _lock:
            for aircraft in batch:
                call=str(aircraft.get('callsign') or '').strip().upper()
                route=routes.get(call,'')
                _cache[call]=(now+(GOOD_TTL_SECONDS if route else MISS_TTL_SECONDS),route)
    finally:
        with _lock:_busy=False
