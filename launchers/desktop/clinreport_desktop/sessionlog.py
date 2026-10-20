"""Logging: launcher.log (all sessions, rotated) and logs/sessions/session-<id>.log (one launch, in full).

The session log also gets what would otherwise be lost when the app starts without a terminal (Finder, pythonw.exe):
uncaught errors in any thread, native crash dumps, stray stdout/stderr, and the window's own JavaScript errors
(Api.client_log). Its first lines describe the machine, so a log sent by a user is enough to start from.
"""

import faulthandler
import logging
import logging.handlers
import os
import platform
import plistlib
import sys
import threading
import time
from pathlib import Path

from . import paths

KEEP_SESSIONS = 20
SESSION_ID = time.strftime('%Y%m%d-%H%M%S') + f'-{os.getpid()}'
SESSION_FORMAT = '%(asctime)s.%(msecs)03d %(levelname)s %(name)s [%(threadName)s] %(message)s'
DEBUG_LOGGERS = ('clinreport', 'pywebview')  # everything else at INFO, so libraries do not flood the session log

log = logging.getLogger('clinreport')
_open_files = []  # the stream and faulthandler files must stay open for the whole process


def sessions_dir() -> Path:
    return paths.logs_dir() / 'sessions'


def session_log() -> Path:
    return sessions_dir() / f'session-{SESSION_ID}.log'


def setup(redirect=None):
    """Log to launcher.log (INFO) and this session's file (DEBUG); `redirect` (default: when nobody would see it)
    sends stdout/stderr into the session file."""
    sessions_dir().mkdir(parents=True, exist_ok=True)
    prune()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for name in DEBUG_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG)

    rolling = logging.handlers.RotatingFileHandler(
        paths.logs_dir() / 'launcher.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8'
    )
    rolling.setLevel(logging.INFO)
    rolling.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S'))
    root.addHandler(rolling)

    session = logging.FileHandler(session_log(), encoding='utf-8')
    session.setLevel(logging.DEBUG)
    session.setFormatter(logging.Formatter(SESSION_FORMAT, '%Y-%m-%d %H:%M:%S'))
    root.addHandler(session)

    if redirect is None:
        redirect = discarded(sys.stdout) or discarded(sys.stderr)
    if redirect:
        redirect_std_streams(session_log())
    else:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%H:%M:%S'))
        root.addHandler(console)

    install_hooks()
    logging.captureWarnings(True)
    log.info('session %s (log: %s)', SESSION_ID, session_log())


def prune(keep=KEEP_SESSIONS):
    """Delete all but the newest `keep` session logs, counting the one about to be written."""
    old = sorted(sessions_dir().glob('session-*.log'), reverse=True)[max(keep - 1, 0) :]
    for path in old:
        try:
            path.unlink()
        except OSError:
            pass  # still open in another running launcher (Windows)


def discarded(stream) -> bool:
    """Nobody reads this stream: no stream at all (pythonw.exe) or /dev/null (an app started from Finder)."""
    if stream is None:
        return True
    try:
        st = os.fstat(stream.fileno())
        null = os.stat(os.devnull)
    except (OSError, ValueError, AttributeError):
        return True
    return st.st_ino != 0 and (st.st_dev, st.st_ino) == (null.st_dev, null.st_ino)


def redirect_std_streams(path: Path):
    """stdout/stderr, Python's and native code's (file descriptors 1 and 2), into `path`."""
    out = open(path, 'a', encoding='utf-8', errors='replace', buffering=1)  # noqa: SIM115
    _open_files.append(out)
    for fd in (1, 2):
        try:
            os.dup2(out.fileno(), fd)
        except OSError:
            pass
    sys.stdout = sys.stderr = out


def install_hooks():
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    # Windows: faulthandler also reports exceptions that .NET (pywebview's WinForms backend) handles itself, so the
    # log would fill with harmless "Windows fatal exception" dumps. Native crashes there land in the Event Log.
    if sys.platform != 'win32':
        crash = open(session_log(), 'a', encoding='utf-8')  # noqa: SIM115
        _open_files.append(crash)
        faulthandler.enable(file=crash, all_threads=True)


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    log.critical('uncaught exception', exc_info=(exc_type, exc, tb))


def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread else '?'
    log.error('uncaught exception in thread %s', name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def watch_webkit():
    """macOS: pywebview ignores failed page loads, and it shows the web view only after a load finishes, so a failed
    load leaves an empty window (just its background colour) and no trace. Log those failures.
    Call before the window is created: WebKit reads which delegate methods exist when the delegate is set."""
    import objc
    from webview.platforms.cocoa import BrowserView

    webkit = logging.getLogger('clinreport.webkit')

    def failed(stage):
        def handler(self, webview, navigation, error):
            url = (error.userInfo() or {}).get('NSErrorFailingURLStringKey') or webview.URL()
            webkit.error(
                'page %s failed: %s (%s %s) %s', stage, error.localizedDescription(), error.domain(), error.code(), url
            )

        return handler

    def terminated(self, webview):
        webkit.error('the WebKit content process ended (crash or out of memory): the window stays empty')

    objc.classAddMethods(
        BrowserView.BrowserDelegate,
        [
            objc.selector(
                failed('load'), selector=b'webView:didFailProvisionalNavigation:withError:', signature=b'v@:@@@'
            ),
            objc.selector(failed('navigation'), selector=b'webView:didFailNavigation:withError:', signature=b'v@:@@@'),
            objc.selector(terminated, selector=b'webViewWebContentProcessDidTerminate:', signature=b'v@:@'),
        ],
    )


# --- what this machine is ---


def environment(versions: dict) -> list:
    """(name, value) pairs for the session log's header."""
    rows = [(f'{key} version', value) for key, value in versions.items()]
    rows += [
        ('system', platform.platform()),
        ('machine', platform.machine()),
        ('executable', sys.executable),
        ('arguments', ' '.join(sys.argv[1:]) or '-'),
        ('bundle', _safe_call(paths.bundle_dir)),
        ('data', paths.data_dir()),
        ('logs', paths.logs_dir()),
        ('locale', os.environ.get('LANG') or os.environ.get('LC_ALL') or '-'),
    ]
    if sys.platform == 'darwin':
        rows += [
            ('macOS', platform.mac_ver()[0]),
            ('WebKit', plist_version('/System/Library/Frameworks/WebKit.framework/Resources/Info.plist')),
            ('Safari', plist_version('/Applications/Safari.app/Contents/Info.plist')),
            # Gatekeeper runs a quarantined app from a random read-only copy ("App Translocation").
            ('translocated', 'AppTranslocation' in sys.executable),
        ]
    elif sys.platform == 'win32':
        rows += [('Windows', ' '.join(platform.win32_ver()[:3])), ('WebView2', webview2_version())]
    return rows


def log_environment(versions: dict):
    for name, value in environment(versions):
        log.info('  %-13s %s', name + ':', value)


def plist_version(path) -> str:
    try:
        with open(path, 'rb') as fh:
            info = plistlib.load(fh)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return '-'
    short, build = info.get('CFBundleShortVersionString'), info.get('CFBundleVersion')
    return f'{short} ({build})' if short and build and short != build else str(short or build or '-')


def webview2_version() -> str:
    """The installed WebView2 Runtime (Edge's), which renders the window on Windows."""
    import winreg

    client = r'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for root, key in (
        (winreg.HKEY_LOCAL_MACHINE, rf'SOFTWARE\WOW6432Node\{client}'),
        (winreg.HKEY_LOCAL_MACHINE, rf'SOFTWARE\{client}'),
        (winreg.HKEY_CURRENT_USER, rf'SOFTWARE\{client}'),
    ):
        try:
            with winreg.OpenKey(root, key) as handle:
                version = winreg.QueryValueEx(handle, 'pv')[0]
        except OSError:
            continue
        if version and version != '0.0.0.0':
            return version
    return 'not found'


def _safe_call(func):
    try:
        return func()
    except BaseException as e:  # paths.bundle_dir() exits when there is no bundle
        return f'? ({e})'
