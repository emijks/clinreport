"""«Отправить в CLINBIO»: token from Keycloak, multipart POST to office, office's answers (HTTP mocked)."""

import pytest

ENV = {
    'CLINBIO_API_URL': 'http://office:8000/api/clinbio/conclusions',
    'CLINBIO_TOKEN_URL': 'http://keycloak:8080/realms/genes/protocol/openid-connect/token',
    'CLINBIO_CLIENT_ID': 'clinreport-svc',
    'CLINBIO_CLIENT_SECRET': 'secret',
}
PARAMS = {
    'context': {'patient': {'id': 'S1'}},
    'kind': 'default',
    'template': 'DZM',
    'filename': 'Заключение (S1).docx',
    'sample': 'S1',
}


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError('not JSON')
        return self._body


@pytest.fixture
def clinbio(service, monkeypatch):
    import requests

    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    service._clinbio_token.update(value=None, expires=0.0)
    monkeypatch.setattr(
        service, 'render', lambda params, caller: service.FileResult(b'PK docx', params['filename'], service.DOCX_MIME)
    )
    calls = []
    answers = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if url == ENV['CLINBIO_TOKEN_URL']:
            return Response(200, {'access_token': f'token{len(calls)}', 'expires_in': 300})
        return answers.pop(0)

    monkeypatch.setattr(requests, 'post', post)
    return service, calls, answers


def doctor(service):
    return service.Caller('alice', multiuser=True)


def test_enabled_only_in_login_mode_with_settings(clinbio, monkeypatch):
    service, _, _ = clinbio
    assert service.get_settings({}, doctor(service))['clinbio_enabled'] is True
    assert service.get_settings({}, service.LOCAL)['clinbio_enabled'] is False
    with pytest.raises(service.ClientError, match='Keycloak'):
        service.send_clinbio(PARAMS, service.LOCAL)
    monkeypatch.delenv('CLINBIO_CLIENT_SECRET')
    assert service.get_settings({}, doctor(service))['clinbio_enabled'] is False
    with pytest.raises(service.ClientError, match='не настроена'):
        service.send_clinbio(PARAMS, doctor(service))


def test_sends_the_rendered_conclusion_as_the_clinician(clinbio):
    service, calls, answers = clinbio
    answers.append(Response(201, {'conclusion': 1, 'sample': 'S1', 'issue': 'CLINBIO-7', 'status': 'received'}))
    result = service.send_clinbio(PARAMS, doctor(service))
    assert result == {'sent': True, 'sample': 'S1', 'issue': 'CLINBIO-7', 'filename': 'Заключение (S1).docx'}
    (token_url, token_call), (api_url, api_call) = calls
    assert token_call['data'] == {
        'grant_type': 'client_credentials',
        'client_id': 'clinreport-svc',
        'client_secret': 'secret',
    }
    assert api_url == ENV['CLINBIO_API_URL']
    assert api_call['headers'] == {'Authorization': 'Bearer token1'}
    assert api_call['data'] == {'sample': 'S1', 'username': 'alice', 'replace': ''}
    assert api_call['files']['file'][:2] == ('Заключение (S1).docx', b'PK docx')

    answers.append(Response(201, {'issue': 'CLINBIO-7'}))
    service.send_clinbio(dict(PARAMS, replace=True), doctor(service))
    assert len(calls) == 3  # the token is cached
    assert calls[-1][1]['data']['replace'] == '1'


def test_already_sent_asks_the_user(clinbio):
    service, _, answers = clinbio
    answers.append(Response(409, {'error': 'Заключение по образцу S1 уже отправлено …', 'code': 'already_sent'}))
    assert service.send_clinbio(PARAMS, doctor(service)) == {
        'already_sent': True,
        'message': 'Заключение по образцу S1 уже отправлено …',
    }


@pytest.mark.parametrize(
    'status, body, message',
    [
        (403, {'error': 'Образец S1 назначен другому врачу (Петров О.).'}, 'другому врачу'),
        (409, {'error': 'Задача ещё не создана', 'code': 'not_ready'}, 'не создана'),
        (502, None, 'HTTP 502'),
    ],
)
def test_office_refusals_are_shown(clinbio, status, body, message):
    service, _, answers = clinbio
    answers.append(Response(status, body))
    with pytest.raises(service.ClientError, match=message):
        service.send_clinbio(PARAMS, doctor(service))


def test_token_is_renewed_once_on_401(clinbio):
    service, calls, answers = clinbio
    answers.extend([Response(401, {'error': 'invalid token'}), Response(201, {'issue': 'CLINBIO-1'})])
    assert service.send_clinbio(PARAMS, doctor(service))['sent'] is True
    assert [url for url, _ in calls] == [
        ENV['CLINBIO_TOKEN_URL'],
        ENV['CLINBIO_API_URL'],
        ENV['CLINBIO_TOKEN_URL'],
        ENV['CLINBIO_API_URL'],
    ]


def test_10x_and_missing_sample_are_refused(clinbio):
    service, _, _ = clinbio
    with pytest.raises(service.ClientError, match='LPWGS'):
        service.send_clinbio(dict(PARAMS, kind='10x'), doctor(service))
    with pytest.raises(service.ClientError, match='образец'):
        service.send_clinbio(dict(PARAMS, sample=''), doctor(service))
