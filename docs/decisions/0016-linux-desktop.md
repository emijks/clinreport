# 0016 · The desktop app on Linux: GTK window, one folder, self-update from the archive

Status: accepted (2026-11-05)

## Context

The desktop app shipped for Windows and macOS; on Linux there was only a "testing" `.tar.gz` with no working window
toolkit, no menu entry, no uninstall and no update. Development and testing now happen on Linux (Debian 13, GNOME), and
the lab asked for an app that can be removed without a trace: on Linux, programs and the libraries under them
scatter files over `~/.cache`, `/tmp`, `~/.local/share/<name>` by default.

Measured with the 3.0.2 launcher on Debian 13: OpenCRAVAT already keeps to its folders (our `cravat-system.yml`; on Linux
the folders its `constants.py` creates on import land in its own package folder, i.e. inside the bundle). What escaped
was WebKit's GPU-process shader cache (`~/.cache/mesa_shader_cache_db`), Python temp files in `/tmp`, and pip's cache
when Store modules install packages.

## Decision

1. **Window: pywebview's GTK backend on the system's WebKitGTK**, with PyGObject built into the bundle. GNOME and most
   desktops ship WebKitGTK; the bundle grows by a few MB. Rejected: Qt WebEngine (+250–400 MB, a whole Chromium; PyQt6 is
   GPL) and a browser-only control UI (a second UI to keep in step with the window). Without WebKitGTK the launcher says
   how to install it and runs OpenCRAVAT in the browser instead.
2. **One folder: `~/.local/share/clinreport`** (`XDG_DATA_HOME`). The program goes to `app/` inside it, next to the data
   as on the other platforms (conf, modules, jobs, logs…); caches to `cache/`, temporary files to `tmp/` (emptied at every
   start). The launcher sets `XDG_CACHE_HOME`, `TMPDIR` and `PIP_CACHE_DIR` for itself and everything it starts
   (WebKit's processes, OpenCRAVAT); programs it opens for the user (browser, file manager) get the user's environment
   back (`isolation.py`). Outside the folder: the menu entry `~/.local/share/applications/clinreport.desktop` (its icon
   is a path into `app/`, so no icon theme is touched), the link `~/.local/bin/clinreport`, and the autostart entry when
   it is on.
3. **Install and remove from the archive itself**: `ClinReport/clinreport --install` copies the folder into `app/` and
   writes the two entries; `clinreport --uninstall` removes the program, caches and entries and keeps the user's data;
   `--purge` removes the data folder too — only if it carries the `.clinreport-data` marker. The same from the window:
   Настройки → «Место на диске» → «Удалить ClinReport…» (done after the window has closed, because WebKit writes its
   storage on exit). CI installs, runs the window, purges and fails if any file is left in the throw-away home.
4. **In-app update from the release archive** for the installed copy: download (size and SHA-256 checked), unpack to
   `.app.new`, check `bundle.json` (platform), close; a detached `sh` waits until the launcher is gone, swaps `app/` and
   starts the new version. A copy run from elsewhere opens the release page, as on macOS.
5. **Supported:** x86-64 distributions with glib ≥ 2.80 and WebKitGTK 4.1 or 4.0 — Debian 13, Ubuntu 24.04+, Fedora 40+ —
   because PyGObject 3.58 needs `girepository-2.0`. The release build runs on `ubuntu-24.04`.

## Consequences

- Building on Linux needs `pkg-config libgirepository-2.0-dev libcairo2-dev` (PyGObject has no Linux wheels); so does
  `pip install -r requirements-dev.txt` on Linux. Users need none of them.
- Rule 4 of AGENTS.md ("user data never lives in program folders") still holds: `app/` is a sibling of the data and is
  the only thing an update replaces.
- Desktop-session bookkeeping is outside our control and stays: GNOME records the app in
  `~/.local/share/gnome-shell/application_state`, as for every application.
- Older distributions (Ubuntu 22.04, Debian 12) would need PyGObject < 3.51 and a build on the oldest supported system;
  revisit if a lab needs them.
- WebKitGTK may show an empty window on some Wayland + NVIDIA setups; `WEBKIT_DISABLE_DMABUF_RENDERER=1` is the known
  workaround (the session log records the desktop and session type).
