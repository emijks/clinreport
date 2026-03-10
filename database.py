from sqlalchemy import create_engine
from urllib.parse import quote
from contextlib import contextmanager
import pandas as pd


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