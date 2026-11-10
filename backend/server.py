"""Airspace Analytics, local-only API and static website (stdlib-only)."""
from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import parse_qs, unquote, urlsplit
import csv
import hmac
import ipaddress
import io
import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import time
import traceback

from . import data

BASE = Path(__file__).resolve().parents[1]
STATIC = BASE / 'frontend'
STATE = BASE / '.airspace-state'
VERSION = (BASE / 'VERSION').read_text().strip()
MAX_POST = 16 * 1024
_CHECK_LOCK = Lock()
_CHECK_CACHE = {'time':0, 'data':None}


def version_info(refresh=False):
    now=time.time()
    with _CHECK_LOCK:
        if not refresh and _CHECK_CACHE['data'] is not None and now-_CHECK_CACHE['time'] < 3*3600:
            return _CHECK_CACHE['data']
        info={'version':VERSION,'available':False,'configured':False,'local_sha':None,'remote_sha':None,
              'repository':None,'error':None,'checked_at':int(now)}
        try:
            def git(*args):
                return subprocess.run(['git','-C',str(BASE),*args],check=True,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,text=True,timeout=14,
                    env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_SSH_COMMAND':'ssh -o BatchMode=yes'}).stdout.strip()
            remote=git('remote','get-url','origin')
            branch=git('branch','--show-current')
            if not branch:
                raise RuntimeError('Detached Git branch; checkout the normal branch')
            local=git('rev-parse','HEAD')
            line=git('ls-remote','origin',f'refs/heads/{branch}')
            if not line: raise RuntimeError('Could not find the remote branch')
            remote_sha=line.split()[0]
            info.update({'configured':True,'repository':remote,'branch':branch,
                         'local_sha':local[:10], 'remote_sha':remote_sha[:10],
                         'available':remote_sha!=local})
        except (subprocess.SubprocessError,RuntimeError,FileNotFoundError) as exc:
            info['error']=str(exc)[:220]
        _CHECK_CACHE.update(time=now,data=info)
        return info


def update_status():
    path=STATE/'update-status.json'
    if not path.exists(): return {'state':'idle','detail':'No updates installed through the UI yet.'}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {'state':'unknown','detail':'Update status file could not be read.'}


def write_status(state, detail):
    STATE.mkdir(parents=True,exist_ok=True)
    temp=STATE/'update-status.tmp'
    temp.write_text(json.dumps({'state':state,'detail':detail,'at':int(time.time())}))
    os.replace(temp,STATE/'update-status.json')


class App(BaseHTTPRequestHandler):
    server_version='AirspaceAnalytics/1.0'

    def log_message(self, format, *args):
        sys.stdout.write('[web] '+format % args+'\n')
        sys.stdout.flush()

    def send_json(self, result, code=200):
        body=json.dumps(result,default=str,allow_nan=False,separators=(',',':')).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.safe_headers()
        self.end_headers()
        self.wfile.write(body)

    def safe_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','SAMEORIGIN')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'self'")

    def _safe_run(self, handler):
        try:
            return handler()
        except (data.DataError, ValueError) as exc:
            self.send_json({'error':str(exc)},400)
        except BrokenPipeError:
            return
        except Exception as exc:
            print('[web] error:',repr(exc),flush=True)
            self.send_json({'error':'Internal website error. Check the airspace-analytics service logs.'},500)

    def get_query(self):
        if len(self.path) > 4096:
            raise ValueError('Request URL too long')
        path=urlsplit(self.path)
        return path.path, {k:v[-1] for k,v in parse_qs(path.query).items()}

    def do_GET(self):
        self._safe_run(self._get)

    def _get(self):
        path, q=self.get_query()
        if not path.startswith('/api/'):
            return self.static(path)
        if path=='/api/config':
            return self.send_json({'version':VERSION,'timezone':'Europe/London',
                'name':'Airspace Analytics','update_token_required':False})
        if path=='/api/health': return self.send_json(data.health())
        if path=='/api/overview': return self.send_json(data.overview())
        if path=='/api/filters': return self.send_json(data.filter_options())
        if path=='/api/analytics': return self.send_json(data.analyze(q))
        if path=='/api/patterns': return self.send_json(data.patterns(q))
        if path=='/api/compare': return self.send_json(data.compare(q))
        if path=='/api/aircraft': return self.send_json({'items':data.aircraft_search(q.get('q',''),int(q.get('limit','40')))})
        if path.startswith('/api/aircraft/'):
            return self.send_json(data.aircraft_detail(path.split('/')[-1]))
        if path=='/api/database/tables': return self.send_json({'tables':data.list_tables()})
        if path=='/api/database/rows':
            return self.send_json(data.table_rows(q.get('table','all_sightings'),int(q.get('page','1')),
                                                  int(q.get('limit','30')),q.get('q','')))
        if path=='/api/database/export': return self.export(q)
        if path=='/api/update/check': return self.send_json(version_info(q.get('refresh')=='1'))
        if path=='/api/update/status': return self.send_json(update_status())
        self.send_json({'error':'Unknown API endpoint'},404)

    def export(self,q):
        table=q.get('table','')
        if table not in data.PUBLIC_TABLES: raise data.DataError('Invalid table')
        rows=[]
        cols=[]
        for page in range(1,26):
            result=data.table_rows(table,page,200,q.get('q',''))
            cols=result['columns']
            rows.extend(result['rows'])
            if not result['has_more']:break
        output=io.StringIO()
        writer=csv.DictWriter(output, fieldnames=cols)
        writer.writeheader()
        # Spreadsheet programs can execute formulas inside exported cells.
        # Escape untrusted aircraft text without altering the source data.
        def spreadsheet_safe(value):
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
                return '\'' + value
            return value
        writer.writerows({key:spreadsheet_safe(val) for key,val in row.items()} for row in rows)
        body=output.getvalue().encode('utf-8-sig')
        self.send_response(200)
        self.send_header('Content-Type','text/csv; charset=utf-8')
        self.send_header('Content-Disposition',f'attachment; filename="{table}-export.csv"')
        self.send_header('Content-Length',str(len(body)))
        self.safe_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._safe_run(self._post)

    def _post(self):
        path, _=self.get_query()
        if path not in ('/api/update/apply','/api/update/rollback'):
            return self.send_json({'error':'Unknown endpoint'},404)
        # One-click updates are limited to loopback, home-LAN and Tailscale
        # clients. Cross-site requests cannot initiate even the fixed Git update.
        origin=self.headers.get('Origin','')
        host=self.headers.get('Host','')
        fetch_site=self.headers.get('Sec-Fetch-Site','')
        if (origin and origin not in ('http://'+host,'https://'+host)) or fetch_site not in ('','same-origin','none'):
            return self.send_json({'error':'Cross-origin update request blocked'},403)
        try:
            remote=ipaddress.ip_address(self.client_address[0])
            trusted_ranges=(
                '127.0.0.0/8','10.0.0.0/8','172.16.0.0/12',
                '192.168.0.0/16','100.64.0.0/10','::1/128','fc00::/7',
            )
            if not any(remote in ipaddress.ip_network(c) for c in trusted_ranges):
                return self.send_json({'error':'Updates are available from the local network only'},403)
        except ValueError:
            return self.send_json({'error':'Invalid client address'},403)
        if update_status().get('state') in ('running','queued'):
            status=update_status()
            if time.time()-status.get('at',0) < 300:
                return self.send_json({'error':'An update is already in progress'},409)
        if not version_info().get('configured'):
            return self.send_json({'error':'This installation is not linked to a GitHub repository'},400)
        action = 'rollback' if path.endswith('/rollback') else 'update'
        if action == 'rollback' and not (STATE/'previous-commit').exists():
            return self.send_json({'error':'No previous version has been recorded to restore.'},400)
        (STATE/'update-action.json').write_text(json.dumps({'action':action}))
        write_status('queued', 'Restoring previous version…' if action=='rollback' else 'Starting GitHub updater…')
        # A root-owned systemd .path unit observes ONLY this signal file.
        # No sudo/root process is launched by the web server; the updater
        # itself runs as this unprivileged user and restarts only our service.
        try:
            marker=STATE/'update-request'
            marker.write_text(str(time.time())+'\n')
            return self.send_json({'ok':True,'state':'queued'})
        except OSError as exc:
            write_status('failed','Could not request update: '+str(exc))
            return self.send_json({'error':'Updater could not be signalled'},503)

    def static(self, request_path):
        raw=unquote(request_path)
        if raw in ('/','/index.html'):
            dest=STATIC/'index.html'
        else:
            rel=raw.lstrip('/')
            if not rel or '\x00' in rel or '..' in Path(rel).parts:
                return self.send_json({'error':'Invalid path'},400)
            dest=(STATIC/rel).resolve()
            if STATIC.resolve() not in dest.parents:
                return self.send_json({'error':'Invalid path'},400)
        if not dest.is_file():
            # Client-side routing supports /explore etc.
            if re.fullmatch(r'/[a-z-]+',raw): dest=STATIC/'index.html'
            else: return self.send_json({'error':'Not found'},404)
        body=dest.read_bytes()
        mime=mimetypes.guess_type(str(dest))[0] or 'application/octet-stream'
        if dest.suffix=='.js': mime='text/javascript'
        self.send_response(200)
        self.send_header('Content-Type',mime+'; charset=utf-8' if mime.startswith('text/') else mime)
        self.send_header('Content-Length',str(len(body)))
        self.safe_headers()
        self.end_headers()
        self.wfile.write(body)


def run():
    host=os.environ.get('AIRSPACE_HOST','0.0.0.0')
    port=int(os.environ.get('AIRSPACE_PORT','8088'))
    ThreadingHTTPServer.daemon_threads=True
    server=ThreadingHTTPServer((host,port),App)
    print(f'Airspace Analytics v{VERSION} on http://{host}:{port}; Aerodrome DB {data.db_path()}',flush=True)
    try: server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__=='__main__':
    run()
