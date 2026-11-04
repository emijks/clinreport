"""Linux: keep what the app and the libraries under it write inside the data folder.

WebKitGTK (and Mesa, for its GPU process), pip and Python's tempfile write to XDG_CACHE_HOME and TMPDIR — by default
~/.cache and /tmp, shared with every other program, so removing ClinReport would leave them behind. contain() points
both into the data folder (cache/, tmp/) for this process and everything it starts: WebKit's own processes and
OpenCRAVAT. Programs started *for the user* (the browser, the file manager) get the environment as it was
(user_env()): a browser that ClinReport happens to start first must not keep its cache in our folder.

Windows and macOS keep their behaviour: their WebView2 / WebKit data already lives in data/webview.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser

from . import paths

log = logging.getLogger('clinreport.isolation')

# Variable → its value before contain() (None: was not set).
_original = {}


def enabled() -> bool:
    return sys.platform.startswith('linux')


def redirections() -> dict:
    return {
        'XDG_CACHE_HOME': paths.cache_dir(),
        'TMPDIR': paths.tmp_dir(),
        'PIP_CACHE_DIR': paths.cache_dir() / 'pip',
    }


def contain():
    """Linux: point caches and temporary files of this process and its children into the data folder."""
    if not enabled():
        return
    for name, folder in redirections().items():
        folder.mkdir(parents=True, exist_ok=True)
        _original.setdefault(name, os.environ.get(name))
        os.environ[name] = str(folder)
    tempfile.tempdir = None  # tempfile caches the folder it found first


def user_env() -> dict:
    """os.environ as it was before contain(): for programs started for the user."""
    env = dict(os.environ)
    for name, value in _original.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def popen_for_user(args: list):
    """Start a program of the user's (file manager, browser) detached, with the user's own environment."""
    return subprocess.Popen(
        args,
        env=user_env(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def open_url(url: str):
    """webbrowser.open, but a browser started on Linux does not inherit our cache and temp folders."""
    if _original and shutil.which('xdg-open'):
        popen_for_user(['xdg-open', url])
    else:
        webbrowser.open(url)


def clean_tmp():
    """Empty tmp/ (call only when no other launcher of this user runs: it may be using it)."""
    folder = paths.tmp_dir()
    if not folder.is_dir():
        return
    removed = 0
    for item in folder.iterdir():
        try:
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed += 1
        except OSError as e:
            log.warning('cannot remove %s: %s', item, e)
    if removed:
        log.info('removed %d leftover temporary item(s)', removed)
