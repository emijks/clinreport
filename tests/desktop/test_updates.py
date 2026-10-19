"""In-app updates: which release is offered, the checked download, how the installer is started (no network)."""

import hashlib
import io
import re
from types import SimpleNamespace

import pytest
from clinreport_desktop import updates
from clinreport_desktop.__main__ import App
from helpers import ROOT

ISS = (ROOT / 'packaging' / 'windows' / 'ClinReport.iss').read_text(encoding='utf-8')


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINREPORT_DATA_DIR', str(tmp_path / 'data'))
    return tmp_path / 'data'


def release(tag, *, prerelease=False, draft=False, assets=()):
    return {
        'tag_name': tag,
        'prerelease': prerelease,
        'draft': draft,
        'html_url': f'https://github.com/emijks/clinreport/releases/tag/{tag}',
        'assets': [{'name': n, 'browser_download_url': f'https://example.invalid/{n}', 'size': 10} for n in assets],
    }


@pytest.mark.parametrize(
    'older, newer',
    [
        ('2.2.0', '3.0.0'),
        ('3.0.0-rc1', '3.0.0-rc2'),
        ('3.0.0-rc2', '3.0.0'),
        ('3.0.0', '3.0.1'),
        ('3.0.9', '3.0.10'),
        ('3.0.0-rc.2', '3.0.0-rc.10'),
        ('dev', '3.0.0'),
        ('2.2-7-gc2bc886-dirty', '3.0.0'),
    ],
)
def test_version_order(older, newer):
    assert updates.version_key(older) < updates.version_key(newer)
    assert updates.version_key('v' + newer) == updates.version_key(newer)


def test_asset_names_match_build_py():
    build = (ROOT / 'packaging' / 'build.py').read_text(encoding='utf-8')
    assert "f'ClinReport-{version}-{platform_tag()}-setup'" in build
    assert "f'ClinReport-{version}-{platform_tag()}.dmg'" in build
    assert updates.asset_suffix('win-x64') == '-win-x64-setup.exe'
    assert updates.asset_suffix('macos-arm64') == '-macos-arm64.dmg'


def test_pick_skips_drafts_prereleases_and_other_tags():
    releases = [
        release('v3.1.0', draft=True),
        release('v3.1.0-rc1', prerelease=True),
        release('desktop-v9.0.0'),
        release('v3.0.1', assets=['ClinReport-3.0.1-win-x64-setup.exe', 'ClinReport-3.0.1-macos-arm64.dmg']),
        release('v3.0.0'),
    ]
    found = updates.pick(releases, '3.0.0', 'win-x64')
    assert found['version'] == '3.0.1' and found['newer'] and not found['prerelease']
    assert found['asset']['name'] == 'ClinReport-3.0.1-win-x64-setup.exe'

    with_pre = updates.pick(releases, '3.0.0', 'win-x64', include_prerelease=True)
    assert with_pre['version'] == '3.1.0-rc1' and with_pre['prerelease'] and with_pre['asset'] is None


def test_pick_current_or_older_is_not_newer():
    releases = [release('v3.0.0', assets=['ClinReport-3.0.0-win-x64-setup.exe'])]
    assert not updates.pick(releases, '3.0.0', 'win-x64')['newer']
    assert not updates.pick(releases, '3.0.1', 'win-x64')['newer']


def test_pick_reads_the_published_digest():
    item = release('v3.0.1', assets=['ClinReport-3.0.1-win-x64-setup.exe'])
    item['assets'][0]['digest'] = 'sha256:' + 'ab' * 32
    assert updates.pick([item], '3.0.0', 'win-x64')['asset']['sha256'] == 'ab' * 32


def test_pick_without_releases_raises():
    with pytest.raises(RuntimeError):
        updates.pick([release('v3.0.0', draft=True)], '3.0.0', 'win-x64')


def fake_get(payload: bytes):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    return lambda url, timeout: Response(payload)


def test_download_checks_size_and_digest(data_dir, monkeypatch):
    payload = b'installer' * 1000
    monkeypatch.setattr(updates, '_get', fake_get(payload))
    seen = []
    asset = {'name': 'ClinReport-3.0.1-win-x64-setup.exe', 'url': 'x', 'size': len(payload),
             'sha256': hashlib.sha256(payload).hexdigest()}
    path = updates.download(asset, lambda done, total: seen.append((done, total)))
    assert path.read_bytes() == payload and path.parent == data_dir / 'updates'
    assert seen[-1] == (len(payload), len(payload))
    assert not list(path.parent.glob('*.part'))


@pytest.mark.parametrize('change', [{'size': 5}, {'sha256': '00' * 32}])
def test_download_rejects_a_damaged_file(data_dir, monkeypatch, change):
    payload = b'installer'
    monkeypatch.setattr(updates, '_get', fake_get(payload))
    asset = dict({'name': 'setup.exe', 'url': 'x', 'size': len(payload), 'sha256': None}, **change)
    with pytest.raises(RuntimeError):
        updates.download(asset)
    assert not list((data_dir / 'updates').iterdir())


def test_clean_downloads(data_dir):
    folder = data_dir / 'updates'
    folder.mkdir(parents=True)
    (folder / 'old-setup.exe').write_bytes(b'x')
    updates.clean_downloads()
    assert not list(folder.iterdir())


def test_installer_is_started_silently_and_relaunches(data_dir, monkeypatch):
    started = []
    monkeypatch.setattr(updates.subprocess, 'Popen', lambda args, **kwargs: started.append(args))
    updates.run_installer(data_dir / 'setup.exe')
    args = started[0]
    assert {'/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/RELAUNCH=1'} <= set(args)
    # The .iss starts the new version only for that parameter, and only in silent mode.
    assert "ExpandConstant('{param:RELAUNCH|0}') = '1'" in ISS and 'Check: RelaunchRequested' in ISS


def test_app_install_update_downloads_then_runs(monkeypatch):
    asset = {'name': 'setup.exe', 'url': 'x', 'size': 3}
    app = SimpleNamespace(update={'state': 'ok', 'newer': True, 'can_install': True, 'version': '3.0.1', 'asset': asset})
    calls = []
    monkeypatch.setattr(updates, 'download', lambda a, progress: (progress(3, 3), calls.append('download'), 'setup')[2])
    monkeypatch.setattr(updates, 'run_installer', lambda setup: calls.append(('run', setup)))
    App.install_update(app)
    assert calls == ['download', ('run', 'setup')] and app.update['state'] == 'installing'


def test_app_install_update_reports_failures(monkeypatch):
    app = SimpleNamespace(update={'state': 'ok', 'newer': True, 'can_install': True, 'asset': {'name': 's', 'url': 'x'}})

    def broken(asset, progress):
        raise RuntimeError('нет сети')

    monkeypatch.setattr(updates, 'download', broken)
    App.install_update(app)
    assert app.update['state'] == 'ok' and app.update['install_error'] == 'нет сети'


def test_app_does_not_install_without_an_installable_update(monkeypatch):
    monkeypatch.setattr(updates, 'download', lambda *a: pytest.fail('must not download'))
    for update in ({'newer': False, 'can_install': True}, {'newer': True, 'can_install': False},
                   {'newer': True, 'can_install': True, 'state': 'downloading'}):
        App.install_update(SimpleNamespace(update=dict(update)))


def test_build_and_updater_use_the_same_tag_prefix():
    assert updates.TAG_PREFIX == 'v'
    assert re.search(r"TAG_PREFIX = 'v'", (ROOT / 'packaging' / 'build.py').read_text(encoding='utf-8'))
