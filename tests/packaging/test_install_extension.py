"""packaging/install_extension.py: install, update and remove the modules in an existing OpenCRAVAT."""

import importlib.util
import shutil

import pytest
from helpers import ROOT

SCRIPT = ROOT / 'packaging' / 'install_extension.py'


def load(path=SCRIPT):
    spec = importlib.util.spec_from_file_location('install_extension', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def md(tmp_path):
    folder = tmp_path / 'modules'
    folder.mkdir()
    return folder


def test_install_update_uninstall(md, capsys):
    installer = load()
    installer.main(['--md', str(md), '--no-deps'])
    for kind, name in installer.MODULES.items():
        assert (md / kind / name / f'{name}.yml').is_file()
    assert not list(md.rglob('__pycache__'))
    assert 'Installed' in capsys.readouterr().out

    stale = md / 'webapps' / 'clinreport' / 'stale.py'
    stale.write_text('# removed in the new version\n', encoding='utf-8')
    installer.main(['--md', str(md), '--no-deps'])
    assert not stale.exists(), 'an update replaces the module folder'
    assert 'Updated' in capsys.readouterr().out

    installer.main(['--md', str(md), '--uninstall'])
    assert not (md / 'webapps' / 'clinreport').exists()
    assert not (md / 'webviewerwidgets' / 'wgclinreport').exists()


def test_other_modules_are_left_alone(md):
    other = md / 'webapps' / 'someoneelse'
    other.mkdir(parents=True)
    load().main(['--md', str(md), '--no-deps'])
    load().main(['--md', str(md), '--uninstall'])
    assert other.is_dir()


def test_works_from_the_extension_zip_layout(tmp_path, md):
    """In the release zip, modules/ sits next to the script."""
    unpacked = tmp_path / 'clinreport-extension'
    unpacked.mkdir()
    shutil.copy2(SCRIPT, unpacked / SCRIPT.name)
    shutil.copytree(ROOT / 'modules', unpacked / 'modules')
    installer = load(unpacked / SCRIPT.name)
    assert installer.source_dir() == unpacked / 'modules'
    installer.main(['--md', str(md), '--no-deps'])
    assert (md / 'webapps' / 'clinreport' / 'route.py').is_file()


def test_dependencies_are_installed_into_the_running_python(md, monkeypatch):
    installer = load()
    calls = []
    monkeypatch.setattr(installer.subprocess, 'check_call', calls.append)
    installer.main(['--md', str(md), '--with-db'])
    assert calls[0][1:4] == ['-m', 'pip', 'install'] and {'docxtpl', 'sqlalchemy', 'psycopg2-binary'} <= set(calls[0])


def test_missing_modules_dir_fails_clearly(tmp_path):
    with pytest.raises(SystemExit, match='does not exist'):
        load().main(['--md', str(tmp_path / 'nope'), '--no-deps'])
