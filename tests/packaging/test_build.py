"""packaging/build.py helpers that run on any OS (the macOS checks parse text; otool itself runs only on macOS)."""

import importlib.util

import pytest
from helpers import ROOT


@pytest.fixture(scope='module')
def build():
    spec = importlib.util.spec_from_file_location('build', ROOT / 'packaging' / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NUMPY_ACCELERATE = 'Wheel-Version: 1.0\nGenerator: meson\nRoot-Is-Purelib: false\nTag: cp313-cp313-macosx_14_0_x86_64\n'
NUMPY_OPENBLAS = 'Wheel-Version: 1.0\nTag: cp313-cp313-macosx_10_13_x86_64\n'
PSUTIL = 'Wheel-Version: 1.0\nTag: cp36-abi3-macosx_10_9_x86_64\nTag: cp36-abi3-macosx_11_0_arm64\n'
PURE = 'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n'
MULTI = 'Wheel-Version: 1.0\nTag: cp313-cp313-macosx_10_13_universal2.macosx_12_0_x86_64\n'


@pytest.mark.parametrize(
    'wheel, expected',
    [(NUMPY_ACCELERATE, '14.0'), (NUMPY_OPENBLAS, '10.13'), (PSUTIL, '10.9'), (PURE, None), (MULTI, '10.13')],
)
def test_wheel_macos_minimum(build, wheel, expected):
    assert build.wheel_macos_minimum(wheel) == expected


def test_wheels_too_new(build, tmp_path):
    for name, version, wheel in (('numpy', '2.5.4', NUMPY_ACCELERATE), ('psutil', '7.2.2', PSUTIL), ('six', '1.17.0', PURE)):
        dist_info = tmp_path / f'{name}-{version}.dist-info'
        dist_info.mkdir()
        (dist_info / 'WHEEL').write_text(wheel, encoding='utf-8')
        (dist_info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n', encoding='utf-8')
    assert build.wheels_too_new(tmp_path, '10.15') == [('numpy', '2.5.4')]
    assert build.wheels_too_new(tmp_path, '14.0') == []


OTOOL_BUILD_VERSION = """Load command 9
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform 1
    minos 11.0
      sdk 14.2
Load command 10
          cmd LC_LOAD_DYLIB
"""
OTOOL_VERSION_MIN = """Load command 8
      cmd LC_VERSION_MIN_MACOSX
  cmdsize 16
  version 10.9
      sdk 10.15
"""


def test_otool_minimum(build):
    assert build.otool_minimum(OTOOL_BUILD_VERSION) == '11.0'
    assert build.otool_minimum(OTOOL_VERSION_MIN) == '10.9'
    assert build.otool_minimum(OTOOL_VERSION_MIN + OTOOL_BUILD_VERSION) == '11.0'
    assert build.otool_minimum('Load command 1\n cmd LC_SEGMENT_64\n') is None


def test_version_tuple_orders_numerically(build):
    assert build.version_tuple('10.15') > build.version_tuple('10.9')
    assert build.version_tuple('11.0') > build.version_tuple('10.15')


def test_stack_and_plist_agree(build):
    assert build.STACK['macos_minimum'] == {'x64': '10.15', 'arm64': '11.0'}
    assert '@MINOS@' in (ROOT / 'packaging' / 'macos' / 'Info.plist').read_text(encoding='utf-8')


def test_our_modules_are_found(build):
    assert build.our_modules() == ['webapps/clinreport', 'webviewerwidgets/wgclinreport']


def test_dev_environment_uses_the_pinned_stack(build):
    """Tests run on the same OpenCRAVAT and Python minor version as the desktop app ships."""
    dev = (ROOT / 'requirements-dev.txt').read_text(encoding='utf-8')
    assert f'open-cravat=={build.STACK["opencravat"]}' in dev.splitlines()
    minor = '.'.join(build.STACK['python'].split('.')[:2])
    ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
    assert ci.count('python-version: "') == ci.count(f'python-version: "{minor}"') > 0


def test_module_versions_follow_the_product_version():
    """One version number for the product (pyproject.toml) and both OpenCRAVAT modules (docs/decisions)."""
    import re
    import tomllib

    product = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    for yml in ('modules/webapps/clinreport/clinreport.yml', 'modules/webviewerwidgets/wgclinreport/wgclinreport.yml'):
        text = (ROOT / yml).read_text(encoding='utf-8')
        assert re.search(r'^version: (\S+)$', text, re.M).group(1) == product, yml
        assert f'  {product}:' in text, f'{yml}: release_note for {product} missing'


@pytest.mark.parametrize('failures, ok', [(0, True), (2, True), (5, False)])
def test_dmg_creation_retries_resource_busy(build, monkeypatch, tmp_path, failures, ok):
    calls = []

    def run(*args):
        calls.append(args[0])
        if args[0] == 'hdiutil' and calls.count('hdiutil') <= failures:
            raise build.subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(build, 'run', run)
    if ok:
        build.create_dmg(tmp_path, tmp_path / 'x.dmg', attempts=5, pause=0)
    else:
        with pytest.raises(build.subprocess.CalledProcessError):
            build.create_dmg(tmp_path, tmp_path / 'x.dmg', attempts=5, pause=0)
    assert calls[0] == 'sync' and calls.count('hdiutil') == min(failures + 1, 5)


def test_empty_module_folders_are_caught(build, tmp_path):
    """A cache with module folders but no files built an installer without hg38/wgnote (2026-10-21)."""
    (tmp_path / 'mappers' / 'hg38').mkdir(parents=True)
    (tmp_path / 'webviewerwidgets' / 'wgnote').mkdir(parents=True)
    (tmp_path / 'webviewerwidgets' / 'wgnote' / 'wgnote.yml').write_text('version: 3.0.0\n', encoding='utf-8')
    assert build.incomplete_modules(tmp_path, ['mappers/hg38', 'webviewerwidgets/wgnote', 'reporters/excelreporter']) == [
        'mappers/hg38',
        'reporters/excelreporter',
    ]


def test_linux_archive_has_the_start_script_and_no_runtime_leftovers(build, tmp_path, monkeypatch):
    """ClinReport-<v>-linux-<arch>.tar.gz: one folder, the start script + icon linuxapp expects, no bytecode, and not the
    folders OpenCRAVAT creates in its package folder when the bundle was test-run."""
    import tarfile

    from clinreport_desktop import linuxapp

    app = tmp_path / 'ClinReport'
    site = app / 'python' / 'lib' / 'python3.13' / 'site-packages'
    for rel in ('cravat/__init__.py', 'cravat/gui/app.py', 'cravat/conf/cravat-system.yml', 'cravat/jobs/x',
                'cravat/workspace/celery/x', 'cravat/__pycache__/a.pyc', 'webview/__init__.py', 'other/modules/m.py'):
        (site / rel).parent.mkdir(parents=True, exist_ok=True)
        (site / rel).write_text('x', encoding='utf-8')
    (app / 'bundle.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(build, 'platform_tag', lambda: 'linux-x64')
    archive = build.package_linux(app, '3.1.0', tmp_path)
    assert archive.name == 'ClinReport-3.1.0-linux-x64.tar.gz'
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
        start = tar.getmember(f'ClinReport/{linuxapp.START_SCRIPT}')
    assert {n.split('/')[0] for n in names} == {'ClinReport'}
    assert start.mode & 0o111 and f'ClinReport/{linuxapp.ICON}' in names
    sp = 'ClinReport/python/lib/python3.13/site-packages'
    assert {f'{sp}/cravat/__init__.py', f'{sp}/cravat/gui/app.py', f'{sp}/webview/__init__.py', f'{sp}/other/modules/m.py'} <= names
    assert not [n for n in names if '__pycache__' in n or any(f'{sp}/cravat/{d}' in n for d in build.OC_IMPORT_FOLDERS)]


def test_linux_start_script_runs_the_bundled_python_through_links(build, tmp_path):
    build.write_linux_start(tmp_path)
    script = (tmp_path / 'clinreport').read_text(encoding='utf-8')
    assert script.startswith('#!/bin/sh\n') and 'readlink -f "$0"' in script  # ~/.local/bin/clinreport is a link
    assert 'python/bin/python3" -I -m clinreport_desktop "$@"' in script


def test_linux_gui_stack_is_pinned():
    requirements = (ROOT / 'packaging' / 'requirements.txt').read_text(encoding='utf-8')
    assert 'PyGObject==' in requirements and 'pycairo==' in requirements
    assert all('sys_platform == "linux"' in line for line in requirements.splitlines() if line.startswith(('PyGObject', 'pycairo')))
