# 006 · OpenCRAVAT 3.x needs our start-up patches on Windows

| Status | Priority |
|---|---|
| open | P3 |

`launchers/desktop/clinreport_oc_compat.py` patches OpenCRAVAT 3.2.3 at import time for Windows (details in
[docs/desktop.md](../../development/packaging.md#opencravat-3x-on-windows-desktoplauncherclinreport_oc_compatpy)):
the Celery results path (`f'/{work_dir}/…'` → `/C:/…`) and the Celery pool (`prefork` cannot work on Windows → `solo`; `threads` breaks Store installs).
Patches against private module internals break silently when OpenCRAVAT changes them.

## TODO

- [ ] Report both to KarchinLab/open-cravat (with the traceback and a minimal fix: `os.path.join(work_dir, 'celery', 'results')`
      and `worker_pool='solo'` on `win32`).
- [ ] After every `OPENCRAVAT_VERSION` bump: re-run the Windows checks (docs/desktop.md); drop each patch once upstream fixes it.

## Acceptance

The desktop app runs released OpenCRAVAT on Windows without `clinreport_oc_compat`.
