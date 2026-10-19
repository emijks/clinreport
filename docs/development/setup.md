# Development setup

## Environment

Python **3.13** (the version in `packaging/stack.toml`); everything else comes from one file:

```text
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt        # Windows: .venv\Scripts\pip
```

That installs OpenCRAVAT 3.2.3, the extension's and the launcher's dependencies (`packaging/requirements.txt`), pytest,
pytest-cov and ruff. Then `python -m pytest` and `ruff check .` must pass ([testing.md](testing.md)).

Example results (patient data, never committed): put `trio1.sqlite` (legacy column layout, three samples) and
`pah2.vevat_annotated.sqlite` (new layout, one sample without an id) into a folder outside the repository and set
`CLINREPORT_EXAMPLES` to it, or into `tests/examples/` (git-ignored).

## Running the extension in OpenCRAVAT

**Linux, macOS (and WSL):** OpenCRAVAT 3.2.3 runs natively.

```text
python packaging/install_extension.py --no-deps      # copies modules/ into `oc config md`
oc module install hg38 wgnote -y                     # base modules: the viewer needs hg38, Notes need wgnote
oc gui path/to/result.sqlite                         # opens the viewer; Summary tab → «Открыть окно заключения»
oc gui --webapp clinreport                           # the review page without a result (path field)
```

**Windows:** OpenCRAVAT 3.2.3 needs the desktop app's start-up patches ([packaging.md](packaging.md#opencravat-3x-on-windows)),
so use the built bundle — it is a complete OpenCRAVAT with the extension:

```text
python packaging/build.py                                          # once, ~5 min; packaging/dist/ClinReport
set CLINREPORT_DATA_DIR=%TEMP%\clinreport-dev                      # a throw-away data folder
packaging\dist\ClinReport\python\python -I -m clinreport_desktop  # the window; or --headless (prints the address)
```

## Edit → see loop

| You changed | Linux/macOS `oc gui` | Windows bundle |
|---|---|---|
| `static/*`, `index.html` | `install_extension.py --no-deps`, reload the page | copy `modules/` over `packaging/dist/ClinReport/modules/`, restart the app (it re-syncs our modules on start) |
| `wgclinreport.js` | same, **hard-reload** the viewer (Ctrl+F5) | same, hard-reload |
| `route.py`, `clinreport_core/*`, templates, `*.yml` | same, **restart `oc gui`** (imported once) | same, restart the app |
| `launchers/desktop/clinreport_desktop/*` | — | copy it over `packaging/dist/ClinReport/python/Lib/site-packages/clinreport_desktop` (macOS: `python/lib/python3.13/site-packages`), restart |

`install_extension.py` replaces the module folders entirely; settings and the lab's templates live in the conf dir and survive.

## Debugging

- The review page's error dialog shows the server traceback (HTTP 500); handler exceptions are **not** in OpenCRAVAT's log.
- Every page call is a plain `fetch` (DevTools → Network), easy to replay:
  `curl -G http://localhost:8080/webapps/clinreport/open --data-urlencode "dbpath=/path/to/result.sqlite"`.
- Handlers without a GUI: the `service` fixture in `tests/conftest.py` (temp conf/jobs dirs, no network), or
  `cd modules/webapps/clinreport && python -c "from clinreport_core import service; …"`.
- Desktop app: `<data>/logs/launcher.log` (window, updates), the server log in the window's Журнал tab
  («Скопировать диагностику»), `<data>/logs/update-setup.log` after an in-app update.
- A viewer stuck on «Retrieving Data…» with nothing in the log: a request is hanging (OpenCRAVAT logs a request when it
  completes); watch DevTools → Network for the pending one.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Viewer spinner forever, `variantcols` 500 | gene mapper `hg38` not installed | `oc module install hg38` (the desktop app ships it) |
| No Note box in the variant detail panel | `wgnote` not installed | `oc module install wgnote` |
| ClinReport card missing on the Summary tab | module not installed / `oc gui` not restarted / hidden in the viewer layout | reinstall, restart, check the viewer's widget menu |
| OC 3.x on Windows: `OSError [WinError 123] … '/C:'` | OpenCRAVAT's Celery path bug | use the desktop bundle (patched) |
| `oc module …` → `ConnectTimeoutError store.opencravat.org` | the lab VPN blocks the Store | turn the VPN off while installing ([issue clinreport/004](../issues/clinreport/004-store-unreachable-dev-machine.md)) |
| `ImportError: DLL load failed … Application Control policy` | Windows Smart App Control blocks unsigned DLLs | turn it off, or see [issue desktop/002](../issues/desktop/002-code-signing.md) |
| A check started with the bundle's Python dies when the app starts | the launcher stops every process of the bundle's Python on start | run checks with another Python |
| `ISCC.exe`: "The system cannot find the path specified" at "Updating icons" | a source path over 260 characters | build under a short path (`packaging/dist` is fine) |
| Git Bash: `/D…` switches or `/data/…` arrive as `C:/Program Files/Git/…` | MSYS path conversion | prefix the command with `MSYS_NO_PATHCONV=1` |
| `UnicodeEncodeError: 'charmap'` printing Russian | Windows console code page | `set PYTHONUTF8=1` (CI sets it) |
| OpenCRAVAT 2.2.9 (extension route): `No module named 'imp'` / `'pkg_resources'` | 2.x needs Python < 3.12 and `setuptools<81` | [issue clinreport/003](../issues/clinreport/003-python-version-constraints.md) |
