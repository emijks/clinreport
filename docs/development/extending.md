# Extending — recipes

Each recipe lists every place to touch. After any recipe: `python -m pytest`, `ruff check .`, then try it in a running
OpenCRAVAT (`packaging/install_extension.py --no-deps` + restart `oc gui` if Python changed, or rebuild the desktop app),
`tests/e2e/smoke_http.py`, and update the docs you affected ([HTTP API](../reference/http-api.md),
[data model](../reference/data-model.md)).

`process.py`/`utils.py` came from the Tk app unchanged; since 3.0 this repository is their only home, so report-content
changes go straight into them (with a test in `tests/core/`).

## Inspect a template's variables

```python
import re, zipfile

xml = zipfile.ZipFile('modules/webapps/clinreport/templates/docx/DZM.docx').read('word/document.xml').decode()
text = re.sub(r'<[^>]+>', '', xml)
print(sorted(set(re.sub(r'\s+', ' ', t) for t in re.findall(r'(\{\{.*?\}\}|\{%.*?%\})', text))))
```

(Headers/footers live in `word/header*.xml` / `word/footer*.xml` — check those too if a variable seems missing.)
Edit templates in Word; keep each Jinja tag inside one run (type it in one go) or docxtpl will not see it.

## Add a template

Word, HTML/PDF, or a whole new report kind: **[templates.md](templates.md)** — the model (a template = one id, a file
per format), the CSS both PDF engines read, and three recipes with the files to touch. A lab's own Word template needs no
code: an admin adds it on the page («Шаблоны»).

## Add an editable patient/tech field (e.g. `patient.birth_date`)

1. Put the key into the context: preferably in `service._report()` (`context['patient'].setdefault('birth_date', '_')`),
   or upstream in `SampleProcessor.build_default_context()`.
2. Template: add `{{ patient.birth_date }}`.
3. `labels.COMMON_FIELDS`: add `('patient', 'birth_date', 'Дата рождения')` → it appears on the page automatically.
4. If it must go to Postgres: add to `labels.PAYLOAD_COMMON` (the DB table needs the column).

## Add a column to the variant tables

1. Produce the field per row (upstream `_process_variant`, or loop over `context[*_variants]` in `service._report()`).
2. `labels.FIELD_LABELS[field] = 'Заголовок'`; add the field to `SNV_FIELDS` / `CARRIER_FIELDS` (page columns).
3. Template: add the cell `{{ v.<field> }}` in the relevant `{%tr for v in … %}` rows.
4. Postgres: add to `PAYLOAD_VARIANT_FIELDS` if it should be stored.
5. Optional styling: `.col-<field>` in `static/app.css`.

## Implement CNV / MT / STR sections (Notes 4, 5, 6)

Today `SampleProcessor.SNV_NOTES = ('1','2','3','7','8')` and the three lists stay empty ([issue 010](../issues/clinreport/010-cnv-mt-str-sections-empty.md)).

1. Decide the data source (which result/annotator provides CNVs; the example results have none).
2. Build rows with the fields the templates already expect ([05 §4](../reference/data-model.md#4-template-variables-docxtpl--jinja)):
   DZM/FND — `cnv_variants`: `variation, disease, genes, copies, classification`;
   `mt_variants`: `gene, disease, variation, classification, coverage`;
   `str_variants`: `gene, disease, expansion, repeat_count, classification`;
   10x — `cnv_variants`: `position, disease, genes, copies, classification`; `mt_variants`: `gene, disease, variation, classification`.
3. Add `LAYOUTS` tables (`('cnv_variants', 'CNV', CNV_FIELDS)` etc.) and labels.
4. Decide whether they go to Postgres (`PAYLOAD_SECTIONS`) — the current table has SNV-shaped columns.
5. Implement upstream in the desktop app first if it is still in use.

## Add an endpoint

1. `service.py`: `def my_action(params: dict) -> dict | FileResult`; raise `ClientError('…')` for user errors.
2. `route.py`: add `('POST', 'my_action', service.my_action)` to `HANDLERS`. **Single path segment only** (OC 3.x).
3. `static/app.js`: `await postJSON('my_action', {...})` (or `postBlob` for files).
4. `tests/core/test_service.py` (+ `test_routes.py` if the HTTP shape matters); document in [http-api](../reference/http-api.md).

## Add a setting

Decide the scope first ([05 §8](../reference/data-model.md#8-settings-files)): per user (almost always) or server-wide.

1. Per user: `service.USER_DEFAULTS['my_key'] = <default>` (bool → coerced like `auto_upload`, choice → validated like
   `template` — extend `update_settings`). Server-wide: an environment variable read on the server (like `CLINREPORT_DB_*`),
   not a page setting.
2. `index.html`: an `<input name="my_key">` / `<select name="my_key">` inside `#settings-form` (checkbox for bools) — `app.js`
   binds by `name`. Server-wide values have no inputs.
3. Read it with `load_user_settings(caller)['my_key']` (the handler receives `caller`). Settings reach the page via
   `open`/`settings` responses. Never put a secret in the response.

## Add a report kind

[templates.md, recipe 3](templates.md#recipe-3--a-new-report-kind-worked-example-screening) — `screening` is the worked
example (context builder, checks, layout with `add_rows`/`lists`, templates, tests).

## Add a batch reporter (optional, CLI / Jobs-table use)

A reporter module (`modules/reporters/clinreportdzmreporter/…`, class `Reporter(CravatReport)`) could call
`ClinReport(self.dbpath).build_context(...)` + `render_context(...)` and zip one `.docx` per sample; the module name must end
in `reporter` and the yml needs `output_filename_schema` (e.g. `'{run_name}.clinreport.zip'`). It cannot show the review
window and receives no options from the GUI ([ADR 0003](../decisions/0003-webapp-and-widget-not-a-reporter.md)). It would
live in this repository next to the webapp and import `clinreport_core` (or the package it becomes,
[ADR 0002](../decisions/0002-one-repository.md)).

## Release / versioning

See [releasing.md](releasing.md): one version number for the product and both modules, a `CHANGELOG.md` section, a tag.
