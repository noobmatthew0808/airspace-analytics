#!/usr/bin/env python3
"""Inspect why commercial airlines remain Unknown without changing Aerodrome.

Usage: python3 scripts/operator_diagnostics.py --days 7 --metric flights
For operator analytics this follows the website's 30-minute visit rule.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import data


def cause(operator,route,call):
    call=(call or '').strip().upper()
    if not call:return 'No callsign recorded', None
    match=re.fullmatch(r'([A-Z]{3})[0-9][A-Z0-9]{0,7}',call)
    if match:return 'Unrecognised airline prefix', match.group(1)
    return 'Non-airline/registration-style callsign',call[:3]


def diagnosis(days=7,metric='flights'):
    now=datetime.now(timezone.utc)
    end=int(now.timestamp());start=int((now-timedelta(days=days)).timestamp())
    first_hour=(start//3600)*3600;last_hour=((end-1)//3600)*3600+3600
    sql='''SELECT h.icao,h.hour_bucket,h.sighting_count,h.first_seen_at,h.last_seen_at,h.callsign,
                 a.category,a.operator,r.airline FROM sightings_hourly h
            LEFT JOIN seen_aircraft a ON a.icao=h.icao
            LEFT JOIN (SELECT callsign,MAX(airline) AS airline FROM route_cache GROUP BY callsign) r
              ON r.callsign=h.callsign
            WHERE h.hour_bucket>=? AND h.hour_bucket<? ORDER BY h.hour_bucket,h.icao'''
    groups=defaultdict(lambda:{'flights':0,'observations':0,'aircraft':set()})
    prefixes=Counter();example=Counter();last_by_icao={}
    with data.connection() as db:
        for row in db.execute(sql,(first_hour-4*3600,last_hour)):
            icao=(row['icao'] or '').lower()
            if not icao:continue
            first=int(row['first_seen_at'] or row['hour_bucket'])
            last=int(row['last_seen_at'] or row['hour_bucket'])
            call=(row['callsign'] or '').strip().upper()
            prev=last_by_icao.get(icao)
            new=not prev or first-prev[0]>data.SESSION_GAP or (prev[1] and call and prev[1]!=call)
            last_by_icao[icao]=(max(last,prev[0]) if prev else last,call or (prev[1] if prev else ''))
            if row['hour_bucket']<first_hour or last<start or first>=end:continue
            cat=(row['category'] or 'unknown').lower().strip() or 'unknown'
            if cat!='commercial':continue
            airline=data.resolved_airline(cat,row['operator'],row['airline'],call)
            if airline=='Unknown airline':
                reason,prefix=cause(row['operator'],row['airline'],call)
                if prefix:prefixes[prefix]+=1
                if call:example[call]+=1
            else:reason='Identified airline/operator'
            bucket=groups[reason]
            bucket['observations']+=int(row['sighting_count'] or 0)
            bucket['aircraft'].add(icao)
            if new and start<=first<end:bucket['flights']+=1
    answer=[]
    for name,v in groups.items():answer.append((name,len(v['aircraft']) if metric=='aircraft' else v[metric]))
    answer.sort(key=lambda x:-x[1]);return answer,prefixes.most_common(20),example.most_common(10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days',type=int,default=7)
    parser.add_argument('--metric',choices=('flights','aircraft','observations'),default='flights')
    args=parser.parse_args()
    if not 1<=args.days<=366:parser.error('--days must be between 1 and 366')
    try:reasons,prefixes,examples=diagnosis(args.days,args.metric)
    except Exception as exc:sys.exit('Read-only diagnostic failed: '+str(exc))
    total=sum(n for _,n in reasons)
    print(f'Commercial airline classification · last {args.days} days · {args.metric} (sampled hourly Aerodrome history)')
    for name,n in reasons:print(f'{name:38s} {n:>9,}  ({n/total*100 if total else 0:5.1f}%)')
    print('\nTop unrecognised prefixes (hourly rows, not flights):')
    for prefix,count in prefixes:print(f'  {prefix:8s} {count:,}')
    print('\nTop unmatched callsigns (hourly rows):')
    for call,count in examples:print(f'  {call:12s} {count:,}')
    print('\nNote: this is a read-only diagnosis; ambiguous operators remain Unknown.')
