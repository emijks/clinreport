# AGENTS.md — ClinReport

Instructions for coding agents (and a fast overview for people). Product overview: [README.md](README.md).
Background and the reasons behind the rules: [docs/](docs/README.md), especially [decisions](docs/decisions/README.md).

## Map

| Path | What | When you change it |
|---|---|---|
| `modules/webapps/clinreport/` | OpenCRAVAT webapp: `route.py` (HTTP), `index.html` + `static/` (review page), `templates/*.docx` | features clinicians use |
| `modules/webapps/clinreport/clinreport_core/` | report logic: `service.py` (handlers), `process.py` (report content), `database.py`, `templates.py`, `labels.py` | almost every feature |
| `modules/webviewerwidgets/wgclinreport/` | Summary-tab button that opens the review page | the entry point in the viewer |
| `launchers/desktop/clinreport_desktop/` | desktop control window (pywebview), starts OpenCRAVAT, updates | desktop-only behaviour |
| `launchers/desktop/clinreport_oc_compat.py` | patches that make OpenCRAVAT 3.2.3 run on Windows | after an OpenCRAVAT bump |
| `launchers/cli/cli.py` | command-line tool on `clinreport_core.service` | CLI options |
| `packaging/` | `build.py` (bundle + installers), `stack.toml` (pinned versions), `windows/ClinReport.iss`, `macos/`, `install_extension.py` | builds, installers, pins |
| `tests/{core,routes,cli,desktop,packaging}/` | pytest; `tests/e2e/` = scripts against a running `oc gui` (not collected) | with every change |
| `.github/workflows/` | `ci.yml` (every push), `release.yml` (tag `v*`) | CI |
| `docs/` | architecture, guides (Russian), development, reference, decisions, issues | when behaviour or a decision changes |

## Commands

```text
pip install -r requirements-dev.txt                  # Python 3.13; OpenCRAVAT 3.2.3 + app deps + pytest/ruff
python -m pytest                                     # ~100 tests, ~15 s; needs no GUI and no network
CLINREPORT_EXAMPLES=<dir> python -m pytest           # + tests on real results (trio1.sqlite, pah2.vevat_annotated.sqlite)
python -m pytest --cov                               # coverage; target 80 % (pyproject), CI only reports it for now
ruff check .                                         # lint (CI fails on it); config in pyproject.toml, modules/ruff.toml
python packaging/build.py [--version X] [--package]  # bundle → packaging/dist/ClinReport (+ installer); ~5 min, cached
packaging/dist/ClinReport/python/python -I -m clinreport_desktop [--headless | --selftest out.json | --quit]
python launchers/cli/cli.py RESULT.sqlite -m default|lpwgs|10x -o OUT --no-ru-annotations
```

Set `CLINREPORT_DATA_DIR=<tmp>` when running the desktop launcher so your real data folder is not used.

## Rules

1. **Clinician features live in the extension** (`clinreport_core/service.py` + `route.py` + the review page). The desktop
   app and the CLI call the same `service` functions; never copy logic into a launcher.
2. **Module code stays Python 3.8-compatible and framework-free**: `from __future__ import annotations`, no `match`, no
   `X | Y` outside annotations; no pandas/numpy; `sqlalchemy`/`psycopg2` imported lazily. `route.py` only adapts handlers to
   aiohttp (OpenCRAVAT 2.x) and Flask (3.x); route paths are a single segment (3.x limitation).
3. **Never write to a result `.sqlite`** — the OpenCRAVAT viewer owns it. **Never commit `*.sqlite`** — results contain
   patient data (git-ignored; tests skip without `CLINREPORT_EXAMPLES`).
4. **User data never lives in program or module folders.** Settings and the lab's own templates: OpenCRAVAT conf dir
   (`clinreport.json`, `clinreport/templates/`). Desktop app: `%LOCALAPPDATA%\ClinReport` / `~/Library/Application
   Support/ClinReport`. Module folders and `{app}` are replaced on every update.
5. **Installer invariants** (`packaging/windows/ClinReport.iss`, tested in `tests/packaging/test_installer.py`): never
   change `AppGuid`; only `{app}\python` and `{app}\modules` are deleted; the launcher mutex name matches
   `instance.MUTEX_NAME`.
6. **One version number**: `pyproject.toml` `version`, both module `.yml` `version:` + `release_note`, and a
   `CHANGELOG.md` section move together (`tests/packaging/test_build.py`). Tags are `vX.Y.Z` / `vX.Y.Z-rcN`.
7. **The stack is pinned in `packaging/stack.toml`**; `requirements-dev.txt` and CI follow it (tested). After an OpenCRAVAT
   bump, re-check `clinreport_oc_compat.py` on Windows ([docs/development/packaging.md](docs/development/packaging.md)).
8. **Language**: user-facing text (UI, messages, `docs/guides/`) in Russian; code, comments, other docs in English.
9. **A decision that is costly to reverse gets an ADR** in `docs/decisions/` (next free number; never edit an accepted
   one — supersede it). Open problems go to `docs/issues/`.
10. **Do not commit.** Stage one logical change, show `git diff --cached --stat` and propose a commit message; the
    maintainer reviews and commits.

## Pitfalls (each one has bitten before)

- The desktop launcher **kills every process running from the bundle's Python** at start-up (leftover OpenCRAVAT workers).
  Do not run checks with `packaging/dist/ClinReport/python` while starting the app — use another Python for them.
- **Inno Setup fails on paths over 260 characters** ("The system cannot find the path specified" at "Updating icons"):
  build under a short path; `packaging/dist` is fine, a deep temp folder is not.
- **Git Bash rewrites `/D…` and `/Q` switches** passed to `ISCC.exe` into paths: prefix with `MSYS_NO_PATHCONV=1`.
- `tests/` subfolders have no `__init__.py`; shared helpers live in `tests/helpers.py` (on pytest's `pythonpath`) —
  do not import one test module from another.
- On macOS, `build.py --package` **moves** the bundle into `ClinReport.app`; test the bundle before packaging
  (`--package-only` packages an existing one).
- pip on a new macOS picks wheels for that macOS (e.g. numpy's Accelerate build needs 14); `build.py` re-fetches them for
  `stack.toml [macos_minimum]` and fails if any binary needs more — do not bypass that check.
- A changed `route.py` or `clinreport_core/` needs `oc gui` restarted; static files only a browser reload. The desktop
  app re-syncs our modules from the bundle on every start.

## Before you finish

`python -m pytest` and `ruff check .` pass; docs touched by the change are updated (guides, reference, AGENTS.md if a rule
or command changed); a new decision has its ADR; `CHANGELOG.md` has an entry under `[Unreleased]` for user-visible changes.
