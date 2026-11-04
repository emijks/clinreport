# Packaging: the desktop app, installers, the extension zip

The desktop app is OpenCRAVAT + ClinReport for one Windows, macOS or Linux user, with a small control window: **no Docker, no
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
modules; pywebview, psutil, pywin32 (Windows), PyGObject + pycairo (Linux) for the launcher).

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
  `ClinReport-<version>-windows-x64.exe`.
- **macOS** → `ClinReport.app` (ad-hoc `codesign`) in `ClinReport-<version>-macos-<arm64|x64>.dmg` (`hdiutil`).
  Packaging **moves** the bundle into the `.app` — test it before packaging.
- **Linux** → `ClinReport-<version>-linux-x64.tar.gz` with one folder, `ClinReport/` (start script `clinreport`, icon
  `clinreport.png`; both are written by the build itself, so the bundle can be installed before packaging). The archive
  leaves out `__pycache__` and the folders OpenCRAVAT creates in its package folder when the bundle was test-run.
  Building needs `pkg-config libgirepository-2.0-dev libcairo2-dev` (pip builds PyGObject; there are no Linux wheels).
  [Below](#linux-one-folder-gtk-window).

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

## Linux: one folder, GTK window

[ADR 0016](../decisions/0016-linux-desktop.md). Everything is in `~/.local/share/clinreport`:

```
~/.local/share/clinreport/
├── app/              the program — `clinreport --install` copies the extracted archive here; replaced on update
├── conf/ modules/ jobs/ logs/ python-packages/ …    the user's data, as on the other platforms
├── cache/            XDG_CACHE_HOME of the app: WebKit, Mesa shader cache, pip (PIP_CACHE_DIR)
├── tmp/              TMPDIR of the app; emptied at every start
└── .clinreport-data  marker: `--purge` deletes only a folder that has it
```

Outside: `~/.local/share/applications/clinreport.desktop` (Icon is the absolute path of `app/clinreport.png`;
`StartupWMClass=clinreport` = `GLib.set_prgname` in the launcher), the link `~/.local/bin/clinreport`, and
`~/.config/autostart/clinreport.desktop` while «Запускать при входе» is on.

- **`isolation.py`**: `contain()` sets `XDG_CACHE_HOME`, `TMPDIR`, `PIP_CACHE_DIR` before GTK is loaded, so the launcher,
  WebKit's processes and OpenCRAVAT write there; `user_env()` / `open_url()` / `popen_for_user()` give programs started
  for the user (xdg-open, the browser) the environment as it was — a browser started by us must not keep its cache in
  our folder. Work folders of the module installs go to `tmp/` on every platform.
- **`linuxapp.py`**: `install` (copy to `.app.new`, swap with `app/`, write the entries; a foreign `clinreport.desktop` —
  one without `X-ClinReport-Bundle` — is never overwritten), `uninstall` (`PROGRAM_PARTS` only; `purge` = the whole folder,
  with the marker check), `folder_sizes`/`clear_cache` for «Место на диске», `unpack_update`/`apply_update`.
- **Update:** the asset `…-linux-x64.tar.gz` is downloaded to `updates/`, unpacked to `.app.new` (tarfile `data` filter;
  one top folder; `bundle.json` platform must match) and a detached `sh` (`linuxapp.UPDATE_SCRIPT`) waits until the
  launcher's process is gone (not merely a zombie), renames `app` → `.app.old`, `.app.new` → `app`, removes the old one
  and starts `app/clinreport`. The launcher removes `.app.new`/`.app.old` left by an interrupted update at start.
- **Window:** pywebview `gui='gtk'` on the system's WebKitGTK (API 4.1, else 4.0). `linux_webkit()` names the program
  and checks that WebKit loads; without it the launcher logs and shows (`notify-send`) the `apt`/`dnf` command and runs
  OpenCRAVAT in the browser (`run_browser_only`). The session log records the distribution, desktop, X11/Wayland, the
  WebKitGTK version and whether this is the installed copy.
- **Uninstall from the window** sets `App.pending_uninstall` and closes; `main()` removes after the window and WebKit
  are gone (WebKit writes its storage on exit and would recreate `webview/`).
- **CI** (`ubuntu-24.04`): the usual headless and window checks (`xvfb-run`), then `--install`, the window self-test of the
  installed copy, `--uninstall --purge` in a throw-away `HOME`, and it fails if any file is left there.

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

The window (`ui/`: plain HTML/CSS/JS in pywebview — WebView2 on Windows, WebKit on macOS, WebKitGTK on Linux) talks
only to `api.py`.
pywebview gets the page as one document (`window_page()` inlines `app.css` and `app.js`), not as a file path: a path would
start pywebview's HTTP server on the fixed port 42001, shared by every pywebview app — when another program holds it the
window stays empty on macOS and shows that program's page on Windows ([issue desktop/007](../issues/desktop/007-empty-window-macos.md)).
So the page must not load files (no `src`/`href` to `ui/`). It must run on Safari 13 (macOS 10.15): `app.js` avoids newer
syntax and APIs, and the inline script in `index.html` supplies `replaceChildren`; `tests/desktop/test_window_page.py`
checks both.

On macOS < 11.3 pywebview 6.2.1 would never load the page at all: its navigation handler calls
`WKNavigationAction.shouldPerformDownload` (macOS 11.3+), the call raises and WebKit never gets an answer.
`webview_compat.py` supplies the method there before the window is created. No CI runner has such a macOS — after a
pywebview bump, re-read `webview/platforms/cocoa.py` for WebKit calls newer than 10.15 on the page-load path.

### Logs

`sessionlog.py` writes `logs/launcher.log` (INFO, all sessions, rotated) and `logs/sessions/session-<id>.log` (one launch
at DEBUG for `clinreport.*` and `pywebview`; the newest 20 kept). macOS keeps `logs/` in `~/Library/Logs/ClinReport`
unless `CLINREPORT_DATA_DIR` is set. A session log starts with the machine (OS, WebKit/Safari or WebView2, executable,
App Translocation) and also gets what is otherwise lost without a terminal: uncaught exceptions in any thread, native
crash dumps (`faulthandler`, not on Windows: .NET's handled exceptions would flood it), stdout/stderr when they go
nowhere (Finder, `pythonw.exe`), failed page loads in WebKit (pywebview ignores them, and shows the web view only after a
load finishes — a failed load leaves an empty window), and the page's own errors: the inline script at the top of
`ui/index.html` (old JavaScript on purpose) sends them to `Api.client_log`; `app.js` reports `ready` after `init()`, and
the launcher logs a warning if that has not come 20 s after the window opened. `--selftest` requires `ready`.
Templates and report settings go through ClinReport's own `service` functions in-process (`CLINREPORT_CONF_DIR` = the
user's conf dir, `CLINREPORT_EDITION=desktop`), so the window and the browser page agree.

## Checking a build

```text
packaging/dist/ClinReport/python/python -I -m clinreport_desktop --headless      # prints "ClinReport: http://localhost:N"
curl -sf http://localhost:N/webapps/clinreport/index.html                         # + /webapps/clinreport/templates, /result/service/widgetlist
packaging/dist/ClinReport/python/python -I -m clinreport_desktop --quit
packaging/dist/ClinReport/python/python -I -m clinreport_desktop --selftest out.json   # opens the real window, checks it, closes
```

CI runs exactly these on Windows, macOS arm64, macOS x64 and Linux x64 for every push (`.github/workflows/ci.yml`),
then packages. On Linux, run the window under `xvfb-run -a` when there is no display.
Set `CLINREPORT_DATA_DIR` to a throw-away folder; run any other checks with a Python other than the bundle's (the launcher
stops the bundle's other processes on start).

## The extension zip

`release.yml` packs `packaging/install_extension.py` + `modules/` into `clinreport-extension-<version>.zip`. Users run
`<OpenCRAVAT python> install_extension.py [--with-db]`; running it again updates. It works from the zip and from the
repository (finds `modules/` next to itself or one level up).
