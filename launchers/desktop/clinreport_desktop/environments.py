r"""OpenCRAVAT installations on this computer ("environments"): find them, describe them, judge whether ClinReport can
use them, and install or remove our two modules there.

Looking never imports or runs another installation's OpenCRAVAT: importing `cravat` creates C:\open-cravat (or
/Users/Shared/open-cravat) and writes cravat-system.yml (docs/reference/opencravat-integration.md). A candidate Python
runs PROBE, which locates the package with importlib.util.find_spec (that does not import it) and lists dist-info
folders; the system conf and the modules are read from disk.

The built-in environment (the bundle's Python) is always there and is described from this process.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import paths

log = logging.getLogger('clinreport.environments')

BUILTIN_ID = 'builtin'
IS_WINDOWS = sys.platform == 'win32'
OUR_MODULES = (('webapps', 'clinreport'), ('webviewerwidgets', 'wgclinreport'))
# What clinreport_core imports at start-up besides the standard library (route.py fails without them).
CORE_PACKAGES = ('docxtpl', 'python-docx', 'jinja2', 'lxml')
PROBE_TIMEOUT = 20
PIP_TIMEOUT = 900
BACKUPS_KEPT = 3

# Runs in the candidate's Python (any 3.x, so no f-strings): where cravat is, without importing it, and which
# distributions are installed (first one on sys.path wins, as for imports).
PROBE = r"""
import json, os, re, sys
out = {'executable': sys.executable, 'python': '.'.join(str(n) for n in sys.version_info[:3]),
       'prefix': sys.prefix, 'base_prefix': getattr(sys, 'base_prefix', sys.prefix), 'platform': sys.platform,
       'cravat': None, 'packages': {}, 'pip': False}
try:
    import importlib.util
    spec = importlib.util.find_spec('cravat')
    if spec is not None and spec.origin:
        out['cravat'] = os.path.dirname(os.path.abspath(spec.origin))
    out['pip'] = importlib.util.find_spec('pip') is not None
except Exception as e:
    out['error'] = repr(e)
pattern = re.compile(r'^(.+?)-(\d[^-]*?)(-py\d.*)?\.(dist|egg)-info$')
for entry in sys.path:
    try:
        names = os.listdir(entry or '.')
    except OSError:
        continue
    for name in names:
        m = pattern.match(name)
        if m:
            key = re.sub(r'[-_.]+', '-', m.group(1)).lower()
            out['packages'].setdefault(key, m.group(2))
print('CLINREPORT-PROBE ' + json.dumps(out))
"""

# Runs in the candidate's Python after our modules were staged: the webapp's core must import there (route.py imports
# it while OpenCRAVAT starts; a failure there is what the user would otherwise discover).
IMPORT_CHECK = r"""
import os, sys
module = sys.argv[1]
sys.path.insert(0, module)
lib = os.path.join(module, 'lib')
if os.path.isdir(lib):
    sys.path.append(lib)
import clinreport_core.service
print('CLINREPORT-IMPORT-OK')
"""


class EnvironmentError_(RuntimeError):
    """A problem to show to the user as is (Russian)."""


# --- small helpers ---


def version_tuple(text) -> tuple:
    numbers = []
    for part in re.split(r'[.+-]', str(text or '')):
        if not part.isdigit():
            break
        numbers.append(int(part))
    return tuple(numbers)


def normalize(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def same_path(a, b) -> bool:
    return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))


def env_id(python) -> str:
    key = os.path.normcase(os.path.realpath(str(python)))
    return 'py-' + hashlib.sha1(key.encode('utf-8')).hexdigest()[:12]


def _no_window() -> dict:
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}


def script_dirs(prefix: Path) -> list:
    """Folders of an environment that hold its commands (and, for conda on Windows, its DLLs)."""
    prefix = Path(prefix)
    if IS_WINDOWS:
        dirs = [prefix, prefix / 'Scripts', prefix / 'Library' / 'bin', prefix / 'Library' / 'usr' / 'bin',
                prefix / 'Library' / 'mingw-w64' / 'bin']  # fmt: skip
    else:
        dirs = [prefix / 'bin']
    return [d for d in dirs if d.is_dir()]


def clean_env(prefix=None) -> dict:
    """Environment for another installation's Python: none of our Python variables, its own folders first on PATH
    (a conda Python started without activation otherwise fails to load ssl/sqlite DLLs on Windows)."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(('PYTHON', 'PIP_', 'OPENCRAVAT_', 'CONDA_'))}
    env['PYTHONIOENCODING'] = 'utf-8'
    if prefix:
        env['PATH'] = os.pathsep.join([str(d) for d in script_dirs(prefix)] + [env.get('PATH', '')])
    return env


def _is_ours(python: Path) -> bool:
    try:
        bundle = paths.bundle_dir()
    except SystemExit:
        return False
    try:
        Path(os.path.realpath(python)).relative_to(os.path.realpath(bundle))
        return True
    except ValueError:
        return False


# --- probing one Python ---


def probe(python, timeout=PROBE_TIMEOUT) -> dict:
    """Run PROBE in `python`. Raises EnvironmentError_ with a user-facing reason."""
    python = Path(python)
    if not python.is_file():
        raise EnvironmentError_(f'Файл не найден: {python}')
    prefix = python.parent.parent if python.parent.name.lower() in ('scripts', 'bin') else python.parent
    try:
        done = subprocess.run(
            [str(python), '-E', '-c', PROBE],
            capture_output=True,
            timeout=timeout,
            env=clean_env(prefix),
            stdin=subprocess.DEVNULL,
            **_no_window(),
        )
    except subprocess.TimeoutExpired:
        raise EnvironmentError_(f'{python} не ответил за {timeout} с.') from None
    except OSError as e:
        raise EnvironmentError_(f'Не удалось запустить {python}: {e}') from None
    for line in done.stdout.decode('utf-8', 'replace').splitlines():
        if line.startswith('CLINREPORT-PROBE '):
            return json.loads(line[len('CLINREPORT-PROBE ') :])
    tail = done.stderr.decode('utf-8', 'replace').strip().splitlines()[-3:]
    raise EnvironmentError_(f'{python} — это не Python 3 или он не запускается: {" ".join(tail) or done.returncode}')


# --- reading an installation from disk ---


def oc_root(package_path: Path, platform: str = sys.platform) -> Path:
    """Where OpenCRAVAT keeps conf/ by default (cravat/constants.py, the same in 2.2.0 – 3.2.4)."""
    if platform == 'win32':
        return Path(os.path.expandvars('%SystemDrive%') + os.sep) / 'open-cravat'
    if platform == 'darwin':
        return Path('/Users/Shared/open-cravat')
    return Path(package_path)


def read_conf(path: Path) -> dict:
    import yaml

    try:
        return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}


def module_version(folder: Path) -> str:
    try:
        text = (Path(folder) / f'{Path(folder).name}.yml').read_text(encoding='utf-8')
    except OSError:
        return ''
    match = re.search(r'^version:\s*["\']?([^"\'\s]+)', text, re.M)
    return match.group(1) if match else ''


def scan_modules(modules_dir: Path) -> dict:
    modules_dir = Path(modules_dir)
    types, names = {}, set()
    try:
        type_dirs = [d for d in modules_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    except OSError:
        type_dirs = []
    for type_dir in type_dirs:
        try:
            found = [d.name for d in type_dir.iterdir() if (d / f'{d.name}.yml').is_file()]
        except OSError:
            continue
        if found:
            types[type_dir.name] = len(found)
            names.update(found)
    return {
        'types': dict(sorted(types.items(), key=lambda kv: -kv[1])),
        'count': sum(types.values()),
        'ours': {name: module_version(modules_dir / kind / name) or None for kind, name in OUR_MODULES},
        'wgnote': 'wgnote' in names,
        'hg38': 'hg38' in names,
    }


def lib_packages(webapp: Path) -> set:
    """Packages installed into our webapp's lib/ (route.py appends it to sys.path)."""
    pattern = re.compile(r'^(.+?)-(\d[^-]*?)\.(dist|egg)-info$')
    try:
        names = os.listdir(Path(webapp) / 'lib')
    except OSError:
        return set()
    return {normalize(m.group(1)) for m in map(pattern.match, names) if m}


def missing_packages(env: dict, webapp: Path = None) -> list:
    """CORE_PACKAGES neither in the environment nor in our module's lib/."""
    have = {p['name'] for p in env.get('packages') or []} | set(env.get('module_lib') or ())
    if webapp is not None:
        have |= lib_packages(webapp)
    return [p for p in CORE_PACKAGES if normalize(p) not in have]


def writable(folder: Path) -> bool:
    folder = Path(folder)
    while not folder.exists() and folder.parent != folder:
        folder = folder.parent
    return os.access(folder, os.W_OK)


def kind_of(info: dict) -> str:
    python = Path(info['executable'])
    prefix = Path(info['prefix'])
    text = str(python).replace('\\', '/').lower()
    if (prefix / 'conda-meta').is_dir():
        return 'conda'
    if '/pipx/' in text:
        return 'pipx'
    if (prefix / 'pyvenv.cfg').is_file() or info.get('prefix') != info.get('base_prefix'):
        return 'venv'
    if '/.pyenv/' in text:
        return 'pyenv'
    if 'opencravat' in text.replace('-', ''):
        return 'installer'
    return 'system'


def name_of(kind: str, info: dict) -> str:
    prefix = Path(info['prefix'])
    if kind in ('conda', 'venv', 'pipx'):
        return prefix.name
    if kind == 'installer':
        return 'OpenCRAVAT (установщик)'
    return f'Python {info["python"]}'


def describe(info: dict, source: str = '') -> dict:
    """An environment from a probe result (cravat found)."""
    package = Path(info['cravat'])
    root = oc_root(package)
    conf_path = root / 'conf' / 'cravat-system.yml'
    conf = read_conf(conf_path)
    modules_dir = Path(conf.get('modules_dir') or root / 'modules')
    kind = kind_of(info)
    packages = info.get('packages') or {}
    python = Path(info['executable'])
    prefix = Path(info['prefix'])
    oc = shutil.which('oc', path=os.pathsep.join(str(d) for d in script_dirs(prefix))) or ''
    env = {
        'id': env_id(python),
        'kind': kind,
        'name': name_of(kind, info),
        'source': source,
        'python': str(python),
        'prefix': str(prefix),
        'python_version': info['python'],
        'opencravat': packages.get('open-cravat', ''),
        'setuptools': packages.get('setuptools', ''),
        'pip': bool(info.get('pip')),
        'package_path': str(package),
        'packages': [{'name': n, 'version': v} for n, v in sorted(packages.items())],
        'conf_path': str(conf_path),
        'conf_exists': conf_path.is_file(),
        'modules_dir': str(modules_dir),
        'jobs_dir': str(conf.get('jobs_dir') or root / 'jobs'),
        'log_dir': str(conf.get('log_dir') or root / 'logs'),
        'conf_dir': str(conf.get('conf_dir') or root / 'conf'),
        'work_dir': str(conf.get('work_dir') or root / 'workspace'),
        'gui_port': int(conf.get('gui_port') or 8060),
        'oc_command': oc,
        'modules': scan_modules(modules_dir),
        'module_lib': sorted(lib_packages(modules_dir / 'webapps' / 'clinreport')),
        'modules_writable': writable(modules_dir),
        'running': [],
        'checked_at': time.time(),
    }
    env['verdict'] = assess(env)
    return env


def builtin() -> dict:
    """The bundle's own environment, described from this process."""
    import importlib.metadata
    import importlib.util

    from .server import console_python, oc_command, user_packages, versions

    spec = importlib.util.find_spec('cravat')
    data = paths.data_dir()
    packages = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata['Name']
        if name:
            packages.setdefault(normalize(name), dist.version)
    v = versions()
    env = {
        'id': BUILTIN_ID,
        'kind': 'builtin',
        'name': 'Встроенное',
        'source': 'программа',
        'python': str(console_python()),
        'prefix': str(Path(sys.prefix)),
        'python_version': v['python'],
        'opencravat': v['opencravat'],
        'setuptools': packages.get('setuptools', ''),
        'pip': True,
        'package_path': str(Path(spec.origin).parent) if spec and spec.origin else '',
        'packages': [{'name': n, 'version': ver} for n, ver in sorted(packages.items())],
        'conf_path': str(paths.conf_dir() / 'cravat-system.yml'),
        'conf_exists': (paths.conf_dir() / 'cravat-system.yml').is_file(),
        'modules_dir': str(data / 'modules'),
        'jobs_dir': str(data / 'jobs'),
        'log_dir': str(paths.logs_dir()),
        'conf_dir': str(paths.conf_dir()),
        'work_dir': str(data / 'workspace'),
        'user_packages': str(user_packages()),
        'oc_command': str(oc_command()),
        'gui_port': None,
        'modules': scan_modules(data / 'modules'),
        'modules_writable': True,
        'running': [],
        'checked_at': time.time(),
    }
    env['verdict'] = {'level': 'ok', 'can_run': True, 'can_install': False, 'reasons': [],
                      'summary': 'Поставляется с ClinReport и обновляется вместе с ним.'}  # fmt: skip
    return env


# --- can ClinReport use it? (docs/reference/opencravat-integration.md, "What the modules need") ---


def bundled_version() -> str:
    try:
        return source_version(bundled_modules_dir())
    except SystemExit:  # no bundle (tests, development)
        return ''


def assess(env: dict, platform: str = sys.platform, latest: str = None) -> dict:
    latest = bundled_version() if latest is None else latest
    oc = version_tuple(env.get('opencravat'))
    py = version_tuple(env.get('python_version'))
    st = version_tuple(env.get('setuptools'))
    reasons = []
    can_run = can_install = True

    def say(level, text):
        reasons.append({'level': level, 'text': text})

    if not oc:
        say('bad', 'Не удалось определить версию OpenCRAVAT.')
        can_run = can_install = False
    elif oc < (2, 2, 0):
        say('bad', f'OpenCRAVAT {env["opencravat"]} слишком старый: ClinReport нужен OpenCRAVAT 2.2 или новее.')
        can_run = can_install = False
    if py and py < (3, 8):
        say('bad', f'Python {env["python_version"]}: модулям ClinReport нужен Python 3.8 или новее.')
        can_run = can_install = False
    if oc and (2, 2, 0) <= oc < (2, 6) and py >= (3, 12):
        say(
            'bad',
            f'OpenCRAVAT {env["opencravat"]} не запускается на Python {env["python_version"]}: нужен Python 3.11 или старше.',
        )
        can_run = False
    if oc and oc < (2, 17) and st >= (81,):
        say('bad', f'setuptools {env["setuptools"]} не подходит OpenCRAVAT {env["opencravat"]} — он не запустится. '
                   'В этом окружении нужен setuptools младше 81: pip install "setuptools<81".')  # fmt: skip
        can_run = False
    if oc >= (3,) and platform == 'win32':
        say('bad', 'OpenCRAVAT 3.x не запускается в Windows без исправлений, которые есть только во встроенном окружении. '
                   'Модули поставить можно, но запустить этот OpenCRAVAT из ClinReport нельзя.')  # fmt: skip
        can_run = False
    if (2, 17) <= oc < (3,) and py >= (3, 14):
        say('warn', 'На Python 3.14 просмотрщик OpenCRAVAT 2.17 может зависать при открытии результата.')
    if oc and can_install and not (oc == (2, 2, 9) or (oc >= (3,) and platform != 'win32' and oc <= (3, 2, 4))):
        say(
            'info',
            f'ClinReport с OpenCRAVAT {env["opencravat"]} не проверялся: устроен он так же, но возможны отличия.',
        )

    modules = env.get('modules') or {}
    ours = modules.get('ours') or {}
    if can_install and not env.get('modules_writable', True):
        say(
            'bad',
            f'Нет прав на запись в папку модулей {env["modules_dir"]}: установите модули от имени владельца этой папки.',
        )
        can_install = False
    missing = missing_packages(env)
    if can_install and missing:
        if env.get('pip'):
            say('info', f'При установке ClinReport скачает в папку своего модуля: {", ".join(missing)} (нужен интернет). '
                        'Пакеты окружения не меняются.')  # fmt: skip
        else:
            say('bad', f'Не хватает пакетов {", ".join(missing)}, а pip в этом окружении нет — установить их нельзя.')
            can_install = False
    if not env.get('conf_exists'):
        say(
            'info',
            f'OpenCRAVAT здесь ещё не запускался: при первом запуске он создаст {Path(env["conf_path"]).parent.parent}.',
        )
    elif not modules.get('wgnote'):
        say(
            'warn',
            'Нет модуля wgnote: без него варианты в колонке Note не отметить. Установите его на вкладке Store в OpenCRAVAT.',
        )
    if not ours.get('clinreport') or not ours.get('wgclinreport'):
        if can_run:
            say('warn', 'Модули ClinReport здесь не установлены: установите их, чтобы запускать это окружение.')
        can_run = False
    elif latest and (
        version_tuple(ours['clinreport']) < version_tuple(latest) or ours['clinreport'] != ours['wgclinreport']
    ):
        say('warn', f'Модули ClinReport здесь устарели ({ours["clinreport"]}); в программе — {latest}. Обновите их.')

    levels = [r['level'] for r in reasons]
    level = (
        'bad'
        if not (can_run or can_install)
        else 'warn'
        if ('bad' in levels or 'warn' in levels or not can_run)
        else 'ok'
    )
    summary = (
        'Готово к работе.' if level == 'ok'
        else 'Можно использовать после установки модулей ClinReport.' if can_install and not can_run and not any(
            r['level'] == 'bad' for r in reasons)
        else 'Есть ограничения — см. ниже.' if can_run or can_install
        else 'ClinReport не может работать с этим окружением.'
    )  # fmt: skip
    return {'level': level, 'can_run': can_run, 'can_install': can_install, 'reasons': reasons, 'summary': summary}


# --- where to look ---


def _glob(base, pattern) -> list:
    try:
        return sorted(Path(base).glob(pattern))
    except (OSError, ValueError):
        return []


def _shebang_python(script: Path):
    """The interpreter a POSIX console script (oc) was installed for."""
    try:
        with open(script, 'rb') as fh:
            first = fh.readline(512).decode('utf-8', 'replace')
    except OSError:
        return None
    if first.startswith('#!'):
        command = first[2:].strip().split()
        if command and 'python' in Path(command[0]).name:
            return Path(command[0])
    return None


def _login_shell_path() -> list:
    """PATH of the user's login shell: an app started from Finder does not see the terminal's PATH."""
    shell = os.environ.get('SHELL') or '/bin/zsh'
    try:
        done = subprocess.run([shell, '-l', '-c', 'printf %s "$PATH"'], capture_output=True, timeout=5,
                              stdin=subprocess.DEVNULL)  # fmt: skip
        return done.stdout.decode('utf-8', 'replace').split(':')
    except (OSError, subprocess.TimeoutExpired):
        return []


def conda_prefixes(home: Path) -> list:
    roots = [home / n for n in ('miniconda3', 'anaconda3', 'miniforge3', 'mambaforge', 'micromamba', 'opt/miniconda3')]
    if IS_WINDOWS:
        for base in filter(None, (os.environ.get('LOCALAPPDATA'), os.environ.get('ProgramData'), 'C:\\')):
            roots += [Path(base) / n for n in ('miniconda3', 'Anaconda3', 'anaconda3', 'miniforge3', 'mambaforge')]
    else:
        roots += [Path(p) for p in ('/opt/miniconda3', '/opt/anaconda3', '/opt/homebrew/Caskroom/miniconda/base',
                                    '/usr/local/Caskroom/miniconda/base', '/opt/conda')]  # fmt: skip
    prefixes = []
    for root in roots:
        prefixes.append(root)
        prefixes += _glob(root, 'envs/*')
    try:  # conda's own list of every environment it created
        prefixes += [
            Path(line.strip())
            for line in (home / '.conda' / 'environments.txt').read_text().splitlines()
            if line.strip()
        ]
    except OSError:
        pass
    return prefixes


def standard_candidates(home: Path = None) -> list:
    """[(python, where it was found)] from the usual places; cheap (no process starts except `py -0p` and the shell)."""
    home = Path(home or Path.home())
    found = []

    def add(python, where):
        if python:
            found.append((Path(python), where))

    exe = 'python.exe' if IS_WINDOWS else 'python3'
    path_dirs = os.environ.get('PATH', '').split(os.pathsep)
    if not IS_WINDOWS:
        path_dirs += _login_shell_path()
    for d in filter(None, path_dirs):
        add(Path(d) / exe, 'PATH')
        if IS_WINDOWS:
            if (Path(d) / 'oc.exe').is_file():
                add(Path(d) / 'python.exe', 'oc в PATH')
                add(Path(d).parent / 'python.exe', 'oc в PATH')
        else:
            add(Path(d) / 'python', 'PATH')
            add(_shebang_python(Path(d) / 'oc'), 'oc в PATH')

    for prefix in conda_prefixes(home):
        add(prefix / ('python.exe' if IS_WINDOWS else 'bin/python'), 'conda')

    if IS_WINDOWS:
        local = Path(os.environ.get('LOCALAPPDATA') or home / 'AppData' / 'Local')
        program_files = [Path(p) for p in {os.environ.get('ProgramFiles'), os.environ.get('ProgramW6432'),
                                           os.environ.get('ProgramFiles(x86)')} if p]  # fmt: skip
        for base in [local / 'Programs' / 'Python', Path('C:/')] + program_files:
            for python in _glob(base, 'Python3*/python.exe'):
                add(python, 'установленный Python')
        for base in [local / 'Programs'] + program_files:
            for python in _glob(base, 'OpenCRAVAT*/python/python.exe') + _glob(base, 'OpenCRAVAT*/python.exe'):
                add(python, 'установщик OpenCRAVAT')
        for python in _glob(home, '.pyenv/pyenv-win/versions/*/python.exe'):
            add(python, 'pyenv')
        for base in (home / '.local' / 'pipx' / 'venvs', home / 'pipx' / 'venvs', local / 'pipx' / 'pipx' / 'venvs'):
            for python in _glob(base, '*/Scripts/python.exe'):
                add(python, 'pipx')
        for python in _py_launcher() + _registry_pythons():
            add(python, 'реестр Windows')
    else:
        for d in ('/usr/local/bin', '/opt/homebrew/bin', '/usr/bin', home / '.local' / 'bin'):
            add(Path(d) / 'python3', 'стандартное место')
            add(_shebang_python(Path(d) / 'oc'), 'oc')
        for python in _glob('/Library/Frameworks/Python.framework/Versions', '*/bin/python3'):
            add(python, 'python.org')
        for python in _glob(home, '.pyenv/versions/*/bin/python'):
            add(python, 'pyenv')
        for python in _glob(home, '.local/pipx/venvs/*/bin/python') + _glob(
            home, '.local/share/pipx/venvs/*/bin/python'
        ):
            add(python, 'pipx')
        for python in _glob('/Applications', '*[Cc][Rr][Aa][Vv][Aa][Tt]*.app/Contents/Resources/**/bin/python3'):
            add(python, 'установщик OpenCRAVAT')
    for python in running_guis():
        add(python, 'запущенный OpenCRAVAT')
    return found


def _py_launcher() -> list:
    try:
        done = subprocess.run(['py', '-0p'], capture_output=True, timeout=10, stdin=subprocess.DEVNULL, **_no_window())
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [Path(m) for m in re.findall(r'([A-Za-z]:\\[^\r\n*]+?python\.exe)', done.stdout.decode('utf-8', 'replace'))]


def _registry_pythons() -> list:
    """PEP 514: every registered Python, per user and per machine."""
    try:
        import winreg
    except ImportError:
        return []
    found = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                root = winreg.OpenKey(hive, r'Software\Python', 0, winreg.KEY_READ | view)
            except OSError:
                continue
            for company in _subkeys(winreg, root):
                if company == 'PyLauncher':
                    continue
                with winreg.OpenKey(root, company) as company_key:
                    for tag in _subkeys(winreg, company_key):
                        try:
                            with winreg.OpenKey(company_key, tag + r'\InstallPath') as key:
                                try:
                                    found.append(Path(winreg.QueryValueEx(key, 'ExecutablePath')[0]))
                                except OSError:
                                    found.append(Path(winreg.QueryValueEx(key, '')[0]) / 'python.exe')
                        except OSError:
                            continue
    return found


def _subkeys(winreg, key) -> list:
    names, i = [], 0
    while True:
        try:
            names.append(winreg.EnumKey(key, i))
        except OSError:
            return names
        i += 1


def running_guis() -> dict:
    """{python: port} of `oc gui` processes running now (not ours)."""
    try:
        import psutil
    except ImportError:
        return {}
    found = {}
    for proc in psutil.process_iter(['cmdline', 'exe']):
        try:
            cmd = proc.info['cmdline'] or []
            exe = proc.info['exe'] or ''
        except (psutil.Error, TypeError):
            continue
        words = [Path(c).name.lower() for c in cmd]
        if 'gui' not in words or not any(w in ('oc', 'oc.exe', 'oc-script.py') or 'cravat' in w for w in words):
            continue
        if not exe or 'python' not in Path(exe).name.lower() or _is_ours(exe):
            continue
        port = None
        if '--port' in cmd and cmd.index('--port') + 1 < len(cmd):
            port = cmd[cmd.index('--port') + 1]
        found[Path(exe)] = int(port) if port and str(port).isdigit() else None
    return found


SKIP_DIRS = {'node_modules', '.git', '.hg', '.svn', '__pycache__', '$recycle.bin', 'system volume information',
             'windows', 'temp', 'tmp', 'caches', '.trash', 'proc', 'sys', 'dev', 'packages', 'microsoft',
             'appdata/local/microsoft', 'library/caches', '.cache', '.npm', '.cargo', '.rustup', 'onedrive'}  # fmt: skip


def deep_candidates(roots, cancel: threading.Event, progress=None, max_depth=9):
    """Walk folders looking for site-packages/cravat; yields (python, where). progress(visited, current)."""
    visited = 0
    stack = [(Path(r), 0) for r in roots]
    while stack:
        if cancel.is_set():
            return
        folder, depth = stack.pop()
        visited += 1
        if progress and visited % 50 == 0:
            progress(visited, str(folder))
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            name = entry.name.lower()
            if name in ('site-packages', 'dist-packages'):
                cravat = Path(entry.path) / 'cravat'
                if (cravat / 'admin_util.py').is_file():
                    python = _python_for_site_packages(Path(entry.path))
                    if python:
                        yield python, 'глубокий поиск'
                continue  # never descend into installed packages
            if (
                name in SKIP_DIRS
                or depth >= max_depth
                or (name.startswith('.') and name not in ('.conda', '.pyenv', '.local', '.venv', '.virtualenvs'))
            ):
                continue
            if _is_ours(Path(entry.path)):
                continue
            stack.append((Path(entry.path), depth + 1))
    if progress:
        progress(visited, '')


def _python_for_site_packages(site: Path):
    """<prefix>/Lib/site-packages (Windows) or <prefix>/lib/pythonX.Y/site-packages → the prefix's python."""
    if IS_WINDOWS:
        prefix = site.parent.parent
        options = [prefix / 'python.exe', prefix / 'Scripts' / 'python.exe']
    else:
        prefix = site.parent.parent.parent
        options = [prefix / 'bin' / site.parent.name, prefix / 'bin' / 'python3', prefix / 'bin' / 'python']
    return next((p for p in options if p.is_file()), None)


def deep_roots() -> list:
    roots = [Path.home()]
    if IS_WINDOWS:
        import string

        drives = [Path(f'{d}:\\') for d in string.ascii_uppercase if Path(f'{d}:\\').exists()]
        home_drive = Path(Path.home().anchor)
        roots += [d for d in drives if d != home_drive] + [home_drive]
    else:
        roots += [Path('/opt'), Path('/usr/local')]
    return roots


def data_only_candidates() -> list:
    """OpenCRAVAT data folders at the default places (left by an install whose Python is not found)."""
    root = oc_root(Path('.'))
    if not IS_WINDOWS and sys.platform != 'darwin':
        return []
    conf_path = root / 'conf' / 'cravat-system.yml'
    if not conf_path.is_file():
        return []
    conf = read_conf(conf_path)
    modules_dir = Path(conf.get('modules_dir') or root / 'modules')
    modules = scan_modules(modules_dir)
    if not modules['count']:
        return []  # an empty folder that importing cravat created
    return [{
        'id': 'data-' + hashlib.sha1(str(root).lower().encode()).hexdigest()[:8], 'kind': 'data', 'name': str(root),
        'source': 'папка данных OpenCRAVAT', 'python': '', 'prefix': '', 'python_version': '', 'opencravat': '',
        'setuptools': '', 'pip': False, 'package_path': '', 'packages': [], 'conf_path': str(conf_path), 'conf_exists': True,
        'modules_dir': str(modules_dir), 'jobs_dir': str(conf.get('jobs_dir') or root / 'jobs'),
        'log_dir': str(conf.get('log_dir') or root / 'logs'), 'conf_dir': str(root / 'conf'),
        'work_dir': str(conf.get('work_dir') or root / 'workspace'), 'gui_port': int(conf.get('gui_port') or 8060),
        'oc_command': '', 'modules': modules, 'modules_writable': writable(modules_dir), 'running': [],
        'checked_at': time.time(),
        'verdict': {'level': 'warn', 'can_run': False, 'can_install': False, 'summary': 'Нужно указать Python.',
                    'reasons': [{'level': 'warn', 'text': 'Здесь есть модули и задания OpenCRAVAT, но не найден Python, '
                                 'в котором он установлен. Укажите его кнопкой «Указать Python…».'}]},
    }]  # fmt: skip


# --- the search (a background job the window polls) ---


def _cache_path() -> Path:
    return paths.data_dir() / 'environments.json'


def load_cache() -> list:
    try:
        return json.loads(_cache_path().read_text(encoding='utf-8')).get('items', [])
    except (OSError, ValueError, AttributeError):
        return []


def save_cache(items: list):
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(
        json.dumps({'saved_at': time.time(), 'items': items}, ensure_ascii=False, indent=1), encoding='utf-8'
    )
    os.replace(tmp, path)


class Search:
    """One search at a time: standard places, then (deep=True) a walk of the disks. Results arrive as found."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self.state = {'running': False, 'phase': '', 'checked': 0, 'total': 0, 'visited': 0, 'current': '',
                      'found': 0, 'deep': False, 'finished_at': None, 'cancelled': False, 'errors': []}  # fmt: skip

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self.state))

    def start(self, deep: bool, on_found, extra=()):
        with self._lock:
            if self.state['running']:
                return False
            self._cancel.clear()
            self.state.update(running=True, phase='Ищу Python в стандартных местах…', checked=0, total=0, visited=0,
                              current='', found=0, deep=deep, cancelled=False, errors=[])  # fmt: skip
        self._thread = threading.Thread(
            target=self._run, args=(deep, on_found, list(extra)), daemon=True, name='env-search'
        )
        self._thread.start()
        return True

    def cancel(self):
        self._cancel.set()

    def _set(self, **changes):
        with self._lock:
            self.state.update(changes)

    def _run(self, deep, on_found, extra):
        seen_python, seen_package, seen_conf = set(), set(), []
        pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='env-probe')

        def check(python, where):
            try:
                info = probe(python)
            except EnvironmentError_ as e:
                return None, str(e)
            if not info.get('cravat'):
                return None, None
            return describe(info, where), None

        def submit_all(candidates):
            futures = []
            for python, where in candidates:
                if self._cancel.is_set():
                    break
                if not python.is_file() or _is_ours(python) or 'windowsapps' in str(python).lower():
                    continue
                key = os.path.normcase(os.path.realpath(python))
                if key in seen_python:
                    continue
                seen_python.add(key)
                with self._lock:
                    self.state['total'] += 1
                futures.append(pool.submit(check, python, where))
            for future in futures:
                env, error = future.result()
                with self._lock:
                    self.state['checked'] += 1
                if error:
                    with self._lock:
                        self.state['errors'].append(error)
                if env:
                    package = os.path.normcase(os.path.realpath(env['package_path']))
                    if package in seen_package:
                        continue
                    seen_package.add(package)
                    seen_conf.append(env['conf_path'])
                    with self._lock:
                        self.state['found'] += 1
                    on_found(env)

        try:
            submit_all([(Path(p), 'указан вручную') for p in extra] + standard_candidates())
            if deep and not self._cancel.is_set():
                self._set(phase='Глубокий поиск: просматриваю папки…')

                def progress(visited, current):
                    self._set(visited=visited, current=current)

                batch = []
                for python, where in deep_candidates(deep_roots(), self._cancel, progress):
                    batch.append((python, where))
                    submit_all(batch)
                    batch = []
            for env in data_only_candidates():
                if not any(same_path(env['conf_path'], c) for c in seen_conf):
                    on_found(env)
        except Exception as e:  # noqa: BLE001 - the window must learn that the search ended
            log.exception('environment search failed')
            self._set(errors=self.state['errors'] + [f'Поиск прервался: {e!r}'])
        finally:
            pool.shutdown(wait=True)
            self._set(running=False, phase='', current='', finished_at=time.time(), cancelled=self._cancel.is_set())


# --- installing our modules into an environment ---


def bundled_modules_dir() -> Path:
    return paths.bundle_dir() / 'modules'


def modules_from_zip(zip_path: Path, into: Path) -> Path:
    """Unpack a clinreport-extension-X.Y.Z.zip; returns its modules/ folder."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                target = (into / member).resolve()
                if not str(target).startswith(str(into.resolve())):
                    raise EnvironmentError_('Архив содержит недопустимые пути.')
            archive.extractall(into)
    except zipfile.BadZipFile:
        raise EnvironmentError_(f'{zip_path.name} — не zip-архив.') from None
    for yml in into.rglob('clinreport.yml'):
        modules = yml.parent.parent.parent
        if yml.parent.parent.name == 'webapps' and (modules / 'webviewerwidgets' / 'wgclinreport').is_dir():
            return modules
    raise EnvironmentError_('В архиве нет модулей ClinReport (webapps/clinreport и webviewerwidgets/wgclinreport).')


def source_version(modules: Path) -> str:
    return module_version(modules / 'webapps' / 'clinreport')


def _backup_dir(env: dict) -> Path:
    return paths.data_dir() / 'module-backups' / env['id']


def _prune_backups(env: dict):
    backups = sorted(_backup_dir(env).glob('*'))
    for old in backups[:-BACKUPS_KEPT]:
        shutil.rmtree(old, ignore_errors=True)


class Installer:
    """Installs or removes our modules in one environment at a time; the window polls state()."""

    def __init__(self):
        self._lock = threading.Lock()
        self.jobs = {}  # env id -> {'state', 'action', 'steps': [...], 'error', 'version'}

    def state(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self.jobs))

    def busy(self) -> bool:
        with self._lock:
            return any(j['state'] == 'running' for j in self.jobs.values())

    def _step(self, env_id, text):
        log.info('[%s] %s', env_id, text)
        with self._lock:
            self.jobs[env_id]['steps'].append(text)

    def start(self, env: dict, action: str, source: Path, on_done):
        with self._lock:
            if any(j['state'] == 'running' for j in self.jobs.values()):
                raise EnvironmentError_('Уже идёт установка в другое окружение. Дождитесь её окончания.')
            self.jobs[env['id']] = {'state': 'running', 'action': action, 'steps': [], 'error': None, 'version': None}
        target = self._install if action == 'install' else self._remove
        threading.Thread(
            target=self._guard, args=(target, env, source, on_done), daemon=True, name='env-install'
        ).start()

    def _guard(self, target, env, source, on_done):
        try:
            version = target(env, source)
            with self._lock:
                self.jobs[env['id']].update(state='done', version=version)
        except Exception as e:  # noqa: BLE001 - shown to the user; the modules are restored before this
            log.exception('modules: %s failed for %s', target.__name__.strip('_'), env.get('python'))
            message = str(e) if isinstance(e, EnvironmentError_) else f'Внутренняя ошибка: {e!r}'
            with self._lock:
                self.jobs[env['id']].update(state='failed', error=message)
        finally:
            on_done(env['id'])

    def _install(self, env: dict, source: Path) -> str:
        modules_dir = Path(env['modules_dir'])
        version = source_version(source)
        if not version:
            raise EnvironmentError_(f'Не найдены модули ClinReport в {source}.')
        self._step(env['id'], f'Устанавливаю модули ClinReport {version} в {modules_dir}')
        paths.data_dir().mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='clinreport-install-', dir=paths.data_dir()))
        try:
            staged = work / 'modules'
            for kind, name in OUR_MODULES:
                shutil.copytree(
                    source / kind / name, staged / kind / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc')
                )
            webapp = staged / 'webapps' / 'clinreport'
            previous_lib = modules_dir / 'webapps' / 'clinreport' / 'lib'
            if previous_lib.is_dir():  # an update: keep the packages downloaded last time (checked below anyway)
                shutil.copytree(previous_lib, webapp / 'lib', ignore=shutil.ignore_patterns('__pycache__'))

            missing = missing_packages(dict(env, module_lib=()), webapp)
            if missing:
                self._step(env['id'], f'Скачиваю пакеты в папку модуля: {", ".join(missing)}')
                self._pip(env, ['install', '--target', str(webapp / 'lib'), *missing])

            self._step(env['id'], 'Проверяю, что модуль загружается в Python этого окружения')
            self._import_check(env, webapp)

            self._step(env['id'], 'Заменяю модули (прежние сохраняются в резервную копию)')
            self._swap(env, staged, modules_dir)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        self._step(env['id'], f'Готово: ClinReport {version}')
        return version

    def _remove(self, env: dict, source=None) -> str:
        modules_dir = Path(env['modules_dir'])
        backup = _backup_dir(env) / time.strftime('%Y%m%d-%H%M%S')
        moved = 0
        for kind, name in OUR_MODULES:
            folder = modules_dir / kind / name
            if folder.exists():
                (backup / kind).mkdir(parents=True, exist_ok=True)
                shutil.move(str(folder), str(backup / kind / name))
                moved += 1
        _prune_backups(env)
        self._step(
            env['id'],
            f'Модули ClinReport удалены ({moved}); копия: {backup}' if moved else 'Модулей ClinReport здесь не было',
        )
        return ''

    def _pip(self, env, args):
        python = Path(env['python'])
        try:
            done = subprocess.run(
                [str(python), '-m', 'pip', '--disable-pip-version-check', '--no-input', *args],
                capture_output=True, timeout=PIP_TIMEOUT, env=clean_env(env['prefix']), stdin=subprocess.DEVNULL, **_no_window(),
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            raise EnvironmentError_('pip не закончил за 15 минут. Проверьте подключение к интернету.') from None
        output = (done.stdout + done.stderr).decode('utf-8', 'replace')
        log.info('pip %s: exit %s\n%s', ' '.join(args), done.returncode, output[-3000:])
        if done.returncode:
            hint = (
                ' Похоже, нет доступа к PyPI (интернет, прокси или VPN).'
                if re.search(r'(?i)connection|resolve|proxy|SSL', output)
                else ''
            )
            tail = '\n'.join(output.strip().splitlines()[-4:])
            raise EnvironmentError_(f'pip не смог установить пакеты.{hint}\n{tail}')

    def _import_check(self, env, webapp: Path):
        try:
            done = subprocess.run(
                [env['python'], '-E', '-c', IMPORT_CHECK, str(webapp)], capture_output=True, timeout=120,
                env=clean_env(env['prefix']), stdin=subprocess.DEVNULL, **_no_window(),
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            raise EnvironmentError_('Проверка модуля не закончилась за 2 минуты.') from None
        if b'CLINREPORT-IMPORT-OK' not in done.stdout:
            tail = '\n'.join(done.stderr.decode('utf-8', 'replace').strip().splitlines()[-3:])
            raise EnvironmentError_(f'Модуль не загружается в Python этого окружения — ничего не изменено.\n{tail}')

    def _swap(self, env, staged: Path, modules_dir: Path):
        backup = _backup_dir(env) / time.strftime('%Y%m%d-%H%M%S')
        moved, placed = [], []
        try:
            for kind, name in OUR_MODULES:
                dst = modules_dir / kind / name
                if dst.exists():
                    (backup / kind).mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dst), str(backup / kind / name))
                    moved.append((kind, name))
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(staged / kind / name, dst)
                placed.append(dst)
        except Exception:
            for dst in placed:
                shutil.rmtree(dst, ignore_errors=True)
            for kind, name in moved:
                shutil.move(str(backup / kind / name), str(modules_dir / kind / name))
            raise
        _prune_backups(env)
