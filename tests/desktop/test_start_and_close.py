"""OpenCRAVAT starts when the user asks, and closing the window stops it first (the window goes last)."""

import argparse
import json
import threading

import pytest
from clinreport_desktop import __main__ as main
from clinreport_desktop import config
from clinreport_desktop.__main__ import App
from helpers import ROOT


def said(window, text) -> bool:
    """The launcher passes the text to the page JSON-encoded."""
    return any(json.dumps(text)[1:-1] in js for js in window.shown)


class FakeWindow:
    def __init__(self):
        self.shown = []
        self.destroyed = threading.Event()

    def evaluate_js(self, code):
        self.shown.append(code)

    def destroy(self):
        self.destroyed.set()


class FakeServer:
    def __init__(self, state):
        self.state = state
        self.environment = None
        self.ready_callbacks = []
        self.stopped = False
        self.started = False

    def stop(self):
        self.stopped = True
        self.state = 'stopped'

    def start(self, *args):
        self.started = True
        self.state = 'starting'


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('CLINREPORT_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('CLINREPORT_BUNDLE_DIR', str(ROOT))
    monkeypatch.setattr(main, 'SHUTDOWN_MIN_SECONDS', 0)

    def make(state='stopped', **args):
        defaults = {'result': None, 'minimized': False, 'selftest': None, 'headless': False}
        made = App(argparse.Namespace(**dict(defaults, **args)))
        made.server = FakeServer(state)
        made.window = FakeWindow()
        made.start_server = made.server.start
        return made

    return make


def test_opencravat_waits_for_the_user(app):
    assert not app().start_at_launch()


@pytest.mark.parametrize('args', [{'result': 'x.sqlite'}, {'minimized': True}, {'selftest': 'out.json'}])
def test_opencravat_starts_with_a_file_autostart_or_selftest(app, args):
    assert app(**args).start_at_launch()


def test_opencravat_starts_at_launch_when_the_user_wants_it(app):
    config.update({'start_server_at_launch': True})
    assert app().start_at_launch()


def test_closing_without_opencravat_is_immediate(app):
    a = app('stopped')
    assert a.on_closing() is True
    assert not a.window.shown


def test_closing_stops_opencravat_first_and_then_closes_the_window(app):
    a = app('running')
    gate, stops = threading.Event(), []
    real_stop = a.server.stop

    def slow_stop():  # OpenCRAVAT takes a moment to stop
        stops.append(1)
        gate.wait(10)
        real_stop()

    a.server.stop = slow_stop
    assert a.on_closing() is False  # the window stays while OpenCRAVAT stops
    assert a.on_closing() is False  # a second click meanwhile does not start a second stop
    assert not a.window.destroyed.wait(0.5)
    gate.set()
    assert a.window.destroyed.wait(10)
    assert a.server.stopped and stops == [1]
    assert said(a.window, 'Останавливаю OpenCRAVAT')
    assert said(a.window, 'Готово')
    assert a.on_closing() is True  # the close pywebview retries now goes through


def test_closing_shows_the_shutdown_long_enough_even_when_opencravat_stops_at_once(app, monkeypatch):
    monkeypatch.setattr(main, 'SHUTDOWN_MIN_SECONDS', 1.5)
    a = app('running')
    assert a.on_closing() is False
    assert not a.window.destroyed.wait(1), 'a fast stop must not flash the window away'
    assert not said(a.window, 'Готово')
    assert a.window.destroyed.wait(10)
    assert a.server.stopped and said(a.window, 'Готово')


def test_switching_environment_starts_nothing_while_opencravat_is_stopped(app):
    from clinreport_desktop.api import Api

    a = app('stopped')
    assert Api(a).env_use('builtin') == {'ok': True, 'restarted': False}
    assert not a.server.started and config.load()['environment'] == 'builtin'


def test_switching_environment_restarts_a_running_opencravat(app):
    from clinreport_desktop.api import Api

    a = app('running')
    assert Api(a).env_use('builtin') == {'ok': True, 'restarted': True}
    assert a.server.stopped and a.server.started


def test_closing_waits_for_a_module_install(app, monkeypatch):
    a = app('running')
    busy = threading.Event()
    busy.set()
    monkeypatch.setattr(a.installer, 'busy', busy.is_set)
    assert a.on_closing() is False
    assert not a.window.destroyed.wait(1.5), 'must not close in the middle of an install'
    assert said(a.window, 'установки модулей')
    busy.clear()
    assert a.window.destroyed.wait(10)


def test_opening_a_result_while_stopped_starts_opencravat_and_queues_it(app):
    a = app('stopped')
    assert a.open_when_ready('C:/r.sqlite', 'report') is True
    assert a.server.started and a.pending == ('C:/r.sqlite', 'report')


def test_waiting_for_processes_survives_pidfd_einval(monkeypatch):
    """psutil 7.2.2 waits with pidfd_open(), which Linux refuses (EINVAL) for a process whose main thread has exited
    while other threads still run — OpenCRAVAT's processes right after terminate(). Waiting must go on by polling."""
    import subprocess
    import sys

    import psutil
    from clinreport_desktop import server

    def einval(*args, **kwargs):
        raise OSError(22, 'Invalid argument')

    monkeypatch.setattr(psutil, 'wait_procs', einval)
    quick = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(0.3)'])
    slow = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        gone, alive = server.wait_gone([psutil.Process(quick.pid), psutil.Process(slow.pid)], timeout=2)
        assert [p.pid for p in gone] == [quick.pid] and [p.pid for p in alive] == [slow.pid]
    finally:
        slow.kill()
        quick.wait()
        slow.wait()


def test_stop_always_ends_stopped(monkeypatch):
    """A failure while ending the processes must not leave the state at «stopping»: the window and --headless wait
    for «stopped» (before: --quit waited 15 s and then killed the launcher)."""
    from clinreport_desktop import server

    srv = server.Server()
    srv.state = 'running'
    monkeypatch.setattr(srv, '_terminate', lambda: (_ for _ in ()).throw(OSError(22, 'Invalid argument')))
    srv.stop()
    assert srv.state == 'stopped'


def test_server_gets_the_bundled_weasyprint(tmp_path, monkeypatch):
    """Windows bundle: OpenCRAVAT's process (where documents are made) is told where WeasyPrint is."""
    from clinreport_desktop import server

    (tmp_path / 'bundle.json').write_text('{}', encoding='utf-8')
    monkeypatch.setenv('CLINREPORT_BUNDLE_DIR', str(tmp_path))
    monkeypatch.setenv('CLINREPORT_DATA_DIR', str(tmp_path / 'data'))
    assert 'CLINREPORT_WEASYPRINT' not in server.server_env(tmp_path / 'conf.yml')
    (tmp_path / 'weasyprint').mkdir()
    (tmp_path / 'weasyprint' / 'weasyprint.exe').write_bytes(b'MZ')
    assert server.server_env(tmp_path / 'conf.yml')['CLINREPORT_WEASYPRINT'] == str(tmp_path / 'weasyprint' / 'weasyprint.exe')
