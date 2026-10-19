"""Start ClinReport (minimised) when the user logs in."""

import os
import plistlib
import sys
from pathlib import Path

from . import paths

LABEL = 'org.genlab.clinreport'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def command() -> list:
    """How this launcher was started, as an argument list, plus --minimized."""
    if sys.platform == 'darwin':
        app = next((p for p in Path(sys.executable).resolve().parents if p.suffix == '.app'), None)
        if app:
            return [str(app / 'Contents' / 'MacOS' / 'ClinReport'), '--minimized']
    exe = Path(sys.executable)
    if sys.platform == 'win32' and exe.name.lower() == 'python.exe':
        exe = exe.with_name('pythonw.exe')
    return [str(exe), '-I', '-m', 'clinreport_desktop', '--minimized']


def is_enabled() -> bool:
    if sys.platform == 'win32':
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, paths.APP_NAME)
            return True
        except OSError:
            return False
    return _posix_file().exists()


def set_enabled(enabled: bool):
    if sys.platform == 'win32':
        import subprocess
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, paths.APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command()))
            else:
                try:
                    winreg.DeleteValue(key, paths.APP_NAME)
                except FileNotFoundError:
                    pass
        return
    target = _posix_file()
    if not enabled:
        if target.exists():
            target.unlink()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'darwin':
        with open(target, 'wb') as fh:
            plistlib.dump({'Label': LABEL, 'ProgramArguments': command(), 'RunAtLoad': True}, fh)
    else:
        import shlex

        target.write_text(
            '[Desktop Entry]\nType=Application\nName=ClinReport\n'
            f'Exec={" ".join(shlex.quote(a) for a in command())}\nX-GNOME-Autostart-enabled=true\n',
            encoding='utf-8',
        )


def _posix_file() -> Path:
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'LaunchAgents' / f'{LABEL}.plist'
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'autostart' / 'clinreport.desktop'
