# Packaging: the desktop app, installers, the extension zip

The desktop app is OpenCRAVAT + ClinReport for one Windows or macOS user, with a small control window: **no Docker, no
separate Python, no administrator rights**. It runs the same extension as any OpenCRAVAT
([ADR 0004](../decisions/0004-features-live-in-the-extension.md)); only the launcher and the packaging are desktop-specific.

## The pinned stack — `packaging/stack.toml`

| Key | Used for |
|---|---|
| `python`, `pbs_release` | the [python-build-standalone](https://github.com/astral-sh/python-build-standalone) CPython in the bundle (checksum-verified) |
| `opencravat` | `pip install open-cravat==…` in the bundle; `requirements-dev.txt` and CI must match (tested) |
| `karchinlab_modules_ref`, `base_modules` | hg38, wgnote, excelreporter from KarchinLab's modules repository at that commit |
| `update_repo` | the GitHub repository whose `v*` releases the in-app update reads (empty = off) |
| `[macos_minimum]` | oldest macOS per architecture (x64 10.15, arm64 11.0), enforced by the build |

Packages the bundle installs next to OpenCRAVAT: `packaging/requirements.txt` (docxtpl and the Postgres client for our
modules; pywebview, psutil, pywin32 for the launcher).

**Bumping OpenCRAVAT:** change `opencravat` in `stack.toml` and `requirements-dev.txt`, run the tests, build on Windows and
re-check [the Windows patches](#opencravat-3x-on-windows) (drop the ones OpenCRAVAT fixed,
[issue desktop/006](../issues/desktop/006-upstream-windows-fixes.md)), run the checklist in [testing.md](testing.md),
update the version matrix in [reference/opencravat-integration.md](../reference/opencravat-integration.md).

## Building

```
python packaging/build.py [--version 3.0.0] [--package | --package-only] [--out packaging/dist]

packaging/dist/ClinReport/
├── python/      CPython + open-cravat + packaging/requirements.txt + the launcher (clinreport_desktop)
│                + clinreport_oc_compat.py/.pth (OpenCRAVAT patches, below)
├── modules/     base modules + our modules/<type>/<module> (*.md left out)
└── bundle.json  versions, build time, "managed" (our modules), update repository
```

Run it with any Python ≥ 3.11; nothing is installed into that Python. Downloads (CPython, base modules) are cached in
`packaging/.cache`. The version defaults to `git describe` of the `v*` tags.

`--package` (or `--package-only` for an existing bundle) must run on the target platform:

- **Windows** → Inno Setup (`ISCC.exe`; per-user install to `%LOCALAPPDATA%\Programs\ClinReport`):
  `ClinReport-<version>-win-x64-setup.exe`.
- **macOS** → `ClinReport.app` (ad-hoc `codesign`) in `ClinReport-<version>-macos-<arm64|x64>.dmg` (`hdiutil`).
  Packaging **moves** the bundle into the `.app` — test it before packaging.
- **Linux** → `.tar.gz` (testing only).

Why a real Python and not PyInstaller: OpenCRAVAT runs `oc report`, `oc util …` and `pip install` by name and imports
module code from disk; a frozen executable has neither ([ADR 0006](../decisions/0006-bundle-portable-python.md)). The app
creates `oc`/`pip` for its Python at start-up (pip's own launchers hard-code the build path).

### macOS: oldest supported system

pip on a new macOS picks wheels built for that macOS (numpy's Accelerate build needs macOS 14). After installing,
`build.py` reads every package's `.dist-info/WHEEL` tags and re-downloads, for `[macos_minimum]`, any package whose wheel
needs a newer system (`pip download --platform macosx_10_15_x86_64 …`); before finishing it checks every Mach-O file in
the bundle with `otool -l` (`LC_BUILD_VERSION minos` / `LC_VERSION_MIN_MACOSX`) and **fails the build** listing the
offenders. `Info.plist`'s `LSMinimumSystemVersion` comes from the same value
([ADR 0011](../decisions/0011-macos-minimum-versions.md)). No CI runner has macOS 10.15; a real launch there needs an old Mac.

## The Windows installer — `packaging/windows/ClinReport.iss`

- **Per-user**, no administrator rights; program in `%LOCALAPPDATA%\Programs\ClinReport`, data in
  `%LOCALAPPDATA%\ClinReport` ([ADR 0010](../decisions/0010-windows-installer-per-user-inno-setup.md)).
- **Updating = installing over the old version.** `AppGuid` never changes; `[InstallDelete]` removes only `{app}\python`
  and `{app}\modules` (packages dropped from the bundle must not linger); user data is never a target.
  `tests/packaging/test_installer.py` enforces all three.
- **Closing a running ClinReport** before files are replaced (and before uninstalling): the installed copy's
  `--quit`; then wait up to 10 s for the launcher's mutex `ClinReportLauncher`; then, as a safety net, PowerShell stops
  every process whose executable is under `{app}` (older copies without `--quit`, hung processes). Without this, Windows'
  Restart Manager lists the bundle's processes as several "Python" applications on "Preparing to Install".
- The welcome page says whether it installs or updates (`DisplayVersion` of the installed copy → new version); the ready
  page lists the ClinReport, OpenCRAVAT and Python versions and the kept data folder.
- `/SILENT /RELAUNCH=1` (used by the in-app update) starts the new version after installing.
- Wizard images: `wizard-large-*.bmp`, `wizard-small-*.bmp` at 100/150/200 %, drawn by `packaging/make_icons.py` (Pillow;
  run it after a design change and commit the outputs).

## OpenCRAVAT 3.x on Windows

OpenCRAVAT 3.2.3 does not run natively on Windows as released (checked 2026-10-15):

1. `cravat/gui/config.py` builds `f'/{work_dir}/celery/results'` → `/C:/…` → `WinError 123` at start-up.
2. Celery's default `prefork` pool cannot start on Windows (`Can't pickle local object 'celery_init_app.<locals>.FlaskTask'`),
   so background jobs (reports from the Jobs page, Store installs) hang. The `threads` pool is no fix: Store installs then
   fail with `signal only works in main thread`.
3. kombu's filesystem broker imports `pywintypes` on Windows → `pywin32` (`packaging/requirements.txt`).

`launchers/desktop/clinreport_oc_compat.py` is imported at interpreter start (a `.pth` file) and, only when
`CLINREPORT_DESKTOP=1` (set by the launcher for the server process), patches `cravat.gui.config` after it is imported and
makes Celery use the `solo` pool (on all platforms, for identical behaviour). No OpenCRAVAT file is edited.

## What the launcher does — `launchers/desktop/clinreport_desktop/`

1. A second start hands its file to the running window and exits (`instance.py`: localhost endpoint + token); the running
   launcher holds the mutex `ClinReportLauncher` (Windows) for the installer.
2. OpenCRAVAT processes left by a crashed session are stopped: anything started from its `bin/`, and anything running the
   bundle's Python except launcher processes.
3. `conf/cravat-system.yml` is written for this user's folders and a port (first free from 8060, or fixed in Настройки);
   `OPENCRAVAT_SYSTEM_CONF_PATH` points OpenCRAVAT at it, so another OpenCRAVAT on the computer is never touched.
4. Bundled modules are synced into the user's `modules/`: ours (`managed`) replaced when changed, base modules only if
   missing (a Store-installed hg38 with its database wins).
5. `oc`/`pip` are created in `bin/` when the interpreter moved; Store modules' Python packages go to `python-packages/`.
6. `oc gui --headless --port N` starts without a console; when the review page answers, the Russian annotations are
   fetched and, if enabled, the browser opens. The update check runs in the background
   ([ADR 0009](../decisions/0009-in-app-updates-from-github-releases.md)). Closing the window stops the process tree.

The window (`ui/`: plain HTML/CSS/JS in pywebview — WebView2 on Windows, WebKit on macOS) talks only to `api.py`.
Templates and report settings go through ClinReport's own `service` functions in-process (`CLINREPORT_CONF_DIR` = the
user's conf dir, `CLINREPORT_EDITION=desktop`), so the window and the browser page agree.

## Checking a build

```text
packaging/dist/ClinReport/python/python -I -m clinreport_desktop --headless      # prints "ClinReport: http://localhost:N"
curl -sf http://localhost:N/webapps/clinreport/index.html                         # + /webapps/clinreport/templates, /result/service/widgetlist
packaging/dist/ClinReport/python/python -I -m clinreport_desktop --quit
packaging/dist/ClinReport/python/python -I -m clinreport_desktop --selftest out.json   # opens the real window, checks it, closes
```

CI runs exactly these on Windows, macOS arm64 and macOS x64 for every push (`.github/workflows/ci.yml`), then packages.
Set `CLINREPORT_DATA_DIR` to a throw-away folder; run any other checks with a Python other than the bundle's (the launcher
stops the bundle's other processes on start).

## The extension zip

`release.yml` packs `packaging/install_extension.py` + `modules/` into `clinreport-extension-<version>.zip`. Users run
`<OpenCRAVAT python> install_extension.py [--with-db]`; running it again updates. It works from the zip and from the
repository (finds `modules/` next to itself or one level up).
