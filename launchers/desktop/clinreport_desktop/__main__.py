"""python -m clinreport_desktop [RESULT.sqlite] [--headless] [--minimized] [--selftest OUT.json]"""

import argparse
import json
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import config, instance, paths, sessionlog, updates
from .server import Server, module_status, versions

log = logging.getLogger('clinreport')
ui_log = logging.getLogger('clinreport.ui')
UI_DIR = Path(__file__).resolve().parent / 'ui'
UI_TIMEOUT = 20  # seconds for the window's page to start before the log says so
UI_LOG_MAX = 200  # messages the page may log per session (a failing timer must not fill the disk)


class App:
    def __init__(self, args):
        self.args = args
        self.window = None
        self.versions = versions()
        self.ru = {'state': 'pending'}
        self.update = {'state': 'pending'}
        self.store = {'state': 'pending'}
        self.server = Server()
        self.server.ready_callbacks.append(self._on_ready)
        self._modules_cache = (0.0, [])
        self.page_loaded = threading.Event()  # pywebview finished loading the window's page
        self.ui_ready = threading.Event()  # app.js ran its init()
        self._ui_logged = 0

    def modules(self):
        at, cached = self._modules_cache
        if time.time() - at > 5:
            cached = module_status()
            self._modules_cache = (time.time(), cached)
        return cached

    # --- lifecycle ---

    def start_server(self):
        settings = config.load()
        self.server.start(settings['port_mode'], settings['port'])

    def _on_ready(self):
        if self.args.result:
            self.open_result(self.args.result)
            self.args.result = None
        elif config.load()['open_browser'] and not self.args.minimized and not self.args.selftest:
            webbrowser.open(self.server.start_url)
        threading.Thread(target=self.check_store, daemon=True).start()
        self.refresh_ru()

    def refresh_ru(self):
        self.ru = {'state': 'loading'}
        try:
            status = self.server.call('POST', 'ru_refresh', timeout=40)
            self.ru = dict(status, state='warning' if status.get('warning') else 'ok')
            log.info('Russian annotations: %s', status.get('warning') or status.get('counts'))
        except Exception as e:
            self.ru = {'state': 'warning', 'warning': f'Не удалось обратиться к серверу: {e}'}

    def check_store(self):
        """Can OpenCRAVAT reach its module Store? (Behind the lab VPN it usually cannot: Store installs then fail.)"""
        import urllib.request

        import yaml

        self.store = {'state': 'checking'}
        try:
            conf = yaml.safe_load((paths.conf_dir() / 'cravat-system.yml').read_text(encoding='utf-8')) or {}
            url = conf.get('store_url') or 'https://store.opencravat.org'
            request = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'ClinReport'})
            urllib.request.urlopen(request, timeout=8).close()
            self.store = {'state': 'ok', 'url': url}
        except urllib.error.HTTPError as e:  # it answered: reachable
            self.store = {'state': 'ok', 'url': url, 'status': e.code}
        except Exception as e:
            self.store = {'state': 'unreachable', 'error': str(e)}
            log.warning('module Store unreachable: %s', e)

    def check_updates(self):
        updates.clean_downloads()
        try:
            found = updates.latest(include_prerelease=config.load()['update_prerelease'])
            self.update = dict(found, state='ok', can_install=updates.can_install() and bool(found['asset']))
            if self.update['newer']:
                log.info('update available: %s', self.update['version'])
        except Exception as e:
            self.update = {'state': 'unknown', 'error': str(e)}

    def install_update(self):
        """Download the newer release's setup and start it (Windows); the setup then closes this launcher."""
        update = self.update
        if not (update.get('newer') and update.get('can_install')) or update.get('state') == 'downloading':
            return

        def progress(done, total):
            self.update = dict(update, state='downloading', done=done, total=total)

        try:
            progress(0, update['asset'].get('size') or 0)
            setup = updates.download(update['asset'], progress)
            self.update = dict(update, state='installing')
            updates.run_installer(setup)
        except Exception as e:
            log.warning('update failed: %s', e)
            self.update = dict(update, state='ok', install_error=str(e))

    def open_result(self, path):
        from .api import Api

        result = Api(self).open_result(path, 'viewer')
        if result.get('error'):
            log.warning('cannot open %s: %s', path, result['error'])

    def activate(self, path):
        """A second launch: open its file (or the start page) and bring the window up."""
        if path:
            if self.server.state == 'running':
                self.open_result(path)
            else:
                self.args.result = path
        elif self.server.state == 'running':
            webbrowser.open(self.server.start_url)
        if self.window:
            try:
                self.window.restore()
                self.window.show()
                self.window.on_top = True
                self.window.on_top = False
            except Exception:
                pass

    def quit(self):
        """Asked by another process (uninstaller): close the window, which stops the server."""
        if self.window:
            self.window.destroy()
        else:
            self.server.stop()
            os._exit(0)

    def shutdown(self):
        log.info('closing')
        self.server.stop()

    # --- the window's page ---

    def on_page_loaded(self):
        self.page_loaded.set()
        log.info('window page loaded')

    def client_log(self, level, message):
        """A message from the window's JavaScript (ui/index.html reports errors; 'ready' = init() ran)."""
        self._ui_logged += 1
        if self._ui_logged > UI_LOG_MAX:
            return
        if self._ui_logged == UI_LOG_MAX:
            ui_log.warning('%s messages from the page; ignoring the rest of this session', UI_LOG_MAX)
            return
        if level == 'ready':
            self.ui_ready.set()
        ui_log.log(logging.ERROR if level == 'error' else logging.INFO, '%s: %s', level, str(message)[:4000])

    def watch_ui(self, timeout=UI_TIMEOUT):
        """Say so in the log when the window's page has not started: the window then looks empty."""
        if self.ui_ready.wait(timeout):
            return
        log.warning(
            'the window page has not started in %s s (page loaded: %s); the window is probably empty',
            timeout,
            self.page_loaded.is_set(),
        )


def run_headless(app):
    """No window: CI, servers, Linux without a desktop. Ctrl+C stops."""
    app.start_server()
    try:
        while app.server.state in ('starting', 'running'):
            if app.server.state == 'running' and not getattr(app, '_announced', False):
                print(f'ClinReport: {app.server.url}  (Ctrl+C — остановить)', flush=True)
                app._announced = True
            time.sleep(0.5)
        if app.server.state == 'failed':
            print(app.server.error, file=sys.stderr)
            return 1
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
    return 0


def window_page() -> str:
    """ui/index.html with app.css and app.js inlined. Given to pywebview as html, the page needs no HTTP server: pywebview's
    listens on the fixed port 42001, which every pywebview app shares; when it is taken, the window stays empty on macOS
    and shows another app's page on Windows (docs/issues/desktop/007)."""
    page = (UI_DIR / 'index.html').read_text(encoding='utf-8')
    css = (UI_DIR / 'app.css').read_text(encoding='utf-8')
    js = (UI_DIR / 'app.js').read_text(encoding='utf-8')
    for tag, inline in (
        ('<link rel="stylesheet" href="app.css">', f'<style>\n{css}</style>'),
        ('<script src="app.js"></script>', f'<script>\n{js}</script>'),
    ):
        if page.count(tag) != 1:
            raise RuntimeError(f'ui/index.html must contain {tag} once')
        page = page.replace(tag, inline)
    return page


def run_window(app):
    import webview

    from .api import Api

    # pywebview prints to stderr itself and resets its level on import; its records reach our handlers through the root.
    logging.getLogger('pywebview').handlers.clear()
    logging.getLogger('pywebview').setLevel(logging.DEBUG)
    if sys.platform == 'darwin':
        from . import webview_compat

        try:
            webview_compat.supply_should_perform_download()
        except Exception:
            log.exception('cannot patch WebKit for pywebview')
        try:
            sessionlog.watch_webkit()
        except Exception:
            log.exception('cannot watch WebKit page loads')

    app.window = webview.create_window(
        'ClinReport',
        html=window_page(),
        js_api=Api(app),
        width=1000,
        height=700,
        min_size=(720, 520),
        minimized=app.args.minimized,
        text_select=True,
        background_color='#F4F6F9',
    )
    app.window.events.closed += app.shutdown
    app.window.events.loaded += app.on_page_loaded

    def after_start():
        threading.Thread(target=app.watch_ui, daemon=True, name='ui-watch').start()
        app.start_server()
        threading.Thread(target=app.check_updates, daemon=True).start()
        if app.args.selftest:
            selftest(app)

    icon = UI_DIR / ('icon.ico' if sys.platform == 'win32' else 'icon.png')  # WinForms accepts only .ico
    webview.start(
        after_start,
        private_mode=False,
        storage_path=str(paths.data_dir() / 'webview'),
        icon=str(icon) if icon.exists() else None,
    )


def selftest(app):
    """Open the real window, wait for the server and the UI, record what the window shows, close."""
    out = Path(app.args.selftest)
    report = {'ok': False, 'session_log': str(sessionlog.session_log())}
    try:
        deadline = time.time() + 200
        while time.time() < deadline and app.server.state not in ('running', 'failed'):
            time.sleep(0.5)
        report['server'] = app.server.snapshot()
        time.sleep(3)  # two status polls of the UI
        report['ui_text'] = app.window.evaluate_js('document.body.innerText')
        report['ui_state'] = app.window.evaluate_js('window.__clinreportState || null')
        report['page_loaded'] = app.page_loaded.is_set()
        report['ui_ready'] = app.ui_ready.is_set()
        report['ok'] = (
            app.server.state == 'running' and app.ui_ready.is_set() and 'работает' in (report['ui_text'] or '').lower()
        )
    except Exception as e:
        report['error'] = repr(e)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if not os.environ.get('CLINREPORT_SELFTEST_KEEP_OPEN'):
        app.window.destroy()


def quit_running(timeout=15) -> int:
    """Stop a running ClinReport (installer/uninstaller): ask the window to close, wait until the launcher has exited
    (its OpenCRAVAT goes with it), end it if it hangs, then stop any OpenCRAVAT process it left behind."""
    import psutil

    from .server import _kill_tree, kill_leftovers

    pid = instance.running_pid()
    if pid and instance.hand_over(action='quit'):
        try:
            psutil.Process(pid).wait(timeout)
        except psutil.TimeoutExpired:
            log.warning('launcher %s did not close in %s s; ending it', pid, timeout)
            _kill_tree(psutil.Process(pid))
        except psutil.NoSuchProcess:
            pass
    kill_leftovers()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='clinreport')
    parser.add_argument('result', nargs='?', help='OpenCRAVAT result .sqlite to open')
    parser.add_argument('--headless', action='store_true', help='no window; print the address and keep running')
    parser.add_argument('--minimized', action='store_true', help='start with the window minimised (autostart)')
    parser.add_argument('--selftest', metavar='OUT.json', help='open the window, check it, write a report and exit')
    parser.add_argument('--quit', action='store_true', help='stop a running ClinReport (used by the uninstaller)')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows consoles/pipes default to a legacy code page
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    if args.result:
        args.result = os.path.abspath(args.result)

    paths.data_dir().mkdir(parents=True, exist_ok=True)
    sessionlog.setup()
    if args.quit:
        return quit_running()
    if not args.selftest and instance.hand_over(args.result or ''):
        return 0  # the running launcher took it

    # The extension's code (settings, templates) runs in this process too, on the same conf dir.
    os.environ['CLINREPORT_CONF_DIR'] = str(paths.conf_dir())
    os.environ['CLINREPORT_EDITION'] = 'desktop'
    sys.path.insert(0, str(paths.extension_dir()))

    app = App(args)
    log.info(
        'ClinReport %s starting (OpenCRAVAT %s, Python %s, %s)',
        app.versions['app'],
        app.versions['opencravat'],
        app.versions['python'],
        app.versions['platform'],
    )
    sessionlog.log_environment(app.versions)
    instance.hold_mutex()
    listener = instance.Listener(app.activate, app.quit)
    try:
        if args.headless:
            return run_headless(app)
        run_window(app)
        return 0
    finally:
        listener.close()
        app.server.stop()


if __name__ == '__main__':
    sys.exit(main())
