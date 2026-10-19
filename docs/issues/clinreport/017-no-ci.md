# 017 · No CI; live tests need a running GUI

| Status | Priority | Type | Area |
|---|---|---|---|
| **in progress** — CI done (3.0.0); synthetic example results open | P3 | testing | `tests/`, `tests/e2e/` |

## Progress (3.0.0)

`.github/workflows/ci.yml` runs on every push: ruff, pytest on Linux and Windows (OpenCRAVAT 3.2.3, Python 3.13) with a
coverage report, and the desktop bundle on Windows, macOS arm64 and macOS x64 with a headless HTTP smoke test and the
window self-test. Still open: synthetic results, so the tests that need example results run in CI too — this is also what
lifts CI coverage to the 80 % target (deferred, see [docs/development/testing.md](../../development/testing.md)).

## Problem

Tests run only by hand. `tests/` needs the two example results from the workspace (skipped otherwise); `tests/e2e/smoke_http.py`
and `tests/e2e/e2e_ui.py` need a running `oc gui` with `hg38` + `wgnote` installed.

## TODO

- [ ] Commit small **synthetic** example results (a few variants, both schemas, one with `NULL` sample id, one trio) under
      `tests/data/` so tests do not depend on the workspace files (patient data must not be committed — the examples may be real).
- [x] GitHub Actions (Windows + Linux; now OpenCRAVAT 3.2.3 / Python 3.13 per `packaging/stack.toml`) + pytest.
- [x] Optional job (done for the desktop bundle: `--headless` + HTTP checks; `smoke_http.py` needs the synthetic results): start `oc gui --headless` (needs `hg38` from the Store or the GitHub copy) and run `tests/e2e/smoke_http.py`.

## Acceptance

Every push runs pytest on OC 2.2.9 / Python 3.11 without local files.
