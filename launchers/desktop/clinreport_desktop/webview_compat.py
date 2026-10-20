"""Patches that make pywebview 6.2.1 work on the oldest supported macOS (10.15). Re-check after a pywebview bump."""

import logging

log = logging.getLogger('clinreport')


def supply_should_perform_download() -> bool:
    """macOS < 11.3: WKNavigationAction has no shouldPerformDownload (Apple: macOS 11.3+), yet pywebview's Cocoa backend
    calls it first thing when WebKit asks whether to load a page. The call raises, WebKit never gets an answer, no page
    is loaded and the window stays empty (docs/issues/desktop/007). Supply it, answering "not a download", as wry
    (Tauri) does. Returns whether the patch was needed. Call before the window is created."""
    import objc
    import WebKit

    if WebKit.WKNavigationAction.instancesRespondToSelector_(b'shouldPerformDownload'):
        return False

    def should_perform_download(self):
        return False

    objc.classAddMethods(
        WebKit.WKNavigationAction,
        [objc.selector(should_perform_download, selector=b'shouldPerformDownload', signature=b'Z@:')],
    )
    log.info('WebKit without shouldPerformDownload (macOS < 11.3): supplied for pywebview')
    return True
