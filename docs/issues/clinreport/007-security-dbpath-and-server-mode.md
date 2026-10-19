# 007 · Arbitrary local file read; no auth — unsafe on a shared server

| Status | Priority | Type | Area |
|---|---|---|---|
| done (2026-09-26) · follow-ups on the server side | P2 (**P1 before any shared/multi-user deployment**) | security | `service.resolve_dbpath`, `service.get/update_settings`, `route.py` |

## Problem (as found)

Designed for a **local** single-user GUI (localhost). If `oc gui` is exposed on a network or run with `--multiuser`:

1. `open`/`process` accept any absolute `dbpath` and read it if it looks like an OC result → any user can read any result
   file the server process can access, including other users' jobs.
2. `GET settings` returns the Postgres password in clear text; `POST settings` lets anyone change the DB target.
3. No authentication or CSRF protection on our routes (the GUI's own multi-user login is not consulted).
4. Everything in `modules/webapps/clinreport/` is statically downloadable (`/webapps/clinreport/route.py`, templates) — harmless
   today, but never put secrets there.
5. Settings are global (one clinician name for everyone on that server).

Confirmed on 2026-09-26 against OpenCRAVAT 3.1.1 in Docker with `OC_MULTIUSER=true`: `GET /webapps/clinreport/settings`
without any cookie → `200` with the full settings. OC 3.x mounts `/webapps/<module>/<action>` without a login check
(`cravat/gui/webapps.py`); the GUI's `before_request` only sets `g.is_multiuser` / `g.username` (None when not logged in).

## What was done

- `route.py` builds a `service.Caller` per request — Flask: `g.is_multiuser` / `g.username`; aiohttp:
  `cravat_web.servermode` + `cravat_multiuser.get_username(request)` — and calls `service.authorize` first:
  login mode without a session → **401** on every endpoint.
- Login mode: `dbpath` is refused; `job_id` is resolved only in `<jobs>/<login>/<job_id>/` (the client's `username` is
  ignored); admins (`admin_list`, default `["admin"]`) may open any user's job. Hand-placed `<jobs>/<id>` jobs are not
  reachable. The page re-sends `job_id` (not the resolved path) to `process`.
- Settings split into two scopes ([05 §8](../../reference/data-model.md#8-settings-files)):
  - **per user**: `clinician`, `template` (new: default DZM/FND), `auto_upload` → `conf/clinreport-users.json` keyed by login;
  - **server**: Postgres connection → `CLINREPORT_DB_*` environment variables, else `conf/clinreport.json`; changeable only
    by admins, read-only when it comes from the environment.
  - `pass` is **never returned** (only `pass_set`); an empty password in `POST` keeps the stored one. Non-admins do not
    see host/user/database at all, only `db_configured`.
  - *Later (2026-10-04):* the connection is env-only; the page and the API no longer show or change it for anyone
    (no `pass_set`/`db_editable`, no `clinreport.json` fallback).
- `POST` requires `Content-Type: application/json` (a cross-site form cannot send it without a CORS preflight).
- Local mode (no login) is unchanged apart from the password no longer being sent to the page: the same
  `clinreport.json`, opening by path, one user `default`.
- Tests: `tests/core/test_multiuser.py`, `tests/routes/test_routes_flask.py`, additions to `tests/routes/test_routes.py` (42 in total).
  Live checks with curl + Playwright against the Docker image in login mode: [08 §5](../../development/testing.md).

## Remaining (not in this module)

- [ ] The OpenCRAVAT viewer itself (`/result/service/*`) also accepts `?dbpath=` without a login check in 3.1.1
      (`cravat/gui/cravat_request.py: jobid_and_db_path`). Block `dbpath=` at the reverse proxy in login mode —
      tracked in [server/002](../server/002-multiuser-and-clinreport-hardening.md).
- [ ] Pass `CLINREPORT_DB_*` through `compose.yaml` / `.env` on the server (optional; the settings dialog works too).
- [ ] Item 4 stays as is: module files are public by design; secrets live in the conf dir or the environment.

## Acceptance

On a multi-user server a user can only open their own jobs, cannot read the DB password and cannot change global
settings; each user keeps their own clinician name. — met (see [08 §5](../../development/testing.md)).
