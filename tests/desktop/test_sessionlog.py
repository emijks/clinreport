"""Session logging: files, retention, hooks for lost errors, the window page's messages."""

import argparse
import faulthandler
import json
import logging
import os
import plistlib
import sys
import threading

import pytest
from clinreport_desktop import paths, sessionlog
from clinreport_desktop.__main__ import UI_LOG_MAX, App


@pytest.fixture
def data(tmp_path, monkeypatch):
    bundle = tmp_path / 'bundle'
    (bundle / 'modules').mkdir(parents=True)
    (bundle / 'bundle.json').write_text(json.dumps({'version': '3.0.0'}), encoding='utf-8')
    monkeypatch.setenv('CLINREPORT_BUNDLE_DIR', str(bundle))
    monkeypatch.setenv('CLINREPORT_DATA_DIR', str(tmp_path / 'data'))
    return tmp_path / 'data'


@pytest.fixture
def logged(data):
    """sessionlog.setup() without stream redirection; global logging state and hooks restored afterwards."""
    root = logging.getLogger()
    saved = (root.level, list(root.handlers), sys.excepthook, threading.excepthook)
    levels = {name: logging.getLogger(name).level for name in sessionlog.DEBUG_LOGGERS}
    sessionlog.setup(redirect=False)
    yield data
    for handler in root.handlers[len(saved[1]) :]:
        handler.close()
    root.setLevel(saved[0])
    root.handlers[:] = saved[1]
    sys.excepthook, threading.excepthook = saved[2], saved[3]
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)
    logging.captureWarnings(False)
    if faulthandler.is_enabled():
        faulthandler.disable()
    while sessionlog._open_files:
        sessionlog._open_files.pop().close()


def test_session_log_and_launcher_log(logged):
    logging.getLogger('clinreport.test').debug('only in the session log')
    logging.getLogger('clinreport.test').info('in both')
    session = sessionlog.session_log().read_text(encoding='utf-8')
    launcher = (paths.logs_dir() / 'launcher.log').read_text(encoding='utf-8')
    assert sessionlog.session_log().parent == logged / 'logs' / 'sessions'
    assert 'only in the session log' in session and 'in both' in session
    assert 'only in the session log' not in launcher and 'in both' in launcher
    assert sessionlog.SESSION_ID in launcher  # the start line points at the session file


def test_errors_in_threads_are_logged(logged):
    def fail():
        raise RuntimeError('port 42001 in use')

    thread = threading.Thread(target=fail, name='bottle')
    thread.start()
    thread.join()
    session = sessionlog.session_log().read_text(encoding='utf-8')
    assert 'uncaught exception in thread bottle' in session and 'RuntimeError: port 42001 in use' in session


def test_old_session_logs_are_pruned(data):
    sessions = paths.logs_dir() / 'sessions'
    sessions.mkdir(parents=True)
    for day in range(1, 31):
        (sessions / f'session-202610{day:02d}-120000-1.log').write_text('', encoding='utf-8')
    sessionlog.prune(keep=20)
    left = sorted(p.name for p in sessions.iterdir())
    assert len(left) == 19 and left[0] == 'session-20261012-120000-1.log'  # 19 + the new one = 20


def test_discarded_streams(tmp_path):
    assert sessionlog.discarded(None)
    with open(tmp_path / 'out.txt', 'w') as fh:
        assert not sessionlog.discarded(fh)


@pytest.mark.skipif(sys.platform == 'win32', reason='NUL has no inode on Windows; pythonw gives None there')
def test_dev_null_counts_as_discarded():
    with open(os.devnull, 'w') as fh:
        assert sessionlog.discarded(fh)


def test_macos_logs_go_to_library_logs(monkeypatch):
    monkeypatch.delenv('CLINREPORT_DATA_DIR', raising=False)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    assert paths.logs_dir() == paths.Path.home() / 'Library' / 'Logs' / 'ClinReport'
    monkeypatch.setenv('CLINREPORT_DATA_DIR', '/tmp/x')
    assert paths.logs_dir() == paths.Path('/tmp/x') / 'logs'


def test_environment_and_plist_version(data, tmp_path):
    rows = dict(sessionlog.environment({'app': '3.0.0'}))
    assert rows['app version'] == '3.0.0' and rows['logs'] == paths.logs_dir()
    plist = tmp_path / 'Info.plist'
    plist.write_bytes(plistlib.dumps({'CFBundleShortVersionString': '15608', 'CFBundleVersion': '15608.4.9'}))
    assert sessionlog.plist_version(plist) == '15608 (15608.4.9)'
    assert sessionlog.plist_version(tmp_path / 'missing.plist') == '-'


def test_page_messages(logged, caplog):
    app = App(argparse.Namespace(result=None, minimized=False, selftest=None))
    app.client_log('error', 'TypeError: replaceChildren is not a function')
    assert not app.ui_ready.is_set()
    app.client_log('ready', 'init done')
    assert app.ui_ready.is_set()
    for _ in range(UI_LOG_MAX + 10):
        app.client_log('info', 'spam')
    session = sessionlog.session_log().read_text(encoding='utf-8')
    assert 'ERROR clinreport.ui' in session and 'replaceChildren is not a function' in session
    assert session.count('info: spam') == UI_LOG_MAX - 3 and 'ignoring the rest' in session


def test_watch_ui_warns_when_the_page_does_not_start(logged):
    app = App(argparse.Namespace(result=None, minimized=False, selftest=None))
    app.watch_ui(timeout=0.01)
    assert 'the window page has not started' in sessionlog.session_log().read_text(encoding='utf-8')
