"""Background, read-only registration status cache for the personal flight log."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from . import alerts, flights_log, flights_live

PERIOD = 5
SHEET_PERIOD = 6 * 3600  # SheetDB free quota is only 500 calls/month
LIVE_TTL = 120
AIRPORT_TTL = 7 * 24 * 3600
MAX_TRACKED = 400
PATH = alerts.STATE_DIR / 'flights-live.json'
_lock = threading.Lock()
_started = False
_entries = {}
_cursor = 0


def _valid(reg):
    return bool(re.fullmatch(r'[A-Z0-9-]{2,16}', reg))


def _airport(item, now):
    code = str(item.get('at_airport') or '').upper()
    stamp = item.get('last_landed_at') or item.get('_checked_at', 0)
    if re.fullmatch(r'[A-Z]{3}', code) and isinstance(stamp, (int, float)) and 0 <= now-stamp <= AIRPORT_TTL:
        return code, stamp
    return '', None


def _merge(old, item, now):
    old=old or {}
    # Local sightings are independent of the external network and must never
    # disappear when a database query or remote provider temporarily fails.
    item=dict(item)
    if (old.get('local_last_seen_at') or 0) > (item.get('local_last_seen_at') or 0):
        item.update(local_last_seen_at=old['local_last_seen_at'],local_hex=old.get('local_hex',''))
    old_stamp=old.get('last_observed_at') or old.get('_checked_at',0)
    new_stamp=item.get('last_observed_at') or item.get('last_landed_at') or (now if item.get('hex') or str(item.get('status','')).startswith('Flying') else 0)
    # A negative response from a different network is not evidence of a change.
    # Preserve recent airborne data, without resetting the observation clock.
    if str(old.get('status','')).startswith('Flying') and 0<=now-old_stamp<=LIVE_TTL:
        if not new_stamp or new_stamp<old_stamp:
            result=dict(old)
            if item.get('route') and item.get('callsign') and item.get('callsign')==old.get('callsign') and item.get('hex')==old.get('hex') and new_stamp and now-new_stamp<=LIVE_TTL and str(item.get('status','')).startswith('Flying'):
                if not old.get('route') or (old.get('route_confidence')=='usual' and item.get('route_confidence')!='usual'):
                    result.update(route=item['route'],route_confidence=item.get('route_confidence',''),
                                  _route_memory={'callsign':item['callsign'],'route':item['route'],'confidence':item.get('route_confidence',''),'at':now})
            for k in ('local_last_seen_at','local_hex'):
                if item.get(k):result[k]=item[k]
            return result
    # Retain a more recent observed landing instead of replacing it with an
    # older nightly-history record. This also preserves the original timestamp.
    old_code,old_airport_stamp=_airport(old,now)
    new_airport_stamp=item.get('last_landed_at') or 0
    if old_code and new_airport_stamp and new_airport_stamp<old_airport_stamp and not item.get('hex'):
        result=dict(old)
        for k in ('local_last_seen_at','local_hex'):
            if item.get(k):result[k]=item[k]
        return result
    entry = dict(item, _checked_at=item.get('last_observed_at') or item.get('last_landed_at') or now)
    if not item.get('last_observed_at') and item.get('status')=='N/A' and old.get('status')=='N/A':
        entry['_checked_at']=old.get('_checked_at',now)
    # Keep the route across rotating position sources and short reception gaps.
    # A changed callsign or observed ground position invalidates this memory.
    memory=(old or {}).get('_route_memory')
    flying=str(entry.get('status','')).startswith('Flying')
    call=entry.get('callsign')
    if memory and (now-memory.get('at',0)>1800 or (call and call!=memory.get('callsign'))):
        memory=None
    if flying and call:
        if entry.get('route'):
            memory={'callsign':call,'route':entry['route'],
                    'confidence':entry.get('route_confidence','cached'),'at':now}
        elif memory:
            entry.update(route=memory['route'],route_confidence=memory['confidence'])
    elif entry.get('at_airport') or entry.get('status')=='Ground':
        memory=None
    if memory:
        entry['_route_memory']=memory
    code, stamp = _airport(entry, now)
    last_airborne = (old or {}).get('_last_airborne', 0)
    if str(entry.get('status', '')).startswith('Flying'):
        last_airborne = max(last_airborne,entry.get('last_observed_at') or now)
    entry['_last_airborne'] = last_airborne
    if code and stamp < last_airborne:
        entry.update(status='N/A', at_airport='', last_landed_at=None)
        code = ''
    if code:
        entry['_airport_evidence'] = stamp
    elif (entry.get('status') == 'N/A' and not entry.get('hex') or entry.get('status')=='Ground') and old:
        # Missing ADS-B is not proof of arrival. Retain only an actually
        # observed recent airport; never predict landing from elapsed time.
        code, stamp = _airport(old, now)
        stamp = old.get('_airport_evidence', stamp)
        if code and stamp and stamp>=last_airborne and 0 <= now-stamp <= AIRPORT_TTL:
            entry.update(at_airport=code, status='Last landed '+code,
                         last_landed_at=stamp, _airport_evidence=stamp,
                         source=old.get('source','Observed airport'),_checked_at=stamp)
    return entry


def _public(item, now):
    if not item:
        return {'status':'N/A'}
    entry = dict(item)
    checked = entry.pop('_checked_at', 0)
    evidence = entry.pop('_airport_evidence', None)
    entry.pop('_last_airborne', None)
    entry.pop('_route_memory', None)
    if now-(entry.get('last_observed_at') or checked) > LIVE_TTL:
        code, stamp = _airport(item, now)
        if code and evidence and 0 <= now-evidence <= AIRPORT_TTL:
            entry.update(status='Last landed '+code, at_airport=code,
                         last_landed_at=evidence, route='', route_confidence='', hex='', callsign='')
        else:
            entry.update(status='N/A', at_airport='', route='', route_confidence='', hex='', callsign='')
    elif entry.get('last_landed_at') and not _airport(item, now)[0]:
        entry.update(status='N/A', at_airport='', last_landed_at=None)
    return entry


def _load():
    try:
        if PATH.stat().st_size > 2_000_000:
            return
        raw = json.loads(PATH.read_text())
        if isinstance(raw, dict):
            _entries.update({reg: value for reg, value in list(raw.items())[:MAX_TRACKED]
                             if _valid(reg) and isinstance(value, dict)})
    except (OSError, ValueError, TypeError):
        pass


def _save(entries):
    try:
        PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temp = PATH.with_suffix('.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(entries, handle, separators=(',', ':'))
        os.replace(temp, PATH)
    except OSError:
        pass


def _registrations(rows):
    return list(dict.fromkeys(reg for row in rows
        if (reg := flights_live.current_registration(row.get('registration')).upper()) != 'NO REG'
        and _valid(reg)))[:MAX_TRACKED]


def _refresh(regs):
    global _cursor
    if not regs:
        return
    # Rotate chunks rather than hammering multiple global queries per cycle.
    chunks = [regs[i:i+flights_live.MAX_REGS] for i in range(0, len(regs), flights_live.MAX_REGS)]
    batch = chunks[_cursor % len(chunks)]
    _cursor += 1
    snapshot = flights_live.snapshot(','.join(batch),background=True)
    now = time.time()
    with _lock:
        previous=dict(_entries)
        for reg, item in snapshot.get('aircraft', {}).items():
            _entries[reg] = _merge(_entries.get(reg), item, now)
        for reg in list(_entries):
            if reg not in regs:
                del _entries[reg]
        saved = dict(_entries)
    if saved!=previous:_save(saved)


def _run():
    rows = [{'registration': reg} for reg in _entries]
    last_sheet = 0
    while True:
        try:
            if not last_sheet or time.monotonic()-last_sheet >= SHEET_PERIOD:
                last_sheet = time.monotonic()
                try:
                    rows = flights_log.read_cached().get('flights', [])
                except (ValueError, OSError):
                    pass  # Continue using known registrations if SheetDB is down.
            # Reuse a fresher SheetDB response from an ordinary page load/edit.
            current_rows=flights_log._CACHE.get('rows')
            if current_rows is not None:
                rows=list(current_rows)
            _refresh(_registrations(rows))
        except Exception as error:
            print('Flights background refresh failed: '+type(error).__name__, flush=True)
        time.sleep(PERIOD)


def start():
    global _started
    with _lock:
        if _started:
            return
        _load()
        _started = True
    threading.Thread(target=_run, daemon=True, name='airspace-flights-cache').start()


def read(value=''):
    # Keep deterministic standalone HTTP tests and non-production callers.
    if not _started:
        return flights_live.snapshot(value)
    regs = list(dict.fromkeys(str(value).upper().split(','))) if value else []
    if len(regs)>flights_live.MAX_REGS or len(value)>2000 or any(not _valid(reg) for reg in regs):
        raise ValueError('Invalid registrations')
    now = time.time()
    with _lock:
        return {'aircraft':{reg:_public(_entries.get(reg), now) for reg in regs},
                'checked_at':int(now),'sources':flights_live.source_health()}
