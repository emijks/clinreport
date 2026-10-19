# 002 · Login mode: ClinReport hardened; server-side hardening still open

| Status | Priority |
|---|---|
| in progress — ClinReport part done 2026-09-26 | **P1** before network use |

`OC_MULTIUSER=true` passes `--multiuser` to `oc gui` (built into 3.x: Flask session login, accounts in `conf/admin.sqlite`,
jobs in `jobs/<user>/<job>/`, admins = `admin_list` in `cravat-system.yml`, default `["admin"]`).

## Findings (2026-09-26, 3.1.1 source + throwaway container with `OC_MULTIUSER=true`)

- Login page and `admin`/`admin` work; the healthcheck command still succeeds (static `index.html`), so
  GenLab Services issue cravat/007 (health check under login) is most likely a non-issue.
- **`/webapps/<module>/<action>` is not protected by the login** (`cravat/gui/webapps.py`); the GUI only sets `g.username`
  (None without a session). Before the fix, `GET /webapps/clinreport/settings` with no cookie → `200` and the settings,
  including the DB password.
- OpenCRAVAT's own per-user settings: JSON column `users.settings` in `admin.sqlite`, used only for `lastAssembly`; readable
  at `GET /server/usersettings`, writable only server-side (`AdminDb.update_user_settings`). Internal, undocumented API.
- Viewer layouts/filters and Notes are stored **in the result `.sqlite`** (`viewersetup` table / Note column), i.e. per job —
  fine with login, since each user imports their own copy.
- **Upstream gap:** the viewer's `/result/service/*` endpoints accept `?dbpath=` and do not check the login
  (`cravat/gui/cravat_request.py: jobid_and_db_path`).
- Anyone who can reach the server can **sign up** (`GET /server/signup?...`) and use guest accounts unless configured off.
  3.x has no admin screen for creating users and no header-based SSO (`enable_remote_user_header` only disables sign-up).

## Done in ClinReport ([clinreport/007](../clinreport/007-security-dbpath-and-server-mode.md))

- Every ClinReport endpoint returns **401** without a login session.
- In login mode results are opened only by `job_id` from the user's own folder; `dbpath` is refused; admins can open any job.
- Per-user settings: clinician, default template, auto-upload (`data/conf/clinreport-users.json`).
- Postgres connection: server-wide, changed only by admins, password never sent to the browser; can come from
  `CLINREPORT_DB_HOST/PORT/NAME/USER/PASS` environment variables instead of `data/conf/clinreport.json`.
- Verified by curl + Playwright against this image in login mode (ClinReport `docs/08-testing.md` §5).

## TODO

- [x] Start with `OC_MULTIUSER=true`: login page, `admin`/`admin`, create users, a job per user.
- [x] Check whether `/webapps/clinreport/*` requires a session (it did not; ClinReport now enforces it itself).
- [x] ClinReport issue 007 (ignore `dbpath`, resolve `job_id` in the logged-in user's folder, admin-only DB settings).
- [ ] `configure.py`: write `noguest: true` into `cravat-system.yml` when `OC_MULTIUSER=true`.
- [ ] Decide on self sign-up. Closing it = `enable_remote_user_header: true` in `cravat-system.yml`, plus a
      `tools/add_user.py` (runs `AdminDb().register_user(...)` via `docker compose exec`) for creating accounts.
- [ ] Reverse proxy (GenLab Services: platform/001, HTTPS reverse proxy): reject requests with a `dbpath=` query parameter in login
      mode (covers the upstream viewer gap).
- [ ] Optional: pass `CLINREPORT_DB_*` through `compose.yaml` / `.env.example` (empty values are ignored by ClinReport).
- [ ] Re-run the checks in [testing.md](../../development/testing.md) logged in, through the proxy.

## Acceptance

With login on, a user can only open their own jobs in ClinReport and cannot read the DB password (**met**), strangers cannot
create accounts, and the viewer cannot be pointed at arbitrary files by path.
