"""One-shot local audit of the production flight adapters.

Run from the installed project: python3 -m scripts.check_flight_sources HA-LDG WZZ580C
Uses existing local credentials; prints no credentials, URLs containing credentials,
raw payloads, or personal flight-log records. No writes to application settings.
One pass only: a missing aircraft is not a failed connection; no retries on 429.
"""
import json
import re
import sys
import time
from backend import alerts, flights_live as live, flights_routes as routes
from backend import flights_cache, extra_flight_sources as extra, api_budget

def main():
    reg=(sys.argv[1] if len(sys.argv)>1 else 'HA-LDG').strip().upper()
    call=(sys.argv[2] if len(sys.argv)>2 else 'WZZ580C').strip().upper()
    if not re.fullmatch(r'[A-Z0-9-]{2,16}',reg) or not re.fullmatch(r'[A-Z]{3}[0-9][A-Z0-9]{0,4}',call):
        raise SystemExit('Invalid registration or callsign')
    keys=live._configured_keys()
    with alerts._lock,alerts.connect() as db:
        credentials=alerts._opensky_credentials(db)
    observations=[]
    try:
        existing=json.loads(flights_cache.PATH.read_text()).get(reg,{})
    except (OSError,ValueError,TypeError):
        existing={}
    known=existing.get('local_hex') or existing.get('hex') or ''
    history=live._local_last_seen([reg]).get(live.normal_reg(reg),{})
    known=history.get('hex') or known
    print('Testing',reg,call,'at',time.strftime('%Y-%m-%d %H:%M:%S UTC',time.gmtime()),flush=True)
    print('Local Aerodrome last seen:',history.get('last_seen_at') or 'not recorded',flush=True)
    def probe(name,fn):
        nonlocal known
        try:
            result=fn()
            if not isinstance(result,list):print(name,':',result,flush=True);return
            found=[p for p in result if live.normal_reg(p.get('r',''))==live.normal_reg(reg)]
            print(name,': accepted response;',len(found),'matching aircraft',flush=True)
            for p in found:
                if re.fullmatch(r'[a-fA-F0-9]{6}',str(p.get('hex') or '')):known=p['hex'].lower()
                observations.append(p)
                wanted=('hex','r','flight','seen','seen_pos','lat','lon','alt_baro','gs','route_origin','route_dest')
                fields={k:p[k] for k in wanted if k in p}
                route=p.get('route')
                if isinstance(route,dict):
                    fields['route']={k:route[k] for k in ('from','to','from_iata','to_iata','count','last_day') if k in route}
                print('  ',json.dumps(fields),flush=True)
        except Exception as e:
            # Adapters sanitize most errors; never print arbitrary upstream or
            # request bodies containing credentials.
            msg=str(e)
            code=re.search(r'HTTP \d{3}|rate limited|stale|timestamp|invalid response|unavailable|too large|timeout',msg,re.I)
            print(name,':',code.group(0) if code else type(e).__name__,flush=True)
    base=live.build_opener(live.ProxyHandler({}),live._NoRedirect()).open
    probe('adsb.fi feeder snapshot',lambda:live._global_snapshot([reg],'',lambda req,timeout:api_budget.open_request('adsb.fi',base,req,timeout),'adsb.fi'))
    for provider in ('FlyItalyADSB','adsb.lol','AvioADSB','ADSBiq'):
        if not keys.get(provider):
            print(provider,': skipped — no saved key',flush=True)
            continue
        probe(provider,lambda p=provider:live._lookup_provider([reg],p,keys[p]))
    probe('airplanes.live',lambda:extra.airplanes_lookup(reg))
    if credentials and re.fullmatch(r'[a-fA-F0-9]{6}',str(known)):
        probe('OpenSky Network',lambda:extra.opensky_lookup(credentials,{known.lower():reg}))
    else:print('OpenSky Network: skipped — no authorised credentials or known ICAO',flush=True)
    # Use a bounded existing connection check; an SBS stream carries no route.
    probe('ADSBHub SBS connection',lambda:extra.test_adsbhub())
    fresh=[p for p in observations if str(p.get('flight') or '').strip().upper()==call and live._active(p)]
    positioned=[p for p in fresh if isinstance(p.get('seen_pos'),(int,float)) and 0<=p['seen_pos']<=30 and all(isinstance(p.get(k),(int,float)) for k in ('lat','lon'))]
    item={'callsign':call}
    if positioned:
        best=min(positioned,key=lambda p:p['seen_pos'])
        item.update(lat=best['lat'],lon=best['lon'])
    if fresh and re.fullmatch(r'[a-fA-F0-9]{6}',str(known)):item['icao']=known
    clean=routes._clean_planes([item])
    for url in routes.SOURCES:
        if not clean or ('lat' not in clean[0] and url!=routes.SOURCES[0]):
            print(url.split('/')[2],': skipped — no fresh matching flight position/identity',flush=True)
            continue
        probe(url.split('/')[2]+' routeset',lambda u=url:routes._request_source(clean,u,routes._open) or {'route':'No matching itinerary'})
    if keys.get('FlyItalyADSB'):
        if api_budget.remaining('FlyItalyADSB')>0:
            print('FlyItalyADSB callsign history: skipped — cooldown',flush=True)
        else:probe('FlyItalyADSB callsign history',lambda:{'usual_route':routes.historical_route(call,keys['FlyItalyADSB']) or 'No unambiguous route'})
    print('Done. A successful response with zero matches is coverage, not authentication failure.',flush=True)

if __name__=='__main__':
    main()
