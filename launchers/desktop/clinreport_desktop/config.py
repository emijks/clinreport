"""Launcher-only settings and the recent-results list (data/launcher.json).

Report settings (clinician, database, default template) belong to the extension and are
stored by it in conf/clinreport.json, so the browser page and this window share them.
"""

import json
import os
import threading
import time
from pathlib import Path

from . import paths

DEFAULTS = {
    # open the OpenCRAVAT start page when the server is ready; renamed from open_browser (default True) so that
    # installs which stored it pick up the new default
    'open_browser_at_start': False,
    'autostart': False,  # start at login (minimised)
    'port_mode': 'auto',  # 'auto' | 'fixed'
    'port': 8080,
    'update_prerelease': False,  # also offer pre-releases (v3.1.0-rc1) as updates
    'recent': [],  # [{"path": ..., "opened": epoch seconds}], newest first
}
RECENT_MAX = 8

_lock = threading.Lock()


def _path() -> Path:
    return paths.data_dir() / 'launcher.json'


def load() -> dict:
    settings = json.loads(json.dumps(DEFAULTS))
    try:
        stored = json.loads(_path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        stored = {}
    settings.update({k: v for k, v in stored.items() if k in DEFAULTS})
    return settings


def save(settings: dict):
    with _lock:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, path)


def update(changes: dict) -> dict:
    settings = load()
    for key, value in changes.items():
        if key not in DEFAULTS or key == 'recent':
            continue
        if key == 'port':
            value = int(value)
            if not 1024 <= value <= 65535:
                raise ValueError('Порт должен быть от 1024 до 65535.')
        elif key == 'port_mode' and value not in ('auto', 'fixed'):
            raise ValueError(f'Неизвестный режим порта: {value}')
        elif key in ('open_browser_at_start', 'autostart', 'update_prerelease'):
            value = bool(value)
        settings[key] = value
    save(settings)
    return settings


def remember_result(path: str):
    settings = load()
    path = os.path.abspath(path)
    recent = [r for r in settings['recent'] if os.path.normcase(r['path']) != os.path.normcase(path)]
    settings['recent'] = [{'path': path, 'opened': time.time()}] + recent[: RECENT_MAX - 1]
    save(settings)


def forget_result(path: str):
    settings = load()
    settings['recent'] = [r for r in settings['recent'] if os.path.normcase(r['path']) != os.path.normcase(path)]
    save(settings)
