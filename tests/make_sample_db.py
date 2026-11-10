"""Generate test-only, fictional aircraft history. Never touches real ADS-B data."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import random
import sqlite3

UTC=timezone.utc

def seed(path, days=45):
    path=Path(path)
    if path.exists():path.unlink()
    db=sqlite3.connect(path)
    db.executescript('''
    CREATE TABLE all_sightings(id INTEGER PRIMARY KEY,icao TEXT,callsign TEXT,speed REAL,lat REAL,lon REAL,altitude REAL,aircraft_type TEXT,type_desc TEXT,seen_at INTEGER,squawk TEXT);
    CREATE TABLE sightings_hourly(icao TEXT,hour_bucket INTEGER,callsign TEXT,aircraft_type TEXT,type_desc TEXT,sighting_count INTEGER,first_seen_at INTEGER,last_seen_at INTEGER,last_lat REAL,last_lon REAL,last_altitude REAL,last_speed REAL,min_altitude REAL,max_altitude REAL,max_speed REAL,last_squawk TEXT,min_nonzero_altitude REAL, PRIMARY KEY(icao,hour_bucket));
    CREATE TABLE seen_aircraft(icao TEXT PRIMARY KEY, first_seen_at INTEGER,first_callsign TEXT,first_aircraft_type TEXT,registration TEXT,last_callsign TEXT,aircraft_type TEXT,aircraft_type_desc TEXT,operator TEXT,country TEXT,last_lat REAL,last_lon REAL,last_seen_at INTEGER,sighting_count INTEGER,fts_dirty INTEGER,last_distance REAL,category TEXT,registered_owner TEXT,manufacturer TEXT,best_track_seconds INTEGER);
    CREATE TABLE route_cache(callsign TEXT PRIMARY KEY,origin_icao TEXT,origin_name TEXT,dest_icao TEXT,dest_name TEXT,airline TEXT,resolved_at INTEGER,last_outcome TEXT,hit_count INTEGER,airports_json TEXT);
    CREATE TABLE concurrent_minute(minute_bucket INTEGER PRIMARY KEY,count INTEGER);
    CREATE TABLE aircraft_track_daily(icao TEXT,day_bucket INTEGER,callsign TEXT,aircraft_type TEXT,current_session_start INTEGER,current_session_last INTEGER,best_session_start INTEGER,best_session_end INTEGER,best_session_duration INTEGER);
    CREATE TABLE military_sightings(id INTEGER PRIMARY KEY,icao TEXT,callsign TEXT,speed REAL,lat REAL,lon REAL,altitude REAL,aircraft_type TEXT,type_desc TEXT,seen_at INTEGER,special_label TEXT,squawk TEXT);
    CREATE TABLE military_hourly(icao TEXT,hour_bucket INTEGER,callsign TEXT,aircraft_type TEXT,type_desc TEXT,special_label TEXT,sighting_count INTEGER,first_seen_at INTEGER,last_seen_at INTEGER);
    CREATE TABLE watchlist_hourly(icao TEXT,hour_bucket INTEGER,watchlist_label TEXT,callsign TEXT,aircraft_type TEXT,type_desc TEXT,sighting_count INTEGER,first_seen_at INTEGER,last_seen_at INTEGER);
    CREATE TABLE watchlist_sightings(id INTEGER PRIMARY KEY,icao TEXT,callsign TEXT,speed REAL,lat REAL,lon REAL,altitude REAL,aircraft_type TEXT,type_desc TEXT,seen_at INTEGER,watchlist_label TEXT,squawk TEXT);
    CREATE TABLE flight_routes(fa_flight_id TEXT,callsign TEXT,registration TEXT,origin_icao TEXT,origin_name TEXT,dest_icao TEXT,dest_name TEXT,departed_at INTEGER,arrives_at INTEGER,looked_up_at INTEGER);
    CREATE TABLE hexdb_cache(icao TEXT,registration TEXT,resolved_at INTEGER,last_outcome TEXT,hit_count INTEGER,last_hit_at INTEGER,registered_owner TEXT,manufacturer TEXT,type_code TEXT);
    CREATE TABLE hexdb_events(id INTEGER,ts INTEGER,kind TEXT,icao TEXT);
    CREATE TABLE stats_records(record_type TEXT,value REAL,icao TEXT,callsign TEXT,aircraft_type TEXT,set_at INTEGER,extra TEXT);
    CREATE TABLE photo_cache(icao TEXT,thumbnail_url TEXT,photo_link TEXT,photographer TEXT,resolved_at INTEGER,last_outcome TEXT,hit_count INTEGER);
    CREATE INDEX idx_hourly_bucket_icao ON sightings_hourly(hour_bucket,icao);
    CREATE INDEX idx_seen_at ON all_sightings(seen_at);
    CREATE INDEX idx_all_icao_seen ON all_sightings(icao,seen_at);
    ''')
    planes=[('4ca123','EZY123','A320','commercial','easyJet','G-EZYA'),('400001','BAW314','B738','commercial','British Airways','G-BAWX'),('4bb008','THY766','A21N','commercial','Turkish Airlines','TC-TUR'),('3c1111','DLH234','A359','commercial','Lufthansa','D-AIXA'),('43c000','RFR102','EUFI','military','Royal Air Force','ZK999'),('4d0009','GABCD','C172','general_aviation','Private','G-ABCD'),('4d0010','HEL01','EC35','helicopter','Air Ambulance','G-HELI')]
    rng=random.Random(1234)
    now=int(datetime.now(UTC).timestamp())
    latest_hour=(now//3600)*3600
    earliest_hour=latest_hour-days*86400
    for icao,call,typ,cat,op,reg in planes:
        db.execute('INSERT INTO seen_aircraft(icao,first_seen_at,last_seen_at,last_callsign,first_callsign,aircraft_type,aircraft_type_desc,operator,registration,country,category,sighting_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                   (icao,earliest_hour,now-90,call,call,typ,typ,op,reg,'United Kingdom',cat,10000))
        db.execute('INSERT INTO route_cache(callsign,airline) VALUES (?,?)',(call,op))
    rows=[]
    for h in range(earliest_hour,latest_hour+3600,3600):
        hour=(h//3600)%24
        # More commercial aircraft by day; GA during daytime; military sparse.
        for j,(icao,call,typ,cat,op,reg) in enumerate(planes):
            if cat=='military' and rng.random()>.08:continue
            if cat in ('general_aviation','helicopter') and (hour<7 or hour>19 or rng.random()>.5):continue
            if cat=='commercial' and rng.random()>(.85 if 6<=hour<=21 else .3):continue
            sight_count=rng.randint(10,110)
            first=h+rng.randint(10,180)
            last=min(now-30,h+rng.randint(1500,3400))
            if last<=first:continue
            rows.append((icao,h,call,typ,typ,sight_count,first,last,50.85+rng.random()/3,.15+rng.random()/4,30000+rng.randint(0,15000),350,2000,43000,400,'7000',2000))
            # One literal row per hour as a small proxy for raw records.
            db.execute('INSERT INTO all_sightings(icao,callsign,speed,lat,lon,altitude,aircraft_type,type_desc,seen_at,squawk) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (icao,call,360,50.9,.12,36000,typ,typ,first,'7000'))
            if cat=='military':db.execute('INSERT INTO military_sightings(icao,callsign,seen_at,aircraft_type) VALUES (?,?,?,?)',(icao,call,first,typ))
        db.executemany('INSERT INTO concurrent_minute(minute_bucket,count) VALUES (?,?)',
                       [(h+m*60,(len(rows)%48)) for m in range(60) if h+m*60 <= now])
    db.executemany('INSERT INTO sightings_hourly VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',rows)
    db.commit(); db.close();return len(rows)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('path');parser.add_argument('--days',type=int,default=45)
    args=parser.parse_args()
    print('Seeded hourly rows:',seed(args.path,args.days))
