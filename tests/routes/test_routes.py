"""route.py served by aiohttp, the way OpenCRAVAT 2.x mounts it."""

import asyncio

import pytest
from helpers import load_route_module

aiohttp = pytest.importorskip('aiohttp')
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


def run(coro):
    return asyncio.run(coro)


async def with_client(check):
    route = load_route_module()
    app = web.Application()
    for method, path, handler in route.routes:  # same as cravat_web.setup_webapp_routes
        app.router.add_route(method, '/webapps/clinreport/' + path, handler)
    async with TestClient(TestServer(app)) as client:
        await check(client)


def test_open_process_render_over_http(service, trio_db):
    async def check(client):
        response = await client.get('/webapps/clinreport/open', params={'dbpath': trio_db})
        assert response.status == 200
        assert len((await response.json())['samples']) == 3

        response = await client.post(
            '/webapps/clinreport/process', json={'dbpath': trio_db, 'target': 0, 'mode': 'default'}
        )
        report = (await response.json())['reports'][0]

        response = await client.post(
            '/webapps/clinreport/render',
            json={'context': report['context'], 'kind': 'default', 'template': 'FND', 'filename': report['filename']},
        )
        assert response.status == 200
        assert response.headers['Content-Type'].startswith(
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        assert "filename*=UTF-8''%D0%97%D0%B0%D0%BA" in response.headers['Content-Disposition']
        assert (await response.read())[:2] == b'PK'

    run(with_client(check))


def test_errors_are_json(service, tmp_path):
    async def check(client):
        response = await client.get('/webapps/clinreport/open', params={'dbpath': str(tmp_path / 'x.sqlite')})
        assert response.status == 400
        assert 'Не найден' in (await response.json())['error']

        response = await client.post(
            '/webapps/clinreport/render', data='not json', headers={'Content-Type': 'application/json'}
        )
        assert response.status == 400

    run(with_client(check))


def test_post_must_be_json(service):
    async def check(client):
        response = await client.post(
            '/webapps/clinreport/settings', data='{"clinician": "x"}', headers={'Content-Type': 'text/plain'}
        )
        assert response.status == 400

    run(with_client(check))


def test_login_mode_uses_the_multiuser_session(service, monkeypatch):
    # 2.x / `oc gui --aiohttp --multiuser`: cravat_web.servermode + cravat_multiuser.get_username(request)
    import sys
    import types

    async def get_username(request):
        return request.headers.get('X-Test-User')

    monkeypatch.setitem(sys.modules, 'cravat.cravat_web', types.SimpleNamespace(servermode=True))
    monkeypatch.setitem(sys.modules, 'cravat_multiuser', types.SimpleNamespace(get_username=get_username))

    async def check(client):
        response = await client.get('/webapps/clinreport/settings')
        assert response.status == 401
        response = await client.get('/webapps/clinreport/settings', headers={'X-Test-User': 'alice'})
        assert response.status == 200 and (await response.json())['username'] == 'alice'

    run(with_client(check))
