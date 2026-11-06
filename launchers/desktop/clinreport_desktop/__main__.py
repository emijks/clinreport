"""python -m clinreport_desktop [RESULT.sqlite] [--headless] [--minimized] [--selftest OUT.json]"""

import argparse
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

from . import config, environments, instance, isolation, paths, sessionlog, updates
from .server import Server, module_status, versions

log = logging.getLogger('clinreport')
ui_log = logging.getLogger('clinreport.ui')
UI_DIR = Path(__file__).resolve().parent / 'ui'
UI_TIMEOUT = 20  # seconds for the window's page to start before the log says so
UI_LOG_MAX = 200  # messages the page may log per session (a failing timer must not fill the disk)
# «Завершение работы» stays at least this long: on a fast computer OpenCRAVAT stops in a blink and the window seemed to
# vanish without stopping anything. Long enough to read and trust, short enough not to feel like a hang.
SHUTDOWN_MIN_SECONDS = 3


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
        self.search = environments.Search()
        self.installer = environments.Installer()
        self._envs_lock = threading.Lock()
        self.envs = {
            e['id']: e
            for e in environments.load_cache()
            if e.get('id') != environments.BUILTIN_ID and not (e.get('python') and environments.clinreport_copy(e['python']))
        }
        self.env_notice = None  # why the chosen environment was not used at start-up
        self.pending = None  # (path, 'viewer' | 'report') to open once OpenCRAVAT is ready
        self._closing = False  # the window's close was cancelled to stop OpenCRAVAT first
        self._may_close = False  # OpenCRAVAT stopped: the next close goes through
        self.pending_uninstall = None  # Linux: «Удалить ClinReport» asked; True = with the data (main() does it)

    def modules(self):
        at, cached = self._modules_cache
        if time.time() - at > 5:
            environment = self.server.environment
            cached = module_status(environment['modules_dir'] if environment else None)
            self._modules_cache = (time.time(), cached)
        return cached

    # --- environments (other OpenCRAVAT installations; environments.py) ---

    def on_env_found(self, env):
        with self._envs_lock:
            self.envs[env['id']] = env
            environments.save_cache(list(self.envs.values()))

    def forget_env(self, env_id):
        with self._envs_lock:
            env = self.envs.pop(env_id, None)
            environments.save_cache(list(self.envs.values()))
        return env

    def refresh_env(self, env_id):
        """Probe a known environment again (after installing, or before using it). Returns it, or None if gone."""
        env = self.envs.get(env_id)
        if env is None or not env.get('python'):
            return env
        try:
            info = environments.probe(env['python'])
        except environments.EnvironmentError_ as e:
            log.warning('environment %s: %s', env['python'], e)
            return None
        if not info.get('cravat'):
            return None
        fresh = environments.describe(info, env.get('source', ''))
        self.on_env_found(fresh)
        return fresh

    def chosen_environment(self):
        """The environment to start (None = built-in). Falls back to the built-in one, with a notice, when the chosen
        environment is gone or cannot run any more."""
        chosen = config.load()['environment']
        if chosen == environments.BUILTIN_ID:
            self.env_notice = None
            return None
        env = self.refresh_env(chosen)
        if env is None or not env['verdict']['can_run']:
            name = (self.envs.get(chosen) or {}).get('name', chosen)
            reasons = [
                r['text'] for r in (env or {}).get('verdict', {}).get('reasons', []) if r['level'] in ('bad', 'warn')
            ]
            self.env_notice = f'Окружение «{name}» сейчас недоступно, запущено встроенное.' + (
                f' {reasons[0]}' if reasons else ''
            )
            log.warning('%s', self.env_notice)
            return None
        self.env_notice = None
        return env

    def on_install_done(self, env_id):
        """After installing/removing modules: describe the environment again; restart it if it is the one running."""
        self.refresh_env(env_id)
        if self.server.environment and self.server.environment.get('id') == env_id and self.server.state == 'running':
            log.info('modules changed in the running environment; restarting OpenCRAVAT')
            self.server.stop()
            self.start_server()

    # --- lifecycle ---

    def start_server(self):
        settings = config.load()
        self._modules_cache = (0.0, [])
        self.server.start(settings['port_mode'], settings['port'], self.chosen_environment())

    def _on_ready(self):
        if self.args.result:
            self.pending = (self.args.result, 'viewer')
            self.args.result = None
        if self.pending:
            path, target = self.pending
            self.pending = None
            self.open_result(path, target)
        elif config.load()['open_browser_at_start'] and not self.args.minimized and not self.args.selftest:
            isolation.open_url(self.server.start_url)
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
        """Download the newer release and install it. Windows: start its setup, which closes this launcher. Linux: unpack
        the archive next to app/ and close; a detached shell swaps the folders and starts the new version."""
        update = self.update
        if not (update.get('newer') and update.get('can_install')) or update.get('state') == 'downloading':
            return

        def progress(done, total):
            self.update = dict(update, state='downloading', done=done, total=total)

        try:
            progress(0, update['asset'].get('size') or 0)
            setup = updates.download(update['asset'], progress)
            self.update = dict(update, state='installing')
            if sys.platform.startswith('linux'):
                from . import linuxapp

                linuxapp.apply_update(setup)
                self.quit()
            else:
                updates.run_installer(setup)
        except Exception as e:
            log.warning('update failed: %s', e)
            self.update = dict(update, state='ok', install_error=str(e))

    def start_at_launch(self) -> bool:
        """OpenCRAVAT starts when the user asks (Запустить, or opening a result) — not merely because the window
        opened. Exceptions: a result given on the command line (double-click on a .sqlite), the sign-in autostart
        (its setting promises a background server), the self-test, and the user's own setting."""
        args = self.args
        return bool(args.result or args.minimized or args.selftest or config.load()['start_server_at_launch'])

    def open_when_ready(self, path, target='viewer'):
        """Open a result now, or start OpenCRAVAT and open it when it is ready. True if it was queued."""
        if self.server.state == 'running':
            self.open_result(path, target)
            return False
        self.pending = (path, target)
        if self.server.state in ('stopped', 'failed'):
            self.start_server()
        return True

    def open_result(self, path, target='viewer'):
        from .api import Api

        result = Api(self).open_result(path, target)
        if result.get('error'):
            log.warning('cannot open %s: %s', path, result['error'])

    def activate(self, path):
        """A second launch: open its file, if any, and bring the window up."""
        if path:
            self.open_when_ready(path)
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

    def on_closing(self):
        """The window is about to close. With OpenCRAVAT running, keep the window open, show «Завершение работы» over
        it, stop OpenCRAVAT on another thread and close the window when it is down: the window is the last thing to
        go, so the user sees when ClinReport has really finished. Never block here (pywebview calls this on the UI
        thread; hide() or evaluate_js from here hangs on Windows)."""
        if self._may_close:
            return True
        busy = self.server.state in ('starting', 'running', 'stopping') or self.installer.busy()
        if not busy:
            return True
        if not self._closing:
            self._closing = True
            threading.Thread(target=self._close_after_stopping, daemon=True, name='closing').start()
        return False

    def _close_after_stopping(self):
        def show(text, done=False):
            try:
                self.window.evaluate_js(f'window.clinreportShutdown && window.clinreportShutdown({json.dumps(text)}, {json.dumps(done)})')
            except Exception:  # noqa: BLE001 - the page may be gone; closing must go on
                pass

        log.info('closing: stopping OpenCRAVAT first')
        started = time.monotonic()
        try:
            self.search.cancel()
            if self.installer.busy():
                show('Дожидаюсь окончания установки модулей ClinReport…')
                while self.installer.busy():
                    time.sleep(0.5)
            if self.server.state in ('starting', 'running', 'stopping'):
                show('Останавливаю OpenCRAVAT…')
                self.server.stop()
            time.sleep(max(0, started + SHUTDOWN_MIN_SECONDS - time.monotonic()))
            show('Готово', done=True)
            time.sleep(0.6)  # let «Готово» be seen
        except Exception:  # noqa: BLE001 - whatever happens, the window must close
            log.exception('stopping OpenCRAVAT on close failed')
        finally:
            self._may_close = True
            try:
                self.window.destroy()
            except Exception:  # noqa: BLE001
                os._exit(0)

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
        # 'stopping' too: --quit stops the server on another thread; leaving now would exit before its workers are gone.
        while app.server.state in ('starting', 'running', 'stopping'):
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


def linux_webkit() -> str:
    """Linux: name GTK's program (window class = the .desktop StartupWMClass; WebKit's cache folder name) and check
    that WebKitGTK can be loaded. Returns its version; raises RuntimeError (Russian, with the fix) when it cannot."""
    try:
        import gi

        gi.require_version('Gtk', '3.0')
        from gi.repository import GLib

        GLib.set_prgname('clinreport')
        GLib.set_application_name('ClinReport')
        for api in ('4.1', '4.0'):  # the APIs pywebview 6.2 supports, in its order
            try:
                gi.require_version('WebKit2', api)
                break
            except ValueError:
                continue
        from gi.repository import WebKit2

        return f'{WebKit2.get_major_version()}.{WebKit2.get_minor_version()}.{WebKit2.get_micro_version()} (WebKit2 {api})'
    except (ImportError, ValueError) as e:
        raise RuntimeError(
            'Окно ClinReport не может открыться: в системе нет WebKitGTK '
            f'({e}). Установите его — Debian/Ubuntu: sudo apt install gir1.2-webkit2-4.1; '
            'Fedora: sudo dnf install webkit2gtk4.1. Пока ClinReport работает в браузере.'
        ) from e


def run_browser_only(app, reason: str):
    """Linux without WebKitGTK: no control window; OpenCRAVAT starts and the browser opens its page."""
    import shutil
    import subprocess

    log.error('%s', reason)
    print(reason, file=sys.stderr, flush=True)
    if shutil.which('notify-send'):
        subprocess.run(['notify-send', '-a', 'ClinReport', 'ClinReport', reason], check=False, timeout=5)
    app.args.minimized = False
    if not config.load()['open_browser_at_start']:  # otherwise App._on_ready opens it already
        app.server.ready_callbacks.append(lambda: isolation.open_url(app.server.start_url))
    return run_headless(app)


def run_window(app):
    if sys.platform.startswith('linux'):
        try:
            log.info('WebKitGTK %s', linux_webkit())
        except RuntimeError as e:
            return run_browser_only(app, str(e))

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
    app.window.events.closing += app.on_closing
    app.window.events.closed += app.shutdown
    app.window.events.loaded += app.on_page_loaded

    def after_start():
        threading.Thread(target=app.watch_ui, daemon=True, name='ui-watch').start()
        if app.start_at_launch():
            app.start_server()
        threading.Thread(target=app.check_updates, daemon=True).start()
        if app.args.selftest:
            selftest(app)

    icon = UI_DIR / ('icon.ico' if sys.platform == 'win32' else 'icon.png')  # WinForms accepts only .ico
    webview.start(
        after_start,
        gui='gtk' if sys.platform.startswith('linux') else None,  # not Qt, even if some Qt is importable
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
        # The page can load well after the server (WebView2 on a CI runner: ~10 s); then give its status polls time.
        app.ui_ready.wait(max(0.0, deadline - time.time()))
        poll_until = min(deadline, time.time() + 20)
        while True:
            report['ui_text'] = app.window.evaluate_js('document.body.innerText')
            if 'работает' in (report['ui_text'] or '').lower() or time.time() > poll_until:
                break
            time.sleep(1)
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

    from .server import _kill_tree, kill_leftovers, wait_gone

    pid = instance.running_pid()
    if pid and instance.hand_over(action='quit'):
        try:
            _gone, alive = wait_gone([psutil.Process(pid)], timeout)
            if alive:
                log.warning('launcher %s did not close in %s s; ending it', pid, timeout)
                _kill_tree(alive[0])
        except psutil.NoSuchProcess:
            pass
    kill_leftovers()
    return 0


def install_or_uninstall(args) -> int:
    """Linux: `clinreport --install` / `--uninstall [--purge]` (linuxapp.py)."""
    from . import linuxapp

    data = paths.data_dir()
    try:
        if args.install:
            target = linuxapp.install(paths.bundle_dir(), stop_running=quit_running)
            print(f'ClinReport установлен в {target}.')
            print('Запуск: меню приложений → ClinReport, или команда «clinreport» в терминале.')
            print('Скачанную папку теперь можно удалить. Удаление программы: clinreport --uninstall [--purge]')
            return 0
        removed = linuxapp.uninstall(purge=args.purge, stop_running=quit_running)
    except linuxapp.InstallError as e:
        print(f'Ошибка: {e}', file=sys.stderr)
        return 1
    for path in removed:
        print(f'удалено: {path}')
    if args.purge:
        print('ClinReport удалён полностью, вместе с данными.')
    else:
        print(f'ClinReport удалён. Данные (настройки, шаблоны, модули, задания) остались в {data};')
        print(f'удалить и их: rm -rf "{data}"')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='clinreport')
    parser.add_argument('result', nargs='?', help='OpenCRAVAT result .sqlite to open')
    parser.add_argument('--headless', action='store_true', help='no window; print the address and keep running')
    parser.add_argument('--minimized', action='store_true', help='start with the window minimised (autostart)')
    parser.add_argument('--selftest', metavar='OUT.json', help='open the window, check it, write a report and exit')
    parser.add_argument('--quit', action='store_true', help='stop a running ClinReport (used by the uninstaller)')
    if sys.platform.startswith('linux'):
        parser.add_argument('--install', action='store_true', help='copy this build into the data folder, add a menu entry')
        parser.add_argument('--uninstall', action='store_true', help='remove the program and its menu entry, keep the data')
        parser.add_argument('--purge', action='store_true', help='with --uninstall: remove the data folder too')
    args = parser.parse_args(argv)
    if getattr(args, 'purge', False) and not args.uninstall:
        parser.error('--purge only goes with --uninstall')
    for stream in (sys.stdout, sys.stderr):  # Windows consoles/pipes default to a legacy code page
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    if args.result:
        args.result = os.path.abspath(args.result)

    paths.data_dir().mkdir(parents=True, exist_ok=True)
    sessionlog.setup()
    if args.quit:
        return quit_running()
    if getattr(args, 'install', False) or getattr(args, 'uninstall', False):
        return install_or_uninstall(args)
    if not args.selftest and instance.hand_over(args.result or ''):
        return 0  # the running launcher took it

    # The only launcher of this user from here on: its temporary files are ours to clear.
    isolation.contain()
    isolation.clean_tmp()
    if sys.platform.startswith('linux'):
        from . import linuxapp

        linuxapp.mark_data_dir()
        linuxapp.clean_leftovers()

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
        return run_window(app) or 0
    finally:
        listener.close()
        app.server.stop()
        if app.pending_uninstall is not None:
            uninstall_after_close(app.pending_uninstall)


def uninstall_after_close(purge: bool):
    """«Удалить ClinReport» in the window (Linux): the window and WebKit are gone; remove the program (and the data)."""
    import shutil
    import subprocess

    from . import linuxapp

    try:
        linuxapp.uninstall(purge=purge)
        text = 'ClinReport удалён' + (' вместе с данными.' if purge else f'. Ваши данные остались в {paths.data_dir()}.')
    except Exception as e:  # noqa: BLE001 - say what happened; nobody else will
        log.exception('uninstall failed')
        text = f'Не удалось удалить ClinReport: {e}'
    print(text, flush=True)
    if shutil.which('notify-send'):
        subprocess.run(['notify-send', '-a', 'ClinReport', 'ClinReport', text], check=False, timeout=5, env=isolation.user_env())


if __name__ == '__main__':
    sys.exit(main())
