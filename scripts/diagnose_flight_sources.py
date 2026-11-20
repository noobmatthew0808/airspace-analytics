#!/usr/bin/env python3
"""Read-only live route source diagnostics. Never prints API keys.

Run from the installed Airspace Analytics repository:
    python3 scripts/diagnose_flight_sources.py
No edits to tar1090, containers, Google Sheets, or alert settings.
"""
from pathlib import Path
import json
import re
import sys
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import flights_routes, flights_live, flights_history

LOCAL='http://127.0.0.1:1090/data/aircraft.json'
CANDIDATES=('http://127.0.0.1:1090/config.js',
            'http://127.0.0.1:1090/map/config.js',
            'http://127.0.0.1:1099/map/config.js')

def read(url,limit=300000):
    with urllib.request.urlopen(url,timeout=6) as response:
        return response.read(limit+1).decode('utf-8','replace')[:limit]

def main():
    print('=== ROUTE SOURCES — READ ONLY ===')
    for path in CANDIDATES:
        try:
            config=read(path)
            matches=re.findall(r'^\s*(?:let\s+|var\s+)?routeApiUrl\s*=\s*[\x22\x27]([^\x22\x27]+)',config,re.M)
            if matches:print('tar1090 configured routeApiUrl:',matches[-1], '(from '+path+')')
        except Exception:pass
    try:
        raw=json.loads(read(LOCAL))
        now=raw.get('now')
        if not isinstance(now,(float,int)) or abs(time.time()-now)>20:raise ValueError('Stale local receiver')
        planes=[{'callsign':str(a.get('flight') or '').strip().upper(),
                 'lat':a['lat'],'lon':a['lon'],
                 'reg':a.get('r'),'hex':a.get('hex')}
                for a in raw.get('aircraft',[])
                if isinstance(a,dict)
                and isinstance(a.get('lat'),(int,float))
                and isinstance(a.get('lon'),(int,float))
                and (a.get('seen_pos') or 0)<=30
                and re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',
                                 str(a.get('flight') or '').strip().upper())]
    except Exception as exc:
        print('Local readsb unavailable:',type(exc).__name__)
        return
    planes=flights_routes._clean_planes(planes)[:8]
    if not planes:
        print('No fresh positioned aircraft with usable callsigns right now.')
        print('Try again when nearby aircraft are showing on the tar1090 map.')
        return
    print('Live sample callsigns:',', '.join(p['callsign'] for p in planes))
    for url in flights_routes.SOURCES:
        host=url.split('/')[2]
        t=time.monotonic()
        try:
            routes=flights_routes._request_source(planes,url,flights_routes._open)
            print(host,'success:',len(routes),'plausible routes,',
                  round(time.monotonic()-t,2),'seconds')
            for callsign,route in list(routes.items())[:4]:print('   ',callsign,route)
        except Exception as exc:
            print(host,'not available:',type(exc).__name__,str(exc)[:70],
                  'after',round(time.monotonic()-t,2),'seconds')
    keys=flights_live._configured_keys()
    key=keys.get('FlyItalyADSB')
    print('FlyItalyADSB key saved:',bool(key),'(never displayed)')
    if key:
        try:
            regs=list(dict.fromkeys(str(a.get('r') or '').strip().upper()
                                    for a in raw.get('aircraft',[])
                                    if a.get('r') and a.get('seen',99)<20))[:3]
            if regs:
                batch=flights_live._lookup_provider(regs,'FlyItalyADSB',key)
                confirmed=[p for p in batch if p.get('route')]
                print('FlyItalyADSB ?with=route:',len(confirmed),
                      'usual routes from',len(batch),'live aircraft')
                for p in confirmed[:3]:
                    route=p['route']
                    print('   ',str(p.get('flight','')).strip(),
                          route.get('from_iata'),route.get('to_iata'),
                          '(observed usual route, NOT confirmed current)')
                history=flights_history.fetch_one(regs[0],key)
                print('Flight-history test:',history or 'No confirmed recent landing')
        except Exception as exc:
            print('FlyItalyADSB check:',type(exc).__name__,str(exc)[:80])
    print('=== FINISHED (NO SETTINGS CHANGED) ===')

if __name__=='__main__':main()
