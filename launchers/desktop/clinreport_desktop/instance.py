"""One launcher per user. A second start (double-click, a .sqlite dropped on the icon) hands its
request to the running one through a localhost control endpoint and exits."""

import json
import logging
import os
import secrets
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import paths

log = logging.getLogger('clinreport.instance')

# Held while a launcher runs; the Windows installer (packaging/windows/ClinReport.iss, LauncherMutex) waits for it to
# disappear before replacing files.
MUTEX_NAME = 'ClinReportLauncher'
_mutex = None


def hold_mutex():
    """Windows: create the named mutex for the life of this process (released by the OS on exit)."""
    global _mutex
    if sys.platform != 'win32' or _mutex:
        return
    import ctypes

    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)


def _file():
    return paths.data_dir() / 'instance.json'


def hand_over(result_path: str = '', action: str = 'activate') -> bool:
    """True if a running launcher took the request (action: 'activate' | 'quit')."""
    try:
        info = json.loads(_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    body = json.dumps({'token': info.get('token'), 'path': result_path, 'action': action}).encode('utf-8')
    request = urllib.request.Request(
        f"http://127.0.0.1:{info.get('port')}/activate",
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def running_pid():
    """Process id of the running launcher, if instance.json names one that is alive."""
    import psutil

    try:
        pid = int(json.loads(_file().read_text(encoding='utf-8')).get('pid'))
    except (OSError, ValueError, TypeError):
        return None
    return pid if psutil.pid_exists(pid) else None


class Listener:
    """Accepts {"path", "action"} from a second launcher: on_activate(path) or on_quit()."""

    def __init__(self, on_activate, on_quit):
        token = secrets.token_hex(16)

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)))
                except ValueError:
                    payload = {}
                if payload.get('token') != token:
                    self.send_response(403)
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                if payload.get('action') == 'quit':
                    threading.Thread(target=on_quit, daemon=True).start()
                else:
                    threading.Thread(target=on_activate, args=(payload.get('path') or '',), daemon=True).start()

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True, name='instance').start()
        path = _file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({'pid': os.getpid(), 'port': self._server.server_address[1], 'token': token}), encoding='utf-8'
        )

    def close(self):
        self._server.shutdown()
        try:
            info = json.loads(_file().read_text(encoding='utf-8'))
            if info.get('pid') == os.getpid():
                _file().unlink()
        except (OSError, ValueError):
            pass
