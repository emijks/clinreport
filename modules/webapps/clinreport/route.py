"""HTTP routes of the ClinReport webapp.

OpenCRAVAT imports this file when the GUI starts and mounts every entry of
`routes` at /webapps/clinreport/<path>. The aiohttp GUI (OpenCRAVAT 2.x, and
`oc gui --aiohttp` in 3.x) serves them as async handlers; the Flask GUI (3.x
default) calls them synchronously with the Flask request and supports only
single-segment paths. The handlers in clinreport_core.service know neither,
so they are wrapped here for whichever GUI loaded the module.

Both wrappers also tell the handlers who is calling: without login mode
everyone is the local user; with `oc gui --multiuser` the OpenCRAVAT login is
read from the GUI's session and requests without one get 401.

OpenCRAVAT imports every webapp's route.py while the GUI starts, without catching
errors: one that fails to import stops the whole GUI. If clinreport_core cannot be
imported here (typically docxtpl missing from OpenCRAVAT's Python), every route
answers 503 with what to install instead.
"""

from __future__ import annotations  # the annotations name service.*, which may be missing

import inspect
import json
import os
import sys
import traceback
from urllib.parse import quote

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)
# Packages the desktop app installed for this module when OpenCRAVAT's Python lacked them (docxtpl…). Appended, so
# whatever OpenCRAVAT's own environment has always wins; lib/ only fills the gaps.
LIB_DIR = os.path.join(MODULE_DIR, 'lib')
if os.path.isdir(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)

try:
    from clinreport_core import service
except Exception as exc:  # noqa: BLE001 - any import failure must leave OpenCRAVAT running
    traceback.print_exc()
    service = None
    missing = getattr(exc, 'name', None) if isinstance(exc, ImportError) else None
    UNAVAILABLE = (
        f'ClinReport не может работать в этом OpenCRAVAT: не установлен пакет «{missing}». '
        f'Установите его в Python, на котором работает OpenCRAVAT (pip install {missing}), и перезапустите OpenCRAVAT.'
        if missing
        else f'ClinReport не может работать в этом OpenCRAVAT: {exc!r}. Перезапустите OpenCRAVAT после исправления.'
    )

# (method, path, name of the clinreport_core.service function)
HANDLERS = (
    ('GET', 'open', 'open_result'),
    ('POST', 'process', 'process'),
    ('POST', 'render', 'render'),
    ('POST', 'upload', 'upload'),
    ('POST', 'similar', 'similar'),
    ('POST', 'send_clinbio', 'send_clinbio'),
    ('GET', 'settings', 'get_settings'),
    ('POST', 'settings', 'update_settings'),
    ('GET', 'ru_status', 'ru_status'),
    ('POST', 'ru_refresh', 'ru_refresh'),
    ('GET', 'templates', 'list_templates'),
    ('POST', 'template_add', 'add_template'),
    ('POST', 'template_delete', 'delete_template'),
    ('POST', 'template_check', 'check_template'),
    ('GET', 'template_file', 'template_file'),
    ('GET', 'template_fields', 'template_fields'),
)

# Template uploads arrive base64-encoded in JSON; aiohttp's default body limit is 1 MB.
MAX_BODY_BYTES = 20 * 1024 * 1024


def _dumps(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _error(exc: Exception):
    """(status, payload) for a failed handler."""
    if isinstance(exc, service.Unauthorized):
        return 401, {'error': str(exc)}
    if isinstance(exc, service.ClientError):
        return 400, {'error': str(exc)}
    return 500, {'error': f'Внутренняя ошибка: {exc!r}', 'traceback': traceback.format_exc()}


def _content_disposition(filename: str) -> str:
    return f"attachment; filename=\"report.docx\"; filename*=UTF-8''{quote(filename)}"


NOT_JSON = 'Некорректный запрос (ожидается JSON).'


async def _aiohttp_caller(request) -> service.Caller:
    """cravat_web.servermode is set by `oc gui --multiuser` (2.x, and 3.x with --aiohttp)
    when the open-cravat-multiuser package is installed."""
    cravat_web = sys.modules.get('cravat.cravat_web')
    if not getattr(cravat_web, 'servermode', False):
        return service.LOCAL
    import cravat_multiuser

    return service.Caller(await cravat_multiuser.get_username(request), multiuser=True)


def _aiohttp_routes():
    import asyncio

    from aiohttp import web

    def wrap(func, method):
        async def handler(request):
            try:
                caller = await _aiohttp_caller(request)
                service.authorize(caller)
                if method == 'GET':
                    params = dict(request.query)
                else:
                    # JSON only: a cross-site form cannot send it without a CORS preflight.
                    if request.content_type != 'application/json':
                        raise service.ClientError(NOT_JSON)
                    # The GUI's aiohttp app keeps the 1 MB default; raise it for this request only.
                    if getattr(request, '_client_max_size', MAX_BODY_BYTES) < MAX_BODY_BYTES:
                        request._client_max_size = MAX_BODY_BYTES
                    try:
                        params = await request.json()
                    except ValueError:
                        raise service.ClientError(NOT_JSON) from None
                result = await asyncio.get_running_loop().run_in_executor(None, func, params, caller)
            except Exception as exc:
                status, payload = _error(exc)
                return web.Response(text=_dumps(payload), status=status, content_type='application/json')
            if isinstance(result, service.FileResult):
                return web.Response(
                    body=result.data,
                    content_type=result.content_type,
                    headers={'Content-Disposition': _content_disposition(result.filename)},
                )
            return web.Response(text=_dumps(result), content_type='application/json')

        return handler

    return [(method, path, wrap(getattr(service, name), method)) for method, path, name in HANDLERS]


def _flask_caller() -> service.Caller:
    """OpenCRAVAT 3.x sets g.is_multiuser and g.username (None = not logged in) before every request."""
    from flask import g

    if not getattr(g, 'is_multiuser', False):
        return service.LOCAL
    return service.Caller(getattr(g, 'username', None), multiuser=True)


def _flask_routes():
    from flask import Response

    def wrap(func, method):
        def handler(request):
            try:
                caller = _flask_caller()
                service.authorize(caller)
                if method == 'GET':
                    params = request.args.to_dict()
                else:
                    # JSON only: a cross-site form cannot send it without a CORS preflight.
                    params = request.get_json(silent=True) if request.is_json else None
                    if params is None:
                        raise service.ClientError(NOT_JSON)
                result = func(params, caller)
            except Exception as exc:
                status, payload = _error(exc)
                return Response(_dumps(payload), status=status, mimetype='application/json')
            if isinstance(result, service.FileResult):
                return Response(
                    result.data,
                    mimetype=result.content_type,
                    headers={'Content-Disposition': _content_disposition(result.filename)},
                )
            return Response(_dumps(result), mimetype='application/json')

        return handler

    return [(method, path, wrap(getattr(service, name), method)) for method, path, name in HANDLERS]


def _unavailable_routes(flask: bool):
    """Every route answers 503 with UNAVAILABLE; the review page shows the message."""
    body = _dumps({'error': UNAVAILABLE})
    if flask:
        from flask import Response

        def handler(request):
            return Response(body, status=503, mimetype='application/json')
    else:
        from aiohttp import web

        async def handler(request):
            return web.Response(text=body, status=503, content_type='application/json')

    return [(method, path, handler) for method, path, _name in HANDLERS]


def _loaded_by_flask_gui() -> bool:
    """Which GUI server is importing this file?

    OpenCRAVAT 3.x serves the Flask app (cravat/gui/webapps.py: webapp_proxy_handler) by default,
    but `oc gui --aiohttp` in 3.x — like every 2.x GUI — imports us from
    cravat_web.setup_webapp_routes. The installed version alone therefore cannot decide.
    """
    for frame in inspect.stack(context=0):
        if frame.function == 'webapp_proxy_handler':
            return True
        if frame.function == 'setup_webapp_routes':
            return False
    return False  # imported directly (tests): aiohttp


if service is None:
    routes = _unavailable_routes(_loaded_by_flask_gui())
else:
    routes = _flask_routes() if _loaded_by_flask_gui() else _aiohttp_routes()
