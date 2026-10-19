"""Postgres code paths, exercised against SQLite through SQLAlchemy."""

from collections import Counter

import pytest

sqlalchemy = pytest.importorskip('sqlalchemy')

from clinreport_core.database import Database, _read_sheet  # noqa: E402
from clinreport_core.labels import FIELD_LABELS  # noqa: E402

COLUMNS = (
    [
        'Номер образца',
        'Пол пациента',
        'Возраст пациента',
        'Предварительный диагноз',
        'Клиницист',
        'Дата заключения',
    ]
    + list(FIELD_LABELS.values())
    + ['uploaded_by', 'upload_id']
)


@pytest.fixture
def sqlite_database(tmp_path):
    database = Database({}, url=f'sqlite:///{tmp_path / "reported.db"}')
    columns = ', '.join(f'"{c}" text' for c in COLUMNS)
    with database.engine.begin() as conn:
        conn.execute(sqlalchemy.text(f'create table "ReportedVariants" ({columns})'))
    return database


@pytest.fixture
def db_service(service, sqlite_database, monkeypatch):
    monkeypatch.setattr(service, '_database', lambda: sqlite_database)
    return service


def test_upload_detects_duplicates_and_similar_finds_rows(db_service, sqlite_database, single_db):
    context = db_service.process({'dbpath': single_db})['reports'][0]['context']

    first = db_service.upload({'context': context})
    assert first == {'inserted': 3}  # P + LP + VUS
    assert db_service.upload({'context': context}) == {'duplicate': True, 'sample': 'pah2'}
    assert db_service.upload({'context': context, 'force': True}) == {'inserted': 3}

    with sqlite_database.engine.connect() as conn:
        uploads = conn.execute(sqlalchemy.text('select distinct uploaded_by, upload_id from "ReportedVariants"')).all()
    assert len(uploads) == 2 and {by for by, _ in uploads} == {''}  # one id per press; local mode: no login

    rows = db_service.similar({'variant': context['p_variants'][0]})['rows']
    assert len(rows) == 2
    assert rows[0]['Номер образца'] == 'pah2'
    assert rows[0]['Патогенность'] == 'Патогенный'


def test_similar_is_parameterised(sqlite_database):
    # a quote in the variation must not break (or inject into) the query
    assert sqlite_database.get_similar_variants({'variation': "x' or '1'='1"}) == []


def test_read_sheet_matches_pandas_to_dict(tmp_path):
    sheet = tmp_path / 'sheet.csv'
    sheet.write_text('Ген,Ассоциированное заболевание,Прочее\nPAH,Фенилкетонурия,\nBRCA1,,x\n', encoding='utf-8')
    table = _read_sheet(sheet.as_uri(), timeout=5)
    assert table == {
        'Ассоциированное заболевание': {'PAH': 'Фенилкетонурия'},
        'Прочее': {'BRCA1': 'x'},
    }


def test_each_upload_is_stamped_with_login_and_id(db_service, sqlite_database):
    row = dict.fromkeys(('gene', 'disease', 'variation', 'zygosity', 'frequency', 'coverage'), 'x')
    context = {'patient': {'id': 's1', 'sex': '', 'age': '', 'diagnosis': ''}, 'clinician': 'Врач',
               'p_variants': [row, row], 'vus_variants': [row]}  # fmt: skip
    alice = db_service.Caller('alice', multiuser=True)
    assert db_service.upload({'context': context}, alice) == {'inserted': 3}
    assert db_service.upload({'context': context, 'force': True}, alice) == {'inserted': 3}
    with sqlite_database.engine.connect() as conn:
        rows = conn.execute(sqlalchemy.text('select uploaded_by, upload_id from "ReportedVariants"')).all()
    assert {by for by, _ in rows} == {'alice'}
    assert sorted(Counter(upload for _, upload in rows).values()) == [3, 3]  # one id per press of the button
