"""Read-only Healthchecks.io status for the two existing ADS-B monitors.

Runs only when the Settings foldout is open. No monitoring jobs, databases or
aircraft services are changed. A cached server-side request avoids API spam.
"""
from datetime import datetime, timezone
from threading import Lock
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import os
import time

# User explicitly authorised committing this project-scoped read-only key.
# Override with an environment variable if the key is later rotated.
_API_KEY = os.environ.get(
    'AIRSPACE_HEALTHCHECKS_READONLY_KEY',
    'hcr_OF64kMIEmNewgKrCh0F2Zisnntjb',
)
_API_ROOT = 'https://healthchecks.io/api/v3/'
_LABELS = ('Ubuntu Server', 'ADSB.im Receiver')
_LOCK = Lock()
_CACHE = {'at': 0.0, 'value': None}
_CACHE_SECONDS = 45


def _get_json(path):
    req = Request(
        _API_ROOT + path,
        headers={'X-Api-Key': _API_KEY, 'Accept': 'application/json'},
    )
    with urlopen(req, timeout=6) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError('Healthchecks response exceeds safety limit')
    return json.loads(raw)


def _dt(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except ValueError:
        return None


def _outages(flips, status, now):
    """Pair recorded down/up transitions; never guess missing start times."""
    if not isinstance(flips, list):
        return []
    events = []
    for flip in flips:
        if not isinstance(flip, dict) or flip.get('up') not in (0, 1, False, True):
            continue
        when = _dt(flip.get('timestamp'))
        if when:
            events.append((when, bool(flip['up'])))
    events.sort(key=lambda item: item[0])
    started = None
    incidents = []
    for instant, is_up in events:
        if not is_up:
            started = instant
        elif started is not None:
            if instant >= started:
                incidents.append({
                    'started_at': started.isoformat(),
                    'ended_at': instant.isoformat(),
                    'duration_seconds': int((instant - started).total_seconds()),
                    'ongoing': False,
                })
            started = None
    if started is not None and status == 'down':
        incidents.append({
            'started_at': started.isoformat(),
            'ended_at': None,
            'duration_seconds': max(0, int((now - started).total_seconds())),
            'ongoing': True,
        })
    incidents.reverse()
    return incidents[:30]


def _fetch_snapshot():
    now = datetime.now(timezone.utc)
    result = _get_json('checks/')
    checks = result.get('checks') if isinstance(result, dict) else None
    if not isinstance(checks, list):
        raise ValueError('Unexpected Healthchecks check list')

    by_name = {str(c.get('name', '')).strip().casefold(): c for c in checks if isinstance(c, dict)}
    rows = []
    for label in _LABELS:
        check = by_name.get(label.casefold())
        if check is None:
            rows.append({
                'name': label, 'status': 'not_found',
                'note': 'Not found in this Healthchecks.io project. The read-only key is project-specific.',
                'outages': [],
            })
            continue
        unique = str(check.get('unique_key', ''))
        status = str(check.get('status', 'new')).lower()
        if status not in ('new', 'up', 'grace', 'down', 'paused'):
            status = 'unknown'
        row = {
            'name': label,
            'status': status,
            'last_ping': check.get('last_ping'),
            'next_ping': check.get('next_ping'),
            'period_seconds': check.get('timeout'),
            'grace_seconds': check.get('grace'),
            'ping_count': check.get('n_pings'),
            'outages': [],
            'history_error': None,
        }
        if unique and len(unique) <= 80 and all(char in '0123456789abcdefABCDEF' for char in unique):
            try:
                row['outages'] = _outages(_get_json('checks/' + unique + '/flips/'), status, now)
            except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
                row['history_error'] = 'Outage history temporarily unavailable.'
        else:
            row['history_error'] = 'No read-only history identifier provided.'
        rows.append(row)
    return {
        'checks': rows,
        'checked_at': now.isoformat(),
        'history_note': 'Healthchecks.io retains status transitions for the current and previous two calendar months. Older outages may not appear.',
    }


def snapshot(refresh=False):
    """Cached, sanitized output; never return the API key or ping URLs."""
    with _LOCK:
        now = time.monotonic()
        if not refresh and _CACHE['value'] is not None and now - _CACHE['at'] < _CACHE_SECONDS:
            return _CACHE['value']
        try:
            value = _fetch_snapshot()
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
            value = {
                'checks': [],
                'checked_at': datetime.now(timezone.utc).isoformat(),
                'error': 'Healthchecks.io could not be reached or the read-only key cannot access this project.',
            }
        _CACHE.update(at=now, value=value)
        return value
