# 008 · Native «Сохранить как…» dialog not covered by automation

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P3 | testing | `static/app.js` (`pickSaveTarget`, `saveReport`) |

## Problem

`saveReport` first calls `window.showSaveFilePicker` (Edge/Chrome, secure context — `localhost` qualifies), then renders and
writes through the file handle. Playwright cannot operate native dialogs, so `tests/e2e/e2e_ui.py` deletes the API and tests only the
download fallback. Not verified:

- the picker opens with the suggested name `Заключение (<sample>).docx` and the `.docx` filter;
- cancel → `AbortError` → silently nothing;
- writing via `createWritable()` produces a valid file; the success banner shows the chosen name;
- the transient-activation assumption (picker first, network after) holds;
- behaviour when the user picks an existing file that is open in Word (write fails → error dialog?).

## TODO

- [ ] Run the manual checklist in [testing](../../development/testing.md#4-manual-checklist-what-automation-does-not-reach) in Edge.
- [ ] Handle `createWritable`/`write` errors with a clear message («Файл занят другой программой?»).

## Acceptance

Checklist passed and recorded (date, browser version) in 08-testing.md.
