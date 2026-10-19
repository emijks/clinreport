"""route.py served by Flask, the way OpenCRAVAT 3.x mounts it (gui/webapps.py: webapp_proxy_handler).

The GUI's before_request hook sets g.is_multiuser / g.username; here a test header stands in for the login."""

import pytest
from helpers import load_route_module

flask = pytest.importorskip('flask')


def make_app(multiuser):
    route = load_route_module()
    handlers = {}
    for method, path, func in route._flask_routes():
        handlers.setdefault(path, {})[method] = func

    app = flask.Flask(__name__)

    @app.before_request
    def login():
        flask.g.is_multiuser = multiuser
        flask.g.username = flask.request.headers.get('X-Test-User') if multiuser else 'default'

    @app.route('/webapps/clinreport/<action>', methods=['GET', 'POST'])
    def proxy(action):
        return handlers[action][flask.request.method](flask.request)

    return app.test_client()


def test_login_mode_requires_a_session(service):
    client = make_app(multiuser=True)
    response = client.get('/webapps/clinreport/settings')
    assert response.status_code == 401 and 'вход' in response.get_json()['error']

    response = client.get('/webapps/clinreport/settings', headers={'X-Test-User': 'alice'})
    assert response.status_code == 200 and response.get_json()['username'] == 'alice'


def test_settings_are_saved_for_the_logged_in_user(service):
    client = make_app(multiuser=True)
    response = client.post(
        '/webapps/clinreport/settings', json={'clinician': 'Алиса'}, headers={'X-Test-User': 'alice'}
    )
    assert response.status_code == 200
    assert client.get('/webapps/clinreport/settings', headers={'X-Test-User': 'bob'}).get_json()['clinician'] == ''

    # the database is the server's: DB keys from the page are ignored
    response = client.post('/webapps/clinreport/settings', json={'host': 'x'}, headers={'X-Test-User': 'alice'})
    assert response.status_code == 200 and 'host' not in response.get_json()


def test_post_must_be_json(service):
    client = make_app(multiuser=False)
    response = client.post('/webapps/clinreport/settings', data='{"clinician": "x"}', content_type='text/plain')
    assert response.status_code == 400
    response = client.post('/webapps/clinreport/settings', json={'clinician': 'x'})
    assert response.status_code == 200 and response.get_json()['clinician'] == 'x'


def test_local_mode_opens_by_path(service, trio_db):
    client = make_app(multiuser=False)
    response = client.get('/webapps/clinreport/open', query_string={'dbpath': trio_db})
    assert response.status_code == 200 and len(response.get_json()['samples']) == 3
