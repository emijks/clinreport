"""Rules of the Windows installer that make updates safe; checked on the .iss source, so they run on any OS."""

import re
import sys

import pytest
from clinreport_desktop import instance
from helpers import ROOT

ISS = ROOT / 'packaging' / 'windows' / 'ClinReport.iss'
BUILD = ROOT / 'packaging' / 'build.py'
TEXT = ISS.read_text(encoding='utf-8')


def section(name):
    match = re.search(rf'^\[{name}\]\n(.*?)(?=^\[|\Z)', TEXT, re.M | re.S)
    return [line for line in (match.group(1) if match else '').splitlines() if line and not line.startswith(';')]


def define(name):
    return re.search(rf'^#define {name} "([^"]*)"', TEXT, re.M).group(1)


def test_app_id_never_changes():
    """A different AppId installs a second copy next to the old one instead of updating it."""
    assert define('AppGuid') == '{6F0B7E3C-2C59-4C7B-9C5A-8E0F3B6C1A42}'
    assert 'AppId={{#AppGuid}' in TEXT


@pytest.mark.parametrize('name', ['InstallDelete', 'UninstallDelete'])
def test_only_bundle_folders_are_deleted(name):
    """User data (settings, the lab's own templates, jobs) is in %LOCALAPPDATA%\\ClinReport and must survive."""
    targets = re.findall(r'Name: "([^"]+)"', '\n'.join(section(name)))
    assert targets and set(targets) <= {'{app}\\python', '{app}\\modules'}


def test_user_data_folder_is_never_a_target():
    for name in ('InstallDelete', 'UninstallDelete', 'Files', 'Dirs'):
        for line in section(name):
            assert '{localappdata}\\ClinReport' not in line and '{userappdata}' not in line, line


def test_default_install_dir_is_outside_the_data_dir():
    install_dir = re.search(r'^DefaultDirName=(.+)$', TEXT, re.M).group(1)
    assert install_dir == '{localappdata}\\Programs\\ClinReport'


def test_installer_waits_for_the_launcher_mutex():
    assert define('LauncherMutex') == instance.MUTEX_NAME
    assert "CheckForMutexes('{#LauncherMutex}')" in TEXT
    assert '--quit' in TEXT


def test_wizard_images_exist():
    for key in ('WizardImageFile', 'WizardSmallImageFile', 'SetupIconFile'):
        files = re.search(rf'^{key}=(.+)$', TEXT, re.M).group(1).split(',')
        for name in files:
            assert (ISS.parent / name.strip()).is_file(), name


def test_build_passes_every_define_the_script_expects():
    expected = set(re.findall(r'^#ifndef (\w+)', TEXT, re.M))
    passed = set(re.findall(r"f'/D(\w+)=", BUILD.read_text(encoding='utf-8')))
    assert expected == passed


@pytest.mark.skipif(sys.platform != 'win32', reason='named mutexes are a Windows feature')
def test_hold_mutex_is_visible_to_other_processes():
    import ctypes

    instance.hold_mutex()
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenMutexW(0x00100000, False, instance.MUTEX_NAME)  # SYNCHRONIZE
    assert handle, 'the installer would not see a running launcher'
    kernel32.CloseHandle(handle)
