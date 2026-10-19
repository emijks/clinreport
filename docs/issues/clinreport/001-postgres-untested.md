# 001 · Postgres upload / «Похожие» never tested against a real server

| Status | Priority | Type | Area |
|---|---|---|---|
| blocked (needs DB access or a local Postgres) | **P1** | testing | `clinreport_core/database.py` (`Database`), `service.upload/similar` |

## Problem

The `Database` class was rewritten from pandas (`to_sql` / `read_sql`) to SQLAlchemy Core with bound parameters
([decisions](../../decisions/README.md)). It is tested only against **SQLite** through SQLAlchemy (`tests/core/test_database.py`).
Not verified against Postgres + psycopg2:

- column names with Cyrillic, spaces, parentheses and `*` (`"Частота*"`, `"Изменение ДНК (HG38) (Изменение белка)"`) — quoted, should work;
- `executemany` of text values into the real column types (e.g. is `"Дата заключения"` a `date` column? we send `'YYYY-MM-DD'` text —
  psycopg2 lets Postgres cast it; the desktop app sent the same string via pandas);
- the table must already exist (pandas `to_sql(if_exists='append')` created it if missing; we do not);
- `LIKE` with `%` inside the variation (none expected);
- connection errors → currently a 500 with traceback in the page (acceptable but could be a friendlier `ClientError`).

## TODO

- [ ] Get the production schema: `\d "ReportedVariants"` (column names and types). Record it in [data-model](../../reference/data-model.md#7-postgres-reportedvariants-payload).
- [ ] Local test DB: `docker run -e POSTGRES_PASSWORD=x -p 5432:5432 postgres:16` (Docker Desktop is installed but was not running),
      create the table with the production DDL.
- [ ] Add an opt-in pytest (`CLINREPORT_PG_URL=postgresql+psycopg2://…`) that runs `test_database.py`'s scenario against it.
- [ ] Manual: settings dialog → upload, duplicate prompt, forced upload, «Похожие», auto-upload after save.
- [ ] Map `sqlalchemy.exc.OperationalError` to `ClientError('Не удалось подключиться к базе данных: …')`.

## Acceptance

The same records land in `ReportedVariants` as the desktop app would write for the same edited context; «Похожие» returns them.

## Progress (2026-10-04)

GenLab Services (the `genlab-services` repository) has its own ClinReport database: `clinreport` in its Postgres, wired into its OpenCRAVAT service. The connection is env-only:
«Настройки» has no DB fields. GenLab Services' `tests/test_clinreport_db.py` (stack) runs upload → duplicate → «Похожие» through the HTTP API against it.
Answered: Cyrillic/space/`*` column names work; `'YYYY-MM-DD'` goes into a `text` column; the 63-byte identifier limit
cuts the variation column's name, but consistently in every statement.

office shows the table («Выгруженные варианты», `/clinbio/variants/`) and deletes wrong uploads; the table gained
`id`, `uploaded_at`, `uploaded_by`, `upload_id` (05-data-model §7).

Still open: the lab's **production** schema (`\d "ReportedVariants"`: are the types the same?) and moving its existing
rows into GenLab Services; the manual UI pass; `OperationalError` → friendly `ClientError`.
