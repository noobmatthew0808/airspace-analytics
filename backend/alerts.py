"""Persistent, receiver-local aircraft alert rules. No writes to Aerodrome or ADS-B services."""
from __future__ import annotations

import fnmatch
from contextlib import contextmanager, closing
import json
import math
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

STATE_DIR = Path(__file__).resolve().parents[1] / '.airspace-state'
DB_PATH = STATE_DIR / 'alerts.sqlite3'
POLL_SECONDS = 3
STALE_SECONDS = 30
LOST_SECONDS = 600
API_MAX = 12 * 1024
DEFAULT_RECEIVER_URLS = (
    'http://127.0.0.1:1099/map/data/aircraft.json',
    'http://127.0.0.1:1099/data/aircraft.json',
    'http://127.0.0.1:1099/map/aircraft.json',
    'http://127.0.0.1:8080/data/aircraft.json',
)
FIELDS = frozenset(('type', 'registration', 'callsign', 'hex', 'operator', 'military'))
GEO_HYSTERESIS_KM = 0.5
ALT_HYSTERESIS_FT = 300
_lock = threading.RLock()
_worker_started = False
_last_sample = {'time': None, 'aircraft': 0, 'error': 'Waiting for receiver', 'lat': None, 'lon': None}


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
        enabled INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL
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
        next_attempt INTEGER NOT NULL DEFAULT 0, last_error TEXT
    );
    CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')
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


def _number(v, lower, upper, name, integer=False):
    if v is None or v == '': return None
    try:
        x = float(v)
        if not math.isfinite(x) or x < lower or x > upper: raise ValueError()
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be between {lower:g} and {upper:g}')
    return int(x) if integer else round(x, 2)


def validate_rule(data):
    if not isinstance(data, dict): raise ValueError('Invalid rule')
    field = str(data.get('field', 'type')).lower()
    if field not in FIELDS: raise ValueError('Invalid match field')
    pattern = str(data.get('pattern', '')).upper().strip()
    if field == 'military': pattern = 'YES'
    else:
        parts = [v.strip() for v in pattern.split(',')]
        allowed = r'[A-Z0-9*?\- ]{1,60}' if field == 'operator' else r'[A-Z0-9*?\-]{1,16}'
        if not parts or len(parts) > 20 or any(not re.fullmatch(allowed, x) for x in parts):
            raise ValueError('Enter up to 20 values separated by commas (letters, numbers, * or ?)')
        pattern = ','.join(parts)
    label = str(data.get('label', '')).strip()
    if not label: label = pattern if field != 'military' else 'Military'
    if len(label) > 50 or any(ord(c)<32 for c in label): raise ValueError('Name must be 1–50 characters')
    max_km = _number(data.get('max_km'), 0.1, 1000, 'Distance')
    min_ft = _number(data.get('min_ft'), -2000, 70000, 'Minimum altitude', True)
    max_ft = _number(data.get('max_ft'), -2000, 70000, 'Maximum altitude', True)
    if min_ft is not None and max_ft is not None and min_ft > max_ft:
        raise ValueError('Minimum altitude must not exceed maximum')
    return {'label': label, 'field':field,'pattern':pattern, 'max_km': max_km,
            'min_ft':min_ft, 'max_ft':max_ft, 'enabled':int(bool(data.get('enabled',True)))}


def save_rule(data):
    item = validate_rule(data)
    with _lock, connect() as c:
        rule_id = data.get('id')
        if rule_id is not None:
            try: rule_id=int(rule_id)
            except (ValueError,TypeError): raise ValueError('Invalid rule ID')
            exists=c.execute('SELECT 1 FROM rules WHERE id=?',(rule_id,)).fetchone()
            if not exists: raise ValueError('Rule not found')
            c.execute('UPDATE rules SET label=?,field=?,pattern=?,max_km=?,min_ft=?,max_ft=?,enabled=? WHERE id=?',
                (*item.values(),rule_id))
            # Changing filters must not leave stale armed state from the old rule.
            c.execute('DELETE FROM occupancy WHERE rule_id=?',(rule_id,))
        else:
            cur=c.execute('INSERT INTO rules(label,field,pattern,max_km,min_ft,max_ft,enabled,created) VALUES(?,?,?,?,?,?,?,?)',
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


def receiver_settings(c):
    cfg = {row['key']:row['value'] for row in c.execute(
        "SELECT key,value FROM config WHERE key IN ('receiver_url','receiver_lat','receiver_lon')")}
    return {'url':cfg.get('receiver_url',''), 'lat':float(cfg['receiver_lat']) if cfg.get('receiver_lat') else None,
            'lon':float(cfg['receiver_lon']) if cfg.get('receiver_lon') else None}


def save_receiver(data):
    """Optional local feed URL / antenna location, stored only in alert state."""
    if not isinstance(data, dict): raise ValueError('Invalid receiver settings')
    url = str(data.get('url','')).strip()
    if len(url)>240: raise ValueError('Receiver URL is too long')
    if url:
        u=urlsplit(url)
        if (u.scheme!='http' or u.hostname not in ('localhost','127.0.0.1') or
                not u.port or not u.path.endswith('/aircraft.json') or
                u.username or u.password or u.query or u.fragment):
            raise ValueError('Use a localhost http://127.0.0.1:PORT/.../aircraft.json URL')
    raw_lat,raw_lon=data.get('lat'),data.get('lon')
    if (raw_lat in ('',None)) != (raw_lon in ('',None)):
        raise ValueError('Enter both antenna latitude and longitude, or leave both blank')
    lat=_number(raw_lat,-90,90,'Latitude')
    lon=_number(raw_lon,-180,180,'Longitude')
    with _lock, connect() as c:
        for key,value in (('receiver_url',url),('receiver_lat',str(lat) if lat is not None else ''),
                          ('receiver_lon',str(lon) if lon is not None else '')):
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',(key,value))


def notifier(c):
    cfg={row['key']:row['value'] for row in c.execute('SELECT key,value FROM config')}
    return {'server':cfg.get('server','https://ntfy.sh'), 'topic':cfg.get('topic',''),
            'token_set':bool(cfg.get('token',''))}, cfg.get('token','')


def snapshot():
    with _lock, connect() as c:
        rules=[dict(x) for x in c.execute('SELECT id,label,field,pattern,max_km,min_ft,max_ft,enabled FROM rules ORDER BY id DESC')]
        active={r['rule_id']:r['n'] for r in c.execute("SELECT rule_id,count(*) n FROM occupancy WHERE state='active' GROUP BY rule_id")}
        for r in rules:r['active']=active.get(r['id'],0)
        events=[dict(x) for x in c.execute('SELECT id,rule_id,rule_label,hex,callsign,registration,aircraft_type,distance_km,altitude_ft,created,delivery FROM events ORDER BY id DESC LIMIT 60')]
        pub,_=notifier(c)
        return {'rules':rules,'events':events,'ntfy':pub,'receiver':dict(_last_sample),
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


def process_snapshot(payload, receiver_lat, receiver_lon, now=None):
    """Transition each (rule,hex) independently, rearming on confirmed departure."""
    now=int(now if now is not None else time.time())
    aircraft=payload.get('aircraft',[])
    if not isinstance(aircraft,list):raise ValueError('Invalid receiver aircraft list')
    enrich_aircraft(aircraft)
    with _lock, connect() as c:
        rules=[dict(x) for x in c.execute('SELECT * FROM rules WHERE enabled=1')]
        current={(x['rule_id'],x['hex']):dict(x) for x in c.execute('SELECT * FROM occupancy')}
        # Keep active tracking state across brief signal gaps, Wi-Fi outages and restarts.
        seen=set()
        for plane in aircraft:
            if not isinstance(plane,dict):continue
            hexcode=str(plane.get('hex','')).lower().strip()
            if not re.fullmatch(r'~?[a-f0-9]{6}',hexcode):continue
            try:
                lat=float(plane['lat']) if plane.get('lat') is not None else None
                lon=float(plane['lon']) if plane.get('lon') is not None else None
            except (TypeError,ValueError):lat=lon=None
            if lat is not None and lon is not None and (not math.isfinite(lat) or not math.isfinite(lon) or not (-90<=lat<=90 and -180<=lon<=180)):
                lat=lon=None
            for rule in rules:
                key=(rule['id'],hexcode)
                old=current.get(key)
                match=_classify(rule,plane,lat,lon,receiver_lat,receiver_lon,bool(old and old['state']=='active'))
                if match is None:continue  # Cannot prove entry or departure.
                seen.add(key)
                if match is False:
                    if old:
                        count=old['outside_count']+1
                        if count >= 2:c.execute('DELETE FROM occupancy WHERE rule_id=? AND hex=?',key)
                        else:c.execute('UPDATE occupancy SET outside_count=?,last_seen=? WHERE rule_id=? AND hex=?',(count,now,*key))
                    continue
                if old and old['state']=='active':
                    c.execute('UPDATE occupancy SET outside_count=0,last_seen=? WHERE rule_id=? AND hex=?',(now,*key))
                    continue
                c.execute('INSERT OR REPLACE INTO occupancy(rule_id,hex,state,outside_count,last_seen) VALUES(?,?,\'active\',0,?)',(rule['id'],hexcode,now))
                c.execute('INSERT INTO events(rule_id,rule_label,hex,callsign,registration,aircraft_type,distance_km,altitude_ft,created,next_attempt) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (rule['id'],rule['label'],hexcode,str(plane.get('flight','')).strip()[:24],str(plane.get('r','')).strip()[:24],
                    str(plane.get('t','')).strip()[:12],match['distance_km'],match['altitude_ft'],now,now))
        # No observations are proof of *neither* entry nor exit. Only expire
        # states after an extended continuous, healthy monitoring period.
        for key,old in current.items():
            if key not in seen and now - old['last_seen'] >= LOST_SECONDS:
                c.execute('DELETE FROM occupancy WHERE rule_id=? AND hex=?',key)
        _last_sample.update(time=now, aircraft=len(aircraft), error=None,lat=receiver_lat,lon=receiver_lon)


def _get_json(url):
    request=Request(url,headers={'User-Agent':'AirspaceAnalytics-Alerts/1'})
    with urlopen(request,timeout=3) as result:
        if int(result.headers.get('Content-Length','0') or 0)>2_000_000:raise ValueError('Receiver response too large')
        raw=result.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Receiver response too large')
        return json.loads(raw)


def read_receiver():
    with _lock, connect() as c: stored=receiver_settings(c)
    custom=stored['url'] or os.environ.get('AIRSPACE_AIRCRAFT_URL','').strip()
    urls=(custom,) if custom else DEFAULT_RECEIVER_URLS
    err='Receiver URL unavailable'
    for url in urls:
        u=urlsplit(url)
        if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost') or not u.port or not u.path.endswith('/aircraft.json'):
            err='Receiver URL must use a localhost aircraft.json endpoint';continue
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
            # Manual settings override the receiver's optional metadata. A missing
            # location must NOT disable type, registration, or hex-only alerts.
            lat=stored['lat'] if stored['lat'] is not None else r.get('lat',r.get('latitude',a.get('lat',os.environ.get('AIRSPACE_RECEIVER_LAT'))))
            lon=stored['lon'] if stored['lon'] is not None else r.get('lon',r.get('longitude',a.get('lon',os.environ.get('AIRSPACE_RECEIVER_LON'))))
            lat=float(lat) if lat not in (None,'') else None
            lon=float(lon) if lon not in (None,'') else None
            if lat is not None and not (-90<=lat<=90):raise ValueError('Invalid antenna latitude')
            if lon is not None and not (-180<=lon<=180):raise ValueError('Invalid antenna longitude')
            return a,lat,lon
        except (ValueError,OSError,URLError,HTTPError,KeyError) as exc:
            err=str(exc)[:180]
    raise ValueError(err)


def check_receiver():
    sample,lat,lon=read_receiver()
    return {'ok':True,'aircraft':len(sample['aircraft']), 'coordinates_available':lat is not None and lon is not None}


def deliver_pending(now=None, opener=urlopen):
    now=int(now if now is not None else time.time())
    with _lock, connect() as c:
        # A forgotten/offline notification should not arrive hours after a flyover.
        c.execute("UPDATE events SET delivery='expired' WHERE delivery='pending' AND created<?",(now-900,))
        public,token=notifier(c)
        if not public['topic']:return
        pending=[dict(x) for x in c.execute("SELECT * FROM events WHERE delivery='pending' AND next_attempt<=? ORDER BY id LIMIT 5",(now,))]
    for event in pending:
        body=f"{event['callsign'] or event['registration'] or event['hex']} · {event['aircraft_type'] or 'Aircraft'}"
        if event['distance_km'] is not None:body+=f" · {event['distance_km']} km"
        if event['altitude_ft'] is not None:body+=f" · {event['altitude_ft']:,} ft"
        headers={'Title':event['rule_label']+' nearby','Priority':'3','Content-Type':'text/plain; charset=utf-8'}
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
            process_snapshot(payload,lat,lon)
        except Exception as exc:
            with _lock:_last_sample['error']=str(exc)[:180]
        try:deliver_pending()
        except Exception as exc:print('[alerts] ntfy:',str(exc)[:180],flush=True)
        time.sleep(POLL_SECONDS)


def start():
    global _worker_started
    with _lock:
        if _worker_started:return
        _worker_started=True
        Thread=threading.Thread(target=loop,name='airspace-alerts',daemon=True)
        Thread.start()