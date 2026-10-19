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
