"""Shared HTTP backoff across alerts, flight history, tests and live lookups.
Only independent providers can proceed during a provider's cooldown.
"""
from __future__ import annotations
from email.utils import parsedate_to_datetime
import threading
import time
from urllib.error import HTTPError

_lock=threading.Lock()
_next={}
MIN_GAP={'FlyItalyADSB':2,'adsb.lol':2,'adsb.fi':2,'AvioADSB':1,
         'ADSBiq':20,'airplanes.live':2,'OpenSky Network':2,'PlaneTrack':2}
DEFAULT_BACKOFF={'AvioADSB':86400,'ADSBiq':900,'FlyItalyADSB':900,
                 'adsb.lol':900,'adsb.fi':120,'airplanes.live':86400,'OpenSky Network':900,'PlaneTrack':3600}

def remaining(provider):
    with _lock:return max(0,_next.get(provider,0)-time.monotonic())

def _retry(error,provider):
    headers=error.headers or {}
    value=headers.get('X-Rate-Limit-Retry-After-Seconds') or headers.get('Retry-After')
    try:return max(1,float(value))
    except (TypeError,ValueError):
        try:return max(1,parsedate_to_datetime(value).timestamp()-time.time())
        except (TypeError,ValueError,OverflowError,AttributeError):
            return DEFAULT_BACKOFF[provider]

def open_request(provider,opener,request,timeout=8):
    with _lock:
        now=time.monotonic()
        wait=_next.get(provider,0)-now
        if wait>0:raise ValueError(provider+' rate limited; retry '+str(int(wait)+1))
        _next[provider]=now+MIN_GAP[provider]
    try:return opener(request,timeout=timeout)
    except HTTPError as error:
        if error.code==429:
            with _lock:
                _next[provider]=max(_next[provider],time.monotonic()+_retry(error,provider))
        raise
