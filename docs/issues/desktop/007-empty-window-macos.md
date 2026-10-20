# 007 · The control window is empty on an old Mac

| Status | Priority |
|---|---|
| fixed — to confirm on the Mac | P1 |

## Problem

Reported 2026-10-20 on an Intel Mac with macOS 10.15.7: the app installs and OpenCRAVAT starts (its page opens in the
browser), but the ClinReport window shows only its background colour — not even the static sidebar of `ui/index.html`.
First seen with the CI artifact `clinreport-macos-x64` of run 39285479834 (commit `3e23938`), whose window self-test had
passed on `macos-15-intel`.

## Cause (from the session log of build 3.0.0-ci.4 on that Mac)

```
macOS 10.15.7, WebKit 15609, Safari 15.6.1
PyObjC: Exception during dealloc of proxy: Completion handler passed to
  -[BrowserDelegate webView:decidePolicyForNavigationAction:decisionHandler:] was not called
WARNING the window page has not started in 20 s (page loaded: False)
```

Before loading a page WebKit asks the navigation delegate for permission. pywebview 6.2.1's handler
(`webview/platforms/cocoa.py`) first calls `action.shouldPerformDownload()`, which Apple added in **macOS 11.3**. On 10.15
the call raises, the handler never answers, no page load starts — and pywebview adds the web view to the window only
after a load finishes, so the window stays empty. No load error is reported because there is no load. wry (Tauri) guards
the same call for the same reason. CI cannot catch it: no runner has macOS < 11.3.

## Other findings

- **pywebview's fixed port 42001.** With a file path pywebview serves `ui/` from its HTTP server on 42001, shared by every
  pywebview app. On Windows a second server binds the taken port anyway and the window shows the other program's page
  (reproduced); on macOS the bind would fail. Not the cause on the reporting Mac, but a real problem: fixed in `eeab8d2`.
- **Old WebKit.** 10.15 as shipped has Safari 13, without `replaceChildren` (used by `app.js`). The reporting Mac has
  Safari 15.6.1, so it was not affected; fixed in `eeab8d2` for Macs that were never updated.

## Done

- Session logs (`sessionlog.py`, [packaging.md → Logs](../../development/packaging.md#logs)): system, WebKit/Safari or
  WebView2 versions, App Translocation, uncaught errors in any thread, native crashes, stdout/stderr without a terminal,
  WebKit's failed page loads, the page's own errors and its `ready` signal; a warning when the page has not started in
  20 s. macOS logs in `~/Library/Logs/ClinReport`. This is what found the cause.
- The window gets its page as one document (`window_page()`, `html=`), so pywebview starts no HTTP server. Checked on
  Windows with a dummy server holding 127.0.0.1:42001.
- `app.js` runs on Safari 13: the inline script supplies `replaceChildren`; `tests/desktop/test_window_page.py` rejects
  newer syntax and APIs.
- **The fix for the cause:** `webview_compat.supply_should_perform_download()` gives `WKNavigationAction` a
  `shouldPerformDownload` that answers "no" when WebKit lacks it (macOS < 11.3), before the window is created. On newer
  macOS nothing changes. The session log says `supplied for pywebview` when it was needed.

## TODO

- [ ] A new build on that Mac: the window shows the Overview; the session log has `supplied for pywebview` and
      `ready: init done`.
- [ ] After a pywebview update: check whether `cocoa.py` still calls `shouldPerformDownload` unguarded (then keep the
      patch) and whether it calls other WebKit APIs newer than 10.15 on the page-load path.

## Acceptance

On the reporting Mac (macOS 10.15.7, Intel) the window shows the Overview with «OpenCRAVAT работает»; the session log
has `ready: init done`.
