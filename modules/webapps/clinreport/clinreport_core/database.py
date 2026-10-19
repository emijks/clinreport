"""Data sources: the OpenCRAVAT SQLite, the Russian annotation sheet and Postgres.

Ported from clinreport/database.py without pandas (it only served the sheet
download and Postgres I/O), so the module installs into any OpenCRAVAT Python.
VariantSource is unchanged.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import urllib.request
from urllib.parse import quote

RU_ANNOTATIONS_URL = 'https://docs.google.com/spreadsheets/d/1Zj_Gw-TolcoKljqfk4eCrQ1hyhlZDs44UOZbFTVTfes'
RU_ANNOTATIONS_SHEETS = {'omim': '0', 'secondary': '706494431'}


def _read_sheet(url: str, timeout: int) -> dict:
    """CSV -> {column: {first-column value: cell}}, like pandas read_csv(index_col=0).to_dict().

    Empty cells are skipped, so a lookup falls back to the OpenCRAVAT value
    instead of returning an empty string.
    """
    with urllib.request.urlopen(url, timeout=timeout) as response:
        text = response.read().decode('utf-8')
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = rows[0]
    table = {column: {} for column in header[1:]}
    for row in rows[1:]:
        if not row:
            continue
        for column, value in zip(header[1:], row[1:]):
            if value != '':
                table[column][row[0]] = value
    return table


def get_ru_annotations(timeout: int = 10) -> dict:
    return {
        name: _read_sheet(f'{RU_ANNOTATIONS_URL}/export?format=csv&gid={gid}', timeout)
        for name, gid in RU_ANNOTATIONS_SHEETS.items()
    }


class Database:
    """Postgres "ReportedVariants" table (sqlalchemy + psycopg2 are optional deps)."""

    TABLE = 'ReportedVariants'
    REQUIRED_KEYS = ('user', 'pass', 'host', 'port', 'name')

    def __init__(self, db_creds: dict, url: str | None = None):
        self.db_creds = db_creds
        self.url = url or (
            f'postgresql+psycopg2://'
            f'{db_creds["user"]}:{quote(db_creds["pass"])}@{db_creds["host"]}:{db_creds["port"]}/{db_creds["name"]}'
        )
        self._engine = None

    @classmethod
    def is_configured(cls, creds: dict) -> bool:
        return all(creds.get(key) for key in cls.REQUIRED_KEYS)

    @property
    def engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine

            self._engine = create_engine(self.url)
        return self._engine

    def insert(self, records: list) -> int:
        if not records:
            return 0
        from sqlalchemy import text

        columns = list(records[0])
        column_sql = ', '.join(f'"{column}"' for column in columns)
        values_sql = ', '.join(f':p{i}' for i in range(len(columns)))
        params = [{f'p{i}': record.get(column) for i, column in enumerate(columns)} for record in records]
        with self.engine.begin() as conn:
            conn.execute(text(f'insert into "{self.TABLE}" ({column_sql}) values ({values_sql})'), params)
        return len(records)

    def sample_data_exists(self, sample) -> bool:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(
                text(f'select 1 from "{self.TABLE}" where "Номер образца" = :sample limit 1'),
                {'sample': str(sample)},
            ).first()
        return row is not None

    def get_similar_variants(self, variant_data: dict) -> list:
        """Earlier reported variants with the same DNA change (variant_data is a context row)."""
        from sqlalchemy import text

        dna_change = str(variant_data.get('variation', '')).split('\n')[0]
        query = text(
            f'select "Номер образца", "Патогенность", "Клиницист", "Дата заключения" '
            f'from "{self.TABLE}" where "Изменение ДНК (HG38) (Изменение белка)" like :pattern'
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query, {'pattern': f'%{dna_change}%'}).mappings().all()
        return [dict(row) for row in rows]


class VariantSource:
    inheritance_map = {
        'Autosomal dominant': 'AD',
        'X-linked dominant': 'XD',
        'Autosomal recessive': 'AR',
        'X-linked recessive': 'XR',
    }

    def __init__(self, sqlite_path: str):
        self.sqlite_path = sqlite_path

    def get_all_samples(self) -> list:
        with sqlite3.connect(self.sqlite_path) as con:
            cur = con.cursor()
            return [row[0] for row in cur.execute('select distinct base__sample_id from sample;').fetchall()]

    def get_variants(self) -> list:
        """Fetch annotated variants; bridge legacy schema to the new column names."""
        with sqlite3.connect(self.sqlite_path) as con:
            cur = con.cursor()
            variant_cols = [col[1] for col in cur.execute('pragma table_info(variant);').fetchall()]
            if 'vep_csq__symbol' not in variant_cols:
                # legacy SQLite
                rows = cur.execute('select * from variant where base__note in (1,2,3,4,5,6,7,8);').fetchall()
                variants = [dict(zip(variant_cols, row)) for row in rows]
                for variant in variants:
                    variant.update(self._annotate_legacy(variant))
            else:
                # new SQLite
                rows = cur.execute('select * from variant where base__note is not null;').fetchall()
                variants = [dict(zip(variant_cols, row)) for row in rows]
        return variants

    def _annotate_legacy(self, variant_data: dict) -> dict:
        extra_vcf_info = self._extra_vcf_info(variant_data)
        for i in range(extra_vcf_info['nblocks']):
            if not extra_vcf_info['CSQ_PICK'][i] == '1':
                continue
            annotation = {
                'vep_csq__symbol': extra_vcf_info['CSQ_SYMBOL'][i],
                'vep_csq__transcript': extra_vcf_info['CSQ_Feature'][i],
                'vep_csq__hgvsc': extra_vcf_info['CSQ_HGVSc'][i].split(':')[-1],
                'vep_csq__hgvsp': extra_vcf_info['CSQ_HGVSp'][i].split(':')[-1],
                'vep_csq__hgvsg': extra_vcf_info['CSQ_HGVSg'][i],
                'vep_csq__consequence': extra_vcf_info['CSQ_Consequence'][i],
                'vep_csq__biotype': extra_vcf_info['CSQ_BIOTYPE'][i],
                'vep_csq__exon': extra_vcf_info['CSQ_EXON'][i],
                'vep_csq__intron': extra_vcf_info['CSQ_INTRON'][i],
                'vep_csq__strand': extra_vcf_info['CSQ_STRAND'][i],
                'vep_csq__codons': extra_vcf_info['CSQ_Codons'][i],
            }
            annotation['vep_csq__refseq'] = (
                extra_vcf_info['CSQ_MANE_SELECT'][i] if extra_vcf_info['CSQ_MANE_SELECT'][i] else None
            )
        annotation['vep_omim_pheno__inher'] = self._inher_from_omim_pheno(variant_data['vep_omim_pheno__pheno'])
        for col in ['filter', 'zygosity', 'ad', 'dp']:
            annotation[f'tagsampler_new__{col}'] = variant_data[f'vevatacmg_postaggregator__{col}']
        annotation['tagsampler_new__samples'] = variant_data['vevatacmg_postaggregator__sample']
        for col in ['id', 'sig']:
            annotation[f'clinvar_new__{col}'] = variant_data[f'clinvar__{col}']
        annotation['clinvar_new__sig_subs'] = annotation['clinvar_new__equivalents'] = annotation[
            'clinvar_new__alternatives'
        ] = None
        return annotation

    def _extra_vcf_info(self, variant_data: dict) -> dict:
        """Make each CSQ block iterable."""
        nblocks = len(variant_data['extra_vcf_info__CSQ_Allele'].split(';'))
        transformed = {'nblocks': nblocks}
        for key, value in variant_data.items():
            if key.startswith('extra_vcf_info__CSQ'):
                value = [''] * nblocks if value is None else value.split(';')
            transformed[key.lstrip('extra_vcf_info__')] = value  # noqa: B005 — inherited bug, docs/issues/clinreport/011
        return transformed

    def _inher_from_omim_pheno(self, phenotype: str) -> str | None:
        if not phenotype:
            return None
        inher = {short for name, short in self.inheritance_map.items() if name in phenotype}
        return ','.join(sorted(inher))
