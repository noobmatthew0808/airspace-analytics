"""Low-volume flight-history cache for reliable *last landed* airports.

FlyItalyADSB's feeder key permits yesterday and earlier observed flight legs.
Only confirmed nearby-ground/low arrivals are labelled last landed. Today
may be available on Fleet, but no user subscription is assumed. Never label
a historical arrival as an aircraft currently parked at that airport.
"""
from __future__ import annotations
from . import api_budget

from datetime import datetime,timezone
import json
import math
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request,build_opener,HTTPRedirectHandler,ProxyHandler

URL='https://api.flyitalyadsb.com/v2/flights/reg/'
MAX_BYTES=600_000
BATCH=4
MIN_INTERVAL=35
MAX_CACHED=400
GOOD_TTL=6*3600
MISS_TTL=20*60
_lock=threading.Lock()
_cache={}          # normalized reg -> (deadline monotonic, result|None)
_last_batch=0.0
_busy=False
_health={'last_success':None,'last_error':'','queried':0,'found':0}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,url):
        return None


def _open(request,timeout=5):
    return build_opener(ProxyHandler({}),_NoRedirect()).open(request,timeout=timeout)


def _reg(text):
    value=str(text or '').strip().upper()
    return value if re.fullmatch(r'[A-Z0-9-]{2,16}',value) else ''


def _time(value):
    if isinstance(value,(int,float)) and math.isfinite(value):
        return float(value)/1000 if value>1e11 else float(value)
    if isinstance(value,str):
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
        except ValueError:return None
    return None


def parse_last_landing(payload,now=None):
    """Extract the most recent *observed* airport arrival, not a prediction."""
    if now is None:now=time.time()
    if not isinstance(payload,dict):return None
    rows=payload.get('flights')
    if not isinstance(rows,list):rows=[]
    today=payload.get('today')
    if isinstance(today,dict) and today.get('available') is True:
        rows=[*rows,*(today.get('flights') if isinstance(today.get('flights'),list) else [])]
    newest=None
    for flight in rows:
        if not isinstance(flight,dict):continue
        arrival=flight.get('to')
        if not isinstance(arrival,dict):continue
        evidence=str(arrival.get('seen') or '').lower()
        if evidence not in ('ground','low'):
            continue
        code=str(arrival.get('iata') or arrival.get('airport_iata') or arrival.get('airport') or '').strip().upper()
        if not re.fullmatch(r'[A-Z]{3,4}',code):continue
        stamp=_time(arrival.get('time'))
        if stamp is None or stamp<1_750_000_000 or stamp>now+120 or now-stamp>31*86400:
            continue
        if newest is None or stamp>newest['time']:
            newest={'airport':code,'time':int(stamp),'evidence':evidence,
                    'source':'FlyItalyADSB observed flights'}
    return newest


def fetch_one(reg,key,opener=None):
    reg=_reg(reg)
    if not reg or not key:raise ValueError('A saved FlyItalyADSB key and registration are required')
    if opener is None:opener=lambda req,timeout:api_budget.open_request('FlyItalyADSB',_open,req,timeout)
    request=Request(URL+reg,headers={'Accept':'application/json',
            'X-Api-Key':key,'User-Agent':'AirspaceAnalytics-Flights/3'})
    try:
        with opener(request,timeout=5) as response:
            if int(response.headers.get('Content-Length','0') or 0)>MAX_BYTES:
                raise ValueError('History response too large')
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('History response too large')
        payload=json.loads(raw)
        if not isinstance(payload,dict):raise ValueError('Unexpected history response')
        return parse_last_landing(payload)
    except HTTPError as error:
        if error.code==404:return None
        if error.code==429:raise ValueError('FlyItalyADSB rate limited') from None
        raise ValueError('FlyItalyADSB history HTTP '+str(error.code)) from None
    except (URLError,OSError,TimeoutError,json.JSONDecodeError):
        raise ValueError('FlyItalyADSB flight history temporarily unavailable') from None


def cached(reg):
    reg=_reg(reg)
    if not reg:return None
    with _lock:
        saved=_cache.get(reg)
        if saved and saved[0]>time.monotonic():
            return dict(saved[1]) if saved[1] else None
    return None


def schedule(registrations,key):
    """Queue at most 4 historical lookups per 35s, never blocking a page."""
    global _last_batch,_busy
    if not key:return
    now=time.monotonic()
    pending=[]
    with _lock:
        for item in registrations:
            reg=_reg(item)
            if not reg or (reg in _cache and _cache[reg][0]>now) or reg in pending:
                continue
            pending.append(reg)
            if len(pending)>=BATCH:break
        if not pending or _busy or (_last_batch and now-_last_batch<MIN_INTERVAL):
            return
        _busy=True
        _last_batch=now
        threading.Thread(target=_refresh,args=(pending,key),daemon=True,
                         name='airspace-flights-history').start()


def _refresh(registrations,key):
    global _busy
    try:
        for reg in registrations:
            try:
                result=fetch_one(reg,key)
                with _lock:
                    _cache[reg]=(time.monotonic()+(GOOD_TTL if result else MISS_TTL),result)
                    _health['queried']+=1
                    if result:
                        _health.update(last_success=time.time(),found=_health['found']+1,
                                       last_error='')
            except ValueError as error:
                with _lock:
                    _health['last_error']=str(error)[:90]
                    _cache[reg]=(time.monotonic()+MISS_TTL,None)
                if 'rate limit' in str(error):
                    with _lock:
                        _cache[reg]=(time.monotonic()+3600,None)
                    break
            time.sleep(0.6)
        with _lock:
            if len(_cache)>MAX_CACHED:
                for reg in list(_cache)[:len(_cache)-MAX_CACHED]:
                    del _cache[reg]
    finally:
        with _lock:_busy=False


def health():
    with _lock:return {**_health,'cached_registrations':len(_cache),'in_progress':_busy}
