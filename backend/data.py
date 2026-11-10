"""Read-only Aerodrome analytics engine.

All observation history lives in Aerodrome. No duplication or writes are made to
its database. Rows are aggregated in memory with bounded, short-lived caching.
"""
from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock, BoundedSemaphore
from time import monotonic
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo
import json
import math
import os
import re
import sqlite3

UK = ZoneInfo('Europe/London')
UTC = timezone.utc
DB_DEFAULT = '/opt/aerodrome/aircraft_history.db'
MAX_WINDOW_SECONDS = 12 * 366 * 86400
MAX_ROWS = 5_000_000  # guardrail; raw observations are never loaded
SESSION_GAP = 30 * 60
# Carrier callsign prefixes observed on the receiver; inference is limited to
# aircraft Aerodrome itself categorises as commercial. This is a conservative,
# editable dictionary, never written back to Aerodrome.
AIRLINE_PREFIXES = {
    'EZY':'easyJet','EJU':'easyJet Europe','RYR':'Ryanair',
    'BAW':'British Airways','EFW':'BA Euroflyer','EXS':'Jet2.com',
    'AFR':'Air France','SWR':'Swiss','DLH':'Lufthansa',
    'WUK':'Wizz Air UK','WZZ':'Wizz Air','TOM':'TUI Airways',
    'THY':'Turkish Airlines','VLG':'Vueling','QTR':'Qatar Airways',
    'UAL':'United Airlines','AAL':'American Airlines','DAL':'Delta Air Lines',
    'KLM':'KLM','EIN':'Aer Lingus','IBE':'Iberia',
    'VIR':'Virgin Atlantic','UAE':'Emirates','ETD':'Etihad Airways',
    'TAP':'TAP Air Portugal','FIN':'Finnair','LOT':'LOT Polish Airlines',
    'SAS':'SAS','ACA':'Air Canada',
    # Airline and commercial operator designators observed in local receiver export.
    'RUK':'Ryanair UK','FDX':'FedEx Express','NPT':'West Atlantic UK',
    'WMT':'Wizz Air Malta','AEE':'Aegean Airlines',
    'TAY':'ASL Airlines Belgium','FPO':'ASL Airlines France',
    'AHY':'Azerbaijan Airlines','AMX':'Aeromexico',
    'ABV':'ASL Airlines UK','BCS':'European Air Transport (DHL)',
    'LHX':'Lufthansa City Airlines','MSR':'Egyptair',
    'CPA':'Cathay Pacific','EVA':'EVA Air','MAS':'Malaysia Airlines',
    'THA':'Thai Airways','GFA':'Gulf Air','AIC':'Air India',
    'MNB':'MNG Airlines','TAM':'LATAM Airlines Brasil',
    'AOJ':'Avcon Jet','MUK':'Maersk Air Cargo UK',
    'FJO':'Flexjet Operations Malta',
}


def resolved_airline(category: str, operator: str | None, route_airline: str | None,
                     callsign: str | None) -> str:
    """Resolve a *commercial* airline from existing metadata, then callsign.

    Never convert general aviation registrations into airline names. Missing
    commercial metadata remains a visible Unknown instead of being hidden.
    """
    if category != 'commercial':
        return ''
    for value in (route_airline, operator):
        if value and value.strip() and value.strip().lower() not in ('unknown','n/a','none','null'):
            return value.strip()
    call = (callsign or '').strip().upper()
    match = re.fullmatch(r'([A-Z]{3})[0-9][A-Z0-9]{0,7}', call)
    if match:
        return AIRLINE_PREFIXES.get(match.group(1), 'Unknown airline')
    return 'Unknown airline'


def resolved_operator(category: str, operator: str | None, airline: str,
                      route_airline: str | None) -> str:
    # Keep GA / military unassigned operators separate; they are not airlines.
    if operator and operator.strip() and operator.strip().lower() not in ('unknown','n/a','none','null'):
        return operator.strip()
    if category == 'commercial':
        return airline
    return {
        'general_aviation':'Unknown GA operator',
        'military':'Unknown military operator',
        'helicopter':'Unknown helicopter operator',
        'unknown':'Unknown category/operator',
    }.get(category, 'Unknown operator')

_DB_SEM = BoundedSemaphore(1)
_CACHE: OrderedDict[tuple, tuple[float, dict]] = OrderedDict()
_CACHE_LOCK = Lock()
CACHE_SECONDS = 75
CACHE_LIMIT = 35

class DataError(Exception):
    pass


def db_path() -> str:
    return os.environ.get('AIRSPACE_DB', DB_DEFAULT)


def connection() -> sqlite3.Connection:
    path = Path(db_path()).expanduser()
    if not path.is_file():
        raise DataError(f'Aerodrome database not found: {path}')
    uri = 'file:' + quote(str(path.resolve()), safe='/') + '?mode=ro'
    try:
        db = sqlite3.connect(uri, uri=True, timeout=0.3)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA busy_timeout=250')
        # Enforce a short read budget even on raw-browser queries. Analytics
        # explicitly supplies its own, longer deadline.
        deadline = monotonic() + 7.0
        db.set_progress_handler(lambda: 1 if monotonic() > deadline else 0, 15000)
        return db
    except sqlite3.Error as exc:
        raise DataError(f'Cannot open Aerodrome database read-only: {exc}') from exc


def epoch(s: str | int | float) -> int:
    if isinstance(s, (int, float)):
        return int(s)
    try:
        # UI datetime-local values are local UK wall-clock, including BST.
        if isinstance(s,str) and s.strip().lstrip('-').isdigit():
            return int(s)
        parsed = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return int(parsed.replace(tzinfo=UK).timestamp() if parsed.tzinfo is None else parsed.timestamp())
    except (ValueError, TypeError, OverflowError) as exc:
        raise DataError('Invalid timestamp; use an ISO-8601 date/time') from exc


def local_day(dt: datetime) -> datetime:
    return dt.astimezone(UK).replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_period(args: dict[str, str]) -> tuple[int, int, str]:
    now = datetime.now(UTC)
    now_ts = int(now.timestamp())
    preset = args.get('period', 'last_7d')
    local = now.astimezone(UK)
    choices = {
        'last_24h': 24 * 3600,
        'last_7d': 7 * 86400,
        'last_30d': 30 * 86400,
        'last_90d': 90 * 86400,
        'last_365d': 365 * 86400,
    }
    if preset in choices:
        start = now_ts - choices[preset]
        end = now_ts
    elif preset == 'today':
        start, end = int(local_day(local).timestamp()), now_ts
    elif preset == 'yesterday':
        midnight = local_day(local)
        start, end = int((midnight - timedelta(days=1)).timestamp()), int(midnight.timestamp())
    elif preset == 'this_week':
        week_start = local_day(local) - timedelta(days=local.weekday())
        start, end = int(week_start.timestamp()), now_ts
    elif preset == 'this_month':
        start, end = int(local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()), now_ts
    elif preset == 'this_year':
        start, end = int(local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()), now_ts
    elif preset == 'all':
        with closing(connection()) as db:
            row = db.execute('SELECT MIN(hour_bucket) FROM sightings_hourly').fetchone()
        start, end = (int(row[0]) if row and row[0] is not None else now_ts - 86400), now_ts
    elif preset == 'custom':
        start = epoch(args.get('start', ''))
        end = epoch(args.get('end', ''))
        end = min(end, now_ts + 3600)
    elif preset == 'rolling':
        try:
            num = int(args.get('amount', '7'))
        except ValueError:
            raise DataError('Rolling duration must be a number')
        if not (1 <= num <= 100_000):
            raise DataError('Rolling duration outside supported range')
        unit = args.get('unit', 'hours')
        secs = {'minutes':60, 'hours':3600, 'days':86400, 'weeks':604800}.get(unit)
        if unit in ('months', 'years'):
            month_count = num * (12 if unit == 'years' else 1)
            target = local.year * 12 + (local.month - 1) - month_count
            year, month = divmod(target, 12)
            if year < 1:
                raise DataError('Rolling range is too long')
            month += 1
            from calendar import monthrange
            earlier = local.replace(year=year, month=month,
                                    day=min(local.day, monthrange(year, month)[1]))
            start, end = int(earlier.timestamp()), now_ts
        elif secs is not None:
            start, end = now_ts - secs * num, now_ts
        else:
            raise DataError('Invalid rolling unit')
    else:
        raise DataError('Unknown time preset')
    if start >= end:
        raise DataError('Start must be before end')
    if end - start > MAX_WINDOW_SECONDS:
        raise DataError('Maximum supported range is 12 years')
    return start, end, preset


def validate_filters(args: dict[str, str]) -> dict[str, str]:
    return {
        'category': args.get('category', 'all').strip()[:80],
        'type': (args.get('type', 'all').strip()[:40].upper() if args.get('type', 'all').strip().lower() != 'all' else 'all'),
        'airline': args.get('airline', 'all').strip()[:120],
        'icao': args.get('icao', 'all').strip()[:12].lower(),
    }


def auto_group(start: int, end: int) -> str:
    span = end - start
    if span <= 72 * 3600: return 'hour'
    if span <= 120 * 86400: return 'day'
    if span <= 3 * 366 * 86400: return 'month'
    return 'year'


def hour_label(ts: int) -> str:
    return datetime.fromtimestamp(ts, UK).strftime('%Y-%m-%d %H:%M %Z')


def bucket_id(ts: int, group: str) -> str:
    dt = datetime.fromtimestamp(ts, UK)
    if group == 'hour': return datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%dT%H:00Z')
    if group == 'day': return dt.strftime('%Y-%m-%d')
    if group == 'week': return (dt.date() - timedelta(days=dt.weekday())).isoformat()
    if group == 'month': return dt.strftime('%Y-%m')
    if group == 'year': return dt.strftime('%Y')
    raise DataError('Unsupported grouping')


def display_bucket(key: str, group: str) -> str:
    if group == 'hour':
        return datetime.fromisoformat(key.replace('Z', '+00:00')).astimezone(UK).strftime('%-d %b, %H:%M')
    if group == 'day': return datetime.strptime(key, '%Y-%m-%d').strftime('%a %-d %b')
    if group == 'week': return 'Week of ' + datetime.strptime(key, '%Y-%m-%d').strftime('%-d %b %Y')
    if group == 'month': return datetime.strptime(key, '%Y-%m').strftime('%b %Y')
    return key


def hours_in_range(start: int, end: int):
    lo, hi = (start // 3600)*3600, ((end - 1)//3600)*3600
    for ts in range(lo, hi+1, 3600):
        yield ts


def _take_cached(key: tuple) -> dict | None:
    with _CACHE_LOCK:
        val = _CACHE.get(key)
        if val and monotonic() - val[0] < CACHE_SECONDS:
            _CACHE.move_to_end(key)
            return val[1]
        if val:
            del _CACHE[key]
    return None


def _put_cached(key: tuple, result: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (monotonic(), result)
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_LIMIT:
            _CACHE.popitem(last=False)


def minute_samples_by_utc_hour(start: int, end: int) -> dict[int, int]:
    """Available Aerodrome concurrency samples, not a guaranteed uptime log.

    Group inside SQLite so Python never receives years of minute-level rows.
    This is strictly a read from Aerodrome's pre-existing minute table.
    """
    if end <= start:
        return {}
    with closing(connection()) as db:
        try:
            rows = db.execute("""SELECT (minute_bucket / 3600) * 3600 AS hour,
                  COUNT(*) AS samples FROM concurrent_minute
                  WHERE minute_bucket >= ? AND minute_bucket < ?
                  GROUP BY (minute_bucket / 3600)""", (start, end))
            return {int(row[0]): int(row[1]) for row in rows}
        except sqlite3.OperationalError as exc:
            if 'interrupted' in str(exc).lower():
                raise DataError('Collection coverage query was too slow; choose a shorter period.') from exc
            raise DataError('Could not read collection coverage: ' + str(exc)) from exc


def coverage_eligible(key: str, unit: str, start: int, end: int,
                      samples: dict[int,int], *, include_partial: bool=False) -> bool:
    """Use only well-observed calendar occurrences in recurring averages.

    Missing minutes are NOT silently assumed to mean zero aircraft. 70% is a
    deliberately conservative signal that an occurrence is sufficiently sampled.
    """
    if unit == 'hour':
        begin = int(datetime.fromisoformat(key.replace('Z','+00:00')).timestamp())
        finish = begin + 3600
    elif unit == 'day':
        begin_dt = datetime.strptime(key,'%Y-%m-%d').replace(tzinfo=UK)
        begin, finish = int(begin_dt.timestamp()), int((begin_dt+timedelta(days=1)).timestamp())
    elif unit == 'month':
        begin_dt = datetime.strptime(key,'%Y-%m').replace(tzinfo=UK)
        next_year = begin_dt.year + (begin_dt.month == 12)
        next_month = begin_dt.month % 12 + 1
        begin, finish = int(begin_dt.timestamp()), int(begin_dt.replace(year=next_year, month=next_month).timestamp())
    else:
        return False
    lo, hi = max(begin, start), min(finish, end)
    if lo >= hi or (not include_partial and (lo != begin or hi != finish)):
        return False
    expected = max(1, math.ceil((hi-lo) / 60))
    found = sum(samples.get(hour, 0) for hour in range((lo//3600)*3600, hi, 3600))
    return found / expected >= 0.70


def recorded_occurrence_eligible(key: str, unit: str, start: int, end: int,
                                 samples: dict[int,int]) -> bool:
    """Include observed partial days for early installations.

    Aerodrome was activated in the evening, so insisting on 100% of a full
    day makes the user's very first Monday/Tuesday misleadingly appear as 0.
    Require actual minute records, not complete calendar dates. The resulting
    mean is per *recorded* day, without scaling partial days to 24 hours.
    """
    if unit == 'month':
        # A partial month is not a meaningful typical month: omit it.
        return coverage_eligible(key, unit, start, end, samples)
    if unit == 'hour':
        ts = int(datetime.fromisoformat(key.replace('Z','+00:00')).timestamp())
        return samples.get(ts, 0) >= 5
    if unit == 'day':
        begin = int(datetime.strptime(key, '%Y-%m-%d').replace(tzinfo=UK).timestamp())
        finish = int((datetime.strptime(key, '%Y-%m-%d').replace(tzinfo=UK) + timedelta(days=1)).timestamp())
        count = sum(n for hour,n in samples.items() if begin <= hour < finish)
        return count >= 30
    return False

def _new_unit() -> dict:
    return {'observations':0, 'flights':0, 'aircraft':set()}


def _metric(unit: dict, metric: str) -> int:
    if metric == 'aircraft': return len(unit['aircraft'])
    return unit[metric]


def analyze(args: dict[str, str]) -> dict[str, Any]:
    start, end, preset = resolve_period(args)
    metric = args.get('metric', 'flights')
    if metric not in ('flights','aircraft','observations'):
        raise DataError('Invalid measurement')
    group = args.get('bucket', 'auto')
    if group == 'auto': group = auto_group(start, end)
    if group not in ('hour','day','week','month','year','weekday','hour_of_day','month_of_year'):
        raise DataError('Invalid grouping')
    # Fail fast before reading large hourly tables when the requested chart
    # would exceed the safe point budget. Automatic grouping stays available.
    bucket_bounds = {'hour':3600, 'day':86400, 'week':604800, 'month':28*86400, 'year':365*86400}
    if group in bucket_bounds and end-start > 1200*bucket_bounds[group]:
        raise DataError('Too many chart points for this grouping. Choose a wider time interval.')
    flt = validate_filters(args)
    # Ranges roll forward; short TTL keys avoid permanently caching today's partial hour.
    aligned_key = (start//60,end//60,preset,metric,group,tuple(sorted(flt.items())),os.environ.get('AIRSPACE_DB',''))
    cached = _take_cached(aligned_key)
    if cached is not None:
        return cached
    if not _DB_SEM.acquire(timeout=0.2):
        raise DataError('The database is already processing another analysis. Please retry shortly.')
    try:
        result = _analyze_uncached(start, end, preset, metric, group, flt)
        _put_cached(aligned_key, result)
        return result
    finally:
        _DB_SEM.release()


def _analyze_uncached(start: int, end: int, preset: str, metric: str, group: str, flt: dict) -> dict:
    # Read hour summaries rather than every 10-second observation. A four-hour
    # lookback helps detect sessions already in progress at the left boundary.
    from_hour = (start // 3600)*3600
    until_hour = ((end-1)//3600)*3600 + 3600
    lookback = 4 * 3600
    base = '''FROM sightings_hourly h
        LEFT JOIN seen_aircraft a ON a.icao=h.icao
        LEFT JOIN (SELECT callsign, MAX(airline) AS airline FROM route_cache GROUP BY callsign) r ON r.callsign=h.callsign'''
    where = ['h.hour_bucket >= ?', 'h.hour_bucket < ?']
    values: list[Any] = [from_hour-lookback, until_hour]
    if flt['category'] != 'all':
        where.append("COALESCE(NULLIF(a.category,''),'unknown') = ?")
        values.append(flt['category'])
    if flt['type'] != 'all':
        where.append('UPPER(COALESCE(h.aircraft_type,a.aircraft_type,\'\')) = ?')
        values.append(flt['type'])
    # Airline/owner filters are evaluated against *resolved* values below,
    # so inferred commercial callsign prefixes remain selectable.
    if flt['icao'] != 'all':
        where.append('h.icao = ?')
        values.append(flt['icao'])
    sql = '''SELECT h.icao, h.hour_bucket, h.sighting_count,
        h.first_seen_at, h.last_seen_at, h.aircraft_type, h.callsign,
        a.category, a.operator, r.airline
        ''' + base + ' WHERE ' + ' AND '.join(where) + ' ORDER BY h.hour_bucket, h.icao'
    # The source uses hourly buckets: positions near exact start/end times are
    # included with the hour. Make the approximation visible in the UI.
    is_pattern = group in ('weekday','hour_of_day','month_of_year')
    underlying = {'weekday':'day','hour_of_day':'hour','month_of_year':'month'}.get(group,group)
    buckets = defaultdict(_new_unit)
    total = _new_unit()
    breakdowns: dict[str, dict[str, dict]] = {k:defaultdict(_new_unit) for k in ('category','type','airline','operator')}
    last_seen: dict[str, tuple[int,str]] = {}
    processed = 0
    first_data = None
    last_data = None
    with closing(connection()) as db:
        # Bound query execution to protect Aerodrome / SDR feeders from heavy reads.
        deadline = monotonic() + 14.0
        db.set_progress_handler(lambda: 1 if monotonic() > deadline else 0, 15000)
        try:
            cursor = db.execute(sql, values)
            for row in cursor:
                processed += 1
                if processed > MAX_ROWS:
                    raise DataError('Too many hourly records for one query. Narrow the date range or filters.')
                icao = (row['icao'] or '').lower()
                if not icao: continue
                seen_start = int(row['first_seen_at'] or row['hour_bucket'])
                seen_end = int(row['last_seen_at'] or row['hour_bucket'])
                callsign = (row['callsign'] or '').strip().upper()
                last = last_seen.get(icao)
                new_flight = not last or seen_start-last[0] > SESSION_GAP or (last[1] and callsign and last[1] != callsign)
                last_seen[icao] = (max(seen_end,last[0]) if last else seen_end,callsign or (last[1] if last else ''))
                # Lookback rows are only for session continuation.
                if row['hour_bucket'] < from_hour or seen_end < start or seen_start >= end:
                    continue
                first_data = seen_start if first_data is None else min(first_data,seen_start)
                last_data = seen_end if last_data is None else max(last_data,seen_end)
                b = bucket_id(int(row['hour_bucket']), underlying)
                n = int(row['sighting_count'] or 0)
                category = (row['category'] or 'unknown').lower().strip() or 'unknown'
                typ = (row['aircraft_type'] or 'Unknown').upper().strip() or 'Unknown'
                airline = resolved_airline(category,row['operator'],row['airline'],callsign)
                operator = resolved_operator(category,row['operator'],airline,row['airline'])
                if flt['airline'] != 'all' and flt['airline'] not in (airline,operator):
                    continue
                # Shared helper values; observed time is approximated to the containing hour.
                unit = buckets[b]
                unit['observations'] += n
                unit['aircraft'].add(icao)
                total['observations'] += n
                total['aircraft'].add(icao)
                vals = (category,typ,airline,operator)
                for label, name in zip(('category','type','airline','operator'),vals):
                    if label == 'airline' and category != 'commercial':
                        continue
                    key_unit = breakdowns[label][name]
                    key_unit['observations'] += n
                    key_unit['aircraft'].add(icao)
                if new_flight and start <= seen_start < end:
                    # Attribute a distinct visit to its approximate start time.
                    flight_key = bucket_id(seen_start, underlying)
                    buckets[flight_key]['flights'] += 1
                    total['flights'] += 1
                    for label,name in zip(('category','type','airline','operator'),vals):
                        if label == 'airline' and category != 'commercial':
                            continue
                        breakdowns[label][name]['flights'] += 1
        except sqlite3.OperationalError as exc:
            if 'interrupted' in str(exc).lower():
                raise DataError('This query exceeded the 14-second safety limit. Please use a narrower date range.') from exc
            raise DataError(f'Database read failed: {exc}') from exc
    # Populate empty time slots, including zero sightings. Silence may mean no
    # aircraft OR receiver downtime; the UI explicitly marks this uncertainty.
    if underlying == 'hour' and (end-start)//3600 > 12000:
        raise DataError('Too many hourly points. Choose a larger grouping.')
    for ts in hours_in_range(start,end):
        buckets[bucket_id(ts,underlying)]
    if is_pattern:
        coverage_hours = minute_samples_by_utc_hour(start, end)
        grouped: dict[str, list[dict]] = defaultdict(list)
        for key, unit in buckets.items():
            if not recorded_occurrence_eligible(key,underlying,start,end,coverage_hours):
                continue
            if group == 'weekday':
                pk = str(datetime.strptime(key,'%Y-%m-%d').weekday())
            elif group == 'hour_of_day':
                pk = str(datetime.fromisoformat(key.replace('Z','+00:00')).astimezone(UK).hour)
            else:
                pk = str(int(key.split('-')[1]))
            grouped[pk].append(unit)
        if group == 'weekday':
            indexes = range(7)
            names = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        elif group == 'hour_of_day':
            indexes = range(24)
            names = [f'{x:02}:00' for x in indexes]
        else:
            indexes = range(1,13)
            names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        series = []
        for idx,name in zip(indexes,names):
            units = grouped.get(str(idx),[])
            mean = sum(_metric(v,metric) for v in units)/len(units) if units else None
            series.append({'key':str(idx),'label':name,'value':round(mean,2) if mean is not None else None,'samples':len(units)})
        aggregation_label = 'Average per recorded occurrence'
    else:
        series = [{'key':key,'label':display_bucket(key,group),'value':_metric(buckets[key],metric)} for key in sorted(buckets)]
        aggregation_label = 'Per time bucket'
    # A chart with >1000 points would be unusable on an iPhone; enforce a
    # predictable response rather than silently dropping or altering dates.
    if len(series) > 1200:
        raise DataError(f'{len(series):,} chart points is too many. Choose a wider grouping.')
    charts = {}
    for label, collection in breakdowns.items():
        items = [{'name':name,'value':_metric(unit,metric)} for name,unit in collection.items()]
        items.sort(key=lambda item:item['value'],reverse=True)
        charts[label] = items[:35]
    values_series = [float(i['value']) for i in series if i['value'] is not None]
    # concurrent_minute is a useful *proxy* for collection completeness. It
    # isn't a definitive proof of uptime (depending on Aerodrome version,
    # genuinely empty minutes may not generate a record).
    with closing(connection()) as check_db:
        sampled=check_db.execute(
            'SELECT COUNT(*) FROM concurrent_minute WHERE minute_bucket >= ? AND minute_bucket < ?',
            (start,end)).fetchone()[0]
    eligible_minutes=max(1, math.ceil((end-start)/60))
    coverage = {'source':'Aerodrome hourly rollups','first':first_data,'last':last_data,
        'hours_with_aircraft':sum(1 for x in buckets.values() if x['observations']>0),
        'sampled_hours':len([x for x in buckets if underlying=='hour']) if underlying=='hour' else None,
        'recorded_minute_samples':sampled, 'expected_minutes':eligible_minutes,
        'sample_ratio':round(min(100,100*sampled/eligible_minutes),1),
        'sample_warning':'Minute samples are a proxy, not a guaranteed receiver-uptime measurement.',
        'precision':'Hourly rollups may include observations outside an exact minute boundary.'}
    result = {
        'metric':metric, 'bucket':group, 'period':preset, 'start':start, 'end':end,
        'filters':flt, 'total':_metric(total,metric),
        'unique_aircraft':len(total['aircraft']), 'estimated_flights':total['flights'],
        'observations':total['observations'], 'series':series, 'aggregation_label':aggregation_label,
        'average':round(sum(values_series)/len(values_series),2) if values_series else 0,
        'peak':max(values_series) if values_series else 0,
        'breakdowns':charts, 'coverage':coverage,
        'notes':[
          'Flights are estimated coverage visits, not verified end-to-end flights. Separate visits within one aircraft-hour may be merged.',
          'Unique aircraft counts in individual time buckets may sum to more than the period total.',
          'Hour summaries are approximate at exact start/end minute boundaries; a quiet hour may also reflect a receiver outage.',
          'Weekday and hour averages include recorded partial days. Unobserved periods are excluded.',
          'Aircraft/airline categories use Aerodrome enrichment, which can be missing or change over time.'
        ],
    }
    return result


def health() -> dict:
    path = Path(db_path())
    with closing(connection()) as db:
        first, last, n = db.execute('SELECT MIN(seen_at),MAX(seen_at),COUNT(*) FROM all_sightings').fetchone()
        hourly_first, hourly_last = db.execute('SELECT MIN(hour_bucket), MAX(hour_bucket) FROM sightings_hourly').fetchone()
        total_seen = db.execute('SELECT COUNT(*) FROM seen_aircraft').fetchone()[0]
        military = db.execute("SELECT COUNT(*) FROM seen_aircraft WHERE category='military'").fetchone()[0]
        last_minute = db.execute('SELECT MAX(minute_bucket) FROM concurrent_minute').fetchone()[0]
    age = int(datetime.now(UTC).timestamp()) - (last or 0)
    return {
        'ok':True, 'db_path':str(path), 'db_size_bytes':path.stat().st_size,
        'first_sighting':first,'last_sighting':last,'raw_observations':n,
        'first_hour':hourly_first,'last_hour':hourly_last,'total_aircraft':total_seen,
        'military_aircraft_all_time':military, 'last_concurrency_sample':last_minute,
        'age_seconds':age, 'fresh':age <= 180,
    }


def overview() -> dict:
    now = datetime.now(UK)
    midnight = int(local_day(now).timestamp())
    with closing(connection()) as db:
        # DISTINCT, not observation count
        unique_today = db.execute('SELECT COUNT(DISTINCT icao) FROM sightings_hourly WHERE hour_bucket >= ?', (midnight,)).fetchone()[0]
        observations_today = db.execute('SELECT COALESCE(SUM(sighting_count),0) FROM sightings_hourly WHERE hour_bucket >= ?', (midnight,)).fetchone()[0]
        peak = db.execute('SELECT MAX(count) FROM concurrent_minute WHERE minute_bucket >= ?', (midnight,)).fetchone()[0] or 0
        latest_concurrent = db.execute('SELECT count FROM concurrent_minute ORDER BY minute_bucket DESC LIMIT 1').fetchone()
    h = health()
    return {
        **h, 'unique_today':unique_today, 'observations_today':observations_today,
        'peak_today':peak, 'live_count':int(latest_concurrent[0]) if latest_concurrent and h['fresh'] else None,
    }


# Database viewer: whitelist existing user-facing tables. No arbitrary SQL.
PUBLIC_TABLES = {
    'all_sightings','sightings_hourly','aircraft_track_daily','concurrent_minute',
    'seen_aircraft','military_hourly','military_sightings','watchlist_hourly',
    'watchlist_sightings','flight_routes','route_cache','hexdb_cache',
    'hexdb_events','stats_records','photo_cache',
}


def list_tables() -> list[dict]:
    result = []
    with closing(connection()) as db:
        for name in sorted(PUBLIC_TABLES):
            exists = db.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?',(name,)).fetchone()
            if not exists: continue
            cols = [r['name'] for r in db.execute(f'PRAGMA table_info("{name}")')]
            result.append({'name':name,'columns':cols})
    return result


def table_rows(name: str, page: int=1, limit: int=30, search: str='') -> dict:
    if name not in PUBLIC_TABLES:
        raise DataError('That table is not available in the read-only viewer')
    if page < 1 or page > 10000 or limit < 1 or limit > 200:
        raise DataError('Invalid page or limit')
    with closing(connection()) as db:
        cols = [r['name'] for r in db.execute(f'PRAGMA table_info("{name}")')]
        if not cols: raise DataError('Table unavailable')
        searchable = [i for i in ('icao','callsign','registration','aircraft_type','category','operator','airline','origin_icao','dest_icao') if i in cols]
        args = []
        where = ''
        if search and searchable:
            where = ' WHERE '+ ' OR '.join(f'"{field}" LIKE ?' for field in searchable)
            args = ['%'+search[:80]+'%'] * len(searchable)
        sort = next((x for x in ('seen_at','hour_bucket','minute_bucket','day_bucket','last_seen_at','id','icao') if x in cols),cols[0])
        sql = f'SELECT * FROM "{name}"{where} ORDER BY "{sort}" DESC LIMIT ? OFFSET ?'
        try:
            rows = db.execute(sql,args+[limit+1,(page-1)*limit]).fetchall()
        except sqlite3.Error as exc:
            raise DataError(str(exc)) from exc
    data = []
    for row in rows[:limit]:
        data.append({k:('‹binary›' if isinstance(row[k],bytes) else row[k]) for k in cols})
    return {'table':name,'columns':cols,'rows':data,'page':page,'limit':limit,'has_more':len(rows)>limit,'search':search}


def aircraft_search(query: str='', limit:int=40) -> list[dict]:
    limit = max(1,min(100,limit))
    with closing(connection()) as db:
        if query:
            like = '%'+query[:90]+'%'
            rows=db.execute('''SELECT icao, registration, last_callsign, aircraft_type, aircraft_type_desc,
                operator, category, country, last_seen_at, sighting_count
                FROM seen_aircraft WHERE icao LIKE ? OR registration LIKE ?
                OR last_callsign LIKE ? OR aircraft_type LIKE ? OR operator LIKE ?
                ORDER BY last_seen_at DESC LIMIT ?''',(*([like]*5),limit)).fetchall()
        else:
            rows=db.execute('''SELECT icao, registration, last_callsign, aircraft_type, aircraft_type_desc,
                operator, category, country, last_seen_at, sighting_count
                FROM seen_aircraft ORDER BY last_seen_at DESC LIMIT ?''',(limit,)).fetchall()
    return [dict(row) for row in rows]


def aircraft_detail(icao: str) -> dict:
    if not re.fullmatch('[0-9a-fA-F]{6}',icao):
        raise DataError('Enter a six-character ICAO hex identifier')
    with closing(connection()) as db:
        aircraft=db.execute('SELECT * FROM seen_aircraft WHERE icao=?',(icao.lower(),)).fetchone()
        if not aircraft: raise DataError('Aircraft not found')
        sightings=db.execute('''SELECT seen_at,callsign,lat,lon,altitude,speed,squawk
            FROM all_sightings WHERE icao=? ORDER BY seen_at DESC LIMIT 250''',(icao.lower(),)).fetchall()
        days=db.execute('''SELECT day_bucket, best_session_duration, best_session_start, best_session_end
            FROM aircraft_track_daily WHERE icao=? ORDER BY day_bucket DESC LIMIT 120''',(icao.lower(),)).fetchall()
    return {'aircraft':dict(aircraft),'sightings':[dict(x) for x in sightings], 'days':[dict(x) for x in days]}


def compare(args: dict[str,str]) -> dict:
    # Compare *equal-length* arbitrary windows, or a preset with its immediately
    # preceding equal-duration window. Use explicit overrides for manual windows.
    first_start, first_end, preset=resolve_period(args)
    if args.get('comparison','previous') == 'year_ago':
        import calendar
        def previous_year(ts):
            d = datetime.fromtimestamp(ts, UK)
            y = d.year - 1
            return int(d.replace(year=y, day=min(d.day, calendar.monthrange(y,d.month)[1])).timestamp())
        second_start, second_end = previous_year(first_start), previous_year(first_end)
    elif args.get('comparison','previous') == 'custom':
        second_start, second_end = epoch(args.get('other_start','')),epoch(args.get('other_end',''))
        if second_start>=second_end: raise DataError('Invalid second period')
    else:
        try: offset=int(args.get('offset','1'))
        except ValueError: raise DataError('Invalid comparison offset')
        if offset<1 or offset>100: raise DataError('Comparison offset must be 1–100')
        # Calendar-aware shifts for today/week/month/year: elapsed time is
        # matched to the equivalent point, not the prior *partial* duration.
        def shift_month(dt, months):
            y = dt.year+(dt.month-1+months)//12
            m = (dt.month-1+months)%12+1
            import calendar
            return dt.replace(year=y,month=m,day=min(dt.day,calendar.monthrange(y,m)[1]))
        if preset in ('today','yesterday','this_week','this_month','this_year'):
            lstart=datetime.fromtimestamp(first_start, UK)
            lend=datetime.fromtimestamp(first_end, UK)
            if preset in ('today','yesterday'):
                a=lstart-timedelta(days=offset)
                b=lend-timedelta(days=offset)
            elif preset=='this_week':
                a=lstart-timedelta(weeks=offset)
                b=lend-timedelta(weeks=offset)
            elif preset=='this_month':
                a=shift_month(lstart,-offset)
                b=shift_month(lend,-offset)
            else:
                a=shift_month(lstart,-12*offset)
                b=shift_month(lend,-12*offset)
            second_start,second_end=int(a.timestamp()),int(b.timestamp())
        else:
            duration=first_end-first_start
            second_start=first_start-(duration*offset)
            second_end=first_end-(duration*offset)
    root={k:v for k,v in args.items() if k not in ('period','start','end','comparison','offset','other_start','other_end')}
    left=analyze({**root,'period':'custom','start':str(first_start),'end':str(first_end)})
    right=analyze({**root,'period':'custom','start':str(second_start),'end':str(second_end)})
    va,vb=float(left['total']),float(right['total'])
    sufficient = right['coverage']['sample_ratio'] >= 50
    change=None if vb==0 or not sufficient else round((va-vb)*100/vb,1)
    return {'left':left,'right':right,'difference':va-vb,'change_percent':change,
        'comparable':sufficient,
        'interpretation':'Comparison periods may have different data availability; below 50% historical minute-sample coverage, a percentage change is not shown.'}


def patterns(args:dict[str,str]) -> dict:
    start,end,preset=resolve_period(args)
    metric=args.get('metric','flights')
    if metric not in ('flights','aircraft','observations'): raise DataError('Invalid measurement')
    filters=validate_filters(args)
    key=('patterns',start//60,end//60,metric,tuple(sorted(filters.items())))
    cached=_take_cached(key)
    if cached:return cached
    if not _DB_SEM.acquire(timeout=0.2):
        raise DataError('An analysis is already running. Please try again shortly.')
    try:
        result=_patterns_uncached(start,end,metric,filters)
        _put_cached(key,result)
        return result
    finally:
        _DB_SEM.release()


def _patterns_uncached(start,end,metric,flt):
    from_hour=(start//3600)*3600
    until_hour=((end-1)//3600)*3600+3600
    w=['h.hour_bucket >= ?','h.hour_bucket < ?']
    v=[from_hour-4*3600,until_hour]
    if flt['category']!='all':
        w.append("COALESCE(NULLIF(a.category,''),'unknown') = ?")
        v.append(flt['category'])
    if flt['type']!='all':
        w.append("UPPER(COALESCE(h.aircraft_type,a.aircraft_type,'')) = ?")
        v.append(flt['type'])
    # Resolve carrier callsigns in Python, in the same way as Traffic.
    if flt['icao']!='all':
        w.append('h.icao = ?');v.append(flt['icao'])
    sql='''SELECT h.icao,h.hour_bucket,h.sighting_count,h.first_seen_at,h.last_seen_at,h.callsign,
       a.category,a.operator,r.airline
       FROM sightings_hourly h LEFT JOIN seen_aircraft a ON a.icao=h.icao
       LEFT JOIN (SELECT callsign, MAX(airline) AS airline FROM route_cache GROUP BY callsign) r ON r.callsign=h.callsign
       WHERE '''+' AND '.join(w)+' ORDER BY h.hour_bucket,h.icao'
    hours=defaultdict(_new_unit)
    last_seen={}
    row_count=0
    with closing(connection()) as db:
        deadline=monotonic()+14
        db.set_progress_handler(lambda:1 if monotonic()>deadline else 0,15000)
        try:
            for row in db.execute(sql,v):
                row_count+=1
                if row_count>MAX_ROWS: raise DataError('Too much data for one pattern request. Narrow the range.')
                icao=(row['icao'] or '').lower()
                if not icao: continue
                first=int(row['first_seen_at'] or row['hour_bucket'])
                last=int(row['last_seen_at'] or row['hour_bucket'])
                call=(row['callsign'] or '').strip().upper()
                cat=(row['category'] or 'unknown').lower()
                air=resolved_airline(cat,row['operator'],row['airline'],call)
                op=resolved_operator(cat,row['operator'],air,row['airline'])
                if flt['airline']!='all' and flt['airline'] not in (air,op):
                    continue
                old=last_seen.get(icao)
                new=not old or first-old[0]>SESSION_GAP or (old[1] and call and old[1]!=call)
                last_seen[icao]=(max(last,old[0]) if old else last,call or (old[1] if old else ''))
                if row['hour_bucket']<from_hour or last<start or first>=end:continue
                slot=hours[int(row['hour_bucket'])]
                slot['observations']+=int(row['sighting_count'] or 0)
                slot['aircraft'].add(icao)
                if new and start<=first<end:
                    hours[(first//3600)*3600]['flights']+=1
        except sqlite3.OperationalError as exc:
            if 'interrupted' in str(exc).lower(): raise DataError('Pattern query exceeded the safety time limit. Select a shorter period.') from exc
            raise DataError(str(exc)) from exc
    minute_hours = minute_samples_by_utc_hour(start,end)
    days=defaultdict(_new_unit)
    cell=defaultdict(list)
    hour_by=defaultdict(list)
    for ts in hours_in_range(start,end):
        x=hours[ts]
        local=datetime.fromtimestamp(ts,UK)
        day=local.strftime('%Y-%m-%d')
        d=days[day]
        d['observations']+=x['observations']
        d['flights']+=x['flights']
        d['aircraft'].update(x['aircraft'])
        wd=local.weekday(); hour=local.hour
        if recorded_occurrence_eligible(bucket_id(ts,'hour'),'hour',start,end,minute_hours):
            cell[(wd,hour)].append(_metric(x,metric))
            hour_by[hour].append(_metric(x,metric))
    weekday_names=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    by_wd=defaultdict(list)
    for date_string, unit in days.items():
        if not recorded_occurrence_eligible(date_string,'day',start,end,minute_hours):
            continue
        wd=datetime.strptime(date_string,'%Y-%m-%d').weekday()
        by_wd[wd].append(_metric(unit,metric))
    weekdays=[{'key':str(d),'label':weekday_names[d],'value':round(sum(by_wd[d])/len(by_wd[d]),2) if by_wd[d] else None,'samples':len(by_wd[d])} for d in range(7)]
    hourly=[{'key':str(h),'label':f'{h:02}:00','value':round(sum(hour_by[h])/len(hour_by[h]),2) if hour_by[h] else None,'samples':len(hour_by[h])} for h in range(24)]
    cells=[{'weekday':d,'hour':h,'value':round(sum(cell[(d,h)])/len(cell[(d,h)]),2) if cell[(d,h)] else None,'samples':len(cell[(d,h)])} for d in range(7) for h in range(24)]
    return {'start':start,'end':end,'metric':metric,'weekday':weekdays,'hourly':hourly,'heatmap':cells,
        'strongest_hour':max((x for x in cells if x['samples'] > 0),key=lambda x:x['value'],default=None),
        'note':'Average per recorded day/hour. Partial days are included; unavailable periods are null.'}


def filter_options() -> dict:
    """Global options; no observation scans or edits are required."""
    with closing(connection()) as db:
        aircraft_types=[r[0] for r in db.execute('''SELECT UPPER(TRIM(aircraft_type)) FROM seen_aircraft
           WHERE aircraft_type IS NOT NULL AND TRIM(aircraft_type)!=''
           GROUP BY UPPER(TRIM(aircraft_type)) ORDER BY COUNT(*) DESC LIMIT 1000''')]
        operators=[r[0] for r in db.execute('''SELECT TRIM(operator) FROM seen_aircraft
           WHERE operator IS NOT NULL AND TRIM(operator)!=''
           GROUP BY TRIM(operator) ORDER BY COUNT(*) DESC LIMIT 1000''')]
        airlines=[r[0] for r in db.execute('''SELECT DISTINCT TRIM(airline) FROM route_cache
           WHERE airline IS NOT NULL AND TRIM(airline)!='' LIMIT 1000''')]
    return {'types':aircraft_types,'airlines':list(dict.fromkeys(airlines+operators+list(AIRLINE_PREFIXES.values())))}
