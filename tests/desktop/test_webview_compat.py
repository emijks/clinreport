"""The pywebview patch for old macOS, against stand-ins for PyObjC (the real one exists only on macOS)."""

import sys
import types

import pytest
from clinreport_desktop import webview_compat


@pytest.fixture
def pyobjc(monkeypatch):
    """Fake objc + WebKit; `responds` says whether WKNavigationAction already has shouldPerformDownload."""
    added = []
    state = types.SimpleNamespace(responds=False, added=added)

    class WKNavigationAction:
        @staticmethod
        def instancesRespondToSelector_(selector):
            assert selector == b'shouldPerformDownload'
            return state.responds

    objc = types.ModuleType('objc')
    objc.selector = lambda func, selector, signature: types.SimpleNamespace(func=func, sel=selector, sig=signature)
    objc.classAddMethods = lambda cls, methods: added.extend((cls, m) for m in methods)
    webkit = types.ModuleType('WebKit')
    webkit.WKNavigationAction = WKNavigationAction
    monkeypatch.setitem(sys.modules, 'objc', objc)
    monkeypatch.setitem(sys.modules, 'WebKit', webkit)
    return state


def test_old_webkit_gets_should_perform_download(pyobjc):
    assert webview_compat.supply_should_perform_download() is True
    [(cls, method)] = pyobjc.added
    assert cls.__name__ == 'WKNavigationAction'
    assert (method.sel, method.sig) == (b'shouldPerformDownload', b'Z@:')  # BOOL, no arguments
    assert method.func(object()) is False  # "not a download": pywebview then allows the navigation


def test_new_webkit_is_left_alone(pyobjc):
    pyobjc.responds = True
    assert webview_compat.supply_should_perform_download() is False
    assert pyobjc.added == []
