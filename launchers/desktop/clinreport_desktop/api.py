"""Methods the window's JavaScript calls (window.pywebview.api.*).

Report settings and templates go through the extension's own service code (the same
functions behind its HTTP routes), so the window and the browser page always agree.
Every method returns JSON-able data; user-facing problems come back as {"error": "..."}.
"""

import base64
import functools
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

from . import autostart, config, paths, sessionlog

log = logging.getLogger('clinreport.api')
NOTE_CODES = ('1', '2', '3', '7', '8')


def _safe(func):
    @functools.wraps(func)
    def wrapper(self, *args):
        from clinreport_core import service

        try:
            return func(self, *args)
        except (service.ClientError, ValueError, RuntimeError) as e:
            return {'error': str(e)}
        except Exception as e:
            log.exception('%s failed', func.__name__)
            return {'error': f'Внутренняя ошибка: {e!r}'}

    return wrapper


def open_folder(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == 'win32':
        os.startfile(str(path))  # noqa: S606
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(path)])
    else:
        subprocess.Popen(['xdg-open', str(path)])


class Api:
    def __init__(self, app):
        self._app = app

    # --- status ---

    @_safe
    def state(self):
        from clinreport_core import service

        app = self._app
        settings = service.load_user_settings()
        templates = service.list_templates({})['templates']
        return {
            'edition': 'desktop',
            'server': app.server.snapshot(),
            'versions': app.versions,
            'modules': app.modules(),
            'ru': app.ru,
            'update': app.update,
            'store': app.store,
            'checks': {
                'clinician': settings.get('clinician', ''),
                'templates_total': len(templates),
                'templates_bad': sum(1 for t in templates if t.get('check') and not t['check'].get('ok')),
            },
            'data_dir': str(paths.data_dir()),
        }

    @_safe
    def start(self):
        settings = config.load()
        self._app.server.start(settings['port_mode'], settings['port'])
        return {'ok': True}

    @_safe
    def stop(self):
        self._app.server.stop()
        return {'ok': True}

    @_safe
    def restart(self):
        self._app.server.stop()
        return self.start()

    # --- results ---

    @_safe
    def open_oc(self):
        self._require_running()
        webbrowser.open(self._app.server.start_url)
        return {'ok': True}

    @_safe
    def choose_result(self):
        import webview

        start_dir = ''
        recent = config.load()['recent']
        if recent:
            start_dir = str(Path(recent[0]['path']).parent)
        chosen = self._app.window.create_file_dialog(
            webview.FileDialog.OPEN,
            directory=start_dir,
            file_types=('Результат OpenCRAVAT (*.sqlite)', 'Все файлы (*.*)'),
        )
        if not chosen:
            return {'cancelled': True}
        return self.open_result(chosen[0], 'viewer')

    @_safe
    def open_result(self, path, target='viewer'):
        from clinreport_core import service

        self._require_running()
        opened = service.open_result({'dbpath': path})  # validates: exists and is an OpenCRAVAT result
        dbpath = urllib.parse.quote(opened['dbpath'])
        if target == 'report':
            url = f'{self._app.server.url}/webapps/clinreport/index.html?dbpath={dbpath}'
        else:
            url = f'{self._app.server.url}/result/index.html?dbpath={dbpath}'
        config.remember_result(opened['dbpath'])
        log.info('opened %s (%s)', opened['dbpath'], 'report' if target == 'report' else 'viewer')
        webbrowser.open(url)
        return {'ok': True}

    @_safe
    def recent(self):
        items = []
        for entry in config.load()['recent']:
            path = entry['path']
            item = {
                'path': path,
                'name': os.path.basename(path),
                'dir': os.path.dirname(path),
                'opened': entry.get('opened'),
                'exists': os.path.isfile(path),
            }
            if item['exists']:
                item.update(_result_summary(path))
            items.append(item)
        return {'items': items}

    @_safe
    def forget_result(self, path):
        config.forget_result(path)
        return {'ok': True}

    # --- templates (the extension's service, same as the browser page) ---

    @_safe
    def templates(self):
        from clinreport_core import service

        return service.list_templates({})

    @_safe
    def pick_docx(self):
        import webview

        chosen = self._app.window.create_file_dialog(webview.FileDialog.OPEN, file_types=('Документ Word (*.docx)',))
        if not chosen:
            return {'cancelled': True}
        path = Path(chosen[0])
        return {'path': str(path), 'title': path.stem, 'size': path.stat().st_size}

    @_safe
    def template_add(self, path, title, kind, replace=''):
        from clinreport_core import service

        data = base64.b64encode(Path(path).read_bytes()).decode('ascii')
        result = service.add_template({'title': title, 'kind': kind, 'data': data, 'replace': replace})
        log.info('template %s «%s» (%s)', 'replaced' if replace else 'added', title, kind)
        return result

    @_safe
    def template_delete(self, template_id):
        from clinreport_core import service

        result = service.delete_template({'id': template_id})
        log.info('template %s deleted', template_id)
        return result

    @_safe
    def template_check(self, template_id):
        from clinreport_core import service

        return service.check_template({'id': template_id})

    @_safe
    def template_save(self, template_id):
        import webview
        from clinreport_core import service

        document = service.template_file({'id': template_id})
        chosen = self._app.window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=document.filename, file_types=('Документ Word (*.docx)',)
        )
        if not chosen:
            return {'cancelled': True}
        target = chosen if isinstance(chosen, str) else chosen[0]
        if not target.lower().endswith('.docx'):
            target += '.docx'
        Path(target).write_bytes(document.data)
        return {'path': target}

    @_safe
    def template_fields(self):
        from clinreport_core import service

        return service.template_fields({})

    @_safe
    def open_templates_folder(self):
        open_folder(paths.conf_dir() / 'clinreport' / 'templates')
        return {'ok': True}

    # --- settings ---

    @_safe
    def settings(self):
        from clinreport_core import service

        launcher = config.load()
        launcher.pop('recent', None)
        launcher['autostart'] = autostart.is_enabled()
        listing = service.list_templates({})
        return {
            'report': service.get_settings({}),
            'launcher': launcher,
            'default_templates': [
                {'id': t['id'], 'title': t['title']} for t in listing['templates'] if t['kind'] == 'default'
            ],
            'default_template': listing['default_template'],
            'data_dir': str(paths.data_dir()),
        }

    @_safe
    def save_settings(self, report, launcher):
        from clinreport_core import service

        before = config.load()
        service.update_settings({k: v for k, v in (report or {}).items() if k in ('clinician', 'template')})
        after = config.update(launcher or {})
        if 'autostart' in (launcher or {}) and bool(launcher['autostart']) != autostart.is_enabled():
            autostart.set_enabled(bool(launcher['autostart']))
        if before['update_prerelease'] != after['update_prerelease']:
            threading.Thread(target=self._app.check_updates, daemon=True).start()
        restart = (before['port_mode'], before['port']) != (after['port_mode'], after['port'])
        log.info('settings saved%s', ' (port changed)' if restart else '')
        return {'ok': True, 'restart_needed': restart and self._app.server.state == 'running'}

    @_safe
    def ru_refresh(self):
        self._require_running()
        self._app.refresh_ru()
        return self._app.ru

    @_safe
    def check_store(self):
        self._app.check_store()
        return self._app.store

    @_safe
    def open_data_folder(self):
        open_folder(paths.data_dir())
        return {'ok': True}

    @_safe
    def open_logs_folder(self):
        open_folder(paths.logs_dir())
        return {'ok': True}

    @_safe
    def install_update(self):
        """Windows: download and run the newer installer in the background; elsewhere: open the release page."""
        update = self._app.update
        if not update.get('newer'):
            raise ValueError('Обновлений нет.')
        if not update.get('can_install'):
            webbrowser.open(update['url'])
            return {'ok': True, 'opened': update['url']}
        threading.Thread(target=self._app.install_update, daemon=True, name='update').start()
        return {'ok': True}

    @_safe
    def open_link(self, url):
        if not url.startswith('https://'):
            raise ValueError('Ссылка не поддерживается.')
        webbrowser.open(url)
        return {'ok': True}

    # --- log ---

    @_safe
    def client_log(self, level, message):
        self._app.client_log(level, message)
        return {'ok': True}

    @_safe
    def log(self):
        return {'lines': _tail(paths.logs_dir() / 'launcher.log', 300), 'server': self._app.server.log_tail(80)}

    @_safe
    def diagnostics(self):
        from clinreport_core import service

        app = self._app
        report = dict(service.get_settings({}))
        launcher = config.load()
        launcher['recent'] = len(launcher['recent'])
        lines = ['ClinReport — диагностика', time.strftime('%Y-%m-%d %H:%M:%S'), '']
        lines += [f'{k}: {v}' for k, v in app.versions.items()]
        lines += [
            '',
            f'data: {paths.data_dir()}',
            f'bundle: {paths.bundle_dir()}',
            f'session log: {sessionlog.session_log()}',
            *(
                f'{name}: {value}'
                for name, value in sessionlog.environment({})  # versions are listed above
                if name not in ('bundle', 'data')
            ),
            f'server: {app.server.snapshot()}',
            f'modules: {app.modules()}',
            f'ru: {app.ru}',
            f'report settings: {report}',
            f'launcher settings: {launcher}',
            '',
            '--- launcher.log ---',
            *_tail(paths.logs_dir() / 'launcher.log', 60),
            '',
            '--- server.log ---',
            app.server.log_tail(40),
        ]
        return {'text': '\n'.join(str(line) for line in lines)}

    # ---

    def _require_running(self):
        if self._app.server.state != 'running':
            raise RuntimeError('OpenCRAVAT ещё не запущен. Дождитесь запуска или нажмите «Запустить».')


def _tail(path: Path, count: int) -> list:
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            return [line.rstrip('\n') for line in fh.readlines()[-count:]]
    except OSError:
        return []


def _result_summary(path: str) -> dict:
    """Samples and marked variants of a result, read-only and best effort."""
    summary = {}
    try:
        with sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=2) as con:
            samples = [row[0] for row in con.execute('select distinct base__sample_id from sample')]
            summary['samples'] = [
                str(s).split('.')[0] if s not in (None, '') else Path(path).name.split('.')[0] for s in samples
            ]
            columns = {row[1] for row in con.execute('pragma table_info(variant)')}
            note = 'base__note' if 'base__note' in columns else None
            if note:
                marks = ','.join('?' * len(NOTE_CODES))
                summary['marked'] = con.execute(
                    f'select count(*) from variant where trim({note}) in ({marks})', NOTE_CODES
                ).fetchone()[0]
    except sqlite3.Error as e:
        summary['problem'] = str(e)
    return summary
