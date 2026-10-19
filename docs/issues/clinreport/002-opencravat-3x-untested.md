# 002 · OpenCRAVAT 3.x (Flask GUI) support

| Status | Priority | Type | Area |
|---|---|---|---|
| **done** for 3.1.1 on Linux (Docker), 2026-09-25; 3.2.3 is the supported version since 3.0.0 (desktop app on Windows/macOS, CI on Linux/Windows) — two small follow-ups open | P3 | compatibility | `route.py`, `service.resolve_dbpath`, widget JS |

## Result

Verified in the former `opencravat-server` Docker image (OpenCRAVAT 3.1.1, Python 3.11, Flask on waitress + Celery):
HTTP smoke test 12/12 documents, full browser flow (widget → review → save → LPWGS → settings), opening by `job_id`, Notes via
`wgnote`. Details: [opencravat-integration](../../reference/opencravat-integration.md#opencravat-3x-specifics-verified-in-docker).

Fixed on the way:

- `route.py` chose the adapter by `find_spec('cravat.gui')`, which is also true under `oc gui --aiohttp` → now detected from the
  call stack (`webapp_proxy_handler` = Flask, `setup_webapp_routes` = aiohttp).
- The 3.x Jobs page opens the viewer with only `?job_id=`, and jobs live in `jobs/default/<id>` → `resolve_dbpath` searches user
  folders (and rejects path-like ids). Tests added.
- Widget font: the viewer's fonts are named `roboto-light`/`roboto-medium`.

## Still open

- [ ] `oc gui --aiohttp` on 3.x — not run.
- [ ] 3.x on Windows natively — OpenCRAVAT bug (`gui/config.py:35`, Celery path `'/C:\…'`); use Docker or report upstream.
- [ ] A unit test for the Flask adapter (build a Flask app with a catch-all like `webapp_proxy_handler`).
