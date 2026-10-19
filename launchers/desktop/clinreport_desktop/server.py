"""Run the bundled OpenCRAVAT GUI server (`oc gui --headless`) for this user.

OpenCRAVAT keeps its settings in a system conf file; we write our own (data/conf/cravat-system.yml)
and point OpenCRAVAT at it with OPENCRAVAT_SYSTEM_CONF_PATH, so this app never shares modules, jobs or
settings with another OpenCRAVAT install. OpenCRAVAT also calls `oc` and `pip` by name (reports, Store
installs), so we provide both, generated for the bundled interpreter, on the server's PATH. Python packages
that Store modules pull in go to data/python-packages (PIP_TARGET + PYTHONPATH), so app updates keep them.

The server process runs with CLINREPORT_DESKTOP=1 (clinreport_oc_compat patches OpenCRAVAT 3.x for Windows)
and CLINREPORT_EDITION=desktop (ClinReport without the database and CLINBIO).
"""

import importlib.metadata
import importlib.util
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import paths

log = logging.getLogger('clinreport.server')

# Our modules (bundle.json "managed", = the repository's modules/) are replaced from the bundle when they changed;
# other bundled modules are copied only if missing, so a Store-installed version (e.g. hg38 with its database) wins.
REQUIRED_MODULES = (
    'mappers/hg38',
    'webviewerwidgets/wgnote',
    'reporters/excelreporter',
    'webapps/clinreport',
    'webviewerwidgets/wgclinreport',
)
FIRST_PORT = 8060
READY_TIMEOUT = 180
# OpenCRAVAT's start page: `/` redirects to it (3.x: /submit/nocache/index.html; 2.x: /submit/index.html).
START_PAGE = '/'
IS_WINDOWS = sys.platform == 'win32'


def console_python() -> Path:
    """python.exe, also when the launcher itself runs windowless under pythonw.exe."""
    exe = Path(sys.executable)
    if IS_WINDOWS and exe.name.lower() == 'pythonw.exe':
        return exe.with_name('python.exe')
    return exe


def bin_dir() -> Path:
    return paths.data_dir() / 'bin'


def oc_command() -> Path:
    return bin_dir() / ('oc.exe' if IS_WINDOWS else 'oc')


def server_log() -> Path:
    return paths.logs_dir() / 'server.log'


# --- preparation (idempotent, runs before every start) ---


def kill_leftovers():
    """OpenCRAVAT processes left by a session that crashed or was killed (they hold the port and
    lock oc.exe): anything started from our bin dir, and anything running the bundle's own Python
    (its multiprocessing workers) — except launcher processes."""
    import psutil

    marker = str(bin_dir()).lower()
    python_dir = str(console_python().parent).lower()
    me = psutil.Process()
    spared = {me.pid} | {p.pid for p in me.parents()}
    victims = []
    for proc in psutil.process_iter(['pid', 'cmdline', 'exe']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or []).lower()
            exe = (proc.info['exe'] or '').lower()
        except (psutil.Error, TypeError):
            continue
        if proc.info['pid'] in spared or 'clinreport_desktop' in cmdline:
            continue
        if marker in cmdline or marker in exe or exe.startswith(python_dir):
            victims.append(proc)
    for proc in victims:
        _kill_tree(proc)
    if victims:
        log.info('stopped %d leftover OpenCRAVAT process(es) from an earlier session', len(victims))


def make_scripts():
    """`oc` and `pip` for the bundled interpreter. pip's own launchers hard-code the path the bundle
    was built at; rewrite ours only when the interpreter moved (the files are locked while in use)."""
    target = bin_dir()
    target.mkdir(parents=True, exist_ok=True)
    python = str(console_python())
    stamp = target / '.interpreter'
    if stamp.is_file() and stamp.read_text(encoding='utf-8') == python and oc_command().exists():
        return
    from pip._vendor.distlib.scripts import ScriptMaker

    maker = ScriptMaker(None, str(target))
    maker.executable = python
    maker.clobber = True
    maker.variants = {''}
    maker.make_multiple(['oc = cravat.oc:main', 'pip = pip._internal.cli.main:main'])
    stamp.write_text(python, encoding='utf-8')
    log.info('created oc/pip for %s', python)


def managed_modules() -> set:
    return set(paths.bundle_info().get('managed') or ())


def sync_modules():
    bundled = paths.bundle_dir() / 'modules'
    modules = paths.data_dir() / 'modules'
    managed = managed_modules()
    for type_dir in sorted(p for p in bundled.iterdir() if p.is_dir()):
        for src in sorted(p for p in type_dir.iterdir() if p.is_dir()):
            rel = f'{type_dir.name}/{src.name}'
            dst = modules / type_dir.name / src.name
            if rel in managed:
                if _module_version(dst) == _module_version(src) and dst.exists() and _same_tree(src, dst):
                    continue
                shutil.rmtree(dst, ignore_errors=True)
            elif dst.exists():
                continue
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__'))
            log.info('module %s %s', rel, 'updated' if rel in managed else 'installed')


def _same_tree(a: Path, b: Path) -> bool:
    """Cheap comparison of two module folders (names, sizes, mtimes ignored)."""

    def listing(root):
        return sorted(
            (str(p.relative_to(root)), p.stat().st_size)
            for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts
        )

    return listing(a) == listing(b)


def _module_version(folder: Path) -> str:
    yml = folder / f'{folder.name}.yml'
    try:
        match = re.search(r'^version:\s*["\']?([^"\'\s]+)', yml.read_text(encoding='utf-8'), re.M)
    except OSError:
        return ''
    return match.group(1) if match else ''


def write_system_conf(port: int) -> Path:
    """OpenCRAVAT's system conf for this user, starting from the package template (store_url etc.)."""
    import yaml

    data = paths.data_dir()
    conf = paths.conf_dir()
    for sub in (conf, data / 'modules', data / 'jobs', data / 'workspace', paths.logs_dir()):
        sub.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.find_spec('cravat')  # locate without importing (importing reads the default conf)
    template = Path(spec.origin).parent / 'cravat-system.template.yml'
    settings = yaml.safe_load(template.read_text(encoding='utf-8')) or {}
    path = conf / 'cravat-system.yml'
    if path.is_file():  # keep what OpenCRAVAT saved there (its Settings, the user-email prompt, …)
        try:
            settings.update(yaml.safe_load(path.read_text(encoding='utf-8')) or {})
        except yaml.YAMLError:
            log.warning('unreadable %s; starting from the template', path)
    settings.update(
        {
            'conf_dir': conf.as_posix(),
            'modules_dir': (data / 'modules').as_posix(),
            'jobs_dir': (data / 'jobs').as_posix(),
            'log_dir': paths.logs_dir().as_posix(),
            'work_dir': (data / 'workspace').as_posix(),  # OpenCRAVAT 3.x: Celery broker/results, Flask cache
            'gui_host': 'localhost',
            'gui_port': port,
        }
    )
    path.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding='utf-8')
    return path


def user_packages() -> Path:
    return paths.data_dir() / 'python-packages'


def server_env(conf_path: Path) -> dict:
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)
    user_packages().mkdir(parents=True, exist_ok=True)
    env.update(
        {
            'OPENCRAVAT_SYSTEM_CONF_PATH': str(conf_path),
            'PATH': os.pathsep.join([str(bin_dir()), str(console_python().parent), env.get('PATH', '')]),
            # OpenCRAVAT 2.2.x: the GUI treats any stderr output of `oc report` as a failure.
            'PYTHONWARNINGS': 'ignore:pkg_resources is deprecated as an API:UserWarning',
            'PYTHONIOENCODING': 'utf-8',
            'PYTHONUTF8': '1',
            'PYTHONPATH': str(user_packages()),
            'PIP_TARGET': str(user_packages()),
            'PIP_DISABLE_PIP_VERSION_CHECK': '1',
            'CLINREPORT_DESKTOP': '1',
            'CLINREPORT_EDITION': 'desktop',
        }
    )
    return env


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def pick_port(mode: str, fixed: int) -> int:
    if mode == 'fixed':
        if not port_free(fixed):
            raise RuntimeError(
                f'Порт {fixed} занят другой программой. Выберите другой порт в настройках или «автоматически».'
            )
        return fixed
    for port in range(FIRST_PORT, FIRST_PORT + 100):
        if port_free(port):
            return port
    raise RuntimeError('Не нашлось свободного порта.')


def _kill_tree(proc):
    import psutil

    try:
        family = proc.children(recursive=True) + [proc]
    except psutil.Error:
        family = [proc]
    for p in family:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _gone, alive = psutil.wait_procs(family, timeout=5)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass


# --- versions / module status (no cravat import) ---


def versions() -> dict:
    info = paths.bundle_info()
    try:
        oc = importlib.metadata.version('open-cravat')
    except importlib.metadata.PackageNotFoundError:
        oc = '?'
    return {
        'app': info.get('version', 'dev'),
        'extension': _module_version(paths.bundle_dir() / 'modules' / 'webapps' / 'clinreport'),
        'opencravat': oc,
        'python': platform.python_version(),
        'platform': f'{platform.system()} {platform.release()} ({platform.machine()})',
        'built': info.get('built', ''),
    }


def module_status() -> list:
    modules = paths.data_dir() / 'modules'
    result = []
    for rel in REQUIRED_MODULES:
        folder = modules / rel
        result.append(
            {
                'name': rel.split('/')[1],
                'ok': (folder / f'{folder.name}.yml').is_file(),
                'version': _module_version(folder),
            }
        )
    return result


# --- the server process ---


class Server:
    def __init__(self, on_change=None):
        self.state = 'stopped'  # stopped | starting | running | stopping | failed
        self.port = None
        self.started_at = None
        self.error = None
        self._proc = None
        self._lock = threading.Lock()
        self._on_change = on_change or (lambda: None)
        self.ready_callbacks = []

    @property
    def url(self) -> str:
        return f'http://localhost:{self.port}' if self.port else ''

    @property
    def start_url(self) -> str:
        return self.url + START_PAGE if self.port else ''

    def snapshot(self) -> dict:
        return {
            'state': self.state,
            'port': self.port,
            'url': self.url,
            'started_at': self.started_at,
            'uptime': int(time.time() - self.started_at) if self.started_at and self.state == 'running' else 0,
            'error': self.error,
        }

    def _set(self, state, error=None):
        self.state, self.error = state, error
        self._on_change()

    def start(self, port_mode='auto', fixed_port=8080):
        """Prepare and launch in the background; state goes starting → running | failed."""
        with self._lock:
            if self.state in ('starting', 'running'):
                return
            self._set('starting')
        threading.Thread(target=self._run, args=(port_mode, fixed_port), daemon=True, name='oc-start').start()

    def _run(self, port_mode, fixed_port):
        try:
            kill_leftovers()
            self.port = pick_port(port_mode, int(fixed_port))
            conf_path = write_system_conf(self.port)
            sync_modules()
            make_scripts()
            log_path = server_log()
            if log_path.exists():
                os.replace(log_path, log_path.with_suffix('.log.1'))
            log_file = open(log_path, 'ab')
            kwargs = {}
            if IS_WINDOWS:
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs['start_new_session'] = True
            self._proc = subprocess.Popen(
                [str(oc_command()), 'gui', '--headless', '--port', str(self.port)],
                cwd=str(paths.data_dir()),
                env=server_env(conf_path),
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **kwargs,
            )
            log_file.close()
            log.info('OpenCRAVAT starting on port %s (pid %s)', self.port, self._proc.pid)
            deadline = time.time() + READY_TIMEOUT
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    raise RuntimeError(f'OpenCRAVAT завершился с кодом {self._proc.returncode}.\n{self.log_tail(15)}')
                if self.responds():
                    self.started_at = time.time()
                    self._set('running')
                    log.info('OpenCRAVAT ready at %s', self.url)
                    for callback in list(self.ready_callbacks):
                        threading.Thread(target=callback, daemon=True).start()
                    threading.Thread(target=self._watch, daemon=True, name='oc-watch').start()
                    return
                if self.state == 'stopping':
                    return
                time.sleep(0.5)
            raise RuntimeError(f'OpenCRAVAT не ответил за {READY_TIMEOUT} с.\n{self.log_tail(15)}')
        except Exception as e:
            log.exception('start failed')
            self._terminate()
            self._set('failed', str(e))

    def _watch(self):
        proc = self._proc
        if proc is None:
            return
        proc.wait()
        if self.state == 'running' and proc is self._proc:
            log.error('OpenCRAVAT exited unexpectedly (code %s)', proc.returncode)
            self.started_at = None
            self._set('failed', f'OpenCRAVAT неожиданно завершился (код {proc.returncode}).\n{self.log_tail(15)}')

    def responds(self) -> bool:
        if not self.port:
            return False
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/webapps/clinreport/index.html', timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def stop(self):
        with self._lock:
            if self.state in ('stopped', 'stopping'):
                return
            self._set('stopping')
        self._terminate()
        self.started_at = None
        log.info('OpenCRAVAT stopped')
        self._set('stopped')

    def _terminate(self):
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        import psutil

        try:
            _kill_tree(psutil.Process(proc.pid))
        except psutil.NoSuchProcess:
            pass

    def log_tail(self, lines=40) -> str:
        try:
            text = server_log().read_text(encoding='utf-8', errors='replace')
        except OSError:
            return ''
        return '\n'.join(text.splitlines()[-lines:])

    # --- calls into the running extension ---

    def call(self, method: str, action: str, payload=None, timeout=30):
        import json

        url = f'http://127.0.0.1:{self.port}/webapps/clinreport/{action}'
        data = None
        headers = {}
        if method == 'POST':
            data = json.dumps(payload or {}).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
