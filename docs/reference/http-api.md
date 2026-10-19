# HTTP API

Base URL: `http://localhost:8080/webapps/clinreport/` (the GUI's host/port). Implemented in
[service.py](../../modules/webapps/clinreport/clinreport_core/service.py), mounted by
[route.py](../../modules/webapps/clinreport/route.py) (`HANDLERS` table).

Conventions:

- `GET` parameters come from the query string; `POST` bodies are JSON (`Content-Type: application/json`).
- JSON responses are UTF-8 with `ensure_ascii=False`; non-JSON values (dates from Postgres) are stringified.
- Errors: `400 {"error": "<Russian message>"}` for `ClientError` (bad input, missing file, DB not configured…);
  `401 {"error": …}` in login mode without a session;
  `500 {"error": "Внутренняя ошибка: …", "traceback": "…"}` for anything else. The page shows both in its error dialog.
- `POST` bodies must be sent as `Content-Type: application/json` (else `400`), so a cross-site HTML form cannot post to the
  API without a CORS preflight.
- Authentication: see [below](#authentication-and-login-mode). Without login mode the API trusts whoever can reach it
  (reads any local path it is given) — keep such a GUI on localhost.
- Paths are single segments (OpenCRAVAT 3.x constraint). Keep it that way when adding routes.

## Authentication and login mode

`route.py` builds a `service.Caller` for every request and passes it to the handler:

| GUI | Login mode detected by | Login name from |
|---|---|---|
| OC 3.x Flask (default) | `flask.g.is_multiuser` (set by the GUI's `before_request`) | `flask.g.username` |
| OC 2.x / 3.x `--aiohttp` | `cravat.cravat_web.servermode` | `await cravat_multiuser.get_username(request)` |

Without login mode every request is the local user `default` with full rights (the behaviour before 2026-09-26).
In login mode:

- no session → `401 {"error": "Требуется вход в OpenCRAVAT: …"}` for **every** endpoint;
- results are opened **only by `job_id`**, in `<jobs_dir>/<login>/<job_id>/`; `dbpath` → `400`; the `username` parameter is
  ignored. Admins (`admin_list` in `cravat-system.yml`, default `["admin"]`) may open any user's job (with `username`, or
  searched in all user folders) — the same rule as OpenCRAVAT's own job routing;
- user settings are per login; only admins change the DB connection (see `settings` below).

The module's files are also served statically (`/webapps/clinreport/route.py`, templates) by the GUI; they contain no secrets.

## Result source parameters

Login mode: `job_id` only, see above. Otherwise `open` and `process` accept either `dbpath` (absolute path to the result `.sqlite`, as seen by the GUI server) or `job_id`
[+ `username`], resolved in `<jobs_dir>/<username>/<job_id>/`, `<jobs_dir>/<job_id>/` and, without a username,
`<jobs_dir>/*/<job_id>/` (the GUI stores jobs under the user `default` in single-user mode; the 3.x Jobs page passes only
`job_id`). Job ids / usernames containing `/`, `\`, `.` or `..` are rejected. `dbpath` wins if both are given. The file must
contain the `variant`, `sample` and `info` tables, else `400`.

## `GET open`

Query: `dbpath` | `job_id` [`username`].

```json
{
  "dbpath": "C:\\open-cravat\\demo\\trio1.sqlite",
  "filename": "trio1.sqlite",
  "samples": [{"index": 0, "label": "sample1"}, {"index": 1, "label": "sample2"}, {"index": 2, "label": "sample3"}],
  "settings": { … as returned by GET settings … }
}
```

`label` = sample id up to the first `.`; a missing id (`None`) becomes the file name up to the first `.` (`pah2`).
Samples are addressed by `index` everywhere (ids can be `null`).

## `POST process`

Body: `{"dbpath": "…" | "job_id": "…", "target": 0, "mode": "default" | "lpwgs"}` (`target` = sample index, default 0;
`mode` default `"default"`).

- `default`: one `kind: "default"` report per sample, in file order. The target only affects the narrative
  ("Вариант обнаружен у …") and `is_target`.
- `lpwgs`: the target → `kind: "default"`, every other sample → `kind: "10x"`.

```json
{
  "mode": "default",
  "reports": [
    {"label": "sample1", "kind": "default", "is_target": true,
     "filename": "Заключение (sample1).docx", "context": { … see 05-data-model … }}
  ],
  "layouts": {"default": { … }, "10x": { … }},
  "warnings": ["Не удалось получить аннотации на русском (…); используются аннотации OpenCRAVAT."]
}
```

`filename` for 10x reports: `Заключение LPWGS (<label>).docx`. The clinician name comes from the caller's settings at the
time of processing. Russian annotations are fetched (or taken from the 10-min cache) during this call; failure only adds a warning.

## `POST render`

Body: `{"context": {…}, "kind": "default" | "10x", "template": "<template id>", "filename": "…"}`.
`template` is a built-in id (`DZM`, `FND`, `10x`) or a custom one (`u-…`, see [Templates](#templates)); default `DZM` /
`10x` by kind. Unknown templates and a template of the other kind → `400`. `filename` is sanitised
(basename, `<>:"/\|?*` → `_`, `.docx` appended).

Response: `200`, body = `.docx` bytes,
`Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
`Content-Disposition: attachment; filename="report.docx"; filename*=UTF-8''<percent-encoded name>`.

The context is rendered as sent (edits included). `variation` and `zygosity` strings are converted to docxtpl
`RichText` so `\n` becomes a line break (`templates.richtextify`).

## `POST upload`

Body: `{"context": {…default-kind context…}, "force": false}`. Requires DB settings (else `400`) and `sqlalchemy` +
`psycopg2-binary` (else `400` with an install hint).

- If `force` is false and `"ReportedVariants"` already has rows with `"Номер образца" = context.patient.id` →
  `{"duplicate": true, "sample": "<id>"}` (nothing written).
- Otherwise inserts one row per variant of `p/lp/vus/sf/carrier_variants` → `{"inserted": <n>}`. Every row of one call
  also carries `uploaded_by` (the login; empty in local mode) and the same new `upload_id` (a UUID).

Row format: [data-model](../reference/data-model.md#7-postgres-reportedvariants-payload).

## `POST similar`

Body: `{"variant": {…a variant row of a default context…}}`. Requires DB settings.
Looks up `"ReportedVariants"` rows whose `"Изменение ДНК (HG38) (Изменение белка)"` contains the first line of
`variant.variation` (the SPDI-like `chr-pos-ref-alt`):

```json
{"rows": [{"Номер образца": "pah2", "Патогенность": "Патогенный", "Клиницист": "", "Дата заключения": "2026-09-25"}]}
```

## `GET settings` / `POST settings`

`GET` →

```json
{"clinician": "Иванова И.И.", "template": "DZM", "auto_upload": false,
 "username": "default", "multiuser": false, "clinbio_enabled": false, "db_configured": true,
 "edition": "server", "templates_editable": true}
```

- first line: the caller's own settings; `template` = default template for new report tabs (any standard-report
  template id, built-in or custom; if it is deleted the tabs fall back to `DZM`);
- `edition`: `server` (an OpenCRAVAT with the extension) or `desktop` (the desktop app, `CLINREPORT_EDITION=desktop`): the desktop
  edition has no database or CLINBIO, `process` returns layouts with `upload`/`similar` false;
- `templates_editable`: the caller may add/delete templates (everyone without login mode; OpenCRAVAT admins with it);
- `db_configured`: the server has a database connection (`CLINREPORT_DB_HOST/PORT/NAME/USER/PASS`, all non-empty).
  That is all the API says about the database: the connection is the server's, never shown or changed through the API.

`POST` body: any subset of `clinician, template, auto_upload` (the caller's own). Unknown keys (DB keys included) are
ignored; strings trimmed; `auto_upload` coerced to bool; unknown `template` or a 10x template → `400`. Returns the new
`GET settings` object. Storage: [05 §8](../reference/data-model.md#8-settings-files).

## `GET ru_status` / `POST ru_refresh`

`ru_status` reports the cached Russian annotations without network access; `ru_refresh` downloads them again now.
Both: `{"loaded_at": "2026-10-15T14:02:07" | null, "counts": {"omim": 4812, "secondary": 81}, "warning": null | "…"}`
(counts = genes per sheet). The desktop app calls `ru_refresh` once its server is up and from its «Обновить» button.

## Templates

Built-in templates ship in the module; the lab's own are stored in `<conf dir>/clinreport/templates/`
(`<id>.docx` + `templates.json`; desktop app: `<data folder>/conf/clinreport/templates/`), so module updates and app
updates keep them. Logic: `clinreport_core/templates.py`. Everyone uses and checks templates; **adding and deleting is for OpenCRAVAT
admins in login mode** (`is_admin`: `admin_list`, filled from `opencravat:admin`), for everyone without it.

| Route | Body / query | Response |
|---|---|---|
| `GET templates` | — | `{"templates": [{"id", "title", "kind", "builtin", "added"?, "check"?}], "kinds": {"default": "…", "10x": "…"}, "editable", "default_template", "max_bytes"}` |
| `POST template_add` | `{"title", "kind": "default"\|"10x", "data": "<base64 .docx>", "replace"?: "<id>"}` | `{"template": {…, "check"}}`; `400` for a duplicate title, a non-.docx file, a Jinja syntax error or a non-admin |
| `POST template_delete` | `{"id"}` | `{"deleted": "<id>"}`; built-ins and non-admins → `400` |
| `POST template_check` | `{"id"}` | `{"ok", "error", "unknown": [{"field": "patient.birth_dat", "suggestion": "patient.birth_date"}]}` |
| `GET template_file` | `?id=` | the `.docx` (download, or the starting point for a new template) |
| `GET template_fields` | — | `{"default": ["patient.id", "p_variants[].gene", …], "10x": […]}` |

**The check** renders the template against an example report with one row in every list (`templates.example_context`)
through a Jinja `Undefined` that records each missing name, and maps it back to a path (`p_variants[].gene`). A template
with unknown fields is still stored (the fields render empty, as docxtpl always did) and the warning is kept in
`templates.json`. `test_example_context_covers_a_real_report` keeps the example in sync with real reports.

**Upload size:** templates are capped at 10 MB; `route.py` lifts aiohttp's 1 MB body limit for its own requests (2.x).

## Using the API without the page

The API is enough for batch use (e.g. a CLI or another UI). Example (Python stdlib):

```python
import json, urllib.request

base = 'http://localhost:8080/webapps/clinreport/'
post = lambda a, p: urllib.request.urlopen(
    urllib.request.Request(base + a, json.dumps(p).encode(), {'Content-Type': 'application/json'})
).read()
reports = json.loads(post('process', {'dbpath': r'C:\open-cravat\demo\trio1.sqlite', 'mode': 'default'}))['reports']
open('out.docx', 'wb').write(post('render', {'context': reports[0]['context'], 'kind': 'default', 'template': 'DZM'}))
```

[tests/e2e/smoke_http.py](../../tests/e2e/smoke_http.py) is a complete example.
