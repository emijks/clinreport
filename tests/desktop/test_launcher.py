"""Launcher logic without a window or a running OpenCRAVAT (needs open-cravat, pyyaml, psutil)."""

import json
import time
from pathlib import Path

import pytest
from clinreport_desktop import config, instance, paths, server


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A fake bundle (bundle.json + modules) and an empty data dir."""
    bundle = tmp_path / 'bundle'
    for rel, version in (('webapps/clinreport', '1.1.0'), ('mappers/hg38', '1.0.0')):
        folder = bundle / 'modules' / rel
        folder.mkdir(parents=True)
        name = rel.split('/')[1]
        (folder / f'{name}.yml').write_text(f'version: {version}\n', encoding='utf-8')
        (folder / f'{name}.py').write_text('# code\n', encoding='utf-8')
    (bundle / 'bundle.json').write_text(
        json.dumps({'version': '3.0.0', 'update_repo': 'x/y', 'managed': ['webapps/clinreport']}), encoding='utf-8'
    )
    monkeypatch.setenv('CLINREPORT_BUNDLE_DIR', str(bundle))
    monkeypatch.setenv('CLINREPORT_DATA_DIR', str(tmp_path / 'data'))
    return tmp_path


def test_config_defaults_update_and_validation(env):
    assert config.load()['port_mode'] == 'auto'
    settings = config.update({'port_mode': 'fixed', 'port': '8099', 'open_browser': 0, 'unknown': 1})
    assert (settings['port_mode'], settings['port'], settings['open_browser']) == ('fixed', 8099, False)
    with pytest.raises(ValueError):
        config.update({'port': 80})
    with pytest.raises(ValueError):
        config.update({'port_mode': 'random'})


def test_recent_results_are_unique_newest_first_and_capped(env):
    for i in range(config.RECENT_MAX + 3):
        config.remember_result(str(env / f'r{i}.sqlite'))
    config.remember_result(str(env / 'r0.sqlite'))
    recent = [Path(r['path']).name for r in config.load()['recent']]
    assert recent[0] == 'r0.sqlite' and len(recent) == config.RECENT_MAX and recent.count('r0.sqlite') == 1
    config.forget_result(str(env / 'r0.sqlite'))
    assert 'r0.sqlite' not in [Path(r['path']).name for r in config.load()['recent']]


def test_sync_replaces_managed_modules_and_keeps_others(env):
    server.sync_modules()
    modules = paths.data_dir() / 'modules'
    assert (modules / 'webapps/clinreport/clinreport.yml').is_file()
    # a Store-installed hg38 must survive; a changed ClinReport must be replaced
    (modules / 'mappers/hg38/data.sqlite').write_text('store install', encoding='utf-8')
    (modules / 'webapps/clinreport/clinreport.py').write_text('# stale\n', encoding='utf-8')
    server.sync_modules()
    assert (modules / 'mappers/hg38/data.sqlite').is_file()
    assert (modules / 'webapps/clinreport/clinreport.py').read_text(encoding='utf-8') == '# code\n'


def test_system_conf_points_everything_into_the_data_dir(env):
    import yaml

    conf = yaml.safe_load(server.write_system_conf(8077).read_text(encoding='utf-8'))
    data = paths.data_dir().as_posix()
    assert conf['gui_port'] == 8077 and conf['modules_dir'] == f'{data}/modules' and conf['conf_dir'] == f'{data}/conf'
    assert conf['store_url']  # merged with OpenCRAVAT's template
    assert conf['work_dir'] == f'{data}/workspace'  # OpenCRAVAT 3.x Celery/cache


def test_scripts_are_written_once_per_interpreter(env):
    server.make_scripts()
    oc = server.oc_command()
    assert oc.exists()
    stamp_before = oc.stat().st_mtime_ns
    time.sleep(0.05)
    server.make_scripts()
    assert oc.stat().st_mtime_ns == stamp_before  # not rewritten (it may be locked by a running server)


def test_pick_port(env):
    port = server.pick_port('auto', 0)
    assert server.FIRST_PORT <= port < server.FIRST_PORT + 100
    import socket

    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        s.listen()
        busy = s.getsockname()[1]
        with pytest.raises(RuntimeError, match='занят'):
            server.pick_port('fixed', busy)


def test_second_launch_hands_over_to_the_first(env):
    got = []
    listener = instance.Listener(lambda path: got.append(('open', path)), lambda: got.append(('quit', '')))
    try:
        assert instance.hand_over('C:/x.sqlite')
        assert instance.hand_over(action='quit')
        deadline = time.time() + 3
        while len(got) < 2 and time.time() < deadline:
            time.sleep(0.05)
        assert sorted(got) == [('open', 'C:/x.sqlite'), ('quit', '')]
    finally:
        listener.close()
    assert not instance.hand_over('again')  # nobody listening any more


def test_server_env_runs_the_desktop_edition_with_user_packages(env):
    run_env = server.server_env(Path('conf.yml'))
    assert run_env['CLINREPORT_EDITION'] == 'desktop' and run_env['CLINREPORT_DESKTOP'] == '1'
    assert run_env['PIP_TARGET'] == run_env['PYTHONPATH'] == str(paths.data_dir() / 'python-packages')


def test_versions_and_module_status(env):
    server.sync_modules()
    v = server.versions()
    assert v['app'] == '3.0.0' and v['extension'] == '1.1.0'
    status = {m['name']: m['ok'] for m in server.module_status()}
    assert status['clinreport'] and status['hg38'] and not status['wgnote']


def test_start_page_is_the_root_redirect():
    """OpenCRAVAT 3.x has no /submit/index.html (404); `/` redirects to the start page in every version."""
    srv = server.Server()
    assert srv.start_url == ''
    srv.port = 8060
    assert srv.start_url == 'http://localhost:8060/'


def test_system_conf_keeps_what_opencravat_saved(env):
    """OpenCRAVAT writes its Settings / the user-email answer into this file; a restart must not drop them."""
    import yaml

    path = server.write_system_conf(8060)
    conf = yaml.safe_load(path.read_text(encoding='utf-8'))
    conf.update(user_email='lab@example.org', user_email_opt_out=True, modules_dir='/elsewhere')
    path.write_text(yaml.safe_dump(conf), encoding='utf-8')
    again = yaml.safe_load(server.write_system_conf(8061).read_text(encoding='utf-8'))
    assert again['user_email'] == 'lab@example.org' and again['user_email_opt_out'] is True
    assert again['modules_dir'] == (paths.data_dir() / 'modules').as_posix() and again['gui_port'] == 8061
