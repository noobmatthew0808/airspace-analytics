"""Background, read-only registration status cache for the personal flight log."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from . import alerts, flights_log, flights_live

PERIOD = 35
SHEET_PERIOD = 6 * 3600  # SheetDB free quota is only 500 calls/month
LIVE_TTL = 45
AIRPORT_TTL = 24 * 3600
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
    entry = dict(item, _checked_at=now)
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
        last_airborne = now
    entry['_last_airborne'] = last_airborne
    if code and stamp < last_airborne:
        entry.update(status='N/A', at_airport='', last_landed_at=None)
        code = ''
    if code:
        entry['_airport_evidence'] = stamp
    elif entry.get('status') == 'N/A' and not entry.get('hex') and old:
        # Missing ADS-B is not proof of arrival. Retain only an actually
        # observed recent airport; never predict landing from elapsed time.
        code, stamp = _airport(old, now)
        stamp = old.get('_airport_evidence', stamp)
        if code and stamp and 0 <= now-stamp <= AIRPORT_TTL:
            entry.update(at_airport=code, status='Last landed '+code,
                         last_landed_at=stamp, _airport_evidence=stamp,
                         source=old.get('source','Observed airport'))
    return entry


def _public(item, now):
    if not item:
        return {'status':'N/A'}
    entry = dict(item)
    checked = entry.pop('_checked_at', 0)
    evidence = entry.pop('_airport_evidence', None)
    entry.pop('_last_airborne', None)
    entry.pop('_route_memory', None)
    if now-checked > LIVE_TTL:
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
    snapshot = flights_live.snapshot(','.join(batch))
    now = time.time()
    with _lock:
        for reg, item in snapshot.get('aircraft', {}).items():
            _entries[reg] = _merge(_entries.get(reg), item, now)
        for reg in list(_entries):
            if reg not in regs:
                del _entries[reg]
        saved = dict(_entries)
    _save(saved)


def _run():
    rows = [{'registration': reg} for reg in _entries]
    last_sheet = 0
    while True:
        try:
            if not last_sheet or time.monotonic()-last_sheet >= SHEET_PERIOD:
                last_sheet = time.monotonic()
                try:
                    rows = flights_log.read().get('flights', [])
                except (ValueError, OSError):
                    pass  # Continue using known registrations if SheetDB is down.
            # Reuse a fresher SheetDB response from an ordinary page load/edit.
            with flights_log._LOCK:
                if flights_log._CACHE['rows'] is not None:
                    rows = list(flights_log._CACHE['rows'])
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
                'checked_at':int(now)}
