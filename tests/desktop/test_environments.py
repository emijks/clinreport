"""Other OpenCRAVAT installations ("environments"): finding them without side effects, judging them, installing our
modules into them, and running their OpenCRAVAT. The real end-to-end run (an OpenCRAVAT 2.2.9 venv) is manual:
docs/development/testing.md."""

import json
import subprocess
import sys
import threading
import venv
from pathlib import Path

import pytest
from clinreport_desktop import config, server
from clinreport_desktop import environments as envs
from helpers import ROOT

WINDOWS = sys.platform == 'win32'


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINREPORT_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('CLINREPORT_BUNDLE_DIR', str(ROOT))  # bundled modules = the repository's modules/
    return tmp_path / 'data'


@pytest.fixture(scope='module')
def fake_oc_venv(tmp_path_factory):
    """A real venv whose site-packages has a `cravat` that records being imported, and its dist-info."""
    root = tmp_path_factory.mktemp('venv')
    venv.EnvBuilder(with_pip=False).create(root)
    python = root / ('Scripts/python.exe' if WINDOWS else 'bin/python')
    site = Path(
        subprocess.check_output(
            [str(python), '-c', 'import sysconfig; print(sysconfig.get_paths()["purelib"])'], text=True
        ).strip()
    )
    marker = root / 'imported'
    (site / 'cravat').mkdir()
    (site / 'cravat' / '__init__.py').write_text(f'open({str(marker)!r}, "w").close()\n', encoding='utf-8')
    (site / 'cravat' / 'admin_util.py').write_text('', encoding='utf-8')
    for name, version in (('open_cravat', '2.2.9'), ('setuptools', '80.10.2'), ('Jinja2', '3.1.6')):
        info = site / f'{name}-{version}.dist-info'
        info.mkdir()
        (info / 'METADATA').write_text(f'Name: {name}\nVersion: {version}\n', encoding='utf-8')
    return python, site, marker


# --- probing: never imports the other OpenCRAVAT ---


def test_probe_finds_opencravat_without_importing_it(fake_oc_venv):
    python, site, marker = fake_oc_venv
    info = envs.probe(python)
    assert Path(info['cravat']) == site / 'cravat'
    assert info['packages']['open-cravat'] == '2.2.9' and info['packages']['jinja2'] == '3.1.6'
    assert not marker.exists(), 'importing cravat creates C:\\open-cravat and writes its conf: the probe must not'


def test_probe_reports_a_python_that_is_not_one(tmp_path):
    fake = tmp_path / ('python.exe' if WINDOWS else 'python3')
    fake.write_text('not a program', encoding='utf-8')
    if not WINDOWS:
        fake.chmod(0o755)
    with pytest.raises(envs.EnvironmentError_):
        envs.probe(fake, timeout=10)


def test_describe_reads_conf_and_modules_from_disk(fake_oc_venv, tmp_path, monkeypatch):
    python, site, _ = fake_oc_venv
    root = tmp_path / 'open-cravat'
    modules = tmp_path / 'elsewhere' / 'modules'
    (root / 'conf').mkdir(parents=True)
    (root / 'conf' / 'cravat-system.yml').write_text(
        f'modules_dir: {modules.as_posix()}\ngui_port: 8070\n', encoding='utf-8'
    )
    for kind, name, version in (
        ('webapps', 'clinreport', '1.0.0'),
        ('webviewerwidgets', 'wgnote', '3.0.0'),
        ('mappers', 'hg38', '1'),
    ):
        (modules / kind / name).mkdir(parents=True)
        (modules / kind / name / f'{name}.yml').write_text(f'version: {version}\n', encoding='utf-8')
    monkeypatch.setattr(envs, 'oc_root', lambda package, platform=sys.platform: root)

    env = envs.describe(envs.probe(python), 'test')
    assert env['kind'] == 'venv' and env['opencravat'] == '2.2.9' and env['gui_port'] == 8070
    assert Path(env['modules_dir']) == modules
    assert env['modules']['ours'] == {'clinreport': '1.0.0', 'wgclinreport': None}
    assert env['modules']['wgnote'] and env['modules']['hg38'] and env['modules']['count'] == 3
    assert env['id'] == envs.env_id(python)


# --- can ClinReport use it? (the matrix in docs/reference/opencravat-integration.md) ---


def _env(oc='2.2.9', py='3.11.9', st='80.0', ours='3.0.1', packages=envs.CORE_PACKAGES, pip=True, writable=True):
    return {
        'opencravat': oc, 'python_version': py, 'setuptools': st, 'pip': pip, 'modules_writable': writable,
        'packages': [{'name': envs.normalize(p)} for p in packages], 'conf_exists': True, 'conf_path': '/x/conf/cravat-system.yml',
        'modules_dir': '/x/modules', 'modules': {'wgnote': True, 'ours': {'clinreport': ours, 'wgclinreport': ours}},
    }  # fmt: skip


@pytest.mark.parametrize(
    'changes, platform, can_run, can_install',
    [
        ({}, 'win32', True, True),
        ({'oc': '2.1.2'}, 'linux', False, False),  # no webapp routes before 2.2.0
        ({'py': '3.7.9'}, 'linux', False, False),  # the modules need 3.8
        ({'oc': '2.5.0', 'py': '3.12.1'}, 'linux', False, True),  # `import imp`
        ({'oc': '2.6.1', 'py': '3.12.1'}, 'linux', True, True),
        ({'st': '81.0'}, 'linux', False, True),  # pkg_resources gone
        ({'oc': '2.17.0', 'st': '81.0'}, 'linux', True, True),
        ({'oc': '3.2.4', 'st': '82.0'}, 'win32', False, True),  # 3.x needs the desktop patches on Windows
        ({'oc': '3.2.4', 'st': '82.0'}, 'darwin', True, True),
        ({'ours': None}, 'linux', False, True),  # install first
        ({'writable': False}, 'linux', True, False),
        ({'packages': ('jinja2',), 'pip': False}, 'linux', True, False),  # docxtpl… cannot be installed
    ],
)
def test_assess(changes, platform, can_run, can_install):
    verdict = envs.assess(_env(**changes), platform=platform, latest='3.0.1')
    assert (verdict['can_run'], verdict['can_install']) == (can_run, can_install), verdict['reasons']
    assert verdict['level'] in ('ok', 'warn', 'bad') and verdict['summary']


def test_assess_asks_to_update_old_modules_and_names_the_packages_it_will_download():
    verdict = envs.assess(_env(ours='1.0.0', packages=('jinja2',)), platform='linux', latest='3.0.1')
    texts = ' '.join(r['text'] for r in verdict['reasons'])
    assert 'устарели (1.0.0)' in texts and 'docxtpl, python-docx, lxml' in texts


def test_packages_in_our_module_lib_count_as_installed(tmp_path):
    lib = tmp_path / 'clinreport' / 'lib'
    for name in ('docxtpl-0.20.2.dist-info', 'python_docx-1.1.2.dist-info', 'lxml-6.1.3.dist-info'):
        (lib / name).mkdir(parents=True)
    assert envs.missing_packages(_env(packages=('jinja2',)), tmp_path / 'clinreport') == []
    assert envs.missing_packages(_env(packages=())) == list(envs.CORE_PACKAGES)


# --- where to look ---


def test_conda_environments_txt_is_read(tmp_path):
    (tmp_path / '.conda').mkdir()
    (tmp_path / '.conda' / 'environments.txt').write_text('/opt/envs/cravat\n\n/home/u/miniconda3\n', encoding='utf-8')
    prefixes = envs.conda_prefixes(tmp_path)
    assert Path('/opt/envs/cravat') in prefixes and tmp_path / 'miniconda3' in prefixes


def _fake_install(base: Path) -> Path:
    if WINDOWS:
        site, python = base / 'Lib' / 'site-packages', base / 'python.exe'
    else:
        site, python = base / 'lib' / 'python3.11' / 'site-packages', base / 'bin' / 'python3.11'
    (site / 'cravat').mkdir(parents=True)
    (site / 'cravat' / 'admin_util.py').write_text('', encoding='utf-8')
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text('', encoding='utf-8')
    return python


def test_deep_search_finds_site_packages_cravat_and_skips_noise(tmp_path):
    wanted = _fake_install(tmp_path / 'work' / 'envs' / 'oc')
    _fake_install(tmp_path / 'project' / 'node_modules' / 'x')  # never walked into
    found = [p for p, _ in envs.deep_candidates([tmp_path], threading.Event())]
    assert found == [wanted]


def test_deep_search_stops_when_cancelled(tmp_path):
    _fake_install(tmp_path / 'a' / 'b')
    cancel = threading.Event()
    cancel.set()
    assert list(envs.deep_candidates([tmp_path], cancel)) == []


# --- installing our modules ---


@pytest.fixture
def target(data, tmp_path):
    """An environment whose Python is this one (it has docxtpl & co., so nothing is downloaded)."""
    env = dict(
        _env(), id='py-test', python=sys.executable, prefix=sys.prefix, modules_dir=str(tmp_path / 'their-modules')
    )
    env['packages'] = [{'name': envs.normalize(p)} for p in envs.CORE_PACKAGES]
    return env


def _run(installer, env, action, source=None):
    done = threading.Event()
    installer.start(env, action, source, lambda _id: done.set())
    assert done.wait(180)
    return installer.state()[env['id']]


def test_install_update_and_remove(target, data):
    installer = envs.Installer()
    modules = Path(target['modules_dir'])
    job = _run(installer, target, 'install', envs.bundled_modules_dir())
    assert job['state'] == 'done', job
    version = envs.source_version(envs.bundled_modules_dir())
    assert envs.module_version(modules / 'webapps' / 'clinreport') == version == job['version']
    assert (modules / 'webviewerwidgets' / 'wgclinreport' / 'wgclinreport.yml').is_file()

    (modules / 'webapps' / 'clinreport' / 'lib' / 'kept-1.0.dist-info').mkdir(parents=True)  # downloaded last time
    assert _run(installer, target, 'install', envs.bundled_modules_dir())['state'] == 'done'
    assert (modules / 'webapps' / 'clinreport' / 'lib' / 'kept-1.0.dist-info').is_dir(), 'an update keeps lib/'
    assert len(list((data / 'module-backups' / 'py-test').iterdir())) == 1

    job = _run(installer, target, 'remove')
    assert job['state'] == 'done' and not (modules / 'webapps' / 'clinreport').exists()
    assert (modules / 'webapps').is_dir(), 'only our folders go'


def test_failed_check_changes_nothing(target, monkeypatch):
    installer = envs.Installer()
    modules = Path(target['modules_dir'])
    old = modules / 'webapps' / 'clinreport'
    old.mkdir(parents=True)
    (old / 'clinreport.yml').write_text('version: 1.0.0\n', encoding='utf-8')

    def broken(self, env, webapp):
        raise envs.EnvironmentError_('Модуль не загружается в Python этого окружения — ничего не изменено.')

    monkeypatch.setattr(envs.Installer, '_import_check', broken)
    job = _run(installer, target, 'install', envs.bundled_modules_dir())
    assert job['state'] == 'failed' and 'ничего не изменено' in job['error']
    assert envs.module_version(old) == '1.0.0'


def test_swap_restores_the_previous_modules_when_copying_fails(target, monkeypatch, tmp_path):
    modules = Path(target['modules_dir'])
    old = modules / 'webapps' / 'clinreport'
    old.mkdir(parents=True)
    (old / 'clinreport.yml').write_text('version: 1.0.0\n', encoding='utf-8')
    staged = tmp_path / 'staged'
    for kind, name in envs.OUR_MODULES:
        (staged / kind / name).mkdir(parents=True)
    real_copytree = envs.shutil.copytree

    def copytree(src, dst, *args, **kwargs):
        if Path(src).name == 'wgclinreport':
            raise OSError('disk full')
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(envs.shutil, 'copytree', copytree)
    with pytest.raises(OSError):
        envs.Installer()._swap(target, staged, modules)
    assert envs.module_version(old) == '1.0.0'
    assert not (modules / 'webviewerwidgets' / 'wgclinreport').exists()


def test_import_check_runs_in_the_environments_python(target, tmp_path):
    webapp = tmp_path / 'clinreport'
    real_copytree = envs.shutil.copytree
    real_copytree(ROOT / 'modules' / 'webapps' / 'clinreport', webapp)
    envs.Installer()._import_check(target, webapp)  # imports clinreport_core.service, raises if it cannot
    (webapp / 'clinreport_core' / 'service.py').write_text('raise ImportError("no docxtpl")\n', encoding='utf-8')
    with pytest.raises(envs.EnvironmentError_, match='ничего не изменено'):
        envs.Installer()._import_check(target, webapp)


def test_zip_must_contain_both_modules(tmp_path):
    import zipfile

    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('clinreport-extension-3.0.1/readme.txt', 'x')
    with pytest.raises(envs.EnvironmentError_, match='нет модулей'):
        envs.modules_from_zip(bad, tmp_path / 'x')
    good = tmp_path / 'good.zip'
    with zipfile.ZipFile(good, 'w') as z:
        for kind, name in envs.OUR_MODULES:
            z.writestr(f'clinreport-extension-3.0.1/modules/{kind}/{name}/{name}.yml', 'version: 3.0.1\n')
    modules = envs.modules_from_zip(good, tmp_path / 'y')
    assert envs.source_version(modules) == '3.0.1'


# --- running another environment's OpenCRAVAT ---


def test_another_environment_runs_with_its_own_conf_and_our_templates(data, monkeypatch):
    monkeypatch.setenv('PYTHONPATH', '/ours')
    monkeypatch.setenv('OPENCRAVAT_SYSTEM_CONF_PATH', '/ours/cravat-system.yml')
    env = {'python': '/their/bin/python', 'prefix': '/their', 'opencravat': '2.2.9'}
    command = server.environment_command(env, 8061)
    assert command == ['/their/bin/python', '-c', server.OC_MAIN, 'gui', '--headless', '--port', '8061']
    assert 'from cravat.oc import main' in server.OC_MAIN
    assert '--port' not in server.environment_command(dict(env, opencravat='2.2.0'), 8061)

    variables = server.environment_env(env)
    assert 'PYTHONPATH' not in variables and 'OPENCRAVAT_SYSTEM_CONF_PATH' not in variables
    assert variables['CLINREPORT_CONF_DIR'] == str(envs.paths.conf_dir())  # templates and settings are shared


def test_leftover_opencravat_of_another_environment_is_stopped(data):
    import psutil

    data.mkdir(parents=True)
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        server.pid_file().write_text(f'{proc.pid} {psutil.Process(proc.pid).create_time()}', encoding='utf-8')
        server._kill_recorded(psutil)
        assert proc.wait(10) is not None
        assert not server.pid_file().exists()
    finally:
        proc.kill()


def test_a_reused_pid_is_not_killed(data):
    import psutil

    data.mkdir(parents=True)
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    try:
        server.pid_file().write_text(f'{proc.pid} 12345.0', encoding='utf-8')  # another process had this pid
        server._kill_recorded(psutil)
        assert proc.poll() is None
    finally:
        proc.kill()


def test_manual_pythons_are_remembered_once(data):
    config.remember_python('/a/python')
    config.remember_python('/a/python')
    assert config.load()['environments_manual'] == ['/a/python']
    config.forget_python('/a/python')
    assert config.load()['environments_manual'] == []


def test_cache_round_trip(data):
    envs.save_cache([{'id': 'py-1', 'name': 'x'}])
    assert envs.load_cache() == [{'id': 'py-1', 'name': 'x'}]
    assert json.loads((data / 'environments.json').read_text(encoding='utf-8'))['items']


def test_route_appends_module_lib_after_the_environment(tmp_path, monkeypatch):
    import importlib.util
    import shutil

    webapp = tmp_path / 'clinreport'
    shutil.copytree(ROOT / 'modules' / 'webapps' / 'clinreport', webapp)
    (webapp / 'lib').mkdir()
    monkeypatch.setattr(sys, 'path', list(sys.path))
    spec = importlib.util.spec_from_file_location('route', webapp / 'route.py')
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert sys.path[-1] == str(webapp / 'lib') and sys.path[0] == str(webapp)
