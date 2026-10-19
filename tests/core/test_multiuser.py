"""Settings scopes and job access with and without OpenCRAVAT's login mode (oc gui --multiuser)."""

import json
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def users(service):
    return {name: service.Caller(name, multiuser=True) for name in ('admin', 'alice', 'bob')}


def put_job(service, db, user, job_id):
    job_dir = Path(service._admin_util().get_jobs_dir()) / user / job_id
    job_dir.mkdir(parents=True)
    shutil.copy(db, job_dir / 'result.sqlite')
    return str(job_dir / 'result.sqlite')


# --- settings ---


def test_local_settings_keep_the_old_file(service):
    saved = service.update_settings({'clinician': 'Иванова', 'template': 'FND'})
    assert saved['template'] == 'FND' and saved['multiuser'] is False
    stored = json.loads(Path(service.settings_path()).read_text(encoding='utf-8'))
    assert stored['clinician'] == 'Иванова'


def test_unknown_template_is_rejected(service):
    with pytest.raises(service.ClientError, match='шаблон'):
        service.update_settings({'template': '../x'})


def test_user_settings_are_per_login(service, users):
    service.update_settings({'clinician': 'Алиса', 'auto_upload': True}, users['alice'])
    service.update_settings({'clinician': 'Боб', 'template': 'FND'}, users['bob'])
    alice, bob = service.get_settings({}, users['alice']), service.get_settings({}, users['bob'])
    assert (alice['clinician'], alice['template'], alice['auto_upload']) == ('Алиса', 'DZM', True)
    assert (bob['clinician'], bob['template'], bob['auto_upload']) == ('Боб', 'FND', False)
    assert alice['username'] == 'alice' and alice['multiuser'] is True
    # the global/local file is not touched by users' own settings
    assert not Path(service.settings_path()).exists()


def test_local_clinician_is_not_inherited_in_login_mode(service, users):
    service.update_settings({'clinician': 'Локальный'})
    assert service.get_settings({}, users['alice'])['clinician'] == ''


DB_ENV = {'HOST': 'env-host', 'PORT': '5432', 'NAME': 'r', 'USER': 'u', 'PASS': 'secret'}
DB_FIELDS = {'host', 'port', 'name', 'user', 'pass', 'pass_set', 'db_editable', 'db_from_env'}


def test_database_comes_only_from_the_environment(service, users, monkeypatch):
    # neither the page nor an old clinreport.json can set it
    service._write_json(service.settings_path(), {'host': 'file-host', 'pass': 'x'})
    for caller in (service.LOCAL, users['admin'], users['alice']):
        saved = service.update_settings({'host': 'evil', 'port': '1', 'name': 'n', 'user': 'u', 'pass': 'p'}, caller)
        assert saved['db_configured'] is False
    assert service.load_db_settings()['host'] == ''

    monkeypatch.setenv(service.DB_ENV_PREFIX + 'HOST', '')  # empty = not set
    assert service.get_settings({}, users['admin'])['db_configured'] is False
    for key, value in DB_ENV.items():
        monkeypatch.setenv(service.DB_ENV_PREFIX + key, value)
    assert service.load_db_settings()['host'] == 'env-host'


def test_nobody_sees_the_connection(service, users, monkeypatch):
    for key, value in DB_ENV.items():
        monkeypatch.setenv(service.DB_ENV_PREFIX + key, value)
    for caller in (service.LOCAL, users['admin'], users['alice']):
        settings = service.get_settings({}, caller)
        assert settings['db_configured'] is True and not DB_FIELDS & set(settings)
        assert 'secret' not in json.dumps(settings) and 'env-host' not in json.dumps(settings)


def test_process_signs_with_the_callers_clinician(service, users, single_db):
    put_job(service, single_db, 'alice', 'j1')
    service.update_settings({'clinician': 'Алиса'}, users['alice'])
    context = service.process({'job_id': 'j1'}, users['alice'])['reports'][0]['context']
    assert context['clinician'] == 'Алиса'


# --- access ---


def test_not_logged_in_is_unauthorized(service):
    with pytest.raises(service.Unauthorized):
        service.authorize(service.Caller(None, multiuser=True))
    service.authorize(service.LOCAL)
    service.authorize(service.Caller('alice', multiuser=True))


def test_login_mode_ignores_paths(service, users, single_db):
    with pytest.raises(service.ClientError, match='Jobs'):
        service.open_result({'dbpath': single_db}, users['admin'])


def test_users_open_only_their_own_jobs(service, users, trio_db, single_db):
    alice_db = put_job(service, trio_db, 'alice', 'j-alice')
    bob_db = put_job(service, single_db, 'bob', 'j-bob')

    assert service.open_result({'job_id': 'j-alice'}, users['alice'])['dbpath'] == alice_db
    with pytest.raises(service.ClientError, match='не найдено'):
        service.open_result({'job_id': 'j-bob'}, users['alice'])
    # a username in the query does not open someone else's folder
    with pytest.raises(service.ClientError, match='не найдено'):
        service.open_result({'job_id': 'j-bob', 'username': 'bob'}, users['alice'])

    # admin sees every user's jobs, like OpenCRAVAT's own job routing
    assert service.open_result({'job_id': 'j-bob'}, users['admin'])['dbpath'] == bob_db
    assert service.open_result({'job_id': 'j-alice', 'username': 'alice'}, users['admin'])['dbpath'] == alice_db


def test_hand_placed_jobs_are_not_shared_in_login_mode(service, users, single_db):
    job_dir = Path(service._admin_util().get_jobs_dir()) / 'loose'
    job_dir.mkdir(parents=True)
    shutil.copy(single_db, job_dir / 'r.sqlite')
    with pytest.raises(service.ClientError):
        service.open_result({'job_id': 'loose'}, users['alice'])
    assert service.open_result({'job_id': 'loose'})['dbpath'] == str(job_dir / 'r.sqlite')  # local mode: as before
