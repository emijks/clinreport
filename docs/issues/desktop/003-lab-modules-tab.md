# 003 · Lab staff cannot add the lab's own OpenCRAVAT modules in the desktop app

| Status | Priority |
|---|---|
| open — deferred (2026-10-15) | P3 |

Store modules already work from OpenCRAVAT's Store tab (their Python packages go to `python-packages/` in the user's data
folder, so app updates keep them). Modules that are not in the Store — e.g. the lab's Excel reporters in sm-ngp
(GenLab Services issue cravat/006) — can only be copied by hand into `<data>/modules/<type>/<name>/`.

## TODO (when picked up)

- [ ] Launcher «Модули» tab: list installed modules (type, version, source: bundled / Store / added), add from a `.zip` or
      folder (validate `<name>.yml`, `type`; install `pypi_dependency` with the app's pip), remove (never our managed modules).
- [ ] Or ship agreed lab modules in the bundle (as GenLab Services' image would, per its cravat/006).

## Acceptance

A lab member installs a module from a zip in the desktop app and sees it in OpenCRAVAT after a restart.
