# AGENTS.md — ClinReport

Instructions for coding agents (and a fast overview for people). Product overview: [README.md](README.md).
Background and the reasons behind the rules: [docs/](docs/README.md), especially [decisions](docs/decisions/README.md).

## Map

| Path | What | When you change it |
|---|---|---|
| `modules/webapps/clinreport/` | OpenCRAVAT webapp: `route.py` (HTTP), `index.html` + `static/` (review page), `templates/*.docx` | features clinicians use |
| `modules/webapps/clinreport/clinreport_core/` | report logic: `service.py` (handlers), `process.py` (report content), `database.py`, `templates.py` (registry, checks), `labels.py` (page layouts) | almost every feature |
| `modules/webapps/clinreport/templates/` | built-in templates, **one id, a file per format**: `docx/<id>.docx` (Word), `html/<id>/` (Jinja HTML + CSS Paged Media → HTML and PDF) | adding/changing a template ([templates.md](docs/development/templates.md)) |
| `modules/webapps/clinreport/clinreport_core/output.py` | every format: DOCX, self-contained HTML, PDF (WeasyPrint → else the browser with Paged.js) | formats, PDF engines |
| `modules/webapps/clinreport/clinreport_core/screening.py` | report kind «Профилактический ДНК-скрининг»: context (Notes 1/2), checks, citations, rich text | the screening report; model for a new kind |
| `modules/webapps/clinreport/vendor/pagedjs/` | Paged.js 0.4.3 (MIT, sha256-pinned): browser PDFs on macOS / without Pango | a Paged.js update |
| `modules/webviewerwidgets/wgclinreport/` | Summary-tab button that opens the review page | the entry point in the viewer |
| `launchers/desktop/clinreport_desktop/` | desktop control window (pywebview), starts OpenCRAVAT, updates | desktop-only behaviour |
| `launchers/desktop/clinreport_desktop/linuxapp.py` | Linux: `--install` / `--uninstall [--purge]`, the menu entry, «Место на диске», the in-app update swap ([ADR 0016](docs/decisions/0016-linux-desktop.md)) | Linux install/update/removal |
| `launchers/desktop/clinreport_desktop/isolation.py` | Linux: caches and temp files into the data folder (`XDG_CACHE_HOME`, `TMPDIR`, `PIP_CACHE_DIR`); the user's environment for the browser/file manager | anything that starts a program for the user |
| `launchers/desktop/clinreport_desktop/environments.py` | other OpenCRAVAT installations: find (no side effects), judge, install our modules ([ADR 0015](docs/decisions/0015-run-on-an-existing-opencravat.md)) | «Окружения»; after a new OpenCRAVAT release (the matrix in `assess`) |
| `launchers/desktop/clinreport_oc_compat.py` | patches that make OpenCRAVAT 3.2.3 run on Windows | after an OpenCRAVAT bump |
| `launchers/desktop/clinreport_desktop/webview_compat.py` | patches that make pywebview 6.2.1 run on macOS 10.15 | after a pywebview bump |
| `launchers/cli/cli.py` | command-line tool on `clinreport_core.service` | CLI options |
| `packaging/` | `build.py` (bundle + installers), `stack.toml` (pinned versions), `windows/ClinReport.iss`, `macos/`, `install_extension.py`, `check_pdf.py` (a bundle's PDF engine), `make_screening_docx.py` (generates `templates/docx/screening.docx`) | builds, installers, pins |
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
packaging/dist/ClinReport/clinreport [--install | --uninstall [--purge]]    # Linux (xvfb-run -a for a window without a display)
python launchers/cli/cli.py RESULT.sqlite -m default|lpwgs|10x -o OUT --no-ru-annotations
python packaging/make_screening_docx.py              # regenerate templates/docx/screening.docx after a text change
packaging/dist/ClinReport/python/bin/python3 -I packaging/check_pdf.py packaging/dist/ClinReport OUT   # PDF engine of a bundle
CLINREPORT_PDF_ENGINE=browser …                      # force the browser PDF path (what macOS gets)
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
   Support/ClinReport` / `~/.local/share/clinreport` (Linux: the program is its `app/` subfolder, the only part an
   update replaces). Module folders and `{app}` are replaced on every update. On Linux nothing else may be written outside
   that folder (CI checks it): open programs for the user with `isolation.open_url` / `popen_for_user`, never
   `webbrowser.open` or a bare `Popen`; temporary folders go to `paths.tmp_dir()`.
5. **Installer invariants** (`packaging/windows/ClinReport.iss`, tested in `tests/packaging/test_installer.py`): never
   change `AppGuid`; only `{app}\python`, `{app}\modules` and `{app}\weasyprint` are deleted; the launcher mutex name
   matches `instance.MUTEX_NAME`.
6. **One version number**: `pyproject.toml` `version`, both module `.yml` `version:` + `release_note`, and a
   `CHANGELOG.md` section move together (`tests/packaging/test_build.py`). Tags are `vX.Y.Z` / `vX.Y.Z-rcN`.
7. **The stack is pinned in `packaging/stack.toml`**; `requirements-dev.txt` and CI follow it (tested). After an OpenCRAVAT
   bump, re-check `clinreport_oc_compat.py` on Windows ([docs/development/packaging.md](docs/development/packaging.md)).
8. **Language**: user-facing text (UI, messages, `docs/guides/`) in Russian; code, comments, other docs in English.
9. **A decision that is costly to reverse gets an ADR** in `docs/decisions/` (next free number; never edit an accepted
   one — supersede it). Open problems go to `docs/issues/`.
10. **Templates and report output** ([templates.md](docs/development/templates.md)): a built-in template is one id
    in `templates.BUILTIN` with a file per format; HTML templates use only CSS both PDF engines read, embed everything
    (`inline_css`, `asset`; no outside URL, no `<script>`), keep the CSP meta, and show report data escaped — rich text
    only through `| rich`, never `| safe`. One WeasyPrint release everywhere (`requirements.txt` = `stack.toml`). The
    lab's own uploaded templates stay Word only.
11. **Do not commit.** Stage one logical change, show `git diff --cached --stat` and propose a commit message; the
    maintainer reviews and commits.

## Adding a template (follow this)

Read [docs/development/templates.md](docs/development/templates.md) first, then pick the recipe:

1. **Word template for an existing kind** — `templates/docx/<ID>.docx` + `('<ID>', '<title>', '<kind>')` in
   `templates.BUILTIN`. Fields: `templates.field_paths(kind)`.
2. **HTML/PDF template for an existing kind** — copy `templates/html/screening/` to `templates/html/<id>/`, keep the
   head of `template.html` (CSP meta, `inline_css`), write sections with the kind's fields, fonts as WOFF2 + license,
   `NOTICE.txt` (not `.md`), a `BUILTIN` entry. A `docx/<id>.docx` with the same id adds Word to the same choice.
3. **New report kind** — the 9-step table in templates.md (builder → `MODES`/button → checks/`prepare` →
   `output.namespace_for` → `KINDS`/`example_context` → `LAYOUTS` (+ `add_rows`, `lists`) → templates → tests → docs);
   `screening` is the worked example.

Done when: `python -m pytest` (the built-in check renders **every format of every template** with the kind's example and
fails on unknown fields), `ruff check .`, the PDF looked at (WeasyPrint) and the browser path tried
(`CLINREPORT_PDF_ENGINE=browser`, «Сохранить как…» → PDF), data model §3/§4 + the guide + CHANGELOG updated.

## Pitfalls (each one has bitten before)

- The desktop launcher **kills every process running from the bundle's Python** at start-up (leftover OpenCRAVAT workers).
  Do not run checks with `packaging/dist/ClinReport/python` while starting the app — use another Python for them.
- **Inno Setup fails on paths over 260 characters** ("The system cannot find the path specified" at "Updating icons"):
  build under a short path; `packaging/dist` is fine, a deep temp folder is not.
- **Git Bash rewrites `/D…` and `/Q` switches** passed to `ISCC.exe` into paths: prefix with `MSYS_NO_PATHCONV=1`.
- **Linux builds need PyGObject's build dependencies** (`pkg-config libgirepository-2.0-dev libcairo2-dev`), also for
  `pip install -r requirements-dev.txt`: there are no Linux wheels. Users need only the desktop's WebKitGTK.
- **Linux: a window self-test opens a real window** (and the `--headless` start opens the browser if «Открывать
  OpenCRAVAT в браузере» is on); on a machine someone is using, prefer `CLINREPORT_DATA_DIR=<tmp>` and expect it.
- **Paged.js cannot read CSS over `file://`** (the browser blocks its `fetch`): it lays out zero pages. Our HTML inlines
  the CSS; to try a template by hand, serve it over HTTP. Headless `chromium --print-to-pdf` prints *before* Paged.js
  finishes — drive Chromium over DevTools and wait for `.pagedjs_page` instead.
- **No new tabs for printing**: Safari blocks a window opened after an `await` (the report check, the request), so the
  browser PDF is laid out and printed in a hidden, off-screen iframe (`printReport`; `display:none` would leave Paged.js
  nothing to measure). The save picker after the «Сохранить с «_»» click still counts as the user's gesture.
- **WeasyPrint ≥ 70 stops a render with `FatalURLFetchingError`, a `BaseException`** — `except Exception` misses it;
  `output.html_to_pdf` converts it. Its `url_fetcher` is a `URLFetcher` object now, not a function.
- **`build.py` drops `*.md` from modules**: license and notice files in a template or `vendor/` must not be Markdown.
- **psutil 7.2.2 `wait_procs` raises `OSError` EINVAL on Linux** (pidfd_open on a process whose main thread exited
  first — OpenCRAVAT's right after `terminate()`): wait with `server.wait_gone`, which falls back to polling.
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
