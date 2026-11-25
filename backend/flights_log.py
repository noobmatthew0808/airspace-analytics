"""Original personal flight log's SheetDB/Google Sheets storage, unchanged in place.

All sheet writes still go through the exact original SheetDB API and preserve
its nine columns. A private, read-only sheet snapshot accelerates page loads.
This tiny server-side bridge is only used to avoid relaxing the dashboard CSP.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path
import json
import os
import re
import threading
import time
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

# Exact endpoint from the uploaded live-main ZIP, script.js line 1.
SHEETDB = 'https://sheetdb.io/api/v1/9fnmgmxtdst8m'
COLUMNS = ('id','date','from_airport','to_airport','flight_code','airline',
           'airplane','registration','who')
MAX_RESPONSE = 2_000_000
_LOCK = threading.RLock()
_CACHE = {'rows':None,'at':0.0,'error':None}
CACHE_PATH=Path(__file__).resolve().parents[1]/'.airspace-state'/'flights-sheet.json'
REFRESH_PERIOD=2*3600
_RETRY_PERIOD=300
_cache_enabled=False
_refresh_gate=threading.Lock()
_last_attempt=None
HEADERS = {'User-Agent':'AirspaceAnalytics-Flights/1',
           'Accept':'application/json','Cache-Control':'no-cache, no-store'}


class SheetError(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _fetch(path='', method='GET', payload=None, opener=None):
    """Never use an attacker-controlled URL, redirect or network proxy."""
    if opener is None:
        opener=build_opener(ProxyHandler({}),_NoRedirect()).open
    if path and not re.fullmatch(r'/id/[0-9]{1,12}',path):
        raise SheetError('Invalid flight ID path')
    raw=json.dumps(payload,separators=(',',':')).encode() if payload is not None else None
    request=Request(SHEETDB+path,data=raw,method=method,
            headers={**HEADERS,**({'Content-Type':'application/json'} if raw is not None else {})})
    try:
        with opener(request,timeout=8) as response:
            if int(response.headers.get('Content-Length','0') or 0)>MAX_RESPONSE:
                raise SheetError('SheetDB response too large')
            content=response.read(MAX_RESPONSE+1)
            if len(content)>MAX_RESPONSE:raise SheetError('SheetDB response too large')
            return json.loads(content) if content else None
    except HTTPError as exc:
        raise SheetError(f'SheetDB HTTP {exc.code}') from None
    except (URLError,OSError,TimeoutError):
        raise SheetError('Cannot reach Google Sheets via SheetDB') from None
    except (json.JSONDecodeError,UnicodeDecodeError):
        raise SheetError('Invalid SheetDB response') from None


def _rows(payload):
    if isinstance(payload,list):rows=payload
    elif isinstance(payload,dict) and isinstance(payload.get('data'),list):
        rows=payload['data']
    else:raise SheetError('SheetDB did not return flight rows')
    if len(rows)>10000:raise SheetError('Too many SheetDB rows')
    return [{key:str(item.get(key,'') or '')[:2500] for key in COLUMNS}
            for item in rows if isinstance(item,dict)]


def _read_locked(force=False):
    now=time.monotonic()
    if not force and _CACHE['rows'] is not None and now-_CACHE['at']<15:
        return {'flights':[dict(row) for row in _CACHE['rows']],
                'cached':False,'source':'Google Sheets via SheetDB'}
    try:
        result=_rows(_fetch())
        _remember(result)
        return {'flights':[dict(row) for row in result],
                'cached':False,'source':'Google Sheets via SheetDB'}
    except SheetError as exc:
        _CACHE['error']=str(exc)
        # An in-memory, clearly flagged read-only snapshot is only for brief
        # SheetDB outages; it never becomes a second database or write source.
        if _CACHE['rows'] is not None and now-_CACHE['at']<7200:
            return {'flights':[dict(row) for row in _CACHE['rows']],
                    'cached':True,'warning':'Google Sheets is temporarily unavailable. Viewing a cached snapshot.',
                    'source':'Google Sheets via SheetDB'}
        raise


def read():
    with _LOCK:return _read_locked()


def _remember(rows):
    stamp=time.time()
    _CACHE.update(rows=rows,at=time.monotonic(),error=None,wall=stamp)
    if not _cache_enabled:return
    try:
        CACHE_PATH.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        temp=CACHE_PATH.with_suffix('.tmp')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as handle:
            json.dump({'at':stamp,'flights':rows},handle,separators=(',',':'))
        os.replace(temp,CACHE_PATH)
    except OSError:
        pass


def start_cache():
    global _cache_enabled
    with _LOCK:
        if _cache_enabled:return
        _cache_enabled=True
        try:
            if CACHE_PATH.stat().st_size>MAX_RESPONSE*2:return
            saved=json.loads(CACHE_PATH.read_text())
            stamp=float(saved['at'])
            if not 0<stamp<=time.time()+60:return
            rows=_rows(saved['flights'])
            _CACHE.update(rows=rows,at=time.monotonic()-max(0,time.time()-stamp),error=None,wall=stamp)
        except (OSError,ValueError,TypeError,KeyError):
            pass


def _schedule_refresh(force=False):
    global _last_attempt
    now=time.monotonic()
    if not force and _last_attempt is not None and now-_last_attempt<_RETRY_PERIOD:return False
    if force and _last_attempt is not None and now-_last_attempt<15:return False
    if not _refresh_gate.acquire(blocking=False):return False
    _last_attempt=now
    def worker():
        try:
            with _LOCK:
                _read_locked(force=True)
        except (SheetError,OSError):
            pass
        finally:_refresh_gate.release()
    try:threading.Thread(target=worker,name='airspace-sheet-refresh',daemon=True).start()
    except RuntimeError:
        _refresh_gate.release()
        return False
    return True


def read_cached(force=False):
    """Return cached rows immediately; the sole refresh worker owns network I/O."""
    if not _cache_enabled:return read()
    current=dict(_CACHE)
    if current['rows'] is None:
        # First ever run without a snapshot must fetch once.
        result=read()
        return {**result,'refreshing':False,'updated_at':_CACHE.get('wall')}
    age=max(0,time.monotonic()-current['at'])
    if force or age>=REFRESH_PERIOD:_schedule_refresh(force)
    current=dict(_CACHE)
    return {'flights':[dict(row) for row in current['rows']],
            'cached':True,'refreshing':_refresh_gate.locked(),
            'updated_at':current.get('wall'),'source':'Google Sheets via SheetDB',
            **({'warning':'Google Sheets temporarily unavailable; showing saved flights.'} if current['error'] else {})}



def _clean(data):
    if not isinstance(data,dict):
        raise SheetError('Invalid flight data')
    value={}
    for col in COLUMNS[1:]:
        raw=data.get(col,'')
        if raw is None:raw=''
        if not isinstance(raw,(str,int,float)):raise SheetError('Invalid '+col)
        string=str(raw).strip()
        if len(string)>500:raise SheetError(col+' is too long')
        if any(ord(x)<32 and x not in ('\n','\r') for x in string):
            raise SheetError('Invalid control character')
        value[col]=string
    # Original form requires these fields; dates are supplied as YYYY-MM-DD.
    for col in ('date','from_airport','to_airport','flight_code',
                'airline','airplane','registration'):
        if not value[col]:raise SheetError('Missing '+col)
    try:
        datetime.strptime(value['date'],'%Y-%m-%d')
    except ValueError:raise SheetError('Date must be YYYY-MM-DD') from None
    for col in ('from_airport','to_airport','flight_code','registration'):
        value[col]=value[col].upper()
    # Source keeps people separated by commas, newlines or semicolons.
    value['who']=', '.join(v.strip() for v in re.split(r'[\n,;]+',value['who']) if v.strip())
    return value


def _id(value):
    code=str(value or '').strip()
    if not re.fullmatch(r'[0-9]{1,12}',code):
        raise SheetError('Invalid flight ID')
    return code


def _next_numeric_id(rows):
    """The old website uses the *lowest unused positive integer*, not max+1."""
    used={int(str(row.get('id','')).strip()) for row in rows
          if re.fullmatch(r'[0-9]+',str(row.get('id','')).strip())
          and int(str(row.get('id','')).strip())>0}
    num=1
    while num in used:num+=1
    return str(num)


def mutate(payload):
    """POST create/edit/delete, never touch any other service or schema."""
    if not isinstance(payload,dict):raise SheetError('Invalid request')
    action=payload.get('action')
    if action not in ('create','update','delete'):
        raise SheetError('Unknown flight action')
    with _LOCK:
        if action=='delete':
            id_value=_id(payload.get('id'))
            # Don't delete an unrelated row when the requested ID is unknown.
            existing=_rows(_fetch())
            if not any(row['id']==id_value for row in existing):
                raise SheetError('Flight not found')
            _fetch('/id/'+quote(id_value,safe=''),method='DELETE')
            updated=[row for row in existing if row['id']!=id_value]
        else:
            cleaned=_clean(payload.get('data'))
            if action=='create':
                current=_rows(_fetch())
                id_value=_next_numeric_id(current)
                _fetch(method='POST',payload={'data':[{'id':id_value,**cleaned}]})
                updated=[*current,{'id':id_value,**cleaned}]
            else:
                id_value=_id(payload.get('id'))
                current=_rows(_fetch())
                if not any(row['id']==id_value for row in current):
                    raise SheetError('Flight not found')
                _fetch('/id/'+quote(id_value,safe=''),method='PATCH',
                       payload={'data':{'id':id_value,**cleaned}})
                updated=[{'id':id_value,**cleaned} if row['id']==id_value else row for row in current]
        if _cache_enabled:_remember(updated)
        else:_CACHE.update(rows=None,at=0.0,error=None)
        return {'ok':True,'id':id_value,'source':'Google Sheets via SheetDB'}
