# Testing

| Layer | Needs | Command | Runs in CI |
|---|---|---|---|
| pytest (`tests/`) | `requirements-dev.txt` | `python -m pytest` (~15 s) | yes, Linux + Windows |
| … with real results | the example results | `CLINREPORT_EXAMPLES=<dir> python -m pytest` | no (patient data) |
| Desktop bundle smoke | a built bundle | `--headless` + HTTP checks, `--selftest` ([packaging.md](packaging.md)) | yes, Windows + macOS arm64/x64 |
| Live HTTP smoke | a running `oc gui` with the extension, example results | `python tests/e2e/smoke_http.py <results…> [--base URL] [--out DIR]` | no |
| Browser end-to-end | a running `oc gui`, Playwright + Edge | `python tests/e2e/e2e_ui.py <multi-sample result> --out DIR` | no |
| Manual checklist | Edge, the example results | below | no |

Run pytest after every change, the live layers after changing routes, the page or the widget, and everything before a release.

## pytest

`tests/` has no `__init__.py`; pytest's `pythonpath` (pyproject.toml) puts `tests/`, `modules/webapps/clinreport`,
`launchers/desktop` and `launchers/cli` on the path, so tests import `clinreport_core`, `clinreport_desktop` and `helpers`
directly. Shared paths and the route loader are in `tests/helpers.py`; fixtures in `tests/conftest.py`:

- `trio_db`, `single_db` — the example results from `CLINREPORT_EXAMPLES` (default `tests/examples/`); **skip** when missing;
- `service` — `clinreport_core.service` with a fake OpenCRAVAT (`conf`/`jobs` under `tmp_path`), no Russian-annotation
  fetch, no database engines.

| Folder | Covers |
|---|---|
| `core/` | `service` (open, process default/LPWGS, render with edits, settings), templates (store, checks, upload over aiohttp), database (Postgres code against SQLite), login mode and settings scopes, CLINBIO, `float2percent` |
| `routes/` | `route.py` loaded the way OpenCRAVAT does, mounted on aiohttp (OC 2.x) and Flask (OC 3.x): JSON errors, content types, login |
| `cli/` | the CLI end to end on a trio (needs examples) |
| `desktop/` | launcher logic without a window: config, module sync, single instance, updates (version order, release choice, checked download, silent installer), session logs (files, retention, thread errors, the page's messages), environments (probe without importing `cravat`, the version matrix, deep search, install/update/remove with rollback, the command for another OpenCRAVAT, leftover pid) |
| `packaging/` | installer rules on the `.iss` source (AppId, what is deleted, mutex), `build.py` helpers (macOS wheel/otool parsing, stack consistency, one version number), `install_extension.py` |

### Another OpenCRAVAT («Окружения»), end to end

pytest uses fake installations. Before a release, run it against a real one on Windows — it must not touch the real
`C:\open-cravat`, so map a scratch folder as the system drive OpenCRAVAT uses:

```text
py -3.11 -m venv <tmp>\oc229 && <tmp>\oc229\Scripts\python -m pip install "open-cravat==2.2.9" "setuptools<81"
subst X: <tmp>\drive
set SystemDrive=X: & set CLINREPORT_DATA_DIR=<tmp>\data
packaging\dist\ClinReport\python\python -I -m clinreport_desktop
```

In «Окружения»: «Указать Python…» → `<tmp>\oc229\Scripts\python.exe`; «Установить» (downloads docxtpl… into the module's
`lib/`); «Использовать» → «Обзор» shows «окружение oc229»; open an example result → «Заключение» → «Обработать»; switch back
to «Встроенное». Afterwards `subst X: /d`.

Not covered by pytest: the real OpenCRAVAT login, the Google Sheet (network), a real Postgres
([issue clinreport/001](../issues/clinreport/001-postgres-untested.md)), the browser page, the native save dialog.

### Coverage

`python -m pytest --cov` reports branch coverage of `clinreport_core`, `clinreport_desktop` and the CLI; the target is
**80 %** (`fail_under` in pyproject.toml). CI shows the report in the job summary but does not fail on it yet
(`--cov-fail-under=0`): without the example results about a fifth of the tests skip and coverage is ~45 % (~60 % with
them). Planned: synthetic results generated in the tests ([issue clinreport/017](../issues/clinreport/017-no-ci.md)) and
launcher tests with mocks, with only the pywebview window start marked `# pragma: no cover` (the window self-test covers
it in CI). Then CI enforces the 80 %.

### Adding tests

- Service behaviour → `tests/core/test_service.py` with the `service` fixture (no network, temp dirs).
- SQL → `tests/core/test_database.py` (SQLite stands in for Postgres: keep SQL portable — quoted identifiers, bound parameters).
- Routes → `tests/routes/test_routes.py` (aiohttp, `with_client`) and `test_routes_flask.py` (`make_app`).
- Who is logged in → `tests/core/test_multiuser.py` (`Caller`s for admin/alice/bob).
- Launcher → `tests/desktop/` with `CLINREPORT_DATA_DIR`/`CLINREPORT_BUNDLE_DIR` pointing at `tmp_path`; never the network.
- Installer and build rules → `tests/packaging/`; they read the source files, so they run on every OS.

## e2e scripts

`tests/e2e/smoke_http.py`: for every result `open` → `process` (default, plus LPWGS for multi-sample files) → edit the
diagnosis → `render` every template → checks the `.docx` (valid, every gene present, the edit present, no literal
`None`). Exit code 1 on any failure.

`tests/e2e/e2e_ui.py`: viewer → ClinReport card → review page → «Обработать» → edits → template FND → «Сохранить как…»
(download) → LPWGS → Настройки, in headless Edge (`--headed` to watch); screenshots per step. It removes
`window.showSaveFilePicker`, so it tests the download fallback; the native dialog is manual
([issue clinreport/008](../issues/clinreport/008-save-dialog-manual-test.md)).

Against the desktop app: start it with `--headless` and pass the printed address as `--base`.

## Manual checklist (before a release)

- [ ] Installer over the previous version **while it runs**: no "Preparing to Install" list of Python processes; the welcome
      page names both versions; settings, the lab's templates and jobs are still there; the new version starts.
- [ ] Mark a variant with Note `8` in the viewer, «Обработать» → it appears under «Носительство»; clear it again.
- [ ] «Сохранить как…» opens the native save dialog with `Заключение (<sample>).docx`; cancel → nothing happens; save →
      the file opens in Word with line breaks in «Изменение ДНК» and «Зиготность».
- [ ] Настройки: clinician → «Обработать» → the document shows the name.
- [ ] Шаблоны: add a `.docx` from the sample, the check passes, it is offered in the review page.
- [ ] Offline: «Обработать» shows the Russian-annotation warning and still builds the reports.
- [ ] Open from the Jobs tab (import the `.sqlite`, View) → widget → the page finds the result by `job_id`.
- [ ] In-app update from the previous pre-release (pre-releases enabled): download, silent install, restart.
- [ ] macOS: first start via right-click → «Открыть»; the window opens; a result opens in the viewer.
