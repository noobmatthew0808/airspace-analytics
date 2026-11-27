"""Small shared dashboard preferences, separate from Aerodrome data."""
from __future__ import annotations
from datetime import date
import json
import re
from urllib.parse import urlsplit
from . import alerts

KEY='dashboard_preferences_v1'
DEFAULT_DATE='2026-11-09'
LINK_FIELDS=('id','name','group','sub','port','path','url','icon','brand','logoDomain','logoSrc','tone','extraLabel','extraUrl','extraPort','extraPath','thirdLabel','thirdUrl')

def dates(value):
    if not isinstance(value,list) or len(value)>64:raise ValueError('Invalid excluded dates')
    result=set()
    for day in value:
        if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day):raise ValueError('Invalid excluded date')
        date.fromisoformat(day)
        result.add(day)
    return sorted(result)

def links(value):
    if not isinstance(value,list) or len(value)>100:raise ValueError('Invalid shortcut list')
    result=[]
    for item in value:
        if not isinstance(item,dict):raise ValueError('Invalid shortcut')
        row={k:str(item[k])[:512] for k in LINK_FIELDS if k in item and item[k] is not None}
        if not row.get('name'):raise ValueError('Missing shortcut name')
        row['group']='feeders' if row.get('group')=='feeders' else 'stats'
        for k in ('url','extraUrl','thirdUrl'):
            if row.get(k):
                u=urlsplit(row[k])
                if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:raise ValueError('Invalid shortcut URL')
        for k in ('port','extraPort'):
            if row.get(k) and (not row[k].isdigit() or not 1<=int(row[k])<=65535):raise ValueError('Invalid shortcut port')
        result.append(row)
    return result

# One-time correction of the four requested launcher links, including existing
# server-side settings. Do not recreate removed links or alter other fields.
FEEDER_LINK_FIXES={
    "adsbiq": "https://adsbiq.com/feeder/51a27442-b77e-45a3",
    "adsbhub": "https://www.adsbhub.org/statistic.php",
    "avioadsb": "https://avioadsb.org/station?id=743cc25e-05b7-472d-a6a7-f7f48d164a64",
    "opensky": "https://opensky-network.org/my-opensky/account"
}
FEEDER_LINK_NAMES={'adsbiq':'adsbiq','adsbhub':'adsbhub','avioadsb':'avioadsb','opensky network':'opensky'}

def _fix_feeder_links(items):
    if items is None:return False
    changed=False
    for row in items:
        id=row.get('id') or FEEDER_LINK_NAMES.get(row.get('name','').strip().lower())
        if id not in FEEDER_LINK_FIXES:continue
        url=FEEDER_LINK_FIXES[id]
        if row.get('url')!=url:
            row['url']=url
            changed=True
        if id=='avioadsb' and row.get('sub')=='Receiver dashboard and API usage':
            row['sub']='Your feeder statistics'
            changed=True
    return changed


DATAERO_LINKS={'url':'https://radar.dataero.eu/user/dashboard','sub':'Feeder stats',
               'extraLabel':'Map','extraUrl':'https://radar.dataero.eu/map'}

def _fix_dataero_links(items):
    changed=False
    for row in items or []:
        if row.get('id')!='dataero' and not (not row.get('id') and row.get('name','').strip().lower()=='dataero'):
            continue
        for key,value in DATAERO_LINKS.items():
            if row.get(key)!=value:
                row[key]=value
                changed=True
    return changed


# New launcher shortcuts, applied once to an existing saved list. Keep all
# unrelated shortcut fields, ordering, exclusions and removal history.
LAUNCHER_FEEDER_LINKS_V11042=[
    {
        "id": "theairtraffic",
        "name": "TheAirTraffic",
        "group": "feeders",
        "sub": "Your feeder status",
        "url": "https://theairtraffic.com/myip",
        "extraLabel": "Live map",
        "extraUrl": "https://globe.theairtraffic.com/",
        "icon": "radar",
        "brand": "AT",
        "logoDomain": "theairtraffic.com",
        "tone": "blue"
    },
    {
        "id": "theairtraffic-mlat",
        "name": "TheAirTraffic MLAT",
        "group": "feeders",
        "sub": "Your Polegate MLAT sync",
        "url": "https://theairtraffic.com/sync/uk-ireland/feeder?id=Polegate_ADS-B",
        "extraLabel": "Feeder network map",
        "extraUrl": "https://theairtraffic.com/feeder-map",
        "icon": "radar",
        "brand": "ML",
        "logoDomain": "theairtraffic.com",
        "tone": "blue"
    },
    {
        "id": "realtraffic",
        "name": "RealTraffic",
        "group": "feeders",
        "sub": "Feeder account dashboard",
        "url": "https://flyrealtraffic.com/account/dashboard",
        "extraLabel": "Live map",
        "extraUrl": "https://flyrealtraffic.com/livemap/",
        "icon": "radar",
        "brand": "RT",
        "logoDomain": "flyrealtraffic.com",
        "tone": "teal"
    },
    {
        "id": "planetrack",
        "name": "PlaneTrack",
        "group": "feeders",
        "sub": "Your provider dashboard",
        "url": "https://planetrack.ai/provider-dashboard.html",
        "extraLabel": "Live map",
        "extraUrl": "https://planetrack.ai/",
        "icon": "radar",
        "brand": "PT",
        "logoDomain": "planetrack.ai",
        "tone": "sky"
    },
    {
        "id": "mlatuk",
        "name": "mlat.uk",
        "group": "feeders",
        "sub": "Receiver stats and MLAT peers",
        "url": "https://www.mlat.uk/network",
        "extraLabel": "Live map",
        "extraUrl": "https://map.mlat.uk/",
        "icon": "radar",
        "brand": "UK",
        "logoDomain": "mlat.uk",
        "tone": "navy"
    },
    {
        "id": "adsbitalia",
        "name": "ADSB Italia",
        "group": "feeders",
        "sub": "Your feeder status",
        "url": "https://www.adsbitalia.it/status.html",
        "extraLabel": "Live map",
        "extraUrl": "https://map.adsbitalia.it/",
        "icon": "radar",
        "brand": "IT",
        "logoDomain": "adsbitalia.it",
        "tone": "green"
    },
    {
        "id": "mapflights",
        "name": "map.flights",
        "group": "feeders",
        "sub": "Station network and coverage",
        "url": "https://map.flights/stations",
        "extraLabel": "Live map",
        "extraUrl": "https://map.flights/",
        "icon": "radar",
        "brand": "MF",
        "logoDomain": "map.flights",
        "tone": "violet"
    },
    {
        "id": "skydex",
        "name": "Skydex",
        "group": "feeders",
        "sub": "Measured receiver coverage",
        "url": "https://skydex.online/adsb/coverage",
        "extraLabel": "Live network map",
        "extraUrl": "https://skydex.online/adsb/live",
        "icon": "radar",
        "brand": "SD",
        "logoDomain": "skydex.online",
        "tone": "teal"
    },
    {
        "id": "planewatch",
        "name": "Plane.watch",
        "group": "feeders",
        "sub": "Feeder account",
        "url": "https://atc.plane.watch/",
        "extraLabel": "Live map",
        "extraUrl": "https://app.plane.watch/",
        "icon": "radar",
        "brand": "PW",
        "logoDomain": "plane.watch",
        "tone": "sky"
    }
]

def _link_identity(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').strip().lower())

def _migrate_launcher_feeders(items):
    if items is None:return False
    changed=False
    for row in items:
        if _link_identity(row.get('id')) in ('dataero','dataaero') or _link_identity(row.get('name')) in ('dataero','dataaero'):
            if row.get('group')!='feeders':
                row['group']='feeders'
                changed=True
    for item in LAUNCHER_FEEDER_LINKS_V11042:
        row=next((r for r in items if _link_identity(r.get('id'))==_link_identity(item['id']) or _link_identity(r.get('name'))==_link_identity(item['name'])),None)
        if row is not None:
            changes={'group':'feeders'}
            if item['id'] in ('theairtraffic','theairtraffic-mlat','realtraffic'):
                changes.update({key:item[key] for key in ('url','sub','extraLabel','extraUrl')})
            for key,value in changes.items():
                if row.get(key)!=value:
                    row[key]=value
                    changed=True
        elif len(items)<100:
            items.append(dict(item))
            changed=True
    return changed

TAT_THREE_LINKS={"group":"feeders","sub":"Live aircraft map","url":"https://globe.theairtraffic.com/","extraLabel":"Feeder status","extraUrl":"https://theairtraffic.com/myip","thirdLabel":"MLAT feeder status","thirdUrl":"https://theairtraffic.com/sync/uk-ireland/feeder?id=Polegate_ADS-B"}
def _merge_tat_links(items):
    if items is None:return False
    def is_main(row):
        return _link_identity(row.get('id'))=='theairtraffic' or _link_identity(row.get('name'))=='theairtraffic'
    def is_mlat(row):
        return _link_identity(row.get('id'))=='theairtrafficmlat' or _link_identity(row.get('name'))=='theairtrafficmlat'
    main=next((r for r in items if is_main(r)),None)
    changed=False
    if main is None:
        main=next((r for r in items if is_mlat(r)),None)
        if main is not None:
            main.update(id='theairtraffic',name='TheAirTraffic')
            changed=True
    if main is None:return False
    for key,value in TAT_THREE_LINKS.items():
        if main.get(key)!=value:
            main[key]=value
            changed=True
    for index in range(len(items)-1,-1,-1):
        row=items[index]
        if row is not main and (is_main(row) or is_mlat(row)):
            del items[index]
            changed=True
    return changed

def _load(c):
    row=c.execute('SELECT value FROM config WHERE key=?',(KEY,)).fetchone()
    if row:
        state=json.loads(row['value'])
        if not state.get('feeder_links_v11033'):
            if _fix_feeder_links(state['links']):state['revision']+=1
            state['feeder_links_v11033']=True
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',(KEY,json.dumps(state,separators=(',',':'))))
        if not state.get('dataero_links_v11041'):
            if _fix_dataero_links(state['links']):state['revision']+=1
            state['dataero_links_v11041']=True
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',(KEY,json.dumps(state,separators=(',',':'))))
        if not state.get('launcher_feeders_v11042') and state['links'] is not None:
            if _migrate_launcher_feeders(state['links']):state['revision']+=1
            state['launcher_feeders_v11042']=True
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',(KEY,json.dumps(state,separators=(',',':'))))
        if not state.get('tat_three_v11043') and state['links'] is not None:
            if _merge_tat_links(state['links']):state['revision']+=1
            state['tat_three_v11043']=True
            c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',(KEY,json.dumps(state,separators=(',',':'))))
        return state
    return {'excluded_days':[DEFAULT_DATE],'links':None,'revision':0,'migrated':[],'dates_initialized':False,'launcher_feeders_v11042':True,'tat_three_v11043':True}

def _public(state):
    return {k:state[k] for k in ('excluded_days','links','revision')}

def read():
    with alerts._lock,alerts.connect() as c:return _public(_load(c))

def update(payload):
    if not isinstance(payload,dict):raise ValueError('Invalid settings')
    action=payload.get('action')
    with alerts._lock,alerts.connect() as c:
        state=_load(c)
        if action=='migrate':
            client=str(payload.get('client',''))
            if not re.fullmatch(r'[a-zA-Z0-9-]{8,100}',client):raise ValueError('Invalid migration identifier')
            if client in state['migrated']:return _public(state)
            if len(state['migrated'])>=200:raise ValueError('Too many migrated browsers')
            incoming=payload.get('excluded_days')
            if incoming is not None:
                incoming=dates(incoming)
                if not state['dates_initialized']:state['excluded_days']=incoming
                else:state['excluded_days']=dates(sorted(set(state['excluded_days'])|(set(incoming)-set(state.get('removed_days',[])))))
                state['dates_initialized']=True
            incoming_links=links(payload.get('links',[]))
            _merge_tat_links(incoming_links)
            _fix_feeder_links(incoming_links)
            _fix_dataero_links(incoming_links)
            for row in incoming_links:
                if _link_identity(row.get('id')) in ('dataero','dataaero') or _link_identity(row.get('name')) in ('dataero','dataaero'):row['group']='feeders'
            if state['links'] is None:state['links']=incoming_links
            elif payload.get('has_legacy_links',True):
                existing=state['links']
                ids={r.get('id') for r in existing if r.get('id')}
                names={r['name'].strip().lower() for r in existing}
                removed=set(state.get('removed_links',[]))
                for r in incoming_links:
                    if 'name:'+r['name'].strip().lower() in removed or (r.get('id') and 'id:'+r['id'] in removed):continue
                    if r.get('id') in ids or r['name'].strip().lower() in names:continue
                    existing.append(r)
                    if r.get('id'):ids.add(r['id'])
                    names.add(r['name'].strip().lower())
                state['links']=links(existing)
            state['migrated'].append(client)
        elif action in ('add_day','remove_day'):
            day=dates([payload.get('day')])[0]
            current=set(state['excluded_days'])
            removed=set(state.get('removed_days',[]))
            if action=='add_day':
                current.add(day);removed.discard(day)
            else:
                current.discard(day);removed.add(day)
            state['removed_days']=sorted(removed)
            state['excluded_days']=dates(sorted(current))
            state['dates_initialized']=True
        elif action=='links':
            if payload.get('revision')!=state['revision']:raise ValueError('Settings changed on another device. Reopen Settings before saving.')
            previous=state['links'] or []
            new=links(payload.get('links'))
            def identities(rows):
                return {'name:'+r['name'].strip().lower() for r in rows}|{'id:'+r['id'] for r in rows if r.get('id')}
            removed=(set(state.get('removed_links',[]))|(identities(previous)-identities(new)))-identities(new)
            state['removed_links']=sorted(removed)
            state['links']=new
        else:raise ValueError('Unknown settings action')
        state['revision']+=1
        c.execute('INSERT OR REPLACE INTO config(key,value) VALUES(?,?)',(KEY,json.dumps(state,separators=(',',':'))))
        return _public(state)
