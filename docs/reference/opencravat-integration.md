# OpenCRAVAT integration

Everything here was checked in OpenCRAVAT source (2.2.9 installed package unless stated) or by running it.
None of these extension points are covered by OpenCRAVAT's official docs (the
[widget tutorial](https://docs.opencravat.org/en/latest/Widget-Tutorial.html) covers only the JS side and
names the Summary key `summary`, which is wrong for 2.x — it is `info`). Re-verify after upgrading OpenCRAVAT.

## Module directories and types

`oc config md` prints the modules dir (this machine: `C:\open-cravat\modules`). Module type ↔ folder:

| Type (`type:` in yml) | Folder | Used here |
|---|---|---|
| `webapp` | `webapps/<name>/` | `clinreport` |
| `webviewerwidget` | `webviewerwidgets/wg<name>/` | `wgclinreport` (ours), `wgnote` (base module, needed for Notes) |
| `mapper` | `mappers/<name>/` | `hg38` (needed by the viewer) |
| `reporter`, `annotator`, … | … | not used |

Copying a folder into place is enough to install a module; `oc module install` is only for Store modules.
The `pypi_dependency` list in a module yml is honoured only by Store installs (`admin_util.py:1036`), which is why
[install.py](../../packaging/install_extension.py) pip-installs dependencies itself.

## Webapp routes (`route.py`)

2.x — `cravat/cravat_web.py`:

- `setup_webapp_routes` (`:435`) runs **once at GUI start-up**: for every folder in `<modules>/webapps/` that contains
  `route.py`, it imports it with `importlib.util.spec_from_file_location("route", path)` and, for each
  `(method, path, handler)` in `module.routes`, calls `app.router.add_route(method, f"/webapps/{name}/" + path, handler)`.
  → Changing `route.py` or anything it imports requires restarting `oc gui`.
- Handlers are **aiohttp** handlers: `async def handler(request) -> web.Response`. aiohttp 3.x still accepts plain
  functions but warns (deprecated), so `route.py` always returns coroutines for 2.x.
- Webapp routes are registered **before** the static route `add_static("/webapps", <modules>/webapps)` (`:470`), so
  `/webapps/clinreport/open` hits the handler and `/webapps/clinreport/index.html` the file. Consequence: **every file in the
  module folder is publicly downloadable** (`route.py`, templates…). Never put secrets there.
- `get_webapp_index` (`:482`) redirects `/webapps/<name>` → `/webapps/<name>/index.html` (keeps the query string).
- `oc gui --webapp <name>` (`:83`) opens `/webapps/<name>/index.html` directly (no `dbpath` → our page shows a path field).
- There is also `GET /webapps/{module}/widgets/{widget}` (`webresult.py`, `serve_webapp_runwidget`) that runs
  `<webapp>/widgets/wg<widget>/wg<widget>.py:get_data` — not used here.

3.x — `cravat/gui/webapps.py` (3.1.1):

- `webapp_proxy_handler` (`:12`) also imports each `route.py` and reads `routes`, but registers **one Flask rule**
  `/webapps/<cravat_module>/<action>` (`:65`) and dispatches by exact `action` and HTTP method → **paths must be a single segment**.
- It calls `handler_func(request)` **synchronously with the Flask request** (`:44`) and returns whatever it returns.
- `route.py` detects the Flask GUI by finding `webapp_proxy_handler` in the call stack while it is imported (the aiohttp
  loader is `setup_webapp_routes`) and builds Flask handlers. Verified on 3.1.1 in Docker ([issue 002](../issues/clinreport/002-opencravat-3x-untested.md)).

Neither loader catches errors (2.2.0 – 3.2.4): a `route.py` that raises on import stops the whole GUI, silently for the
user. `route.py` therefore imports `clinreport_core` inside `try` and, if that fails (typically `docxtpl` missing from
OpenCRAVAT's Python), registers routes that answer 503 with the package to install.

## Result viewer and widgets

Files: `cravat/webresult/webresult.py`, `cravat/webresult/nocache/js/{main,setup,variables}.js`.

- Widget discovery: `GET /result/service/widgetlist` → `get_widgetlist` (`webresult.py:282`) lists installed
  `webviewerwidget` modules with `required_annotator` (default: module name without `wg`).
- Loading: `loadWidgets` (`main.js:745`) does `$.getScript('/result/widgetfile/wg<name>/wg<name>.js')` for every widget,
  i.e. the JS is served from the module folder (browser may cache it — hard-reload after changing the widget).
- **Gating**: a widget is shown on a tab only if `usedAnnotators[tab].includes(required_annotator)` (`main.js:804`).
  `usedAnnotators` = column groups present in the result. Every result has `base`, hence `required_annotator: base`.
- The JS registers `widgetGenerators['<name>'] = { '<tab>': {...} }`. Tabs: `variant`, `gene`, and **`info` = Summary tab**
  (`setup.js:1955` `drawSummaryWidget` reads `widgetGenerators[name]['info']`). Summary generator keys:
  `name` (card title), `width`, `height`, `function(div, data)`; optional `callserver: true` + `requestmethod` +
  `variables.callserverparams` make the viewer call `GET|POST /result/runwidget/<name>` first and pass the JSON `data`
  (server side: `wg<name>.py: async def get_data(queries)`, `webresult.py:604/638`). Our widget needs no server call.
- Helpers available to widget JS (viewer globals): `getEl(tag)`, `addEl(parent, child)`, jQuery `$`.
- **Viewer globals** (`variables.js`): `username` (`:9`), `jobId` (`:10`), `dbPath` (`:30`). Set from the URL in
  `main.js:1076-1091`. When opened with `?dbpath=`, `jobId` is set to the last `/`-separated token of `dbPath` —
  on Windows that is the whole backslash path. Our widget passes all three; the webapp resolves `dbpath` first.
- Widget visibility is part of the viewer layout: a user can hide the ClinReport card via the viewer's widget menu and
  the choice is saved with the layout ([issue 016](../issues/clinreport/016-widget-discoverability.md)).

### Notes (`base__note`) are written by the `wgnote` widget, not by the viewer core

The viewer core has no note endpoint. The **`wgnote`** base module
([KarchinLab modules repo](https://github.com/KarchinLab/open-cravat-modules-karchinlab/tree/master/webviewerwidgets/wgnote),
v3.0.0) adds a text box + **Save** to the variant/gene detail panel and calls `GET /result/runwidget/note`
(`wgnote.py:get_data`) which runs `update variant set <col>=? where base__uid=?`, where `<col>` is
**`base__note_variant` if that column exists (results made/updated by OC ≥ 2.3.1), else `base__note`**.
ClinReport reads `base__note_variant` when the result has it and `base__note` otherwise
(`VariantSource._note_expression`; [issue 019](../issues/clinreport/019-note-column-base-note-variant.md), fixed in 3.0.1).
Results of OC ≥ 2.3.1 have only `base__note_variant` (`constants.crv_def`); the bundled OC 3.2.3 is one of them.
Without `wgnote` installed, clinicians cannot mark variants at all.

### Resolving the result file

`get_jobid_dbpath` (`webresult.py:401`) resolves `job_id`/`dbpath`/`username` for viewer requests. The webapp does its own,
simpler resolution in `service.resolve_dbpath`: `dbpath` if given; else `<jobs_dir>/<username>/<job_id>/*.sqlite`,
`<jobs_dir>/<job_id>/*.sqlite` and — without a username — `<jobs_dir>/*/<job_id>/*.sqlite` (the GUI stores jobs under the
user `default` in single-user mode; job ids/usernames with path characters are rejected). The file must exist and contain
the `variant`, `sample` and `info` tables.

### The viewer needs a gene mapper module

Building the column list (`cravat_report.py:792-796`, `make_col_info`) calls
`au.get_local_module_info(<mapper of the result>)` (e.g. `hg38`) and dereferences it; if the mapper is not installed
the viewer's `/result/service/variantcols` returns 500 and the page spins forever. Only the mapper's **constructor** is
used (its gene database is loaded in `setup()`, i.e. only when annotating), so the code-only module from GitHub is
enough for viewing ([issue 004](../issues/clinreport/004-store-unreachable-dev-machine.md)). Missing *annotators* are skipped gracefully.

## Why not a reporter (GUI report generation limits, 2.2.9)

`cravat/websubmit/websubmit.py`: `get_valid_report_types` (`:682`) lists installed reporters; `generate_report` (`:695`)
runs `oc report <db> -t <type>` with **no module options**; `download_report` (`:723`) serves **only `report_paths[0]`**
(`:731`); buttons exist only for jobs in the Jobs table. Why that rules it out: [ADR 0003](../decisions/0003-webapp-and-widget-not-a-reporter.md).

## GUI server facts useful for debugging

- `oc gui [result.sqlite] [--port N] [--headless] [--webapp NAME] [--multiuser] [--debug]`; default port 8080;
  without `--headless` it opens the default browser.
- System readiness only checks that the modules dir exists (`admin_util.system_ready`).
- Log: `<OC root>/logs/wcravat.log` (this machine `C:\open-cravat\logs\wcravat.log`): access log + tracebacks of
  unhandled handler exceptions (ours are caught and returned as JSON, so they do **not** appear there). An access-log line is
  written only when the response completes — a request that hangs never shows up.
- `cravat/cravat_class.py:32` calls `nest_asyncio.apply()` on import of `cravat` → affects every asyncio user in the process
  (see version matrix).
- OC dirs: `admin_util.get_conf_dir()` (`:469`), `get_jobs_dir()` (`:553`), `get_modules_dir()` (`:694`).

## Version matrix

| OpenCRAVAT | Python | Result | Evidence |
|---|---|---|---|
| **2.2.9** | **3.11.9** | ✅ everything works (viewer, Notes via wgnote, widget, webapp, docx) | pytest 25/25, `tests/e2e/smoke_http.py`, `tests/e2e/e2e_ui.py` |
| 2.2.9 | ≥ 3.12 | ❌ `import imp` (`cravat_web.py`, `webresult/webresult.py`, `webresult/cravat_view.py`) | `imp` removed in 3.12 |
| 2.2.9 | any, setuptools ≥ 81 | ❌ `import pkg_resources` (`store_utils.py:13`) | pin `setuptools<81` |
| 2.17.0 | 3.14.6 | ⚠️ GUI + webapp routes work (open/process/render verified over HTTP), but the **viewer hangs** on `GET /result/service/loadfiltersetting` when fired concurrently (`nest_asyncio` on 3.14); aiohttp `TestClient` also breaks | observed |
| 2.17.0 | 3.9–3.11 | ❔ not tested; expected to work (same aiohttp GUI as 2.2.9, no `imp`) | — |
| 3.1.1 | 3.14.6 (Windows) | ❌ GUI does not start: `cravat/gui/config.py:35` builds `f'/{work_dir}/celery/results'` → `'/C:\…'` → `OSError [WinError 123]` in `os.makedirs` | observed |
| **3.1.1** | **3.11 (Linux, Docker)** | ✅ everything works: Flask route adapter, widget, Notes, `.docx`, OC's Excel report via the Jobs page | the former `opencravat-server` Docker setup (2026-09-25): smoke 12/12, e2e, `report_via_jobs.py` |
| 3.2.3 | 3.11 (Windows, native) | ❌ same `/C:` crash as 3.1.1; with the path fixed, Celery's `prefork` workers die (`Can't pickle local object 'celery_init_app.<locals>.FlaskTask'`) and kombu's filesystem broker needs `pywin32` | observed 2026-10-15 |
| **3.2.3** | **3.11 (Windows, native) + desktop patches** | ✅ viewer, widget, review page, custom templates, `.docx`, Excel via the Jobs page and Store installs (Celery `solo` pool) | 2026-10-15: smoke 12/12, e2e 7/7, `report_via_jobs.py` (`launchers/desktop/clinreport_oc_compat.py`) |
| **2.2.9** | **3.11 (Linux, Docker)** | ✅ same checks | same |
| 3.x `oc gui --aiohttp` | any | ❔ not tested (route.py detects it from the call stack) | — |

### What the modules need, by OpenCRAVAT version (source analysis)

From the PyPI sources of 21 releases, 1.8.0 – 3.2.4 (2026-10-21); read, not run. "Untested" means the mechanisms are there
but nobody has run ClinReport on it.

| OpenCRAVAT | Python (OC's own) | Modules | What decides it |
|---|---|---|---|
| ≤ 2.1.x | — | ❌ | no webapp route loader (`setup_webapp_routes` appears in 2.2.0): the page loads, every action fails |
| 2.2.0 – 2.2.7 | 3.8 – 3.11 | ⚠️ untested | OC still allows Python 3.6/3.7; the modules need 3.8 |
| 2.2.8 – 2.5.0 | 3.8 – 3.11 | ✅ 2.2.9 tested | `import imp` (gone in Python 3.12) until 2.5.0; `pkg_resources` → `setuptools < 81` |
| 2.6 – 2.15 | 3.8/3.9 – 3.13 | ⚠️ untested | no `imp`; still `pkg_resources` → `setuptools < 81` |
| 2.17 | 3.9 – 3.13 | ⚠️ untested | no `pkg_resources`; on 3.14 the viewer hangs (`nest_asyncio`, see above) |
| 3.0 – 3.2.4 | 3.9+ | ✅ Linux/macOS; ❌ Windows | Windows needs the desktop patches; **3.2.4 still has the `/C:` path and `prefork` pool** |

The same in every release from 2.2.0 to 3.2.4: the `routes` format and its `/webapps/<name>/` prefix, `admin_util`
`get_conf_dir` / `get_jobs_dir` / `get_system_conf`, the viewer globals `dbPath` / `jobId` / `username` and
`widgetGenerators`. The modules' own packages install on Python 3.8 (`docxtpl` 0.20, `jinja2` 3.1, `lxml` 6;
`python-docx` stops at 1.1.2 there).

**Importing `cravat` writes to disk** in every release: `constants.py` creates `C:\open-cravat`, `/Users/Shared/open-cravat`
or (Linux) `conf/` inside the package, and copies `cravat-system.yml` from the template when it is missing — whatever
`OPENCRAVAT_SYSTEM_CONF_PATH` says. Any `oc` command (`oc version`, `oc config md`) therefore changes the computer; to
inspect another OpenCRAVAT without that, locate the package with `importlib.util.find_spec('cravat')` (does not import it)
and read its dist-info and `cravat-system.yml` directly.

## OpenCRAVAT 3.x specifics (verified in Docker)

- `oc gui` runs the Flask app on **waitress** (12 threads) and starts **three Celery workers** itself (filesystem broker in
  `work_dir`); `oc gui --aiohttp` runs the old server. `route.py` therefore decides by **who imports it**
  (`webapp_proxy_handler` in the call stack → Flask), not by the installed version.
- The viewer JS is unchanged where it matters: Summary key `info`, globals `dbPath`/`jobId`/`username`, `/result/widgetfile/…`.
- The **Jobs page opens the viewer with only `?job_id=<id>`** (`websubmit/nocache/websubmit.js:476`) — no `dbpath`, no `username`.
- The GUI keeps jobs in **`<jobs_dir>/<user>/<job_id>/`**, user **`default`** in single-user mode — **2.2.9 does the same**.
  `service.resolve_dbpath` therefore searches `<jobs>/<user>/<id>`, `<jobs>/<id>` and, without a username, `<jobs>/*/<id>`.
- Report generation is a Celery task (`gui/tasks.py:run_report`); `POST /submit/jobs/<id>/reports/<type>` returns immediately.
- The 2.2.9 GUI reports a report as `fail` if `oc report` writes anything to stderr (e.g. the `pkg_resources` deprecation
  warning) although the file is produced — the server image sets `PYTHONWARNINGS` to silence it.
- Viewer font names are `roboto-light` / `roboto-medium` (`webresult/nocache/css/widget.css`); `Roboto` does not exist there.
