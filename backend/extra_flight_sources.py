"""Optional additional personal flight-log sources; never feed network data to readsb.
All lookups use fixed documented hosts and retain only the tracked airframes.
"""
from __future__ import annotations
import json
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

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _open(request,timeout=8):
    return build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=timeout)

def _json(url,headers=None,body=None,opener=None,limit=4_000_000):
    request=Request(url,data=body,headers={'User-Agent':AGENT,'Accept':'application/json',**(headers or {})})
    try:
        with (opener or _open)(request,timeout=8) as response:
            raw=response.read(limit+1)
            if len(raw)>limit:raise ValueError('Response too large')
            result=json.loads(raw)
            return result
    except HTTPError as e:
        retry=e.headers.get('X-Rate-Limit-Retry-After-Seconds',e.headers.get('Retry-After','')) if e.headers else ''
        raise ValueError('HTTP '+str(e.code)+(' retry '+retry if retry.isdigit() else '')) from None
    except (URLError,OSError,TypeError,UnicodeError,ValueError):
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

def parse_opensky(payload,identities,now=None):
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
        if hexcode not in identities or not _number(row[4]) or not -10<=now-row[4]<=120:continue
        plane={'hex':hexcode,'r':identities[hexcode],'flight':str(row[1] or '').strip(),
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
    try:payload=_json(url,{'Authorization':'Bearer '+token},opener=opener)
    except ValueError as error:
        if str(error)!='HTTP 401':raise
        with _lock:_tokens.clear()
        payload=_json(url,{'Authorization':'Bearer '+_token(credentials,opener)},opener=opener)
    return parse_opensky(payload,identities)

def test_opensky(credentials,opener=None):
    # No unfiltered global query. Test OAuth, then check one valid hex from
    # the tracked registrations if available; even zero states is valid.
    if not credentials.get('permission'):raise ValueError('Written OpenSky permission required for automated use')
    with _lock:identities=dict(_targets)
    if identities:opensky_lookup(credentials,dict(list(identities.items())[:1]),opener)
    else:
        # Token verification alone cannot establish data endpoint access.
        token=_token(credentials,opener)
        payload=_json(STATES_URL+'?icao24=000000',{'Authorization':'Bearer '+token},opener=opener)
        parse_opensky(payload,{})
    return {'ok':True,'plan':'OAuth and data endpoint verified'}

def airplanes_lookup(reg,opener=None):
    if not re.fullmatch(r'[A-Z0-9-]{2,16}',reg):raise ValueError('Invalid registration')
    try:payload=_json(AIRPLANES_URL+reg,opener=opener)
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
        p=dict(row,_source='airplanes.live')
        for field in ('seen','seen_pos'):
            age=p.get(field)
            if _number(age) and 0<=age<=120:p[field]=age+max(0,now-stamp)
            else:p.pop(field,None)
        result.append(p)
    return result

def test_airplanes():
    # This shares the background budget. A known registration is picked
    # from the current flight log rather than submitting an unbounded query.
    from . import flights_log
    regs=[]
    for row in flights_log.read_cached().get('flights',[]):
        reg=str(row.get('registration') or '').strip().upper()
        match=re.search(r'\(([^()]*)\)\s*$',reg)
        if match:reg=match[1].strip()
        if re.fullmatch(r'[A-Z0-9-]{2,16}',reg) and reg!='NO-REG':regs.append(reg)
    if not regs:raise ValueError('Load at least one registered aircraft in Flights first')
    with _lock:
        if time.monotonic()<_next.get('airplanes.live',0):raise ValueError('Wait for the next scheduled lookup to avoid excess requests')
        _next['airplanes.live']=time.monotonic()+180
    found=airplanes_lookup(regs[0])
    return {'ok':True,'plan':'Registration API accessible','aircraft':len(found)}

def collect(registrations,identities,missing,credentials=None,airplanes=False):
    """Schedule independent, bounded work; return only fresh completed lookups."""
    global _cursor,_targets
    now=time.monotonic()
    wanted=set(registrations)
    clean={h:r for h,r in identities.items() if re.fullmatch(r'[a-f0-9]{6}',h) and r in wanted}
    with _lock:
        _targets=clean
        def schedule(name,delay,work):
            if name in _busy or now<_next.get(name,0):return
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
            # 480 requests/day maximum even with only the anonymous allowance.
            pool=sorted(set(missing)&wanted) or sorted(wanted)
            reg=pool[_cursor%len(pool)]
            _cursor+=1
            schedule('airplanes.live',180,lambda:airplanes_lookup(reg))
        result=[]
        for name,store in _cache.items():
            for reg,(stamp,p) in list(store.items()):
                elapsed=max(0,time.monotonic()-stamp)
                if elapsed>120 or reg not in wanted:
                    del store[reg]
                    continue
                if name=='OpenSky Network' and not credentials or name=='airplanes.live' and not airplanes:continue
                plane=dict(p)
                for field in ('seen','seen_pos'):
                    if _number(plane.get(field)):plane[field]+=elapsed
                if plane.get('seen',999)<=120:result.append(plane)
        return result

def health():
    with _lock:
        return {name:{'matching_aircraft':len(_cache.get(name,{})),'error':_errors.get(name),
                      'retry_seconds':round(max(0,_next.get(name,0)-time.monotonic()))}
                for name in ('OpenSky Network','airplanes.live')}
