# 0015 · The desktop app can run an OpenCRAVAT that is already on the computer

Status: accepted (2026-10-21)

## Context

Clinicians who already use OpenCRAVAT (pip, conda, the official installer) got a second one with the desktop app: a second
modules folder (hg38 alone is about 1 GB), a second jobs folder, and our modules only in the copy they do not use.
Installing the extension into their OpenCRAVAT was manual (`install_extension.py`, issue desktop/004).

## Decision

The desktop app lists OpenCRAVAT installations ("environments", tab «Окружения»), can install our two modules into one,
and can run its OpenCRAVAT instead of the built-in one. The built-in environment stays the default and the fallback.

- **Looking changes nothing.** Importing `cravat` creates `C:\open-cravat` / `/Users/Shared/open-cravat` and writes
  `cravat-system.yml`, so `oc` is never run to inspect another installation: its Python runs a probe that uses
  `importlib.util.find_spec` and lists dist-info folders; the conf and the modules are read from disk.
- **Their environment is not modified.** Only `<modules_dir>/webapps/clinreport` and `<modules_dir>/webviewerwidgets/wgclinreport`
  are written, after the user confirms. Python packages our core needs and the environment lacks (`docxtpl`…) are installed
  with that environment's pip into the webapp's own `lib/`, which `route.py` appends to `sys.path` (theirs wins). Before the
  swap the staged module must import in their Python; the previous modules go to a backup in our data folder and come
  back if anything fails.
- **Their OpenCRAVAT runs as configured.** No `OPENCRAVAT_SYSTEM_CONF_PATH`, no rewritten conf; only `CLINREPORT_CONF_DIR`
  points at our conf dir, so templates and report settings are shared by every environment.
- **What can run is decided by the version matrix** in `docs/reference/opencravat-integration.md` (OpenCRAVAT ≥ 2.2,
  Python ≥ 3.8, `setuptools < 81` before 2.17, no 3.x on Windows outside the bundle).
- A chosen environment that disappears or stops qualifying falls back to the built-in one with a notice.

## Consequences

- `route.py` must stay importable on Python 3.8 and fail softly (503) when a package is missing (ADR 0005).
- Our process may now start another Python; the launcher records its pid (`server.pid`) because `kill_leftovers` cannot
  recognise it by path.
- Untested OpenCRAVAT versions are allowed with an «не проверялся» note rather than refused.
- `install_extension.py` remains for machines without the desktop app.
