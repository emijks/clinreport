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
