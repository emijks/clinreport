# 014 · Distribution, version checks, updates

| Status | Priority | Type | Area |
|---|---|---|---|
| **done** (3.0.0) — environment check moved to [desktop/004](../desktop/004-install-into-existing-opencravat.md) | P2 | distribution | `install_extension.py`, repo, release process |

## Resolution (3.0.0)

Git history and tags (`vX.Y.Z`), a `CHANGELOG.md`, and GitHub releases built by `release.yml` with the desktop installers
and `clinreport-extension-<version>.zip` (`install_extension.py` + `modules/`). Re-running `install_extension.py` updates
and prints the old → new module version. The desktop app is the recommended route for clinicians
([ADR 0006](../../decisions/0006-bundle-portable-python.md)). Still open, in desktop/004: finding OpenCRAVAT's Python and a
`--check` mode.

## Problem

Today: copy the repo folder, run `<OC python> install_extension.py [--with-db]`, restart `oc gui`. Gaps:

- the repo is **not under git** yet (no history, no tags);
- no packaged release (zip) and no changelog beyond `release_note` in the ymls;
- `install_extension.py` does no environment checks ([003](003-python-version-constraints.md)) and cannot tell which version is installed
  (compare `version` in the installed `clinreport.yml`);
- clinicians must know "OpenCRAVAT's Python" — typically the Python where `oc` lives (`where oc` → its `Scripts` dir);
- no update path other than re-running the installer; no uninstall of pip deps (fine);
- publishing to the OpenCRAVAT Store is possible for modules but inappropriate (internal templates, private Google Sheet URL, DB);
  a private store is not set up.

## TODO

- [ ] `git init`, first commit, tag `v1.0.0`; `.gitignore` exists.
- [ ] Release artifact: zip of `install_extension.py`, `modules/`, `README.md` (+ a Russian install guide) — optionally a GitHub Actions
      workflow like the desktop app's `release.yml`.
- [ ] `install_extension.py`: show installed vs new version; `--check` mode (versions, required base modules, can import docxtpl).
- [ ] A Windows `install.bat` that finds `oc` on PATH and runs `install_extension.py` with the right Python
      (`for /f %%i in ('where oc') do …\python.exe install.py`).

## Acceptance

A clinician can install/update from a single artifact with one command and see what version they have.
