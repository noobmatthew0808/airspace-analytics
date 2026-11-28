"""Personal trip tracking; independent of flight log and Aerodrome writes."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from contextlib import contextmanager
import json, os, re, sqlite3, threading, time, uuid
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from . import alerts, flights_log, flights_cache, acars, new_networks, live_details

PATH=Path(__file__).resolve().parents[1]/'.airspace-state'/'tracker.sqlite3'
PROVIDERS={'flightbyte':('FlightByte',110,600),'aviationstack':('Aviationstack',90,900),
           'airlabs':('AirLabs',900,300),'aerodatabox':('AeroDataBox',60,600),
           'mapflights':('map.flights',200,180),'weather':('Aviation Weather Center',200,900)}
PRIORITY={'mapflights':4,'flightbyte':3,'aerodatabox':3,'aviationstack':2,'airlabs':1,'weather':1}
LABELS={'dep_gate':'Departure gate','arr_gate':'Arrival gate','dep_terminal':'Departure terminal',
        'arr_terminal':'Arrival terminal','belt':'Baggage carousel','status':'Flight status',
        'registration':'Aircraft registration','checkin':'Check-in desks','dep_est':'Departure time',
        'arr_est':'Arrival time'}
_lock=threading.RLock()
_started=False
_busy=set()
_sessions={}
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _open(req,timeout=10):
    return build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=timeout)
@contextmanager
def db():
    PATH.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with sqlite3.connect(str(PATH),timeout=8) as c:
        c.row_factory=sqlite3.Row
        c.executescript("""
        CREATE TABLE IF NOT EXISTS trips(id TEXT PRIMARY KEY, spec TEXT NOT NULL, fields TEXT NOT NULL DEFAULT '{}', active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS keys(provider TEXT PRIMARY KEY, secret TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(provider TEXT NOT NULL, at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS state(trip TEXT, provider TEXT, next INTEGER, note TEXT, PRIMARY KEY(trip,provider));
        CREATE TABLE IF NOT EXISTS timeline(id INTEGER PRIMARY KEY, trip TEXT, field TEXT, value TEXT, source TEXT, at INTEGER, delivery TEXT DEFAULT 'none');
        """)
        try:os.chmod(PATH,0o600)
        except OSError:pass
        yield c

def _date(value):
    s=str(value or '').strip()
    if re.fullmatch(r'\d{2}/\d{2}/\d{4}',s):s=s[6:]+'-'+s[3:5]+'-'+s[:2]
    try:return date.fromisoformat(s).isoformat()
    except ValueError:raise ValueError('Enter a valid flight date') from None
def _code(value):
    s=str(value or '').strip().upper()
    if not re.fullmatch(r'[A-Z]{3}',s):raise ValueError('Enter three-letter IATA airport codes')
    return s
def _flight(value):
    s=re.sub(r'\s+','',str(value or '').upper())
    if not re.fullmatch(r'[A-Z0-9]{2}\d{1,5}[A-Z]?',s):raise ValueError('Enter an airline flight number, e.g. BA123')
    return s
def clean(data):
    flight=_flight(data.get('flight'))
    day=_date(data.get('date'))
    origin,destination=_code(data.get('origin')),_code(data.get('destination'))
    if origin==destination:raise ValueError('Departure and arrival airports must differ')
    arrival=_date(data['arrival_date']) if data.get('arrival_date') else ''
    if arrival and abs((date.fromisoformat(arrival)-date.fromisoformat(day)).days)>2:raise ValueError('Check arrival date')
    if abs((date.fromisoformat(day)-date.today()).days)>365:raise ValueError('Choose a flight within one year')
    return dict(flight=flight,date=day,origin=origin,destination=destination,arrival_date=arrival,notify=data.get('notify') is True,acars=data.get('acars') is True)
def identity(s):return tuple(s[k] for k in ('flight','date','origin','destination'))
def suggestions(rows,existing,today=None):
    today=today or datetime.now(ZoneInfo('Europe/London')).date().isoformat()
    seen={identity(x) for x in existing}
    out=[]
    for row in rows:
        try:s=clean(dict(flight=row.get('flight_code'),date=row.get('date'),origin=row.get('from_airport'),destination=row.get('to_airport')))
        except (ValueError,TypeError):continue
        if s['date']<today or identity(s) in seen:continue
        seen.add(identity(s));out.append(s)
    return sorted(out,key=lambda s:s['date'])[:5]

def _keys(c):return {r['provider']:r['secret'] for r in c.execute('SELECT * FROM keys')}
def _usage(c,p,now):
    window=86400 if p in ('mapflights','weather') else 31*86400
    return c.execute('SELECT count(*) FROM attempts WHERE provider=? AND at>?',(p,now-window)).fetchone()[0]
def settings():
    now=int(time.time())
    with _lock,db() as c:
        keys=_keys(c)
        return {p:{'name':name,'key_set':bool(keys.get(p)),'used':_usage(c,p,now),'limit':limit}
                for p,(name,limit,_) in PROVIDERS.items() if p not in ('mapflights','weather')}
def save_key(data):
    p=data.get('provider')
    if p not in ('flightbyte','aviationstack','airlabs','aerodatabox'):raise ValueError('Invalid provider')
    with _lock,db() as c:
        if data.get('clear'):c.execute('DELETE FROM keys WHERE provider=?',(p,))
        else:
            key=str(data.get('key','')).strip()
            if not re.fullmatch(r'[A-Za-z0-9._-]{8,500}',key):raise ValueError('Invalid API key format')
            if p=='aerodatabox' and data.get('credit_only') is not True:raise ValueError('Confirm direct feeder credits only; no paid subscription')
            c.execute('INSERT OR REPLACE INTO keys VALUES(?,?)',(p,key))
        c.execute('DELETE FROM state WHERE provider=?',(p,))
    return {'ok':True}
def mutate(data):
    action=data.get('action')
    with _lock,db() as c:
        if action=='add':
            spec=clean(data)
            for row in c.execute('SELECT * FROM trips'):
                if identity(json.loads(row['spec']))==identity(spec):raise ValueError('This flight is already in your tracker')
            if c.execute('SELECT count(*) FROM trips').fetchone()[0]>=100:raise ValueError('Remove older tracked flights first')
            if c.execute('SELECT count(*) FROM trips WHERE active=1').fetchone()[0]>=8:raise ValueError('Maximum eight active trips')
            c.execute('INSERT INTO trips(id,spec) VALUES(?,?)',(uuid.uuid4().hex,json.dumps(spec)))
        elif action in ('pause','resume','delete','options','refresh'):
            id=str(data.get('id',''))
            row=c.execute('SELECT * FROM trips WHERE id=?',(id,)).fetchone()
            if not row:raise ValueError('Flight not found')
            if action=='delete':
                for table,col in (('trips','id'),('timeline','trip'),('state','trip')):c.execute('DELETE FROM '+table+' WHERE '+col+'=?',(id,))
                _sessions.pop(id,None)
            elif action in ('pause','resume'):
                if action=='resume' and c.execute('SELECT count(*) FROM trips WHERE active=1 AND id<>?',(id,)).fetchone()[0]>=8:raise ValueError('Maximum eight active trips')
                c.execute('UPDATE trips SET active=? WHERE id=?',(int(action=='resume'),id))
                if action=='pause':_sessions.pop(id,None)
            elif action=='options':
                spec=json.loads(row['spec']);spec.update(notify=data.get('notify') is True,acars=data.get('acars') is True)
                c.execute('UPDATE trips SET spec=? WHERE id=?',(json.dumps(spec),id))
                if not spec['acars']:_sessions.pop(id,None)
            elif action=='refresh':
                # Manual refresh never overrides provider cooldown or quota.
                pass
        else:raise ValueError('Unknown tracker action')
    return {'ok':True}

def _dict(v):return v if isinstance(v,dict) else {}
def _norm(v):return re.sub(r'\s+','',str(v or '').upper())
def _text(v):
    if not isinstance(v,(str,int,float)) or isinstance(v,bool):return ''
    s=str(v).strip()[:180]
    return s if s.lower() not in ('','unknown','n/a','null','none','-') else ''
def _put(out,**fields):
    out.update({k:s for k,v in fields.items() if (s:=_text(v))})
def _time(v):
    if not isinstance(v,str):return ''
    try:return datetime.fromisoformat(v.replace('Z','+00:00')).isoformat()
    except ValueError:return ''
def _clock(out,prefix,scheduled,estimated,actual=None):
    _put(out,**{prefix+'_scheduled':_time(scheduled),prefix+'_est':_time(estimated),prefix+'_actual':_time(actual)})
    if prefix=='arr' and _time(scheduled):out['arrival_date']=_time(scheduled)[:10]
def _matches(s,flight,origin,destination,day):
    return (_norm(flight)==s['flight'] and _norm(origin)==s['origin'] and _norm(destination)==s['destination'] and str(day or '')[:10]==s['date'])
def _one(rows):return rows[0] if len(rows)==1 else {}
def parse_flightbyte(payload,s):
    d=_dict(payload);dep=_dict(d.get('departure'));arr=_dict(d.get('arrival'))
    if not _matches(s,str(d.get('carrierCode',''))+str(d.get('flightNumber','')),_dict(dep.get('airport')).get('iata'),_dict(arr.get('airport')).get('iata'),d.get('date')):return {}
    out={}
    for pre,row in (('dep',dep),('arr',arr)):
        _put(out,**{pre+'_gate':row.get('gate'),pre+'_terminal':row.get('terminal')})
        t=_dict(row.get('times'))
        _clock(out,pre,*[_dict(t.get(x)).get('local') for x in ('scheduledGate','estimatedGate','actualGate')])
    _put(out,belt=arr.get('baggage'),status=_dict(d.get('status')).get('label'),registration=_dict(d.get('equipment')).get('tailNumber'),aircraft_type=_dict(d.get('equipment')).get('name'))
    return out
def parse_aviationstack(payload,s):
    rows=_dict(payload).get('data')
    if not isinstance(rows,list):return {}
    r=_one([x for x in rows if isinstance(x,dict) and _matches(s,_dict(x.get('flight')).get('iata'),_dict(x.get('departure')).get('iata'),_dict(x.get('arrival')).get('iata'),x.get('flight_date'))])
    if not r:return {}
    out={}
    for pre,field in (('dep','departure'),('arr','arrival')):
        x=_dict(r.get(field))
        _put(out,**{pre+'_gate':x.get('gate'),pre+'_terminal':x.get('terminal')})
        _clock(out,pre,x.get('scheduled'),x.get('estimated'),x.get('actual'))
    _put(out,belt=_dict(r.get('arrival')).get('baggage'),status=r.get('flight_status'),registration=_dict(r.get('aircraft')).get('registration'),aircraft_type=_dict(r.get('aircraft')).get('iata'))
    return out
def parse_airlabs(payload,s):
    rows=_dict(payload).get('response')
    if isinstance(rows,dict):rows=[rows]
    if not isinstance(rows,list):return {}
    r=_one([x for x in rows if isinstance(x,dict) and _matches(s,x.get('flight_iata'),x.get('dep_iata'),x.get('arr_iata'),x.get('dep_time'))])
    if not r:return {}
    out={}
    for pre in ('dep','arr'):
        _put(out,**{pre+'_gate':r.get(pre+'_gate'),pre+'_terminal':r.get(pre+'_terminal')})
        _clock(out,pre,r.get(pre+'_time'),r.get(pre+'_estimated'),r.get(pre+'_actual'))
    _put(out,belt=r.get('arr_baggage'),status=r.get('status'),registration=r.get('reg_number'),aircraft_type=r.get('aircraft_icao'),callsign=r.get('flight_icao'))
    return out
def parse_aerodatabox(payload,s):
    if not isinstance(payload,list):return {}
    r=_one([x for x in payload if isinstance(x,dict) and _matches(s,x.get('number'),_dict(_dict(x.get('departure')).get('airport')).get('iata'),_dict(_dict(x.get('arrival')).get('airport')).get('iata'),_dict(_dict(x.get('departure')).get('scheduledTime')).get('local'))])
    if not r:return {}
    out={}
    for pre,k in (('dep','departure'),('arr','arrival')):
        x=_dict(r.get(k))
        _put(out,**{pre+'_gate':x.get('gate'),pre+'_terminal':x.get('terminal')})
        _clock(out,pre,_dict(x.get('scheduledTime')).get('local'),_dict(x.get('revisedTime')).get('local'))
    _put(out,belt=_dict(r.get('arrival')).get('baggageBelt'),checkin=_dict(r.get('departure')).get('checkInDesk'),status=r.get('status'),registration=_dict(r.get('aircraft')).get('reg'),aircraft_type=_dict(r.get('aircraft')).get('model'),callsign=r.get('callSign'))
    return out
def parse_board(payload,s,direction,day,now=None):
    now=time.time() if now is None else now
    d=_dict(payload);airport=s['origin'] if direction=='dep' else s['destination']
    other=s['destination'] if direction=='dep' else s['origin']
    if d.get('iata')!=airport or d.get('dir')!=direction or d.get('date')!=day or d.get('truncated') is True:return {}
    rows=d.get('rows')
    if not isinstance(rows,list):return {}
    r=_one([x for x in rows if isinstance(x,dict) and (_norm(x.get('flightNumber'))==s['flight'] or s['flight'] in [_norm(v) for v in (x.get('codeshares') or []) if isinstance(v,str)]) and _dict(x.get('counterpart')).get('iata')==other and x.get('basis') in ('board','schedule')])
    if not r:return {}
    out={}
    # Board times are absolute instants; display using its own airport timezone.
    def local(v):
        t=_time(v)
        try:
            dt=datetime.fromisoformat(t)
            return dt.astimezone(ZoneInfo(d['tz'])).isoformat() if dt.tzinfo else ''
        except (ValueError,KeyError,TypeError):return ''
    _clock(out,direction,local(r.get('planTime')),local(r.get('estTime')))
    _put(out,callsign=r.get('callsign'),aircraft_type=r.get('typecode'))
    stamp=new_networks._stamp(d.get('boardFetched'))
    if d.get('source')=='feed' and r.get('basis')=='board' and stamp is not None and -10<=now-stamp<=900:
        _put(out,**{direction+'_gate':r.get('gate'),direction+'_terminal':r.get('terminal')})
        if direction=='arr':_put(out,belt=r.get('belt'))
        if direction=='dep':_put(out,status=r.get('status'))
    else:
        out.pop(direction+'_est',None)
    return out

def _json(url,key='',header='X-API-Key'):
    req=Request(url,headers={'Accept':'application/json','User-Agent':'AirspaceAnalytics-Tracker/1',**({header:key} if key else {})})
    try:
        with _open(req) as res:
            raw=res.read(3_000_001)
        if len(raw)>3_000_000:raise ValueError('Response too large')
        return json.loads(raw) if raw else {}
    except HTTPError as e:raise ValueError('HTTP '+str(e.code)) from None
    except (URLError,OSError,ValueError,TypeError):raise ValueError('Provider unavailable or invalid JSON') from None
def _request(p,s,key,fields):
    flight=s['flight'];day=s['date']
    if p=='flightbyte':
        return parse_flightbyte(_json('https://api.flightbyte.dev/v1/flights/'+flight[:2]+'/'+flight[2:]+'/'+day+'?'+urlencode({'origin':s['origin'],'destination':s['destination']}),key),s)
    if p=='aviationstack':
        return parse_aviationstack(_json('https://api.aviationstack.com/v1/flights?'+urlencode({'access_key':key,'flight_iata':flight,'dep_iata':s['origin'],'arr_iata':s['destination'],'limit':10})),s)
    if p=='airlabs':
        return parse_airlabs(_json('https://airlabs.co/api/v9/schedules?'+urlencode({'api_key':key,'flight_iata':flight,'dep_iata':s['origin'],'arr_iata':s['destination']})),s)
    if p=='aerodatabox':
        return parse_aerodatabox(_json('https://api.aerodatabox.com/flights/Number/'+flight+'/'+day,key),s)
    if p=='weather':
        out={}
        airports=live_details._airports()
        for pre,port in (('dep',s['origin']),('arr',s['destination'])):
            code=next((icao for icao,iata in airports.items() if iata==port and re.fullmatch(r'[A-Z]{4}',icao)),None)
            if not code:continue
            # Charge at most two requests per scheduled weather cycle; grouped in one URL below.
            out[pre]=code
        if not out:return {}
        data=_json('https://aviationweather.gov/api/data/metar?'+urlencode({'ids':','.join(out.values()),'format':'json'}))
        return {pre+'_weather':r['rawOb'] for pre,code in out.items() for r in (data if isinstance(data,list) else []) if isinstance(r,dict) and r.get('icaoId')==code and _text(r.get('rawOb'))}
    raise ValueError('Unknown provider')

def _field(fields,k):return _dict(fields.get(k)).get('value','')
def _due_date(s,now):
    d=date.fromisoformat(s['date'])
    return (d-datetime.fromtimestamp(now,timezone.utc).date()).days
def _eligible(s,p,now):
    delta=_due_date(s,now)
    if delta < -2:return False
    if p in ('flightbyte','aerodatabox'):return delta<=7
    return delta<=1
def _claim(c,id,p,s,now):
    name,limit,interval=PROVIDERS[p]
    if _usage(c,p,now)>=limit:return False
    r=c.execute('SELECT next FROM state WHERE trip=? AND provider=?',(id,p)).fetchone()
    if r and r['next']>now:return False
    delay=interval if _due_date(s,now)<=0 else max(interval,3600)
    # Store the charge before network I/O. Restarting or switching keys never resets quotas.
    c.execute('INSERT INTO attempts VALUES(?,?)',(p,now))
    c.execute('INSERT OR REPLACE INTO state VALUES(?,?,?,?)',(id,p,now+delay,'Checking'))
    return True
def _merge(fields,values,p,now):
    changes=[]
    for k,v in values.items():
        v=_text(v)
        if not v:continue
        previous=_dict(fields.get(k));old=previous.get('value')
        if previous and previous.get('source')!=p and PRIORITY.get(previous.get('source'),0)>PRIORITY[p] and now-previous.get('at',0)<1800:continue
        if old!=v and k in LABELS:changes.append((k,v))
        fields[k]={'value':v,'source':p,'at':now}
    return changes
def _board_request(s,key,fields,direction):
    day=s['date'] if direction=='dep' else s.get('arrival_date') or _field(fields,'arrival_date')
    if not day:return {}
    airport=s['origin'] if direction=='dep' else s['destination']
    delta=(date.fromisoformat(day)-datetime.now(timezone.utc).date()).days
    if delta not in (-1,0,1):return {}
    value=new_networks._request(new_networks.MAP,'/airports/'+airport+'/day-board?'+urlencode({'dir':direction,'day':delta}),key)
    return parse_board(value,s,direction,day)

def _work(id,s,p,key,fields,scope=None):
    now=int(time.time())
    result={};note='Provider unavailable'
    try:
        result=_board_request(s,key,fields,scope) if p=='mapflights' else _request(p,s,key,fields)
        note='Matched flight · '+str(len(result))+' fields' if result else 'No matching data'
    except (ValueError,OSError,TypeError,KeyError) as e:
        result={};note=(str(e).replace(key,'[redacted]') if key else str(e))[:100]
    finally:
        with _lock,db() as c:
            row=c.execute('SELECT * FROM trips WHERE id=?',(id,)).fetchone()
            if row and row['active']:
                spec=json.loads(row['spec']);current=json.loads(row['fields'])
                changes=_merge(current,result,p,now)
                c.execute('UPDATE trips SET fields=? WHERE id=?',(json.dumps(current),id))
                for k,v in changes:
                    c.execute('INSERT INTO timeline(trip,field,value,source,at,delivery) VALUES(?,?,?,?,?,?)',(id,k,v,p,now,'pending' if spec['notify'] else 'none'))
                slot=p if not scope else p+'-'+scope
                c.execute('UPDATE state SET note=? WHERE trip=? AND provider=?',(note,id,slot))
                if 'HTTP 429' in note or 'HTTP 402' in note or 'HTTP 401' in note or 'HTTP 403' in note:
                    c.execute('UPDATE state SET next=max(next,?) WHERE trip=? AND provider=?',(now+3600,id,slot))
            _busy.discard(p)

def _mapkey():
    with alerts._lock,alerts.connect() as c:
        return alerts._mapflights_key(c) if alerts._provider_tests(c).get('mapflights',{}).get('ok') else ''
def tick():
    now=int(time.time())
    mapkey=_mapkey()
    with _lock,db() as c:
        keys=_keys(c)
        rows=c.execute('SELECT * FROM trips WHERE active=1').fetchall()
        c.execute('DELETE FROM attempts WHERE at<?',(now-32*86400,))
        # Keep provider-derived flight data for at most seven days after the last update.
        c.execute("DELETE FROM timeline WHERE at<?",(now-7*86400,))
        for row in c.execute('SELECT id,fields FROM trips').fetchall():
            fields=json.loads(row['fields']);trim={k:v for k,v in fields.items() if now-v.get('at',0)<7*86400}
            if trim!=fields:c.execute('UPDATE trips SET fields=? WHERE id=?',(json.dumps(trim),row['id']))
        for row in rows:
            id=row['id'];s=json.loads(row['spec']);fields=json.loads(row['fields'])
            if _due_date(s,now)<-2:
                c.execute('UPDATE trips SET active=0 WHERE id=?',(id,));_sessions.pop(id,None);continue
            for p,key in {**keys,'mapflights':mapkey,'weather':''}.items():
                if p not in PROVIDERS or p in _busy or not _eligible(s,p,now) or (p!='weather' and not key):continue
                if p=='mapflights':
                    if new_networks.api_budget.remaining(new_networks.MAP)>0:continue
                    scope=next((x for x in ('dep','arr') if (x=='dep' or s.get('arrival_date') or _field(fields,'arrival_date')) and not c.execute('SELECT 1 FROM state WHERE trip=? AND provider=? AND next>?',(id,p+'-'+x,now)).fetchone()),None)
                    if not scope or _usage(c,p,now)>=PROVIDERS[p][1]:continue
                    c.execute('INSERT INTO attempts VALUES(?,?)',(p,now))
                    c.execute('INSERT OR REPLACE INTO state VALUES(?,?,?,?)',(id,p+'-'+scope,now+180,'Checking'))
                else:
                    scope=None
                    if not _claim(c,id,p,s,now):continue
                _busy.add(p)
                threading.Thread(target=_work,args=(id,s,p,key,fields,scope),daemon=True,name='tracker-'+p).start()
    # Existing ACARS engine stays alive; only explicitly enabled trips with
    # a provider-matched registration/callsign are followed, near travel day.
    for row in rows:
        id=row['id'];s=json.loads(row['spec']);fields=json.loads(row['fields'])
        if not s['acars'] or not -1<=_due_date(s,now)<=0:continue
        query=_field(fields,'callsign') or _field(fields,'registration')
        if not query:continue
        kind='flight' if _field(fields,'callsign') else 'reg'
        try:
            with _lock:session=_sessions.get(id)
            if session and session[0]==query:
                try:acars.read(session[1]);continue
                except ValueError:pass
            result=acars.search({'query':query,'kind':kind,'hours':6})
            with _lock:_sessions[id]=(query,result['id'])
        except (ValueError,OSError):pass
def deliver():
    with _lock,db() as c:
        row=c.execute("SELECT t.*,s.spec,s.active FROM timeline t JOIN trips s ON t.trip=s.id WHERE delivery='pending' ORDER BY t.id LIMIT 1").fetchone()
        if not row:return
        spec=json.loads(row['spec'])
        # Claim before send to avoid repeated notifications on restart.
        c.execute("UPDATE timeline SET delivery='sending' WHERE id=?",(row['id'],))
    state='skipped'
    if spec['notify'] and row['active']:
        try:
            with alerts._lock,alerts.connect() as c:cfg,token=alerts.notifier(c)
            if cfg['topic']:
                headers={'Title':spec['flight']+' - '+LABELS[row['field']],'Priority':'3','Cache':'no','Content-Type':'text/plain'}
                if token:headers['Authorization']='Bearer '+token
                body=(LABELS[row['field']]+': '+row['value']+' ('+PROVIDERS[row['source']][0]+')').encode()
                with _open(Request(cfg['server']+'/'+cfg['topic'],data=body,headers=headers,method='POST')) as response:
                    state='sent' if 200<=response.status<300 else 'failed'
            else:state='ntfy not configured'
        except (ValueError,OSError,KeyError):state='failed'
    with _lock,db() as c:c.execute('UPDATE timeline SET delivery=? WHERE id=?',(state,row['id']))
def snapshot():
    now=int(time.time())
    with _lock,db() as c:
        result=[]
        for row in c.execute('SELECT * FROM trips ORDER BY active DESC').fetchall():
            s=json.loads(row['spec']);fields=json.loads(row['fields']);id=row['id']
            item={**s,'id':id,'active':bool(row['active']),'fields':fields,'sources':[dict(x) for x in c.execute('SELECT provider,note,next FROM state WHERE trip=?',(id,))],
                  'events':[dict(x) for x in c.execute('SELECT field,value,source,at,delivery FROM timeline WHERE trip=? ORDER BY id DESC LIMIT 25',(id,))]}
            reg=_field(fields,'registration');call=_field(fields,'callsign')
            if reg and call and re.fullmatch(r'[A-Z0-9-]{2,16}',reg) and -1<=_due_date(s,now)<=0 and flights_cache._started:
                live=flights_cache.read(reg)['aircraft'].get(reg,{})
                if _norm(live.get('callsign'))==_norm(call) and 0<=now-(live.get('last_observed_at') or 0)<=120:
                    item['live']={k:live.get(k) for k in ('status','source','hex','last_observed_at')}
            session=_sessions.get(id)
            if session and item['active'] and s['acars']:
                try:
                    messages=acars.read(session[1])
                    item['messages']=messages['messages'][:30];item['acars_sources']=messages['providers']
                except ValueError:pass
            result.append(item)
        existing=[dict(x) for x in result]
    # No network request when opening tracker: use the existing log cache.
    rows=flights_log._CACHE.get('rows') or []
    return {'trips':sorted(result,key=lambda x:(not x['active'],x['date'])),'suggestions':suggestions(rows,existing),'checked_at':now}
def start():
    global _started
    if _started:return
    _started=True
    def run():
        while True:
            try:tick();deliver()
            except Exception as e:print('Tracker refresh failed: '+type(e).__name__,flush=True)
            time.sleep(5)
    threading.Thread(target=run,daemon=True,name='airspace-tracker').start()
