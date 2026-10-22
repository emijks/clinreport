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
    'start_server_at_launch': False,  # start OpenCRAVAT when the window opens (otherwise: «Запустить»)
    'autostart': False,  # start at login (minimised)
    'port_mode': 'auto',  # 'auto' | 'fixed'
    'port': 8080,
    'update_prerelease': False,  # also offer pre-releases (v3.1.0-rc1) as updates
    'recent': [],  # [{"path": ..., "opened": epoch seconds}], newest first
    'environment': 'builtin',  # which OpenCRAVAT runs: 'builtin' or an environments.env_id
    'environments_manual': [],  # Pythons the user pointed at («Указать Python…»), searched every time
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
        if key not in DEFAULTS or key in ('recent', 'environments_manual'):
            continue
        if key == 'port':
            value = int(value)
            if not 1024 <= value <= 65535:
                raise ValueError('Порт должен быть от 1024 до 65535.')
        elif key == 'port_mode' and value not in ('auto', 'fixed'):
            raise ValueError(f'Неизвестный режим порта: {value}')
        elif key in ('open_browser_at_start', 'start_server_at_launch', 'autostart', 'update_prerelease'):
            value = bool(value)
        elif key == 'environment':
            value = str(value)
        settings[key] = value
    save(settings)
    return settings


def remember_result(path: str):
    settings = load()
    path = os.path.abspath(path)
    recent = [r for r in settings['recent'] if os.path.normcase(r['path']) != os.path.normcase(path)]
    settings['recent'] = [{'path': path, 'opened': time.time()}] + recent[: RECENT_MAX - 1]
    save(settings)


def remember_python(python: str):
    settings = load()
    if not any(os.path.normcase(p) == os.path.normcase(python) for p in settings['environments_manual']):
        settings['environments_manual'].append(python)
        save(settings)


def forget_python(python: str):
    settings = load()
    settings['environments_manual'] = [
        p for p in settings['environments_manual'] if os.path.normcase(p) != os.path.normcase(python)
    ]
    save(settings)


def job_results(jobs_dir) -> list:
    """Finished OpenCRAVAT jobs (<jobs_dir>/<user>/<job>/*.sqlite), newest first. Results opened in the browser never
    pass through the launcher, so without these «Недавние результаты» stayed empty."""
    found = []
    for result in Path(os.path.abspath(jobs_dir)).glob('*/*/*.sqlite'):
        try:
            found.append({'path': str(result), 'opened': result.stat().st_mtime})
        except OSError:
            continue
    found.sort(key=lambda r: r['opened'], reverse=True)
    return found[:RECENT_MAX]


def recent_results(jobs_dir=None) -> list:
    """Results opened from the window plus finished jobs, newest first, each once."""
    items = list(load()['recent'])
    seen = {os.path.normcase(r['path']) for r in items}
    if jobs_dir:
        items += [r for r in job_results(jobs_dir) if os.path.normcase(r['path']) not in seen]
    items.sort(key=lambda r: r.get('opened') or 0, reverse=True)
    return items[:RECENT_MAX]


def forget_result(path: str):
    settings = load()
    settings['recent'] = [r for r in settings['recent'] if os.path.normcase(r['path']) != os.path.normcase(path)]
    save(settings)
