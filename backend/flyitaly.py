"""FlyItalyADSB optional live-data cache for Alerts (no aircraft history stored).

Only the Alerts background worker calls this module. Secrets are held in the
existing private Alerts config DB and sent solely as HTTPS X-Api-Key headers.
Never put credentials in URLs, repository files, logs or API responses.
"""
from __future__ import annotations

import json
import math
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = 'https://api.flyitalyadsb.com'
MAX_BYTES = 2_000_000
MAX_AGE = 36
_lock = threading.Lock()
_state = {
    'aircraft': [], 'last_success': None, 'last_error': None,
    'source_now': None, 'plan': None, 'monthly_used': None,
    'monthly_quota': None, 'last_count': 0,
}


def clear():
    """Discard all cached external aircraft immediately (e.g. after key change)."""
    with _lock:
        _state.update(aircraft=[], last_success=None, last_error=None,
                      source_now=None, plan=None, monthly_used=None,
                      monthly_quota=None, last_count=0)


def status(key_set=False):
    with _lock:
        return {
            'key_set': bool(key_set),
            'connected': bool(_state['last_success'] and
                              time.time() - _state['last_success'] < MAX_AGE),
            'last_success': _state['last_success'],
            'error': _state['last_error'],
            'aircraft': _state['last_count'],
            'plan': _state['plan'],
            'monthly_used': _state['monthly_used'],
            'monthly_quota': _state['monthly_quota'],
        }


def _safe_age(value, maximum):
    return isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= maximum


def fetch(key, lat, lon, radius_km, opener=urlopen):
    """Fetch geographic aircraft by radius in **kilometres**.

    This runs in a SEPARATE background thread, never in the three-second local
    receiver loop. Bad JSON, stale responses or an HTTP error cannot create
    network-only alerts; the last cache expires after MAX_AGE seconds.
    """
    if not isinstance(key, str) or not key.strip():
        raise ValueError('FlyItalyADSB key is missing')
    if not all(isinstance(x, (float, int)) and math.isfinite(x)
               for x in (lat, lon, radius_km)):
        raise ValueError('Antenna coordinates are needed for network coverage')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0.1 <= radius_km <= 500):
        raise ValueError('Invalid FlyItalyADSB search coordinates or radius')
    url = f'{BASE}/v2/lat/{lat:.7f}/lon/{lon:.7f}/dist/{radius_km:.1f}'
    req = Request(url, headers={
        'X-Api-Key': key,
        'User-Agent': 'AirspaceAnalytics-Alerts/1',
        'Accept': 'application/json',
    })
    try:
        with opener(req, timeout=5) as response:
            if int(response.headers.get('Content-Length', '0') or 0) > MAX_BYTES:
                raise ValueError('FlyItalyADSB response too large')
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError('FlyItalyADSB response too large')
            meta = {k: response.headers.get(k) for k in (
                'X-FIA-Plan', 'X-FIA-Used-Month', 'X-FIA-Quota-Month')}
        obj = json.loads(raw)
        if not isinstance(obj, dict) or not isinstance(obj.get('ac'), list):
            raise ValueError('Invalid FlyItalyADSB aircraft list')
        source_now = obj.get('now')
        current = time.time()
        if not isinstance(source_now, (int,float)) or not math.isfinite(source_now):
            raise ValueError('Missing network snapshot timestamp')
        if source_now < current-30 or source_now > current+10:
            raise ValueError('Stale FlyItalyADSB aircraft snapshot')
        elapsed = max(0., current - source_now)
        aircraft = []
        for src in obj['ac'][:3000]:
            if not isinstance(src, dict):
                continue
            p = dict(src)
            for field in ('seen', 'seen_pos'):
                if _safe_age(p.get(field), 60):
                    p[field] = p[field] + elapsed
                else:
                    p.pop(field, None)
            aircraft.append(p)
        with _lock:
            _state.update(
                aircraft=aircraft, last_success=current, last_error=None,
                source_now=source_now, last_count=len(aircraft),
                plan=meta['X-FIA-Plan'],
                monthly_used=meta['X-FIA-Used-Month'],
                monthly_quota=meta['X-FIA-Quota-Month'],
            )
        return status(key_set=True)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        if isinstance(exc, HTTPError):
            msg = f'FlyItalyADSB HTTP {exc.code}'
        elif isinstance(exc, URLError):
            msg = 'FlyItalyADSB connection failed'
        else:
            msg = str(exc)[:120]
        with _lock:
            _state['last_error'] = msg
        raise ValueError(msg) from None


def aircraft():
    """Return fresh-only copies, ageing source data in the cache between polls."""
    with _lock:
        saved_at = _state['last_success']
        if saved_at is None or time.time()-saved_at >= MAX_AGE:
            return []
        elapsed = max(0., time.time()-saved_at)
        saved = [dict(p) for p in _state['aircraft']]
    for p in saved:
        for field in ('seen', 'seen_pos'):
            if _safe_age(p.get(field), 80):
                p[field] += elapsed
            else:
                p.pop(field, None)
    return saved
