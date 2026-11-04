"""Linux: everything in one folder (isolation.py), install / uninstall / in-app update (linuxapp.py).

No GUI and no network: a fake bundle (bundle.json + the start script) stands in for a build, and HOME, XDG_DATA_HOME,
XDG_CONFIG_HOME and CLINREPORT_DATA_DIR point into tmp_path, so nothing outside it is touched.
"""

import json
import os
import subprocess
import sys
import tarfile
import tempfile

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux desktop integration')

from clinreport_desktop import autostart, isolation, linuxapp, paths  # noqa: E402


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake home: data folder ~/.local/share/clinreport, menu entries, autostart — all under tmp_path."""
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('XDG_DATA_HOME', str(home / '.local' / 'share'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(home / '.config'))
    monkeypatch.delenv('CLINREPORT_DATA_DIR', raising=False)
    monkeypatch.delenv('CLINREPORT_BUNDLE_DIR', raising=False)
    assert paths.data_dir() == home / '.local' / 'share' / 'clinreport'
    return home


def make_bundle(folder, version='3.1.0', platform='linux-x64', marker=''):
    """A stand-in for packaging/dist/ClinReport. Its start script records that it ran (for the update test)."""
    folder.mkdir(parents=True)
    (folder / 'bundle.json').write_text(json.dumps({'version': version, 'platform': platform}), encoding='utf-8')
    script = folder / linuxapp.START_SCRIPT
    script.write_text(f'#!/bin/sh\necho "{version}" > "{marker or "/dev/null"}"\n', encoding='utf-8')
    script.chmod(0o755)
    (folder / linuxapp.ICON).write_bytes(b'png')
    (folder / 'python').mkdir()
    (folder / 'python' / f'v{version}').write_text('x', encoding='utf-8')
    return folder


def user_data(data):
    """What uninstall must keep: settings, the lab's templates, Store modules, jobs, logs."""
    keep = ['conf/cravat-system.yml', 'conf/clinreport/templates/lab.docx', 'modules/annotators/x/x.yml',
            'jobs/j1/result.sqlite', 'logs/launcher.log', 'python-packages/p.py', 'launcher.json']
    for rel in keep:
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_text('data', encoding='utf-8')
    return keep


# --- isolation ---


def test_contain_points_caches_and_temp_files_into_the_data_folder(home, monkeypatch):
    monkeypatch.setattr(isolation, '_original', {})
    monkeypatch.setenv('TMPDIR', '/tmp')
    monkeypatch.delenv('XDG_CACHE_HOME', raising=False)
    monkeypatch.setattr(tempfile, 'tempdir', None)
    isolation.contain()
    data = paths.data_dir()
    assert os.environ['XDG_CACHE_HOME'] == str(data / 'cache')
    assert os.environ['TMPDIR'] == str(data / 'tmp')
    assert os.environ['PIP_CACHE_DIR'] == str(data / 'cache' / 'pip')
    assert tempfile.gettempdir() == str(data / 'tmp')
    # Programs started for the user get their own environment back: a set variable restored, an unset one removed.
    user = isolation.user_env()
    assert user['TMPDIR'] == '/tmp' and 'XDG_CACHE_HOME' not in user and 'PIP_CACHE_DIR' not in user
    monkeypatch.setattr(tempfile, 'tempdir', None)


def test_programs_for_the_user_get_the_users_environment(monkeypatch):
    monkeypatch.setattr(isolation, '_original', {'TMPDIR': None})
    monkeypatch.setenv('TMPDIR', '/somewhere/ours')
    started = []
    monkeypatch.setattr(isolation.subprocess, 'Popen', lambda args, **kw: started.append((args, kw)))
    monkeypatch.setattr(isolation.shutil, 'which', lambda name: '/usr/bin/' + name)
    isolation.open_url('http://localhost:8060/')
    (args, kw), = started
    assert args == ['xdg-open', 'http://localhost:8060/']
    assert 'TMPDIR' not in kw['env'] and kw['start_new_session']


def test_clean_tmp_empties_only_tmp(home):
    tmp = paths.tmp_dir()
    (tmp / 'clinreport-zip-1' / 'modules').mkdir(parents=True)
    (tmp / 'stray.txt').write_text('x', encoding='utf-8')
    (paths.data_dir() / 'conf').mkdir()
    isolation.clean_tmp()
    assert tmp.is_dir() and not list(tmp.iterdir()) and (paths.data_dir() / 'conf').is_dir()


# --- install ---


def test_install_copies_the_bundle_and_adds_a_menu_entry(home, tmp_path):
    source = make_bundle(tmp_path / 'Downloads' / 'ClinReport')
    target = linuxapp.install(source)
    assert target == paths.data_dir() / 'app' and (target / 'python' / 'v3.1.0').is_file()
    assert source.is_dir(), 'the download is left for the user to delete'
    entry = (home / '.local' / 'share' / 'applications' / 'clinreport.desktop').read_text(encoding='utf-8')
    assert f'Exec={target}/clinreport %f' in entry
    assert f'Icon={target}/clinreport.png' in entry
    assert 'StartupWMClass=clinreport' in entry and f'{linuxapp.DESKTOP_MARK}={target}' in entry
    link = home / '.local' / 'bin' / 'clinreport'
    assert link.is_symlink() and os.readlink(link) == str(target / 'clinreport')
    assert (paths.data_dir() / linuxapp.DATA_MARKER).is_file()


def test_installing_again_replaces_the_program_and_keeps_the_data(home, tmp_path):
    linuxapp.install(make_bundle(tmp_path / 'a' / 'ClinReport', version='3.1.0'))
    keep = user_data(paths.data_dir())
    stopped = []
    target = linuxapp.install(make_bundle(tmp_path / 'b' / 'ClinReport', version='3.1.1'), stop_running=lambda: stopped.append(1))
    assert stopped == [1], 'a running ClinReport is closed before its files are replaced'
    assert (target / 'python' / 'v3.1.1').is_file() and not (target / 'python' / 'v3.1.0').exists()
    assert all((paths.data_dir() / rel).is_file() for rel in keep)
    assert not linuxapp.staging_dir().exists() and not linuxapp.old_dir().exists()


def test_install_from_the_installed_copy_only_refreshes_the_entries(home, tmp_path):
    target = linuxapp.install(make_bundle(tmp_path / 'ClinReport'))
    (home / '.local' / 'share' / 'applications' / 'clinreport.desktop').unlink()
    assert linuxapp.install(target, stop_running=lambda: pytest.fail('must not stop itself')) == target
    assert (home / '.local' / 'share' / 'applications' / 'clinreport.desktop').is_file()


@pytest.mark.parametrize('platform', ['windows-x64', 'macos-arm64'])
def test_install_refuses_other_platforms(home, tmp_path, platform):
    with pytest.raises(linuxapp.InstallError):
        linuxapp.install(make_bundle(tmp_path / 'ClinReport', platform=platform))
    assert not paths.install_dir().exists()


def test_a_desktop_file_of_another_program_is_never_overwritten(home, tmp_path):
    foreign = home / '.local' / 'share' / 'applications' / 'clinreport.desktop'
    foreign.parent.mkdir(parents=True)
    foreign.write_text('[Desktop Entry]\nName=Something else\n', encoding='utf-8')
    with pytest.raises(linuxapp.InstallError):
        linuxapp.install(make_bundle(tmp_path / 'ClinReport'))
    linuxapp.uninstall()
    assert foreign.read_text(encoding='utf-8') == '[Desktop Entry]\nName=Something else\n'


def test_exec_line_quotes_paths_with_spaces():
    assert linuxapp._exec_arg('/home/a/app/clinreport') == '/home/a/app/clinreport'
    assert linuxapp._exec_arg('/home/Иван Петров/$x/clinreport') == '"/home/Иван Петров/\\$x/clinreport"'


# --- uninstall ---


def test_uninstall_removes_the_program_and_keeps_the_data(home, tmp_path):
    linuxapp.install(make_bundle(tmp_path / 'ClinReport'))
    data = paths.data_dir()
    keep = user_data(data)
    for part in ('cache/webkitgtk/x', 'tmp/t', 'updates/ClinReport-3.1.1-linux-x64.tar.gz', 'bin/oc', 'webview/ls', 'workspace/celery/x'):
        (data / part).parent.mkdir(parents=True, exist_ok=True)
        (data / part).write_text('x', encoding='utf-8')
    autostart.set_enabled(True)
    removed = linuxapp.uninstall()
    for name in linuxapp.PROGRAM_PARTS:
        assert not (data / name).exists(), name
    assert all((data / rel).is_file() for rel in keep)
    assert not (home / '.local' / 'share' / 'applications' / 'clinreport.desktop').exists()
    assert not (home / '.local' / 'bin' / 'clinreport').exists() and not autostart.is_enabled()
    assert data / 'app' in removed


def test_purge_removes_the_whole_data_folder(home, tmp_path):
    linuxapp.install(make_bundle(tmp_path / 'ClinReport'))
    user_data(paths.data_dir())
    linuxapp.uninstall(purge=True)
    assert not paths.data_dir().exists()
    left = sorted(str(p.relative_to(home)) for p in home.rglob('*') if not p.is_dir())
    assert left == [], f'files left outside the data folder: {left}'


def test_purge_refuses_a_folder_that_is_not_ours(home, monkeypatch):
    monkeypatch.setenv('CLINREPORT_DATA_DIR', str(home))  # e.g. a mistyped variable
    (home / 'thesis.docx').write_text('precious', encoding='utf-8')
    with pytest.raises(linuxapp.InstallError):
        linuxapp.uninstall(purge=True)
    (home / linuxapp.DATA_MARKER).write_text('', encoding='utf-8')
    with pytest.raises(linuxapp.InstallError):
        linuxapp.uninstall(purge=True)
    assert (home / 'thesis.docx').is_file()


def test_link_to_another_program_is_kept(home, tmp_path):
    link = home / '.local' / 'bin' / 'clinreport'
    link.parent.mkdir(parents=True)
    link.symlink_to('/opt/other/clinreport')
    linuxapp.uninstall()
    assert link.is_symlink()


def test_folder_sizes(home):
    data = paths.data_dir()
    for rel, size in (('app/python/x', 1000), ('cache/x', 300), ('tmp/y', 20), ('jobs/j/r.sqlite', 5000), ('launcher.json', 5)):
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_bytes(b'x' * size)
    assert linuxapp.folder_sizes() == {'program': 1000, 'cache': 320, 'data': 5005}
    linuxapp.clear_cache()
    assert linuxapp.folder_sizes()['cache'] == 20, 'tmp/ is emptied at start-up, not while the app may use it'


# --- in-app update ---


def release_archive(tmp_path, version, **kwargs):
    bundle = make_bundle(tmp_path / f'build-{version}' / 'ClinReport', version=version, **kwargs)
    archive = tmp_path / f'ClinReport-{version}-linux-x64.tar.gz'
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(bundle, arcname='ClinReport')
    return archive


def test_unpack_update_checks_the_archive(home, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'bundle_info', lambda: {'platform': 'linux-x64'})
    staging = linuxapp.unpack_update(release_archive(tmp_path, '3.1.1'))
    assert staging == linuxapp.staging_dir() and (staging / 'python' / 'v3.1.1').is_file()
    with pytest.raises(linuxapp.InstallError):
        linuxapp.unpack_update(release_archive(tmp_path, '3.1.2', platform='linux-arm64'))


def test_unpack_update_refuses_files_outside_the_folder(home, tmp_path):
    archive = tmp_path / 'evil.tar.gz'
    payload = tmp_path / 'payload'
    payload.write_text('x', encoding='utf-8')
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(payload, arcname='../../escaped')
    with pytest.raises(tarfile.TarError):
        linuxapp.unpack_update(archive)
    assert not (paths.data_dir().parent / 'escaped').exists()


def test_update_script_swaps_the_folders_after_the_launcher_exits_and_starts_the_new_version(home, tmp_path, monkeypatch):
    started = tmp_path / 'started'
    target = linuxapp.install(make_bundle(tmp_path / 'old' / 'ClinReport', version='3.1.0'))
    monkeypatch.setattr(paths, 'bundle_info', lambda: {'platform': 'linux-x64'})
    staging = linuxapp.unpack_update(release_archive(tmp_path, '3.1.1', marker=str(started)))
    launcher = subprocess.Popen(['sleep', '0.5'])  # stands in for the running launcher
    subprocess.run(
        ['sh', '-c', linuxapp.UPDATE_SCRIPT, 'clinreport-update', str(launcher.pid), str(staging), str(target),
         str(linuxapp.old_dir())],
        check=True, timeout=20,
    )
    launcher.wait()
    assert (target / 'python' / 'v3.1.1').is_file() and not (target / 'python' / 'v3.1.0').exists()
    assert not staging.exists() and not linuxapp.old_dir().exists()
    assert started.read_text(encoding='utf-8').strip() == '3.1.1', 'the new version was started'


def test_apply_update_needs_the_installed_copy(home, tmp_path, monkeypatch):
    monkeypatch.setattr(linuxapp, 'is_installed', lambda: False)
    with pytest.raises(linuxapp.InstallError):
        linuxapp.apply_update(release_archive(tmp_path, '3.1.1'))


def test_programs_for_the_user_are_only_started_through_isolation():
    """AGENTS.md rule 4: a browser or file manager started with our TMPDIR/XDG_CACHE_HOME would keep its files in our
    folder (and lose them on --purge). Only isolation.py may call webbrowser.open or start xdg-open."""
    import re

    from helpers import ROOT

    offenders = []
    for path in sorted((ROOT / 'launchers' / 'desktop' / 'clinreport_desktop').glob('*.py')):
        if path.name == 'isolation.py':
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if re.search(r'webbrowser\.open|Popen\(\[.xdg-open', line):
                offenders.append(f'{path.name}:{number}: {line.strip()}')
    assert offenders == []
