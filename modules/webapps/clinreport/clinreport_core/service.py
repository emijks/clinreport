"""Request handlers of the ClinReport webapp, independent of the web framework.

Each public handler takes the request parameters as a dict and the Caller (who is
logged in to OpenCRAVAT) and returns either a JSON-serialisable dict or a FileResult.
route.py adapts them to the GUI server that loaded the webapp. ClientError carries a
message meant for the user.
"""

from __future__ import annotations

import base64
import copy
import glob
import io
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from . import templates as tpl
from .clinreport import DEFAULT_TEMPLATES, ClinReport, render_context
from .database import Database, get_ru_annotations
from .labels import LAYOUTS, context_to_payload_records

DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
SETTINGS_FILENAME = 'clinreport.json'  # local mode: the user's settings
USER_SETTINGS_FILENAME = 'clinreport-users.json'  # login mode: {username: user settings}
DB_KEYS = ('host', 'port', 'name', 'user', 'pass')
DB_ENV_PREFIX = 'CLINREPORT_DB_'  # CLINREPORT_DB_HOST … CLINREPORT_DB_PASS: the only source of the DB connection
USER_DEFAULTS = {
    'clinician': '',
    'template': DEFAULT_TEMPLATES[0],
    'auto_upload': False,
}
RU_ANNOTATIONS_TTL = 600  # seconds
# 'server' (GLS image) or 'desktop' (the offline backup app, desktop/): the desktop edition has no database
# or CLINBIO, so the page hides those buttons instead of showing them disabled.
EDITION_ENV = 'CLINREPORT_EDITION'


class ClientError(Exception):
    """Invalid request or unavailable resource; the message is shown to the user."""


class Unauthorized(ClientError):
    """Login mode and nobody is logged in."""


class FileResult:
    def __init__(self, data: bytes, filename: str, content_type: str):
        self.data = data
        self.filename = filename
        self.content_type = content_type


class Caller:
    """Who sends the request. `name` is the OpenCRAVAT login (None = not logged in);
    without login mode (`multiuser` False) everyone is the local user 'default'."""

    def __init__(self, name: str | None = 'default', multiuser: bool = False):
        self.name = name
        self.multiuser = multiuser


LOCAL = Caller()


def _admin_util():
    from cravat import admin_util

    return admin_util


def authorize(caller: Caller) -> None:
    """route.py calls this before every handler."""
    if caller.multiuser and not caller.name:
        raise Unauthorized('Требуется вход в OpenCRAVAT: обновите страницу и войдите.')


def is_admin(caller: Caller) -> bool:
    if not caller.multiuser:
        return True
    return caller.name in _admin_util().get_system_conf().get('admin_list', ['admin'])


# --- settings (kept in the OpenCRAVAT conf dir, so reinstalling the module keeps them) ---
#
# DB connection: one per server, from CLINREPORT_DB_* environment variables only. The page never sees or
# changes it; it only learns whether the database is connected (db_configured).
# User settings (clinician, template, auto_upload): per OpenCRAVAT login in clinreport-users.json;
# in local mode they stay in clinreport.json next to the DB settings, as before.

_settings_lock = threading.Lock()


def conf_dir() -> str:
    """OpenCRAVAT's conf dir; CLINREPORT_CONF_DIR overrides it for callers that do not import cravat
    (the desktop launcher, the CLI)."""
    return os.environ.get('CLINREPORT_CONF_DIR') or _admin_util().get_conf_dir()


def edition() -> str:
    return 'desktop' if os.environ.get(EDITION_ENV) == 'desktop' else 'server'


def settings_path() -> str:
    return os.path.join(conf_dir(), SETTINGS_FILENAME)


def user_settings_path() -> str:
    return os.path.join(conf_dir(), USER_SETTINGS_FILENAME)


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _db_env() -> dict:
    """Non-empty CLINREPORT_DB_* variables (empty ones, e.g. from an unset compose passthrough, do not count)."""
    values = {key: os.environ.get(DB_ENV_PREFIX + key.upper(), '') for key in DB_KEYS}
    return {key: value for key, value in values.items() if value}


def load_db_settings() -> dict:
    env = _db_env()
    return {key: env.get(key, '') for key in DB_KEYS}


def load_user_settings(caller: Caller = LOCAL) -> dict:
    if caller.multiuser:
        stored = _read_json(user_settings_path()).get(caller.name) or {}
    else:
        stored = _read_json(settings_path())
    settings = dict(USER_DEFAULTS)
    settings.update({key: stored[key] for key in USER_DEFAULTS if key in stored})
    return settings


def _public_settings(caller: Caller) -> dict:
    return dict(
        load_user_settings(caller),
        username=caller.name,
        multiuser=caller.multiuser,
        clinbio_enabled=clinbio_configured(caller),
        db_configured=Database.is_configured(load_db_settings()),
        edition=edition(),
        templates_editable=is_admin(caller),
    )


def get_settings(params: dict, caller: Caller = LOCAL) -> dict:
    return _public_settings(caller)


def update_settings(params: dict, caller: Caller = LOCAL) -> dict:
    user_changes = {}
    for key in USER_DEFAULTS:
        if key not in params:
            continue
        if key == 'auto_upload':
            user_changes[key] = bool(params[key])
        elif key == 'template':
            try:
                item = _store().get(str(params[key]))
            except tpl.TemplateProblem as e:
                raise ClientError(str(e)) from None
            if item['kind'] != 'default':
                raise ClientError('Шаблон по умолчанию должен быть для стандартного заключения.')
            user_changes[key] = item['id']
        else:
            user_changes[key] = str(params[key]).strip()
    with _settings_lock:
        if not caller.multiuser:
            stored = _read_json(settings_path())
            stored.update(user_changes)
            _write_json(settings_path(), stored)
        elif user_changes:
            users = _read_json(user_settings_path())
            users[caller.name] = dict(users.get(caller.name) or {}, **user_changes)
            _write_json(user_settings_path(), users)
    return _public_settings(caller)


# --- Russian OMIM / secondary-findings overrides (cached; failure is only a warning) ---

_ru_lock = threading.Lock()
_ru_cache = {'at': 0.0, 'data': None, 'warning': None}


def ru_annotations():
    """Return (annotations or None, warning or None)."""
    with _ru_lock:
        if time.time() - _ru_cache['at'] > RU_ANNOTATIONS_TTL:
            try:
                _ru_cache['data'], _ru_cache['warning'] = get_ru_annotations(), None
            except Exception as e:
                _ru_cache['data'] = None
                _ru_cache['warning'] = (
                    f'Не удалось получить аннотации на русском ({e!r}); используются аннотации OpenCRAVAT.'
                )
            _ru_cache['at'] = time.time()
        return _ru_cache['data'], _ru_cache['warning']


def ru_status(params: dict, caller: Caller = LOCAL) -> dict:
    """What the last download gave (no network): {loaded_at, counts: {sheet: genes}, warning}."""
    with _ru_lock:
        at, data, warning = _ru_cache['at'], _ru_cache['data'], _ru_cache['warning']
    return {
        'loaded_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(at)) if at else None,
        # sheets are {column: {gene: text}}; count genes
        'counts': {
            name: len(set().union(*(col.keys() for col in table.values()))) if table else 0
            for name, table in (data or {}).items()
        },
        'warning': warning,
    }


def ru_refresh(params: dict, caller: Caller = LOCAL) -> dict:
    """Download the sheets again now (the desktop app's «Обновить»; it also warms the cache at start-up)."""
    with _ru_lock:
        _ru_cache['at'] = 0.0
    ru_annotations()
    return ru_status(params, caller)


# --- result file ---


def _is_cravat_db(path: str) -> bool:
    try:
        with sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True) as con:
            tables = {row[0] for row in con.execute("select name from sqlite_master where type='table'")}
    except sqlite3.Error:
        return False
    return {'variant', 'sample', 'info'} <= tables


def _is_plain_name(value: str) -> bool:
    """A single folder name — no path separators, not '.'/'..' (job ids and usernames come from the URL)."""
    return value not in ('', '.', '..') and '/' not in value and '\\' not in value


def _job_dirs(jobs_dir: str, job_id: str, username: str, hand_placed: bool = True) -> list:
    """Where a job may live: the GUI (2.2.9 and 3.x) imports/creates jobs in `<jobs>/<user>/<id>`,
    with the user `default` in single-user mode; `<jobs>/<id>` is kept for jobs placed by hand.
    The 3.x Jobs page opens the viewer with only `?job_id=`, so without a username every user
    folder is searched."""
    root = [os.path.join(jobs_dir, job_id)] if hand_placed else []
    if username:
        return [os.path.join(jobs_dir, username, job_id)] + root
    return root + sorted(glob.glob(os.path.join(glob.escape(jobs_dir), '*', job_id)))


def resolve_dbpath(dbpath: str = '', job_id: str = '', username: str = '', caller: Caller = LOCAL) -> str:
    """The viewer passes dbpath (oc gui file.sqlite) or only job_id (Jobs tab).

    Login mode: only job_id counts, looked up in the caller's own folder `<jobs>/<login>/<id>`
    (an admin: in the given user's folder, or in all of them) — like OpenCRAVAT's own job routing."""
    if caller.multiuser:
        if not job_id:
            raise ClientError(
                'Откройте результат со страницы заданий (Jobs) OpenCRAVAT: '
                'в режиме с входом файл по пути не открывается.'
            )
        dbpath = ''
        if not is_admin(caller):
            username = caller.name or ''
    if dbpath:
        candidates = [dbpath]
    elif job_id:
        if not _is_plain_name(job_id) or (username and not _is_plain_name(username)):
            raise ClientError('Некорректный идентификатор задания.')
        candidates = []
        for job_dir in _job_dirs(_admin_util().get_jobs_dir(), job_id, username, hand_placed=not caller.multiuser):
            candidates.extend(sorted(glob.glob(os.path.join(glob.escape(job_dir), '*.sqlite'))))
        if not candidates:
            raise ClientError(f'Задание {job_id} не найдено в папке заданий OpenCRAVAT.')
    else:
        raise ClientError('Не указан файл результата OpenCRAVAT (.sqlite).')
    for candidate in candidates:
        path = os.path.abspath(candidate)
        if os.path.isfile(path) and _is_cravat_db(path):
            return path
    raise ClientError(f'Не найден файл результата OpenCRAVAT: {candidates[0]}')


def _dbpath_from(params: dict, caller: Caller) -> str:
    return resolve_dbpath(params.get('dbpath') or '', params.get('job_id') or '', params.get('username') or '', caller)


def _sample_label(sample, dbpath: str) -> str:
    label = str(sample).split('.')[0]
    if not label or label == 'None':
        label = Path(dbpath).name.split('.')[0]
    return label


def open_result(params: dict, caller: Caller = LOCAL) -> dict:
    dbpath = _dbpath_from(params, caller)
    try:
        samples = ClinReport(dbpath).all_samples
    except (sqlite3.Error, IndexError) as e:
        raise ClientError(f'Не удалось прочитать образцы из {dbpath}: {e}') from e
    return {
        'dbpath': dbpath,
        'filename': os.path.basename(dbpath),
        'samples': [{'index': i, 'label': _sample_label(s, dbpath)} for i, s in enumerate(samples)],
        'settings': _public_settings(caller),
    }


def _report(clinreport: ClinReport, sample, kind: str, dbpath: str) -> dict:
    label = _sample_label(sample, dbpath)
    context = clinreport.build_context(sample, kind)
    # Single-sample results have no sample id: SampleProcessor then writes 'None'
    # as the sample number; use the file-name label instead.
    for section, key in (('patient', 'id'), ('patient', 'lab_number'), ('sample', 'id')):
        if context.get(section, {}).get(key) == 'None':
            context[section][key] = label
    return {
        'label': label,
        'kind': kind,
        'is_target': sample == clinreport.target_sample,
        'filename': f'Заключение LPWGS ({label}).docx' if kind == '10x' else f'Заключение ({label}).docx',
        'context': context,
    }


def process(params: dict, caller: Caller = LOCAL) -> dict:
    """Standard mode: a default report per sample. LPWGS: target -> default, others -> 10x."""
    dbpath = _dbpath_from(params, caller)
    mode = params.get('mode', 'default')
    if mode not in ('default', 'lpwgs'):
        raise ClientError(f'Неизвестный режим обработки: {mode}')
    annotations, warning = ru_annotations()
    clinician = load_user_settings(caller)['clinician']
    clinreport = ClinReport(dbpath, clinician=clinician, ru_annotations=annotations)
    try:
        target = clinreport.all_samples[int(params.get('target', 0))]
    except (ValueError, IndexError):
        raise ClientError('Неверный целевой образец.') from None
    clinreport.target_sample = target

    if mode == 'default':
        reports = [_report(clinreport, sample, 'default', dbpath) for sample in clinreport.all_samples]
    else:
        reports = [_report(clinreport, target, 'default', dbpath)]
        reports += [_report(clinreport, s, '10x', dbpath) for s in clinreport.all_samples if s != target]
    return {
        'mode': mode,
        'reports': reports,
        'layouts': layouts(caller),
        'warnings': [warning] if warning else [],
    }


def layouts(caller: Caller = LOCAL) -> dict:
    """labels.LAYOUTS with the current template choice per report kind ({id, title}), the user's preselected one,
    and no database features in the desktop edition."""
    result = copy.deepcopy(LAYOUTS)
    store = _store()
    preferred = load_user_settings(caller).get('template')
    for kind, layout in result.items():
        choices = [{'id': t['id'], 'title': t['title']} for t in store.for_kind(kind)]
        layout['templates'] = choices
        wanted = preferred if kind == 'default' else ''
        layout['template_default'] = wanted if wanted in [c['id'] for c in choices] else tpl.DEFAULT_FOR_KIND[kind]
        if edition() == 'desktop':
            layout['upload'] = layout['similar'] = False
    return result


# --- document ---


def _safe_filename(name: str, default: str) -> str:
    name = os.path.basename(str(name or '')).strip()
    for char in '<>:"/\\|?*':
        name = name.replace(char, '_')
    if not name:
        name = default
    return name if name.lower().endswith('.docx') else name + '.docx'


def render(params: dict, caller: Caller = LOCAL) -> FileResult:
    context = params.get('context')
    if not isinstance(context, dict):
        raise ClientError('Нет данных для формирования документа.')
    kind = '10x' if params.get('kind') == '10x' else 'default'
    template = params.get('template') or tpl.DEFAULT_FOR_KIND[kind]
    store = _store()
    item = _template_error(lambda: store.get(template))
    if item['kind'] != kind:
        raise ClientError(f'Шаблон «{item["title"]}» не подходит для этого документа.')
    buffer = io.BytesIO()
    render_context(context, str(store.path(template))).save(buffer)
    return FileResult(buffer.getvalue(), _safe_filename(params.get('filename'), 'report.docx'), DOCX_MIME)


# --- Postgres ---

_databases = {}


def _database() -> Database:
    settings = load_db_settings()
    if not Database.is_configured(settings):
        raise ClientError('База данных не подключена на сервере (CLINREPORT_DB_*): обратитесь к администратору.')
    key = tuple(settings[k] for k in Database.REQUIRED_KEYS)
    if key not in _databases:
        _databases[key] = Database(settings)
    return _databases[key]


def _run_db(action):
    try:
        return action()
    except ImportError as e:
        raise ClientError(f'Для работы с БД установите sqlalchemy и psycopg2-binary ({e}).') from e


def upload(params: dict, caller: Caller = LOCAL) -> dict:
    """Upload a default-report context. Returns {'duplicate': True} unless forced."""
    context = params.get('context')
    if not isinstance(context, dict) or 'patient' not in context:
        raise ClientError('Нет данных для выгрузки.')
    database = _database()
    sample = str(context['patient'].get('id', ''))
    if not params.get('force') and _run_db(lambda: database.sample_data_exists(sample)):
        return {'duplicate': True, 'sample': sample}
    # GLS columns next to the desktop ones: who pressed the button (the login) and which press it was, so office's
    # «Выгруженные варианты» can show and delete one upload (infra/postgres/init/20-clinreport.sh).
    stamp = {'uploaded_by': caller.name if caller.multiuser else '', 'upload_id': str(uuid.uuid4())}
    records = [dict(record, **stamp) for record in context_to_payload_records(context)]
    inserted = _run_db(lambda: database.insert(records))
    return {'inserted': inserted}


def similar(params: dict, caller: Caller = LOCAL) -> dict:
    variant = params.get('variant')
    if not isinstance(variant, dict):
        raise ClientError('Не указан вариант.')
    database = _database()
    rows = _run_db(lambda: database.get_similar_variants(variant))
    return {'rows': [{k: ('' if v is None else str(v)) for k, v in row.items()} for row in rows]}


# --- CLINBIO hand-off (genlab office) ---
#
# «Отправить в CLINBIO»: the conclusion is rendered here, as for «Сохранить как…», and posted to office
# (POST /api/clinbio/conclusions) with the logged-in clinician's name. office checks that the sample is
# assigned to that clinician and emails the conclusion to the lab. ClinReport authenticates as the Keycloak
# service account `clinreport-svc` (client credentials). Login mode only: in local mode nobody is identified.

CLINBIO_ENV = ('CLINBIO_API_URL', 'CLINBIO_TOKEN_URL', 'CLINBIO_CLIENT_ID', 'CLINBIO_CLIENT_SECRET')
_clinbio_token = {'value': None, 'expires': 0.0}
_clinbio_lock = threading.Lock()


def clinbio_configured(caller: Caller = LOCAL) -> bool:
    return caller.multiuser and all(os.environ.get(name) for name in CLINBIO_ENV)


def _service_token(refresh: bool = False) -> str:
    import requests

    with _clinbio_lock:
        if refresh or not _clinbio_token['value'] or _clinbio_token['expires'] < time.time():
            try:
                response = requests.post(
                    os.environ['CLINBIO_TOKEN_URL'],
                    timeout=15,
                    data={
                        'grant_type': 'client_credentials',
                        'client_id': os.environ['CLINBIO_CLIENT_ID'],
                        'client_secret': os.environ['CLINBIO_CLIENT_SECRET'],
                    },
                )
            except requests.RequestException as e:
                raise ClientError(f'Нет связи с Keycloak: {e}') from e
            if response.status_code != 200:
                raise ClientError(f'Keycloak не выдал токен для отправки в CLINBIO (HTTP {response.status_code}).')
            data = response.json()
            _clinbio_token['value'] = data['access_token']
            _clinbio_token['expires'] = time.time() + max(int(data.get('expires_in', 60)) - 30, 0)
        return _clinbio_token['value']


def send_clinbio(params: dict, caller: Caller = LOCAL) -> dict:
    """Render the report and hand it to CLINBIO. Returns {'sent': True, 'issue': ...}, or
    {'already_sent': True, 'message': ...} when a conclusion was sent before (resend with replace=True)."""
    import requests

    if not caller.multiuser:
        raise ClientError('Отправка в CLINBIO работает только при входе в OpenCRAVAT через Keycloak.')
    if not clinbio_configured(caller):
        raise ClientError('Отправка в CLINBIO не настроена на сервере (переменные CLINBIO_*).')
    if params.get('kind') == '10x':
        raise ClientError('В CLINBIO отправляется заключение, а не технический документ LPWGS.')
    sample = str(params.get('sample') or '').strip()
    if not sample:
        raise ClientError('Не указан образец.')
    document = render(params, caller)
    data = {'sample': sample, 'username': caller.name, 'replace': '1' if params.get('replace') else ''}

    def post(token):
        return requests.post(
            os.environ['CLINBIO_API_URL'],
            timeout=60,
            data=data,
            headers={'Authorization': f'Bearer {token}'},
            files={'file': (document.filename, document.data, DOCX_MIME)},
        )

    try:
        response = post(_service_token())
        if response.status_code == 401:  # the cached token was revoked or the keys rotated
            response = post(_service_token(refresh=True))
    except requests.RequestException as e:
        raise ClientError(f'Нет связи с office (CLINBIO): {e}') from e
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code == 409 and body.get('code') == 'already_sent':
        return {'already_sent': True, 'message': body.get('error', '')}
    if response.status_code != 201:
        raise ClientError(body.get('error') or f'CLINBIO не принял заключение (HTTP {response.status_code}).')
    return {'sent': True, 'sample': sample, 'issue': body.get('issue', ''), 'filename': document.filename}


# --- templates (built-in + the lab's own, clinreport_core/templates.py) ---


def _store() -> tpl.TemplateStore:
    return tpl.TemplateStore(conf_dir())


def _template_error(func):
    try:
        return func()
    except tpl.TemplateProblem as e:
        raise ClientError(str(e)) from None


def _require_template_admin(caller: Caller):
    """Templates are shared by everyone on a server: in login mode only OpenCRAVAT admins change them."""
    if not is_admin(caller):
        raise ClientError('Шаблоны меняет администратор OpenCRAVAT.')


def list_templates(params: dict, caller: Caller = LOCAL) -> dict:
    return {
        'templates': _store().list(),
        'kinds': tpl.KINDS,
        'editable': is_admin(caller),
        'default_template': load_user_settings(caller).get('template') or tpl.DEFAULT_FOR_KIND['default'],
        'max_bytes': tpl.MAX_TEMPLATE_BYTES,
    }


def add_template(params: dict, caller: Caller = LOCAL) -> dict:
    """Body: {title, kind, data (base64 .docx), replace?: id}."""
    _require_template_admin(caller)
    try:
        data = base64.b64decode(params.get('data') or '', validate=True)
    except ValueError:
        raise ClientError('Файл шаблона повреждён при передаче.') from None
    store = _store()
    item = _template_error(
        lambda: store.add(
            params.get('title', ''), params.get('kind', 'default'), data, replace=params.get('replace') or ''
        )
    )
    return {'template': item}


def delete_template(params: dict, caller: Caller = LOCAL) -> dict:
    """Users whose default was this template fall back to DZM (layouts() checks that the id still exists)."""
    _require_template_admin(caller)
    template_id = str(params.get('id') or '')
    store = _store()
    _template_error(lambda: store.delete(template_id))
    return {'deleted': template_id}


def check_template(params: dict, caller: Caller = LOCAL) -> dict:
    store = _store()
    return _template_error(lambda: store.recheck(str(params.get('id') or '')))


def template_file(params: dict, caller: Caller = LOCAL) -> FileResult:
    template_id = str(params.get('id') or '')
    store = _store()
    item = _template_error(lambda: store.get(template_id))
    return FileResult(store.path(template_id).read_bytes(), _safe_filename(item['title'], 'template.docx'), DOCX_MIME)


def template_fields(params: dict, caller: Caller = LOCAL) -> dict:
    return {kind: tpl.field_paths(kind) for kind in tpl.KINDS}
