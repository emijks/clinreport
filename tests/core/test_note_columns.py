"""The Note column: base__note (results of OpenCRAVAT <= 2.3.0) and base__note_variant (>= 2.3.1, where wgnote 3.0.0
writes the clinician's marks). Issue clinreport/019: reading only base__note gave reports without variants."""

import shutil
import sqlite3

from clinreport_core.database import VariantSource


def _result(path, columns, rows):
    with sqlite3.connect(path) as con:
        con.execute(f'create table variant ({", ".join(f"{c} text" for c in columns)})')
        con.executemany(f'insert into variant values ({", ".join("?" * len(columns))})', rows)
    return str(path)


def _marks(path):
    return {v['base__uid']: v['base__note'] for v in VariantSource(path).get_variants()}


def test_result_of_opencravat_2_3_1_and_newer_has_only_base__note_variant(tmp_path):
    path = _result(tmp_path / 'r.sqlite', ['base__uid', 'vep_csq__symbol', 'base__note_variant'],
                   [('1', 'PAH', '1'), ('2', 'PAH', None), ('3', 'PAH', ' 3 '), ('4', 'PAH', '')])  # fmt: skip
    assert _marks(path) == {'1': '1', '3': '3'}


def test_result_of_opencravat_2_3_0_and_older_has_only_base__note(tmp_path):
    path = _result(
        tmp_path / 'r.sqlite', ['base__uid', 'vep_csq__symbol', 'base__note'], [('1', 'PAH', '2'), ('2', 'PAH', None)]
    )
    assert _marks(path) == {'1': '2'}


def test_upgraded_result_prefers_base__note_variant_and_falls_back_to_base__note(tmp_path):
    path = _result(tmp_path / 'r.sqlite', ['base__uid', 'vep_csq__symbol', 'base__note', 'base__note_variant'],
                   [('1', 'PAH', '1', '2'), ('2', 'PAH', '3', ''), ('3', 'PAH', '7', None), ('4', 'PAH', None, None)])  # fmt: skip
    assert _marks(path) == {'1': '2', '2': '3', '3': '7'}


def test_result_without_a_note_column_has_no_marked_variants(tmp_path):
    assert (
        VariantSource(_result(tmp_path / 'r.sqlite', ['base__uid', 'vep_csq__symbol'], [('1', 'PAH')])).get_variants()
        == []
    )


def test_marks_in_base__note_variant_give_the_same_report(service, single_db, tmp_path):
    """The example result (OpenCRAVAT 2.2.9) with its marks moved to the column wgnote 3.0.0 writes."""
    moved = tmp_path / 'moved.sqlite'
    shutil.copyfile(single_db, moved)
    with sqlite3.connect(moved) as con:
        con.execute('alter table variant add column base__note_variant text')
        con.execute('update variant set base__note_variant = base__note, base__note = null')

    def variants(dbpath):
        context = service.process({'dbpath': str(dbpath)})['reports'][0]['context']
        return {key: context[key] for key in ('p_variants', 'lp_variants', 'vus_variants')}

    expected = variants(single_db)
    assert sum(map(len, expected.values())) == 3  # P + LP + VUS
    assert variants(moved) == expected
