# 004 · Installing ClinReport into an existing OpenCRAVAT is manual

| Status | Priority |
|---|---|
| done (3.0.1: tab «Окружения», [ADR 0015](../../decisions/0015-run-on-an-existing-opencravat.md)) | P3 |

Staff who already run OpenCRAVAT (official installer, pip, conda) use `packaging/install_extension.py`, which must be run with
OpenCRAVAT's own Python. Nothing finds that Python or checks versions ([clinreport/014](../clinreport/014-distribution-and-versioning.md),
[clinreport/003](../clinreport/003-python-version-constraints.md)). The desktop app is the supported route; this is for
people who keep their own OpenCRAVAT.

## TODO (when picked up)

- [ ] `install_extension.py --detect`: find `oc` on PATH, the official installers' Pythons (`C:\Program Files\OpenCRAVAT\python`,
      `/Applications/OpenCRAVAT.app/Contents/Resources/bin`), conda envs; print OpenCRAVAT/Python versions; re-run itself
      with the chosen Python.
- [ ] Refuse known-broken combinations (OpenCRAVAT 3.x natively on Windows without the desktop patches; 2.x on Python ≥ 3.12).
- [x] A release zip with `install_extension.py` + `modules/` (3.0.0).

## Acceptance

One command installs ClinReport into a detected OpenCRAVAT, or explains why it cannot.
