from sqlalchemy import create_engine
from urllib.parse import quote
from contextlib import contextmanager
import sqlite3
import pandas as pd
import json

class Database:

    def __init__(self, db_creds: str | dict):
        self.db_creds = self.setup_creds(db_creds)

    def setup_creds(self, creds: str | dict) -> dict:
        if isinstance(creds, dict):
            return creds
        with open(creds, 'r') as fh:
            return json.load(fh)

    @contextmanager
    def conn(self):
        engine = create_engine(
            f'postgresql+psycopg2://'
            f'{self.db_creds["user"]}:{quote(self.db_creds["pass"])}@{self.db_creds["host"]}:{self.db_creds["port"]}/{self.db_creds["name"]}'
        )
        with engine.connect() as conn:
            yield conn
            conn.commit()

    def insert(self, payload):
        with self.conn() as conn:
            payload.to_sql("ReportedVariants", con=conn, if_exists="append", index=False)


    def sample_data_exists(self, sample):
        with self.conn() as conn:
            sample_data = pd.read_sql(
                f'''select * from "ReportedVariants" where "Номер образца" = '{sample}';''',
                con=conn
            )
        return bool(len(sample_data))

    def get_similar_variants(self, variant_data):
            """Запрос к БД для получения похожих вариантов"""
            dna_change = variant_data['Изменение ДНК (HG38) (Изменение белка)'].split('\n')[0]
            with self.conn() as conn:
                query = f"""
                    SELECT 
                        "Номер образца", "Патогенность", "Клиницист", "Дата заключения"
                    FROM "ReportedVariants" 
                    WHERE "Изменение ДНК (HG38) (Изменение белка)" LIKE '%%{dna_change}%%'
                    """
                similar_variants = pd.read_sql(query, conn).to_dict('records')
                return similar_variants


class VariantSource:
    """Reads variants from a per-run OpenCRAVAT SQLite.

    Produces new-schema variant dicts regardless of whether the SQLite is the
    current or the legacy schema (legacy is bridged to the new column names).
    This is the *input* data source -- distinct from `Database` above, which is
    the *output* Postgres archive.
    """

    inheritance_map = {
        'Autosomal dominant': 'AD',
        'X-linked dominant': 'XD',
        'Autosomal recessive': 'AR',
        'X-linked recessive': 'XR',
    }

    def __init__(self, sqlite_path: str):
        self.sqlite_path = sqlite_path

    def all_samples(self) -> list:
        with sqlite3.connect(self.sqlite_path) as con:
            cur = con.cursor()
            return [row[0] for row in cur.execute('select distinct base__sample_id from sample;').fetchall()]

    def variants(self) -> list[dict]:
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

    # --- legacy-schema bridge (faithful port from clinreport_old.py; B5 keep) ---
    # NOTE: `annotation` is assigned inside the CSQ_PICK loop and read after it;
    # ported as-is from the old untested legacy path. Revisit if legacy SQLites
    # ever flow through the new render path.
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
            annotation['vep_csq__refseq'] = extra_vcf_info['CSQ_MANE_SELECT'][i] if extra_vcf_info['CSQ_MANE_SELECT'][i] else None
        annotation['vep_omim_pheno__inher'] = self._inher_from_omim_pheno(variant_data['vep_omim_pheno__pheno'])
        for col in ['filter', 'zygosity', 'ad', 'dp']:
            annotation[f'tagsampler_new__{col}'] = variant_data[f'vevatacmg_postaggregator__{col}']
        annotation['tagsampler_new__samples'] = variant_data['vevatacmg_postaggregator__sample']
        for col in ['id', 'sig']:
            annotation[f'clinvar_new__{col}'] = variant_data[f'clinvar__{col}']
        annotation['clinvar_new__sig_subs'] = annotation['clinvar_new__equivalents'] = annotation['clinvar_new__alternatives'] = None
        return annotation

    def _extra_vcf_info(self, variant_data: dict) -> dict:
        """Make each CSQ block iterable."""
        nblocks = len(variant_data['extra_vcf_info__CSQ_Allele'].split(';'))
        transformed = {'nblocks': nblocks}
        for key, value in variant_data.items():
            if key.startswith('extra_vcf_info__CSQ'):
                value = ['']*nblocks if value is None else value.split(';')
            transformed[key.lstrip('extra_vcf_info__')] = value
        return transformed

    def _inher_from_omim_pheno(self, phenotype: str) -> str | None:
        if not phenotype:
            return None
        inher = {short for name, short in self.inheritance_map.items() if name in phenotype}
        return ','.join(sorted(inher))