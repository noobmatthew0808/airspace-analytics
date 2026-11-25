"""Optional additional personal flight-log sources; never feed network data to readsb.
All lookups use fixed documented hosts and retain only the tracked airframes.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
import socket
from . import api_budget
import math
import re
import threading
import time
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

TOKEN_URL='https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token'
STATES_URL='https://opensky-network.org/api/states/all'
AIRPLANES_URL='https://api.airplanes.live/v2/reg/'
AGENT='AirspaceAnalytics-Flights/5'
_lock=threading.RLock()
_tokens={}
_cache={}
_busy=set()
_next={}
_errors={}
_targets={}
_cursor=0
_hub_enabled=False
_hub_running=False
_hub_touch=0
_hub_fields={}
_known={}
_airplanes_test=None
_hub_region=None
_hub_region_enabled=False
_hub_region_touch=0
_hub_last_message=0

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _open(request,timeout=8):
    return build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=timeout)

def _json(url,headers=None,body=None,opener=None,limit=4_000_000,provider=None):
    request=Request(url,data=body,headers={'User-Agent':AGENT,'Accept':'application/json',**(headers or {})})
    try:
        open_call=(lambda req,timeout:api_budget.open_request(provider,_open,req,timeout)) if provider and opener is None else (opener or _open)
        with open_call(request,timeout=8) as response:
            raw=response.read(limit+1)
            if len(raw)>limit:raise ValueError('Response too large')
            result=json.loads(raw)
            return result
    except HTTPError as e:
        retry=e.headers.get('X-Rate-Limit-Retry-After-Seconds',e.headers.get('Retry-After','')) if e.headers else ''
        raise ValueError('HTTP '+str(e.code)+(' retry '+retry if retry.isdigit() else '')) from None
    except ValueError as error:
        if 'rate limited; retry' in str(error):raise
        raise ValueError('Network or invalid API response') from None
    except (URLError,OSError,TypeError,UnicodeError):
        raise ValueError('Network or invalid API response') from None

def _number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)

def _token(credentials,opener=None):
    client,secret=credentials['client_id'],credentials['client_secret']
    identity=(client,secret)
    with _lock:
        old=_tokens.get(identity)
        if old and old[1]>time.monotonic():return old[0]
    result=_json(TOKEN_URL,{'Content-Type':'application/x-www-form-urlencoded'},
                 urlencode({'grant_type':'client_credentials','client_id':client,'client_secret':secret}).encode(),opener,64_000)
    token=result.get('access_token') if isinstance(result,dict) else None
    if not isinstance(token,str) or not token or len(token)>16000:raise ValueError('Invalid OAuth token response')
    duration=result.get('expires_in',1800)
    if not _number(duration):duration=1800
    with _lock:
        _tokens.clear()
        _tokens[identity]=(token,time.monotonic()+max(1,min(duration,1800)-30))
    return token

def parse_opensky(payload,identities,now=None,allow_unknown=False):
    """The API reports ICAO hex, not registration. Never guess a registration."""
    now=time.time() if now is None else now
    if not isinstance(payload,dict) or not _number(payload.get('time')) or not -10<=now-payload['time']<=50:
        raise ValueError('Stale or invalid OpenSky response')
    states=payload.get('states')
    if states is None:return []
    if not isinstance(states,list):raise ValueError('Invalid OpenSky states')
    result=[]
    for row in states:
        if not isinstance(row,list) or len(row)<17:continue
        hexcode=str(row[0]).lower()
        if not re.fullmatch(r'[a-f0-9]{6}',hexcode) or (not allow_unknown and hexcode not in identities) or not _number(row[4]) or not -10<=now-row[4]<=120:continue
        plane={'hex':hexcode,'r':identities.get(hexcode,''),'flight':str(row[1] or '').strip(),
               'seen':max(0,now-row[4]),'_source':'OpenSky Network'}
        if row[8] is True:plane['alt_baro']='ground'
        elif _number(row[7]):plane['alt_baro']=row[7]*3.280839895
        if _number(row[9]):plane['gs']=row[9]*1.943844492
        if all(_number(v) for v in (row[3],row[5],row[6])) and -10<=now-row[3]<=120 and -180<=row[5]<=180 and -90<=row[6]<=90:
            plane.update(lon=row[5],lat=row[6],seen_pos=max(0,now-row[3]))
        result.append(plane)
    return result

def opensky_lookup(credentials,identities,opener=None):
    if not credentials.get('permission'):raise ValueError('Written OpenSky permission required for automated use')
    if not identities:return []
    url=STATES_URL+'?'+urlencode([('icao24',h) for h in sorted(identities)[:80]])
    token=_token(credentials,opener)
    try:payload=_json(url,{'Authorization':'Bearer '+token},opener=opener,provider='OpenSky Network')
    except ValueError as error:
        if str(error)!='HTTP 401':raise
        with _lock:_tokens.clear()
        payload=_json(url,{'Authorization':'Bearer '+_token(credentials,opener)},opener=opener,provider='OpenSky Network')
    return parse_opensky(payload,identities)

def opensky_region(credentials,area):
    if not credentials.get('permission'):raise ValueError('Written OpenSky permission required for automated use')
    lat,lon,km=area
    dlat=min(2.,km/110.5)
    dlon=min(3.,km/(111.32*max(.2,math.cos(math.radians(lat)))))
    url=STATES_URL+'?'+urlencode({'lamin':max(-90,lat-dlat),'lamax':min(90,lat+dlat),
                                  'lomin':max(-180,lon-dlon),'lomax':min(180,lon+dlon)})
    payload=_json(url,{'Authorization':'Bearer '+_token(credentials)},provider='OpenSky Network')
    with _lock:identities=dict(_targets)
    return parse_opensky(payload,identities,allow_unknown=True)

def test_opensky(credentials,opener=None):
    # No unfiltered global query. Test OAuth, then check one valid hex from
    # the tracked registrations if available; even zero states is valid.
    if not credentials.get('permission'):raise ValueError('Written OpenSky permission required for automated use')
    with _lock:identities=dict(_targets)
    if identities:opensky_lookup(credentials,dict(list(identities.items())[:1]),opener)
    else:
        # Token verification alone cannot establish data endpoint access.
        raise ValueError('No known aircraft hex yet; open Flights before testing')
    return {'ok':True,'plan':'OAuth and data endpoint verified'}

def airplanes_lookup(reg,opener=None):
    if not re.fullmatch(r'[A-Z0-9-]{2,16}',reg):raise ValueError('Invalid registration')
    try:payload=_json(AIRPLANES_URL+reg,opener=opener,provider='airplanes.live')
    except ValueError as error:
        if str(error)=='HTTP 404':return []
        raise
    now=time.time()
    if not isinstance(payload,dict) or not isinstance(payload.get('ac'),list):raise ValueError('Invalid airplanes.live response')
    stamp=payload.get('now')
    if not _number(stamp):raise ValueError('Missing aircraft timestamp')
    if stamp>1e11:stamp/=1000
    if not -10<=now-stamp<=50:raise ValueError('Stale airplanes.live response')
    result=[]
    for row in payload['ac']:
        if not isinstance(row,dict) or str(row.get('r','')).replace('-','').upper()!=reg.replace('-',''):continue
        p=dict(row,r=reg,_source='airplanes.live')
        for field in ('seen','seen_pos'):
            age=p.get(field)
            if _number(age) and 0<=age<=120:p[field]=age+max(0,now-stamp)
            else:p.pop(field,None)
        result.append(p)
    return result

def test_airplanes():
    # A small public-airport area verifies a real HTTP 200 response. Never
    # report an unknown registration's 404 as successful authentication.
    global _airplanes_test
    with _lock:
        now=time.monotonic()
        if _airplanes_test and now-_airplanes_test[0]<900:
            ok,value=_airplanes_test[1:]
            if not ok:raise ValueError(value)
            return {**value,'plan':'Recently verified feeder API'}
        if 'airplanes.live' in _busy:
            raise ValueError('Background lookup in progress; retry after it completes')
        _busy.add('airplanes.live')
        _next['airplanes.live']=max(_next.get('airplanes.live',0),now+240)
    try:
        payload=_json('https://api.airplanes.live/v2/point/51.47/-0.45/10',provider='airplanes.live')
        if not isinstance(payload,dict) or not isinstance(payload.get('ac'),list):
            raise ValueError('Invalid airplanes.live response')
        value={'ok':True,'plan':'Feeder API accessible','aircraft':len(payload['ac'])}
        with _lock:_airplanes_test=(now,True,value)
        return value
    except ValueError as error:
        with _lock:
            _airplanes_test=(now,False,str(error))
            match=re.search(r'retry (\d+)',str(error))
            wait=int(match[1]) if match else (86400 if 'HTTP 429' in str(error) else 900)
            _next['airplanes.live']=max(_next['airplanes.live'],now+wait)
        raise
    finally:
        with _lock:_busy.discard('airplanes.live')

def _sbs(line,now):
    """Parse current SBS messages; positions and flight state have independent ages."""
    fields=line.strip().split(',')
    if len(fields)<22 or fields[0]!='MSG' or not re.fullmatch(r'[a-fA-F0-9]{1,6}',fields[4]):return None
    # ADSBHub emits unpadded numeric ICAO24 addresses in SBS. Restore
    # canonical six-digit hexadecimal identifiers before matching airframes.
    hexcode=fields[4].lower().zfill(6)
    try:
        stamp=datetime.fromisoformat(fields[6].replace('/','-')+'T'+fields[7]).replace(tzinfo=timezone.utc).timestamp()
    except (ValueError,OverflowError):return None
    if not -10<=now-stamp<=120:return None
    values={}
    def number(i):
        try:
            v=float(fields[i])
            return v if math.isfinite(v) else None
        except (ValueError,TypeError):return None
    if fields[10].strip():values['flight']=fields[10].strip()[:8]
    altitude,speed,lat,lon=number(11),number(12),number(14),number(15)
    if fields[21] in ('-1','1'):values['alt_baro']='ground'
    elif altitude is not None:values['alt_baro']=altitude
    if speed is not None and 0<=speed<=2000:values['gs']=speed
    if lat is not None and lon is not None and -90<=lat<=90 and -180<=lon<=180:
        values['position']=(lat,lon)
    return hexcode,stamp,values

def test_adsbhub(connect=None):
    if connect is None:
        with _lock:
            if _hub_running and _hub_last_message and time.monotonic()-_hub_last_message<30:
                return {'ok':True,'plan':'Live SBS stream receiving data'}
    connect=connect or socket.create_connection
    connected=False
    received=False
    try:
        with connect(('data.adsbhub.org',5002),timeout=6) as sock:
            connected=True
            sock.settimeout(6)
            with sock.makefile('rb') as stream:
                deadline=time.monotonic()+6
                for _ in range(1000):
                    if time.monotonic()>deadline:break
                    line=stream.readline(2048)
                    if not line:break
                    received=True
                    if _sbs(line.decode('ascii','ignore'),time.time()):
                        return {'ok':True,'plan':'Live SBS stream accessible'}
    except (OSError,ValueError):
        pass
    if received:
        raise ValueError('ADSBHub connected and sent data, but no fresh valid SBS message was decoded; check Data Access protocol and clock')
    if connected:
        raise ValueError('ADSBHub connected but sent no data; check active station and Data Access IP')
    raise ValueError('ADSBHub TCP connection failed; check network access to port 5002')

def _hub_wanted():
    now=time.monotonic()
    return bool((_hub_enabled and now-_hub_touch<=90 and _targets) or
                (_hub_region_enabled and now-_hub_region_touch<=90 and _hub_region))

def set_region(area,enabled):
    global _hub_region,_hub_region_enabled,_hub_region_touch,_hub_running
    with _lock:
        _hub_region=area
        _hub_region_enabled=bool(area and enabled)
        _hub_region_touch=time.monotonic()
        if _hub_wanted() and not _hub_running:
            _hub_running=True
            threading.Thread(target=_hub_work,daemon=True,name='airspace-adsbhub').start()

def _hub_work():
    global _hub_running,_hub_last_message
    try:
        while True:
            with _lock:
                if not _hub_wanted():return
            try:
                with socket.create_connection(('data.adsbhub.org',5002),timeout=8) as sock:
                    sock.settimeout(10)
                    with sock.makefile('rb') as stream:
                        while True:
                            with _lock:
                                if not _hub_wanted():return
                            line=stream.readline(2048)
                            if not line:raise OSError('Stream disconnected')
                            item=_sbs(line.decode('ascii','ignore'),time.time())
                            if not item:continue
                            hexcode,stamp,values=item
                            with _lock:
                                _hub_last_message=time.monotonic()
                                _errors.pop('ADSBHub',None)
                                if hexcode not in _targets:
                                    if not _hub_region_enabled:continue
                                    if 'position' in values:
                                        from .regional_sources import nearby
                                        if not nearby(dict(zip(('lat','lon'),values['position'])),_hub_region):
                                            _hub_fields.pop(hexcode,None)
                                            continue
                                    elif hexcode not in _hub_fields:continue
                                    if hexcode not in _hub_fields and len(_hub_fields)>=3000:continue
                                record=_hub_fields.setdefault(hexcode,{})
                                for field,value in values.items():
                                    if stamp>=record.get(field,(0,None))[0]:record[field]=(stamp,value)
                                record['seen']=(max(stamp,record.get('seen',(0,None))[0]),True)
            except (OSError,ValueError):
                with _lock:_errors['ADSBHub']='Stream disconnected; retrying in 60 seconds'
                for _ in range(6):
                    time.sleep(10)
                    with _lock:
                        if not _hub_wanted():return
    finally:
        with _lock:_hub_running=False

def _hub_planes(regional=False):
    now=time.time()
    result=[]
    for hexcode,record in list(_hub_fields.items()):
        if now-record.get('seen',(0,None))[0]>120 or (hexcode not in _targets and not _hub_region_enabled):
            del _hub_fields[hexcode]
            continue
        if not regional and hexcode not in _targets:continue
        p={'hex':hexcode,'r':_targets.get(hexcode,''),'_source':'ADSBHub','seen':max(0,now-record['seen'][0])}
        for field,ttl in (('flight',120),('alt_baro',35),('gs',35),('position',35)):
            stamp,value=record.get(field,(0,None))
            if now-stamp>ttl:continue
            if field=='position':p.update(lat=value[0],lon=value[1],seen_pos=max(0,now-stamp))
            else:p[field]=value
        if 'alt_baro' in p or 'gs' in p:
            if regional:
                from .regional_sources import nearby
                if not nearby(p,_hub_region):continue
                p['_network_source']='ADSBHub'
            result.append(p)
    return result

def hub_nearby():
    with _lock:
        return _hub_planes(regional=True) if _hub_region_enabled else []

def collect(registrations,identities,missing,credentials=None,airplanes=False,hub=False):
    """Schedule independent, bounded work; return only fresh completed lookups."""
    global _cursor,_targets,_hub_enabled,_hub_running,_hub_touch
    now=time.monotonic()
    wanted=set(registrations)
    clean={h:r for h,r in identities.items() if re.fullmatch(r'[a-f0-9]{6}',h) and r in wanted}
    with _lock:
        for h,r in clean.items():
            for old,(reg,_) in list(_known.items()):
                if reg==r and old!=h:del _known[old]
            _known[h]=(r,now)
        for h,(r,stamp) in list(_known.items()):
            if r not in wanted or now-stamp>86400:del _known[h]
        clean={h:r for h,(r,_) in _known.items()}
        _targets=clean
        _hub_enabled=hub
        _hub_touch=now
        if _hub_wanted() and not _hub_running:
            _hub_running=True
            threading.Thread(target=_hub_work,daemon=True,name='airspace-adsbhub').start()
        def schedule(name,delay,work):
            if name in _busy or now<_next.get(name,0) or api_budget.remaining(name)>0:return
            _busy.add(name)
            _next[name]=now+delay
            def task():
                try:
                    started=time.monotonic()
                    found=work()
                    with _lock:
                        old=_cache.setdefault(name,{})
                        for p in found:
                            if _number(p.get('seen')):old[p['r']]=(started,p)
                        _errors.pop(name,None)
                except (OSError,ValueError) as error:
                    with _lock:
                        _errors[name]=str(error)[:120]
                        match=re.search(r'retry (\d+)',str(error))
                        wait=int(match[1]) if match else (86400 if 'HTTP 429' in str(error) else 900)
                        _next[name]=max(_next[name],time.monotonic()+wait)
                finally:
                    with _lock:_busy.discard(name)
            threading.Thread(target=task,daemon=True,name='airspace-extra-'+name).start()
        # 4 credits per query, at most 2,880/day even before active feeder upgrade.
        if credentials and credentials.get('permission') and clean:
            schedule('OpenSky Network',120,lambda:opensky_lookup(credentials,clean))
        if airplanes and registrations and now>=_next.get('airplanes.live',0):
            # Two 480-second schedules (registration and nearby) total <=360/day, plus manual checks.
            pool=sorted(set(missing)&wanted) or sorted(wanted)
            reg=pool[_cursor%len(pool)]
            _cursor+=1
            schedule('airplanes.live',480,lambda:airplanes_lookup(reg))
        result=[]
        for name,store in _cache.items():
            for reg,(stamp,p) in list(store.items()):
                elapsed=max(0,time.monotonic()-stamp)
                if elapsed>120 or reg not in wanted:
                    del store[reg]
                    continue
                if (name=='OpenSky Network' and not credentials) or (name=='airplanes.live' and not airplanes):continue
                plane=dict(p)
                for field in ('seen','seen_pos'):
                    if _number(plane.get(field)):plane[field]+=elapsed
                if plane.get('seen',999)<=120:result.append(plane)
        if hub:result.extend(_hub_planes())
        return result

def health():
    with _lock:
        return {name:{'matching_aircraft':len(_hub_planes()) if name=='ADSBHub' else len(_cache.get(name,{})),'error':_errors.get(name),
                      'retry_seconds':round(max(0,_next.get(name,0)-time.monotonic()))}
                for name in ('OpenSky Network','airplanes.live','ADSBHub')}
