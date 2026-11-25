"""Persistent, receiver-local aircraft alert rules. No writes to Aerodrome or ADS-B services."""
from __future__ import annotations

import fnmatch
from contextlib import contextmanager, closing
import ipaddress
import json
import hashlib
import math
import os
import re
import socket
import sqlite3
import threading
import time
from pathlib import Path

from . import flyitaly, adsblol, adsbfi, regional_sources, api_budget
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.parse import urlsplit

STATE_DIR = Path(__file__).resolve().parents[1] / '.airspace-state'
DB_PATH = STATE_DIR / 'alerts.sqlite3'
POLL_SECONDS = 3
STALE_SECONDS = 30
LOST_SECONDS = 600
API_MAX = 12 * 1024
DEFAULT_RECEIVER_URLS = (
    # Ultrafeeder publishes readsb JSON on port 1090; prefer the confirmed
    # on-host HTTP endpoint without granting the website access to Docker.
    'http://127.0.0.1:1090/data/aircraft.json',
    'http://127.0.0.1:1099/map/data/aircraft.json',
    'http://127.0.0.1:1099/data/aircraft.json',
    'http://127.0.0.1:1099/map/aircraft.json',
    'http://127.0.0.1:8080/data/aircraft.json',
    'http://127.0.0.1:8080/tar1090/data/aircraft.json',
)
FIELDS = frozenset(('type', 'registration', 'callsign', 'hex', 'operator', 'military'))
GEO_HYSTERESIS_KM = 0.5
ALT_HYSTERESIS_FT = 300
_lock = threading.RLock()
_worker_started = False
_last_good_url = None
_last_live_scan_at = 0
_aerodrome_cursor = 0
_AERODROME_SOURCE = 'Aerodrome (10-second samples)'
_last_sample = {'time': None, 'aircraft': 0, 'error': 'Waiting for receiver', 'lat': None, 'lon': None, 'source': None}


@contextmanager
def connect():
    DB_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    PRAGMA busy_timeout=5000;
    CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY, label TEXT NOT NULL, field TEXT NOT NULL,
        pattern TEXT NOT NULL, max_km REAL, min_ft INTEGER, max_ft INTEGER,
        enabled INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL,
        use_flyitaly INTEGER NOT NULL DEFAULT 0,
        network_only INTEGER NOT NULL DEFAULT 0,
        min_rssi REAL
    );
    CREATE TABLE IF NOT EXISTS occupancy (
        rule_id INTEGER NOT NULL, hex TEXT NOT NULL, state TEXT NOT NULL,
        outside_count INTEGER NOT NULL DEFAULT 0, last_seen INTEGER NOT NULL,
        PRIMARY KEY(rule_id, hex), FOREIGN KEY(rule_id) REFERENCES rules(id)
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY, rule_id INTEGER, rule_label TEXT NOT NULL,
        hex TEXT NOT NULL, callsign TEXT, registration TEXT, aircraft_type TEXT,
        distance_km REAL, altitude_ft INTEGER, created INTEGER NOT NULL,
        delivery TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt INTEGER NOT NULL DEFAULT 0, last_error TEXT,
        source TEXT NOT NULL DEFAULT 'local'
    );
    CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')
    # Add new optional columns on existing installs without changing rules or history.
    for table, additions in (
        ('rules', (('use_flyitaly', 'INTEGER NOT NULL DEFAULT 0'),
                   ('network_only', 'INTEGER NOT NULL DEFAULT 0'),
                   ('min_rssi', 'REAL'))),
        ('events', (('source', "TEXT NOT NULL DEFAULT 'local'"),)),
    ):
        existing = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        for column, declaration in additions:
            if column not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}')
    try: os.chmod(DB_PATH, 0o600)
    except OSError: pass
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _number(v, lower, upper, name, integer=False, digits=2):
    if v is None or v == '': return None
    try:
        x = float(v)
        if not math.isfinite(x) or x < lower or x > upper: raise ValueError()
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be between {lower:g} and {upper:g}')
    return int(x) if integer else round(x, digits)


def validate_rule(data):
    if not isinstance(data, dict): raise ValueError('Invalid rule')
    field = str(data.get('field', 'type')).lower()
    if field not in FIELDS: raise ValueError('Invalid match field')
    pattern = str(data.get('pattern', '')).upper().strip()
    if field == 'military': pattern = 'YES'
    else:
        parts = [v.strip() for v in pattern.split(',')]
        allowed = r'[A-Z0-9*?\- ]{1,60}' if field == 'operator' else r'[A-Z0-9*?\-]{1,16}'
        if not parts or len(parts) > 100 or any(not re.fullmatch(allowed, x) for x in parts):
            raise ValueError('Enter up to 100 values separated by commas (letters, numbers, * or ?)')
        pattern = ','.join(parts)
    label = str(data.get('label', '')).strip()
    if not label: label = pattern if field != 'military' else 'Military'
    if len(label) > 50 or any(ord(c)<32 for c in label): raise ValueError('Name must be 1–50 characters')
    max_km = _number(data.get('max_km'), 0.1, 1000, 'Distance')
    min_ft = _number(data.get('min_ft'), -2000, 70000, 'Minimum altitude', True)
    max_ft = _number(data.get('max_ft'), -2000, 70000, 'Maximum altitude', True)
    if min_ft is not None and max_ft is not None and min_ft > max_ft:
        raise ValueError('Minimum altitude must not exceed maximum')
    # Legacy column now stores the global Backup APIs option; RSSI retired.
    min_rssi = None
    use_flyitaly = int(bool(data.get('backup_apis',data.get('use_flyitaly',False))))
    # Single Backup APIs checkbox: when on, local aircraft gain API enrichment.
    # With an explicit radius the same rule can also match network aircraft.
    # Without a radius, only locally received aircraft may trigger.
    network_only = int(bool(use_flyitaly and max_km is not None))
    return {'label': label, 'field':field,'pattern':pattern, 'max_km': max_km,
            'min_ft':min_ft, 'max_ft':max_ft, 'enabled':int(bool(data.get('enabled',True))),
            'use_flyitaly':use_flyitaly,'network_only':network_only,'min_rssi':min_rssi}


def save_rule(data):
    item = validate_rule(data)
    with _lock, connect() as c:
        rule_id = data.get('id')
        if rule_id is not None:
            try: rule_id=int(rule_id)
            except (ValueError,TypeError): raise ValueError('Invalid rule ID')
            exists=c.execute('SELECT 1 FROM rules WHERE id=?',(rule_id,)).fetchone()
            if not exists: raise ValueError('Rule not found')
            c.execute('UPDATE rules SET label=?,field=?,pattern=?,max_km=?,min_ft=?,max_ft=?,enabled=?,use_flyitaly=?,network_only=?,min_rssi=? WHERE id=?',
                (*item.values(),rule_id))
            # Changing filters must not leave stale armed state from the old rule.
            c.execute('DELETE FROM occupancy WHERE rule_id=?',(rule_id,))
        else:
            cur=c.execute('INSERT INTO rules(label,field,pattern,max_km,min_ft,max_ft,enabled,use_flyitaly,network_only,min_rssi,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (*item.values(),int(time.time())))
            rule_id=cur.lastrowid
        return rule_id


def delete_rule(rule_id):
    with _lock, connect() as c:
        c.execute('DELETE FROM occupancy WHERE rule_id=?',(int(rule_id),))
        result=c.execute('DELETE FROM rules WHERE id=?',(int(rule_id),))
        if not result.rowcount: raise ValueError('Rule not found')


def save_notifier(data):
    if not isinstance(data,dict): raise ValueError('Invalid notification configuration')
    base = str(data.get('server','https://ntfy.sh')).strip().rstrip('/')
    from urllib.parse import urlsplit
    u=urlsplit(base)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
        raise ValueError('ntfy server must be an HTTPS address without a path')
    topic=str(data.get('topic','')).strip()
    if topic and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',topic):
        raise ValueError('Topic must contain letters, digits, hyphens or underscores')
    with _lock, connect() as c:
        c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',('server',base))
        c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',('topic',topic))
        if 'token' in data:
            token=str(data['token']).strip()
            if len(token)>500: raise ValueError('Token too long')
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',('token',token))


def save_flyitaly(data):
    """Store the API key in private local SQLite state only, never in GitHub."""
    if not isinstance(data,dict):raise ValueError('Invalid FlyItalyADSB settings')
    changed=False
    with _lock, connect() as c:
        if data.get('clear'):
            c.execute("DELETE FROM config WHERE key='flyitaly_key'")
            changed=True
        elif 'key' in data and str(data['key']).strip():
            key=str(data['key']).strip()
            if not re.fullmatch(r'[A-Za-z0-9_-]{20,250}',key):
                raise ValueError('Invalid FlyItalyADSB API key format')
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',
                      ('flyitaly_key',key))
            changed=True
    if changed:flyitaly.clear()


def save_adsblol(data):
    """Save/remove adsb.lol key only in existing private local configuration."""
    if not isinstance(data,dict):raise ValueError('Invalid adsb.lol settings')
    changed=False
    with _lock, connect() as c:
        if data.get('clear'):
            c.execute("DELETE FROM config WHERE key='adsblol_key'")
            changed=True
        elif str(data.get('key','')).strip():
            key=str(data['key']).strip()
            if not re.fullmatch(r'[A-Za-z0-9_\-]{12,500}',key):
                raise ValueError('Invalid adsb.lol key format')
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',
                      ('adsblol_key',key))
            changed=True
    if changed:adsblol.clear()


def _adsbiq_key(c):
    row=c.execute("SELECT value FROM config WHERE key='adsbiq_key'").fetchone()
    return row['value'] if row else ''


def save_adsbiq(data):
    with _lock,connect() as c:
        if data.get('clear'):
            c.execute("DELETE FROM config WHERE key='adsbiq_key'")
        else:
            key=str(data.get('key','')).strip()
            if not re.fullmatch(r'iq_[A-Za-z0-9_-]{8,500}',key):
                raise ValueError('Invalid ADSBiq API key format')
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',('adsbiq_key',key))


def test_adsbiq():
    with _lock,connect() as c:key=_adsbiq_key(c)
    if not key:raise ValueError('Save your ADSBiq key first')
    from .flights_live import _NoRedirect as NoRedirect, _global_snapshot
    base=build_opener(ProxyHandler({}),NoRedirect()).open
    _global_snapshot([],key,lambda req,timeout:api_budget.open_request('ADSBiq',base,req,timeout),'ADSBiq')
    return {'ok':True,'plan':'API accessible'}


def _avio_key(c):
    row=c.execute("SELECT value FROM config WHERE key='avioadsb_key'").fetchone()
    return row['value'] if row else ''


def save_avio(data):
    with _lock,connect() as c:
        if data.get('clear'):
            c.execute("DELETE FROM config WHERE key='avioadsb_key'")
        else:
            key=str(data.get('key','')).strip()
            if not re.fullmatch(r'avio_[A-Za-z0-9_-]{8,500}',key):
                raise ValueError('Invalid AvioADSB API key format')
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',('avioadsb_key',key))


def test_avio():
    with _lock,connect() as c:key=_avio_key(c)
    if not key:raise ValueError('Save your AvioADSB key first')
    from .flights_live import _NoRedirect as NoRedirect
    request=Request('https://avioadsb.org/v1/me',headers={'X-API-Key':key,'Accept':'application/json',
                    'User-Agent':'AirspaceAnalytics-Flights/4'})
    try:
        with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=6) as response:
            payload=json.loads(response.read(50000))
        if not isinstance(payload,dict):raise ValueError('Invalid response')
        tier=str(payload.get('tier','unknown'))[:40]
        if tier!='contributor':raise ValueError('AvioADSB tier '+tier+'; claim an active station to unlock global aircraft access')
        return {'ok':True,'plan':tier,'aircraft':None}
    except HTTPError as error:
        raise ValueError('AvioADSB HTTP '+str(error.code)+'; check key or feeder status') from None
    except (URLError,OSError,TimeoutError):
        raise ValueError('AvioADSB network connection failed') from None
    except (ValueError,TypeError) as error:
        if str(error).startswith('AvioADSB tier '):raise
        raise ValueError('AvioADSB returned an invalid response') from None


def _adsblol_key(c):
    row=c.execute("SELECT value FROM config WHERE key='adsblol_key'").fetchone()
    return row['value'] if row else ''


def test_adsblol():
    with _lock, connect() as c:
        key=_adsblol_key(c)
        coords=receiver_settings(c)
    if not key:raise ValueError('Save your adsb.lol feeder key first')
    if coords['lat'] is None or coords['lon'] is None:
        raise ValueError('Save antenna coordinates in Receiver setup')
    return adsblol.fetch(key,coords['lat'],coords['lon'],50)


def test_adsbfi():
    """Public API connectivity test; no secret or feeder key required."""
    with _lock, connect() as c:coords=receiver_settings(c)
    if coords['lat'] is None or coords['lon'] is None:
        raise ValueError('Save antenna coordinates under Receiver first')
    return adsbfi.fetch(coords['lat'],coords['lon'],50)


def _flyitaly_key(c):
    row=c.execute("SELECT value FROM config WHERE key='flyitaly_key'").fetchone()
    return row['value'] if row else ''


def flyitaly_status():
    with _lock, connect() as c:
        configured=bool(_flyitaly_key(c))
    return flyitaly.status(key_set=configured)


def test_flyitaly():
    with _lock, connect() as c:
        key=_flyitaly_key(c)
        coords=receiver_settings(c)
    if not key:raise ValueError('Save your FlyItalyADSB key first')
    if coords['lat'] is None or coords['lon'] is None:
        raise ValueError('Save your antenna coordinates under Receiver setup first')
    return flyitaly.fetch(key,coords['lat'],coords['lon'],50)


def receiver_settings(c):
    cfg = {row['key']:row['value'] for row in c.execute(
        "SELECT key,value FROM config WHERE key IN ('receiver_url','receiver_lat','receiver_lon')")}
    return {'url':cfg.get('receiver_url',''), 'lat':float(cfg['receiver_lat']) if cfg.get('receiver_lat') else None,
            'lon':float(cfg['receiver_lon']) if cfg.get('receiver_lon') else None}


def _local_addresses():
    """IPv4 addresses actually belonging to this Linux machine.

    Docker may publish tar1090 to the Wi-Fi IP but not 127.0.0.1. Only
    advertise/accept this machine's own private addresses, never another
    LAN device or an arbitrary URL selected by a browser.
    """
    addresses = {'127.0.0.1'}
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None,
                                       family=socket.AF_INET, type=socket.SOCK_STREAM):
            addresses.add(item[4][0])
    except OSError:
        pass
    try:
        # UDP connect chooses the local egress interface without sending data.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.connect(('192.0.2.1', 9))  # TEST-NET address, not contacted
            addresses.add(client.getsockname()[0])
    except OSError:
        pass
    allowed = set()
    for value in addresses:
        try:
            address = ipaddress.IPv4Address(value)
            if (address.is_loopback or
                (address.is_private and not address.is_link_local and
                 not address.is_multicast and not address.is_unspecified)):
                allowed.add(str(address))
        except ipaddress.AddressValueError:
            continue
    return allowed


def _receiver_url_allowed(url, addresses):
    try:
        u = urlsplit(url)
        return (u.scheme == 'http' and u.hostname in (addresses | {'localhost'})
                and u.port is not None and u.path.endswith('/aircraft.json')
                and not (u.username or u.password or u.query or u.fragment))
    except ValueError:
        return False


def _receiver_candidates(addresses):
    # Preserve previous localhost probes, then add same-machine LAN probes.
    urls = list(DEFAULT_RECEIVER_URLS)
    paths = ('/map/data/aircraft.json', '/data/aircraft.json',
             '/tar1090/data/aircraft.json', '/map/aircraft.json')
    for host in sorted(addresses - {'127.0.0.1'}):
        for port in (1090, 1099, 8080):
            urls.extend(f'http://{host}:{port}{path}' for path in paths)
    return tuple(dict.fromkeys(urls))


def save_receiver(data):
    """Optional local feed URL / antenna location, stored only in alert state."""
    if not isinstance(data, dict): raise ValueError('Invalid receiver settings')
    url = str(data.get('url','')).strip()
    if len(url)>240: raise ValueError('Receiver URL is too long')
    if url:
        u=urlsplit(url)
        if not _receiver_url_allowed(url, _local_addresses()):
            raise ValueError('Use this PC\'s localhost or LAN address with an aircraft.json URL')
    raw_lat,raw_lon=data.get('lat'),data.get('lon')
    if (raw_lat in ('',None)) != (raw_lon in ('',None)):
        raise ValueError('Enter both antenna latitude and longitude, or leave both blank')
    lat=_number(raw_lat,-90,90,'Latitude',digits=7)
    lon=_number(raw_lon,-180,180,'Longitude',digits=7)
    with _lock, connect() as c:
        for key,value in (('receiver_url',url),('receiver_lat',str(lat) if lat is not None else ''),
                          ('receiver_lon',str(lon) if lon is not None else '')):
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',(key,value))


def notifier(c):
    cfg={row['key']:row['value'] for row in c.execute('SELECT key,value FROM config')}
    return {'server':cfg.get('server','https://ntfy.sh'), 'topic':cfg.get('topic',''),
            'token_set':bool(cfg.get('token',''))}, cfg.get('token','')


# Explicit test results belong to the server, not to the browser. A result is
# bound to the credential used, so replacing a key never inherits verification.
def _opensky_key(c):
    row=c.execute("SELECT value FROM config WHERE key='opensky_credentials'").fetchone()
    return row['value'] if row else ''

def _opensky_credentials(c):
    raw=_opensky_key(c)
    if not raw:return None
    try:credentials=json.loads(raw)
    except (ValueError,TypeError):return None
    return credentials if isinstance(credentials,dict) and credentials.get('permission') else None

def save_opensky(payload):
    with _lock,connect() as c:
        if payload.get('clear'):
            c.execute("DELETE FROM config WHERE key='opensky_credentials'")
            return
        if payload.get('permission') is not True:
            raise ValueError('Confirm written OpenSky permission before enabling automated access')
        client=str(payload.get('client_id','')).strip()
        secret=str(payload.get('key','')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_.@-]{2,200}',client) or not secret or len(secret)>512 or any(ord(x)<32 for x in secret):
            raise ValueError('Enter a valid OAuth client ID and client secret')
        c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',
                  ('opensky_credentials',json.dumps({'client_id':client,'client_secret':secret,'permission':True})))

def test_opensky():
    from . import extra_flight_sources
    with _lock,connect() as c:credentials=_opensky_credentials(c)
    if not credentials:raise ValueError('Save permitted OpenSky OAuth credentials first')
    return extra_flight_sources.test_opensky(credentials)

def test_adsbhub():
    from . import extra_flight_sources
    return extra_flight_sources.test_adsbhub()

def test_airplaneslive():
    from . import extra_flight_sources
    return extra_flight_sources.test_airplanes()

def _provider_key(c,provider):
    getters={'flyitaly':_flyitaly_key,'adsblol':_adsblol_key,
             'avioadsb':_avio_key,'adsbiq':_adsbiq_key,'opensky':_opensky_key}
    return getters[provider](c) if provider in getters else ''

def _provider_fingerprint(key):
    return hashlib.sha256(key.encode()).hexdigest()

def _provider_tests(c):
    result={}
    for provider in ('flyitaly','adsblol','avioadsb','adsbiq','adsbfi','opensky','airplaneslive','adsbhub'):
        row=c.execute('SELECT value FROM config WHERE key=?',('provider_test_'+provider,)).fetchone()
        if not row:continue
        try:entry=json.loads(row['value'])
        except (TypeError,ValueError):continue
        if not isinstance(entry,dict) or entry.get('credential')!=_provider_fingerprint(_provider_key(c,provider)):continue
        result[provider]={k:entry[k] for k in ('ok','at','message') if k in entry}
    return result

def save_provider_key(provider,payload):
    functions={'flyitaly':save_flyitaly,'adsblol':save_adsblol,
               'avioadsb':save_avio,'adsbiq':save_adsbiq,'opensky':save_opensky}
    if provider not in functions:raise ValueError('Unknown API source')
    with _lock:
        functions[provider](payload)
        with connect() as c:
            c.execute('DELETE FROM config WHERE key=?',('provider_test_'+provider,))


def run_provider_test(provider):
    functions={'flyitaly':test_flyitaly,'adsblol':test_adsblol,
               'avioadsb':test_avio,'adsbiq':test_adsbiq,'adsbfi':test_adsbfi,
               'opensky':test_opensky,'airplaneslive':test_airplaneslive,'adsbhub':test_adsbhub}
    if provider not in functions:raise ValueError('Unknown API source')
    with _lock,connect() as c:
        key=_provider_key(c,provider)
    fingerprint=_provider_fingerprint(key)
    def save(ok,message):
        with _lock,connect() as c:
            if _provider_fingerprint(_provider_key(c,provider))!=fingerprint:return
            # Do not expose credential text, even if an upstream error echoes it.
            if key:message=message.replace(key,'[redacted]')
            record={'credential':fingerprint,'ok':ok,'at':int(time.time()),'message':message[:300]}
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',
                      ('provider_test_'+provider,json.dumps(record)))
    try:
        result=functions[provider]()
    except (ValueError,OSError) as error:
        # A temporary cooldown is not a revoked key or a failed authorization.
        # Preserve activation so a provider can resume automatically.
        if not any(x in str(error).lower() for x in ('rate limit','http 429','retry later','background lookup in progress')):
            save(False,str(error))
        raise
    message='Connection successful'
    if result.get('plan'):message+=' · '+str(result['plan'])[:50]
    if result.get('aircraft') is not None:message+=' · '+str(result['aircraft'])+' aircraft'
    save(True,message)
    return result


def provider_usage():
    from . import flights_live
    global_status=flights_live.source_health()
    regional=regional_sources.health()
    ids={'flyitaly':'FlyItalyADSB','adsblol':'adsb.lol','adsbfi':'adsb.fi',
         'avioadsb':'AvioADSB','adsbiq':'ADSBiq','airplaneslive':'airplanes.live',
         'adsbhub':'ADSBHub','opensky':'OpenSky Network'}
    result={}
    for id,name in ids.items():
        combined=dict(global_status.get(name,{}))
        near=regional.get(name,{})
        if 'nearby_aircraft' in near:combined['nearby_aircraft']=near['nearby_aircraft']
        if near.get('error') and not combined.get('error'):combined['error']=near['error']
        combined['retry_seconds']=max(combined.get('retry_seconds',0),near.get('retry_seconds',0),
                                      round(api_budget.remaining(name)))
        if id in ('flyitaly','adsblol','adsbfi'):
            state={'flyitaly':flyitaly,'adsblol':adsblol,'adsbfi':adsbfi}[id].status()
            combined['nearby_aircraft']=state.get('aircraft',0) if state.get('connected') else 0
        result[id]=combined
    return result


def snapshot():
    usage=provider_usage()
    with _lock, connect() as c:
        rules=[dict(x) for x in c.execute('SELECT id,label,field,pattern,max_km,min_ft,max_ft,enabled,use_flyitaly,network_only,min_rssi FROM rules ORDER BY id DESC')]
        active={r['rule_id']:r['n'] for r in c.execute("SELECT rule_id,count(*) n FROM occupancy WHERE state='active' GROUP BY rule_id")}
        for r in rules:r['active']=active.get(r['id'],0)
        events=[dict(x) for x in c.execute('SELECT id,rule_id,rule_label,hex,callsign,registration,aircraft_type,distance_km,altitude_ft,created,delivery,source FROM events ORDER BY id DESC LIMIT 60')]
        pub,_=notifier(c)
        return {'rules':rules,'events':events,'ntfy':pub,'flyitaly':flyitaly.status(bool(_flyitaly_key(c))), 'receiver':dict(_last_sample),
                'adsblol':adsblol.status(bool(_adsblol_key(c))),'adsbfi':adsbfi.status(),
                'avioadsb':{'key_set':bool(_avio_key(c))},'adsbiq':{'key_set':bool(_adsbiq_key(c))},
                'opensky':{'key_set':bool(_opensky_key(c))},'airplaneslive':{'key_required':False},'adsbhub':{'key_required':False},
                'provider_tests':_provider_tests(c),'provider_usage':usage,
                'receiver_settings':receiver_settings(c)}


def dist_km(lat1,lon1,lat2,lon2):
    p1,p2=math.radians(lat1),math.radians(lat2)
    dlat=p2-p1; dlon=math.radians(lon2-lon1)
    h=math.sin(dlat/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 12742 * math.asin(min(1,math.sqrt(h)))


def _match_pattern(pattern, value):
    return any(fnmatch.fnmatchcase(value.upper(),p) for p in pattern.split(','))


def _classify(rule, plane, lat,lon, receiver_lat,receiver_lon, was_active):
    source_age=plane.get('seen',99)
    if not isinstance(source_age,(int,float)) or not math.isfinite(source_age) or source_age>STALE_SECONDS:return None
    field=rule['field']
    if field == 'military':
        try: flags=int(plane.get('dbFlags') or 0)
        except (TypeError,ValueError): flags=0
        matched = bool(flags & 1) or plane.get('_aerodrome_category') == 'military'
    else:
        value={'type':plane.get('t'),'registration':plane.get('r'),'callsign':plane.get('flight'),
               'hex':plane.get('hex'),'operator':plane.get('_operator') or plane.get('ownOp')}.get(field)
        matched = bool(value and _match_pattern(rule['pattern'],str(value).strip()))
    if not matched: return False
    max_km=rule['max_km']
    if max_km is not None:
        if lat is None or lon is None or receiver_lat is None or receiver_lon is None:return None
        age=plane.get('seen_pos',99)
        if not isinstance(age,(int,float)) or not math.isfinite(age) or age > STALE_SECONDS:return None
        distance=dist_km(receiver_lat,receiver_lon,lat,lon)
        if distance > max_km + (GEO_HYSTERESIS_KM if was_active else 0):return False
    else: distance=dist_km(receiver_lat,receiver_lon,lat,lon) if None not in (lat,lon,receiver_lat,receiver_lon) else None
    altitude=plane.get('alt_baro')
    if isinstance(altitude,str):altitude=0 if altitude.lower()=='ground' else None
    if isinstance(altitude,(int,float)) and not math.isfinite(altitude):altitude=None
    if (rule['min_ft'] is not None or rule['max_ft'] is not None):
        if not isinstance(altitude,(int,float)):return None
        if rule['min_ft'] is not None and altitude < rule['min_ft'] - (ALT_HYSTERESIS_FT if was_active else 0):return False
        if rule['max_ft'] is not None and altitude > rule['max_ft'] + (ALT_HYSTERESIS_FT if was_active else 0):return False
    return {'distance_km':round(distance,1) if distance is not None else None,
            'altitude_ft':int(altitude) if isinstance(altitude,(int,float)) else None}


def enrich_aircraft(aircraft):
    """Read only missing registry fields from the EXISTING Aerodrome database.

    This never copies sightings, uses one bounded indexed query, and is best
    effort; a database outage must not stop live type/hex alerting.
    """
    candidates = [p for p in aircraft if isinstance(p,dict) and
        re.fullmatch(r'[0-9a-fA-F]{6}',str(p.get('hex',''))) and
        (not p.get('t') or not p.get('r') or not p.get('ownOp') or not p.get('dbFlags'))]
    if not candidates:return
    ids=list(dict.fromkeys(str(p['hex']).lower() for p in candidates))[:400]
    try:
        from . import data
        with closing(data.connection()) as db:
            result=db.execute('SELECT icao,registration,aircraft_type,operator,category FROM seen_aircraft WHERE icao IN ('+
                ','.join('?' for _ in ids)+')',ids).fetchall()
        found={str(row['icao']).lower():row for row in result}
        for p in candidates:
            row=found.get(str(p['hex']).lower())
            if not row:continue
            if not p.get('t') and row['aircraft_type']:p['t']=row['aircraft_type']
            if not p.get('r') and row['registration']:p['r']=row['registration']
            if row['operator']:p['_operator']=row['operator']
            if row['category']:p['_aerodrome_category']=row['category']
    except Exception:
        pass  # Enrichment is optional; even Aerodrome's DataError must not interrupt alerts.


def _merge_external(local, remote):
    """Fill missing local fields with recent network data, never replace fresh local data.

    Only called for rules that explicitly enable Backup APIs.
    """
    if not remote:return local
    merged=dict(local)
    for field in ('r','t','flight','ownOp','alt_baro'):
        if merged.get(field) in (None,'') and remote.get(field) not in (None,''):
            merged[field]=remote[field]
    try:
        merged['dbFlags']=int(local.get('dbFlags') or 0) | int(remote.get('dbFlags') or 0)
    except (TypeError,ValueError):
        pass
    pos_age=merged.get('seen_pos')
    local_position_fresh=(
        merged.get('lat') is not None and merged.get('lon') is not None
        and isinstance(pos_age,(float,int)) and math.isfinite(pos_age)
        and 0 <= pos_age <= STALE_SECONDS
    )
    remote_age=remote.get('seen_pos')
    if (not local_position_fresh and
            isinstance(remote_age,(float,int)) and math.isfinite(remote_age)
            and 0 <= remote_age <= STALE_SECONDS and
            remote.get('lat') is not None and remote.get('lon') is not None):
        merged.update(lat=remote['lat'],lon=remote['lon'],seen_pos=remote_age)
    return merged


def process_snapshot(payload, receiver_lat, receiver_lon, now=None, external=None):
    """Local-first per-rule matching with strictly opt-in cached network coverage.

    Neither a slow nor an unavailable API can delay local matching or create
    phantom departures. Each (rule, ICAO hex) keeps its original deduplication.
    """
    now=int(now if now is not None else time.time())
    aircraft=payload.get('aircraft',[])
    if not isinstance(aircraft,list):raise ValueError('Invalid receiver aircraft list')
    enrich_aircraft(aircraft)
    incoming=external if isinstance(external,list) else []
    extra={}
    for p in incoming[:3000]:
        if not isinstance(p,dict):continue
        code=str(p.get('hex','')).lower().strip()
        if re.fullmatch(r'[0-9a-f]{6}',code):
            # Merge matching ICAOs from multiple networks; prefer freshest position.
            previous=extra.get(code)
            if previous is None:extra[code]=p
            else:
                prior_age=previous.get('seen_pos')
                new_age=p.get('seen_pos')
                better=(isinstance(new_age,(int,float)) and math.isfinite(new_age)
                        and (not isinstance(prior_age,(int,float)) or
                             not math.isfinite(prior_age) or new_age<prior_age))
                extra[code]=(_merge_external(p,previous) if better
                             else _merge_external(previous,p))
    # Existing Aerodrome data is still available for unclassified external aircraft.
    if extra:enrich_aircraft(list(extra.values()))
    local_hex={
        str(p.get('hex','')).lower().strip() for p in aircraft
        if isinstance(p,dict) and re.fullmatch(r'~?[0-9a-f]{6}',str(p.get('hex','')).lower().strip())
    }
    combined=[(p,False) for p in aircraft]
    combined.extend((p,True) for code,p in extra.items() if code not in local_hex)
    with _lock, connect() as c:
        rules=[dict(x) for x in c.execute('SELECT * FROM rules WHERE enabled=1')]
        current={(x['rule_id'],x['hex']):dict(x) for x in c.execute('SELECT * FROM occupancy')}
        seen=set()
        for original, network_only in combined:
            if not isinstance(original,dict):continue
            hexcode=str(original.get('hex','')).lower().strip()
            if not re.fullmatch(r'~?[a-f0-9]{6}',hexcode):continue
            for rule in rules:
                if network_only and not (rule['use_flyitaly'] and rule['max_km'] is not None):
                    continue
                plane=(original if network_only or not rule['use_flyitaly'] else
                       _merge_external(original,extra.get(hexcode)))
                try:
                    lat=float(plane['lat']) if plane.get('lat') is not None else None
                    lon=float(plane['lon']) if plane.get('lon') is not None else None
                except (TypeError,ValueError):lat=lon=None
                if lat is not None and lon is not None and (
                        not math.isfinite(lat) or not math.isfinite(lon)
                        or not (-90<=lat<=90 and -180<=lon<=180)):
                    lat=lon=None
                key=(rule['id'],hexcode)
                old=current.get(key)
                match=_classify(rule,plane,lat,lon,receiver_lat,receiver_lon,
                                bool(old and old['state']=='active'))
                if match is None:continue
                seen.add(key)
                if match is False:
                    if old:
                        count=old['outside_count']+1
                        if count>=2:c.execute('DELETE FROM occupancy WHERE rule_id=? AND hex=?',key)
                        else:c.execute('UPDATE occupancy SET outside_count=?,last_seen=? WHERE rule_id=? AND hex=?',
                                       (count,now,*key))
                    continue
                if old and old['state']=='active':
                    c.execute('UPDATE occupancy SET outside_count=0,last_seen=? WHERE rule_id=? AND hex=?',
                              (now,*key))
                    continue
                c.execute("INSERT OR REPLACE INTO occupancy(rule_id,hex,state,outside_count,last_seen) VALUES(?,?,'active',0,?)",
                          (rule['id'],hexcode,now))
                c.execute('INSERT INTO events(rule_id,rule_label,hex,callsign,registration,aircraft_type,distance_km,altitude_ft,created,next_attempt,source) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (rule['id'],rule['label'],hexcode,
                     str(plane.get('flight') or '').strip()[:24],
                     str(plane.get('r') or '').strip()[:24],
                     str(plane.get('t') or '').strip()[:12],
                     match['distance_km'],match['altitude_ft'],now,now,
                     (str(plane.get('_network_source') or 'FlyItalyADSB') if network_only else 'local')))
        # Missing observations are not proof of exit. Preserve prior behaviour.
        for key,old in current.items():
            if key not in seen and now-old['last_seen']>=LOST_SECONDS:
                c.execute('DELETE FROM occupancy WHERE rule_id=? AND hex=?',key)
        _last_sample.update(time=now,aircraft=payload.get('recent_aircraft_count',len(aircraft)),
                            error=None,lat=receiver_lat,lon=receiver_lon)


class _NoReceiverRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _get_json(url):
    request=Request(url,headers={'User-Agent':'AirspaceAnalytics-Alerts/1'})
    # Do not follow a redirect to an untrusted website; never use an HTTP proxy
    # to fetch loopback or the receiver's own LAN address.
    with build_opener(ProxyHandler({}), _NoReceiverRedirect()).open(request,timeout=3) as result:
        if int(result.headers.get('Content-Length','0') or 0)>2_000_000:raise ValueError('Receiver response too large')
        raw=result.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Receiver response too large')
        return json.loads(raw)



def _aerodrome_snapshot(lat, lon, consume=True):
    """Fresh read-only Aerodrome observations, without duplicating history.

    A primary-key DESC/LIMIT query avoids table scans on long-lived data. Only
    newly observed rows are sent to the rearming state machine: polling the
    same historical row must not count as two confirmed exits.
    """
    global _aerodrome_cursor
    from . import data
    now=time.time()
    with closing(data.connection()) as db:
        rows=db.execute(
            'SELECT id,icao,callsign,aircraft_type,lat,lon,altitude,seen_at '
            'FROM all_sightings ORDER BY id DESC LIMIT 2500'
        ).fetchall()
    newest_id=int(rows[0]['id']) if rows else 0
    flights={}
    recent_hex=set()
    for row in rows:
        rid=int(row['id'])
        try: observed=float(row['seen_at'])
        except (ValueError,TypeError): continue
        age=now-observed
        if age>STALE_SECONDS: break
        if age< -5: continue
        hexcode=str(row['icao'] or '').lower()
        if not re.fullmatch(r'[0-9a-f]{6}',hexcode):continue
        # Count all fresh aircraft, even rows already consumed by alert matching.
        recent_hex.add(hexcode)
        if consume and rid<=_aerodrome_cursor:continue
        plane=flights.setdefault(hexcode,{'hex':hexcode,'seen':max(0,age)})
        # Take newest available identity, while retaining a newer sample's
        # observed position and altitude, and keeping missing values unknown.
        if row['aircraft_type'] and not plane.get('t'):plane['t']=str(row['aircraft_type'])
        if row['callsign'] and not plane.get('flight'):plane['flight']=str(row['callsign'])
        if row['altitude'] is not None and not plane.get('_alt_set'):
            try:
                altitude=float(row['altitude'])
                if math.isfinite(altitude):
                    plane['alt_baro']=altitude
                    plane['_alt_set']=True
            except (ValueError,TypeError):pass
        if 'seen_pos' not in plane and row['lat'] is not None and row['lon'] is not None:
            try:
                latitude,longitude=float(row['lat']),float(row['lon'])
                if (math.isfinite(latitude) and math.isfinite(longitude) and
                    -90<=latitude<=90 and -180<=longitude<=180):
                    plane.update(lat=latitude,lon=longitude,seen_pos=max(0,age))
            except (ValueError,TypeError):pass
    if consume:_aerodrome_cursor=max(_aerodrome_cursor,newest_id)
    for plane in flights.values():plane.pop('_alt_set',None)
    return {'now':now,'aircraft':list(flights.values()),
            'recent_aircraft_count':len(recent_hex)},lat,lon


def read_receiver(consume=True):
    global _last_good_url, _last_live_scan_at
    with _lock, connect() as c: stored=receiver_settings(c)
    custom=stored['url'] or os.environ.get('AIRSPACE_AIRCRAFT_URL','').strip()
    addresses=_local_addresses()
    urls=(custom,) if custom else _receiver_candidates(addresses)
    if not custom and _last_good_url in urls:
        urls=(_last_good_url,)+tuple(x for x in urls if x!=_last_good_url)
    # Once the live feed fails, use Aerodrome temporarily instead of trying
    # many refused ports every three seconds. Retry the live feed each minute.
    if (_last_good_url==_AERODROME_SOURCE and
            time.time()-_last_live_scan_at < 60):
        try:
            return _aerodrome_snapshot(stored['lat'],stored['lon'],consume)
        except Exception:
            pass
    err='No aircraft feed available'
    for url in urls:
        if not _receiver_url_allowed(url,addresses):
            err='Receiver URL must point to this PC (localhost or its LAN IP)';continue
        try:
            a=_get_json(url)
            if not isinstance(a,dict) or not isinstance(a.get('aircraft'),list):raise ValueError('Not an aircraft.json response')
            updated=a.get('now')
            if isinstance(updated,(int,float)) and (time.time()-updated>20 or updated>time.time()+20):
                raise ValueError('Receiver snapshot is stale')
            try:
                r=_get_json(url.replace('aircraft.json','receiver.json'))
            except (ValueError,OSError,URLError,HTTPError):
                r={}
            # Manual settings override optional receiver metadata. Missing antenna
            # coordinates should not disable type, registration and hex-only rules.
            lat=stored['lat'] if stored['lat'] is not None else r.get('lat',r.get('latitude',a.get('lat',os.environ.get('AIRSPACE_RECEIVER_LAT'))))
            lon=stored['lon'] if stored['lon'] is not None else r.get('lon',r.get('longitude',a.get('lon',os.environ.get('AIRSPACE_RECEIVER_LON'))))
            lat=float(lat) if lat not in (None,'') else None
            lon=float(lon) if lon not in (None,'') else None
            if lat is not None and not (-90<=lat<=90):raise ValueError('Invalid antenna latitude')
            if lon is not None and not (-180<=lon<=180):raise ValueError('Invalid antenna longitude')
            _last_good_url=url
            return a,lat,lon
        except (ValueError,OSError,URLError,HTTPError,KeyError) as exc:
            err=str(exc)[:150]
    _last_good_url=None
    _last_live_scan_at=time.time()
    try:
        output=_aerodrome_snapshot(stored['lat'],stored['lon'],consume)
        _last_good_url=_AERODROME_SOURCE
        return output
    except Exception:
        if custom:raise ValueError('Receiver URL unreachable: '+err)
        raise ValueError('Live feed unavailable, and no Aerodrome sightings accessible: '+err)


def check_receiver():
    # The Test connection button must not consume unseen database samples.
    sample,lat,lon=read_receiver(consume=False)
    return {'ok':True,'aircraft':len(sample['aircraft']),
            'coordinates_available':lat is not None and lon is not None,
            'source':_last_good_url}


def _tar1090_local_click_url(hexcode=None):
    """Build a LAN-only tar1090 link without exposing or hardcoding home IPs.

    Prefer the host's actual 192.168.x.x Wi-Fi/Ethernet address. Do not link
    to loopback, Docker networks or Tailscale addresses on iOS.
    """
    if hexcode is not None and not re.fullmatch(r'[0-9a-fA-F]{6}',str(hexcode)):
        return None
    addresses = []
    try:
        for value in _local_addresses():
            host = ipaddress.IPv4Address(value)
            if host in ipaddress.IPv4Network('192.168.0.0/16'):
                priority = 0
            elif host in ipaddress.IPv4Network('10.0.0.0/8'):
                priority = 1
            elif host in ipaddress.IPv4Network('172.16.0.0/12'):
                priority = 2
            else:
                continue
            addresses.append((priority,int(host),str(host)))
    except (OSError,ValueError):
        return None
    if not addresses:
        return None
    host = min(addresses)[2]
    url = f'http://{host}:1099/map/'
    if hexcode is not None:
        url += f'?icao={str(hexcode).upper()}&noIsolation'
    return url


def deliver_pending(now=None, opener=urlopen):
    now=int(now if now is not None else time.time())
    with _lock, connect() as c:
        # A forgotten/offline notification should not arrive hours after a flyover.
        c.execute("UPDATE events SET delivery='expired' WHERE delivery='pending' AND created<?",(now-900,))
        public,token=notifier(c)
        if not public['topic']:return
        pending=[dict(x) for x in c.execute("SELECT * FROM events WHERE delivery='pending' AND next_attempt<=? ORDER BY id LIMIT 5",(now,))]
    for event in pending:
        # Show the registration as well as the callsign whenever it is known.
        # Only add a second identifier when it is different (a registration-
        # only sighting must not display the same text twice).
        callsign=str(event['callsign'] or '').strip()
        registration=str(event['registration'] or '').strip()
        identity=callsign or registration or str(event['hex'])
        identifiers=[identity]
        if callsign and registration and registration.casefold()!=callsign.casefold():
            identifiers.append(registration)
        identifiers.append(event['aircraft_type'] or 'Aircraft')
        body=' · '.join(identifiers)
        if event['distance_km'] is not None:body+=f" · {event['distance_km']} km"
        if event['altitude_ft'] is not None:body+=f" · {event['altitude_ft']:,} ft"
        network=event['source']!='local'
        headers={'Title':event['rule_label']+(' (network)' if network else '')+' nearby',
                 'Priority':'3','Content-Type':'text/plain; charset=utf-8'}
        # A network-only aircraft may not exist on the LOCAL tar1090 map.
        click_url=None if network else _tar1090_local_click_url(event['hex'])
        if click_url:headers['Click']=click_url
        if token:headers['Authorization']='Bearer '+token
        url=public['server']+'/'+public['topic']
        try:
            req=Request(url,body.encode(),headers=headers,method='POST')
            with opener(req,timeout=4) as result:
                if result.status < 200 or result.status>=300:raise OSError('ntfy returned HTTP '+str(result.status))
            with _lock, connect() as c:c.execute("UPDATE events SET delivery='sent',attempts=attempts+1,last_error=NULL WHERE id=?",(event['id'],))
        except (OSError,HTTPError,URLError,ValueError) as exc:
            attempts=event['attempts']+1
            delay=min(3600,30*2**min(7,attempts-1))
            with _lock, connect() as c:c.execute('UPDATE events SET attempts=?,next_attempt=?,last_error=? WHERE id=?',(attempts,now+delay,str(exc)[:180],event['id']))


def send_test(opener=urlopen):
    with _lock, connect() as c:
        public,token=notifier(c)
    if not public['topic']:raise ValueError('Set an ntfy topic first')
    headers={'Title':'Airspace Analytics test','Priority':'3','Content-Type':'text/plain; charset=utf-8'}
    click_url=_tar1090_local_click_url()
    if click_url:headers['Click']=click_url
    if token:headers['Authorization']='Bearer '+token
    req=Request(public['server']+'/'+public['topic'],b'Alerts are connected.',headers=headers,method='POST')
    try:
        with opener(req,timeout=5) as response:
            if response.status < 200 or response.status >= 300:raise ValueError('ntfy did not accept the test')
    except (OSError,URLError,HTTPError) as exc:raise ValueError('Could not deliver test to ntfy: '+str(exc)[:120])
    return {'ok':True}


def loop():
    while True:
        try:
            payload,lat,lon=read_receiver()
            process_snapshot(payload,lat,lon,
                             external=flyitaly.aircraft()+adsblol.aircraft()+adsbfi.aircraft()+regional_sources.aircraft())
            with _lock:_last_sample['source']=_last_good_url
        except Exception as exc:
            with _lock:_last_sample['error']=str(exc)[:180]
        try:deliver_pending()
        except Exception as exc:print('[alerts] ntfy:',str(exc)[:180],flush=True)
        time.sleep(POLL_SECONDS)


def regional_loop():
    """Additional sources are optional, shared and never block receiver matching."""
    while True:
        try:
            with _lock,connect() as c:
                receiver=receiver_settings(c)
                rows=c.execute('SELECT max_km FROM rules WHERE enabled=1 AND use_flyitaly=1 AND max_km IS NOT NULL').fetchall()
                keys={'AvioADSB':_avio_key(c),'ADSBiq':_adsbiq_key(c),'OpenSky Network':_opensky_credentials(c)}
                verified=_provider_tests(c)
            area=None
            if rows and receiver['lat'] is not None and receiver['lon'] is not None:
                area=(receiver['lat'],receiver['lon'],min(450.,max(10.,*(float(r['max_km'])+5 for r in rows))))
            regional_sources.configure(area,keys,verified)
        except Exception:
            pass
        time.sleep(10)


def flyitaly_loop():
    """Independent network polling: never block the local 3-second alert worker."""
    while True:
        interval=20
        try:
            with _lock, connect() as c:
                key=_flyitaly_key(c)
                receiver=receiver_settings(c)
                rows=c.execute('SELECT max_km FROM rules WHERE enabled=1 AND use_flyitaly=1').fetchall()
            if key and rows and receiver['lat'] is not None and receiver['lon'] is not None:
                # Always use km. 500 km is within the provider's Free plan.
                radius=min(500.,max(75.,*(float(row['max_km'] or 100) for row in rows)))
                try:flyitaly.fetch(key,receiver['lat'],receiver['lon'],radius)
                except ValueError:pass   # Status is visible without exposing keys
                interval=12
            else:
                flyitaly.discard_aircraft()
        except Exception:
            # Optional network failure must never affect the local alerts.
            pass
        time.sleep(interval)


def adsblol_loop():
    """Optional adsb.lol feeder API, separate from local and FlyItaly workers."""
    while True:
        interval=30
        try:
            with _lock, connect() as c:
                key=_adsblol_key(c)
                receiver=receiver_settings(c)
                rows=c.execute('SELECT max_km FROM rules WHERE enabled=1 AND use_flyitaly=1').fetchall()
            if key and rows and receiver['lat'] is not None and receiver['lon'] is not None:
                radius=min(450.,max(75.,*(float(row['max_km'] or 100) for row in rows)))
                try:adsblol.fetch(key,receiver['lat'],receiver['lon'],radius)
                except ValueError:pass
            else:adsblol.discard_aircraft()
        except Exception:pass
        time.sleep(interval)


def adsbfi_loop():
    """Conservative one-minute keyless public API, only for opted-in rules."""
    while True:
        interval=60
        try:
            with _lock, connect() as c:
                receiver=receiver_settings(c)
                rows=c.execute('SELECT max_km FROM rules WHERE enabled=1 AND use_flyitaly=1').fetchall()
            if rows and receiver['lat'] is not None and receiver['lon'] is not None:
                radius=min(450.,max(55.,*(float(row['max_km'] or 80) for row in rows)))
                try:adsbfi.fetch(receiver['lat'],receiver['lon'],radius)
                except ValueError:pass
            else:adsbfi.discard_aircraft()
        except Exception:pass
        time.sleep(interval)


def start():
    global _worker_started
    with _lock:
        if _worker_started:return
        _worker_started=True
        Thread=threading.Thread(target=loop,name='airspace-alerts',daemon=True)
        Thread.start()
        threading.Thread(target=flyitaly_loop,name='airspace-flyitaly',
                         daemon=True).start()
        threading.Thread(target=adsblol_loop,name='airspace-adsblol',
                         daemon=True).start()
        threading.Thread(target=adsbfi_loop,name='airspace-adsbfi',
                         daemon=True).start()
        threading.Thread(target=regional_loop,name='airspace-regional-sources',daemon=True).start()