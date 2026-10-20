# 007 · The control window is empty on an old Mac

| Status | Priority |
|---|---|
| fixed — to confirm on the Mac | P1 |

## Problem

Reported 2026-10-20 on an Intel Mac with macOS ~10.15: the app installs and OpenCRAVAT starts (its page opens in the
browser), but the ClinReport window shows only its background colour — not even the static sidebar of `ui/index.html`.
Installed build: the CI artifact `clinreport-macos-x64` of run 39285479834 (commit `3e23938`), whose window self-test
passed on `macos-15-intel`.

## Cause (reproduced on Windows, not yet confirmed on the Mac)

The window loads `ui/index.html` from pywebview's built-in HTTP server. With `private_mode=False` pywebview 6.2.1 uses a
**fixed port, 42001** (`webview.settings['DEFAULT_HTTP_PORT']`), the same for every pywebview app, and starts the server
in a daemon thread whose errors go to stderr only (lost when started from Finder).

- On Windows, a second server binds the taken port anyway (`SO_REUSEADDR`), and the window silently gets the **other
  process's** page. Reproduced: a test launcher started while the installed ClinReport was running showed the installed
  version's `index.html`.
- On macOS the bind fails. pywebview's Cocoa backend adds the web view to the window only in
  `webView_didFinishNavigation_`, so a load that never finishes leaves the window empty — the reported symptom.

Two more problems wait behind it on 10.15:

- **Old WebKit.** The window uses the system WebKit, as new as the installed Safari (13–15.6 on 10.15). `app.js` calls
  `replaceChildren` (Safari 14+) 11 times; with Safari 13 the page would stay at «Запуск…». Flex `gap` (Safari 14.1) only
  loses spacing.
- **App Transport Security.** `Contents/MacOS/ClinReport` `exec`s the bundled `python3`, so the process's main bundle is
  not `ClinReport.app` and its `Info.plist` is not used; pywebview writes `NSAllowsArbitraryLoads` into the in-memory
  Info dictionary on import. Unclear whether that covers `http://127.0.0.1` on 10.15.

## Done

- Session logs (`sessionlog.py`, [packaging.md → Logs](../../development/packaging.md#logs)): system, WebKit/Safari or
  WebView2 versions, App Translocation, uncaught errors in any thread, native crashes, stdout/stderr without a terminal,
  WebKit's failed page loads, the page's own errors and its `ready` signal; a warning when the page has not started in
  20 s. macOS logs in `~/Library/Logs/ClinReport`.
- The window gets its page as one document (`window_page()`: `app.css` and `app.js` inlined, `html=`), so pywebview
  starts no HTTP server and port 42001 no longer matters. Checked on Windows: with a dummy server answering on
  127.0.0.1:42001, the window self-test still shows our page and logs `ready: init done`; before the change the window
  showed the other server's page.
- `app.js` runs on Safari 13: the inline script supplies `replaceChildren`; `tests/desktop/test_window_page.py` rejects
  newer syntax and APIs and any file the page would load. (`.flat`, `max()` are older; `accent-color`, flex `gap` only
  lose styling; the clipboard call already falls back to `execCommand('copy')`.)

## TODO

- [ ] On the Mac (optional now, confirms the cause): `sw_vers`, Safari and WebKit versions; `lsof -nP -iTCP:42001 -sTCP:LISTEN` and
      `curl http://127.0.0.1:42001/index.html` while ClinReport runs; start it from Terminal
      (`/Applications/ClinReport.app/Contents/MacOS/ClinReport`) and keep the output; `xattr -l` on the app; the old
      logs from `~/Library/Application Support/ClinReport/logs`.
- [x] Stop depending on port 42001.
- [x] Make `app.js` run on Safari 13.
- [x] ATS keys in `packaging/macos/Info.plist`: not needed now — the window loads nothing over HTTP.
- [ ] A new build on that Mac, with its session log.

## Acceptance

On the reporting Mac (macOS 10.15, Intel) the window shows the Overview with «OpenCRAVAT работает», also when another
program holds port 42001; the session log has `ready: init done`.
