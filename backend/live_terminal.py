"""Read-only on-demand SSE stream mirroring the real Ultrafeeder viewadsb PTY."""
import errno
import fcntl
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import termios
import time
from threading import BoundedSemaphore

COMMAND = ('docker', 'exec', '-e', 'TERM=xterm', '-t', 'ultrafeeder', 'viewadsb')
ROWS, COLS = 42, 132
SLOTS = BoundedSemaphore(3)

def stream(handler):
    """Stream screen redraws as they arrive; never poll aircraft.json."""
    if not SLOTS.acquire(blocking=False):
        return handler.send_json({'error': 'Too many concurrent terminal viewers'}, 503)
    master = slave = process = None
    connected = False
    try:
        if not shutil.which('docker'):
            return handler.send_json({'error': 'Docker is unavailable to the website service'}, 503)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ,
                    struct.pack('HHHH', ROWS, COLS, 0, 0))
        # Command is fixed. No shell, sudo, user-provided arguments or stdin.
        process = subprocess.Popen(COMMAND, stdin=subprocess.DEVNULL,
                                   stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)
        slave = None
        handler.send_response(200)
        handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
        handler.send_header('X-Accel-Buffering', 'no')
        handler.safe_headers()
        handler.end_headers()
        connected = True
        handler.close_connection = True
        handler.wfile.write(b': connected\n\n')
        handler.wfile.flush()
        last_ping = time.monotonic()
        while True:
            ready, _, _ = select.select([master], [], [], 0.5)
            if ready:
                try:
                    raw = os.read(master, 16384)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not raw:
                    break
                handler.wfile.write(('data: ' + json.dumps(raw.decode('utf-8', 'replace'))
                                     + '\n\n').encode())
                handler.wfile.flush()
            if process.poll() is not None:
                break
            if time.monotonic() - last_ping >= 2:
                handler.wfile.write(b': heartbeat\n\n')
                handler.wfile.flush()
                last_ping = time.monotonic()
        handler.wfile.write(b'event: stopped\ndata: {}\n\n')
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass
    except OSError as exc:
        if connected:
            try:
                handler.wfile.write(('event: stopped\ndata: ' +
                                     json.dumps({'error': str(exc)[:120]}) +
                                     '\n\n').encode())
                handler.wfile.flush()
            except OSError:
                pass
        else:
            handler.send_json({'error': 'Unable to open viewadsb: ' + str(exc)[:120]}, 503)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        for fd in (master, slave):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        SLOTS.release()
