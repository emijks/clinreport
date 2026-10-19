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
"""

import inspect
import json
import os
import sys
import traceback
from urllib.parse import quote

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

from clinreport_core import service  # noqa: E402

HANDLERS = (
    ('GET', 'open', service.open_result),
    ('POST', 'process', service.process),
    ('POST', 'render', service.render),
    ('POST', 'upload', service.upload),
    ('POST', 'similar', service.similar),
    ('POST', 'send_clinbio', service.send_clinbio),
    ('GET', 'settings', service.get_settings),
    ('POST', 'settings', service.update_settings),
    ('GET', 'ru_status', service.ru_status),
    ('POST', 'ru_refresh', service.ru_refresh),
    ('GET', 'templates', service.list_templates),
    ('POST', 'template_add', service.add_template),
    ('POST', 'template_delete', service.delete_template),
    ('POST', 'template_check', service.check_template),
    ('GET', 'template_file', service.template_file),
    ('GET', 'template_fields', service.template_fields),
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

    return [(method, path, wrap(func, method)) for method, path, func in HANDLERS]


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

    return [(method, path, wrap(func, method)) for method, path, func in HANDLERS]


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


routes = _flask_routes() if _loaded_by_flask_gui() else _aiohttp_routes()
