# 013 · Report core is a copy of the desktop app — divergence risk

| Status | Priority | Type | Area |
|---|---|---|---|
| **done** (3.0.0) | P2 | maintenance | `clinreport_core/` |

## Resolution (3.0.0)

Option 1: the Tk app was retired and its repository became this one, so `clinreport_core` is the only copy of the report
logic. Option 2 (separate Python packages) remains the long-term plan ([ADR 0002](../../decisions/0002-one-repository.md)).

## Problem

`process.py`, `utils.py`, templates and `VariantSource` were copies of the Tk app's files at `2ac1bf6`
([decisions](../../decisions/README.md)). Every report-content fix must be made twice or synced by hand; forgetting it means the
desktop app and the GUI extension produce different reports for the same file.

## Options

1. **Retire the desktop app** once the extension is accepted → `clinreport_core` becomes the single source. Simplest.
2. **Shared package**: move `process.py`, `utils.py`, `clinreport.py`, `database.py` (pandas-free), `labels.py` and templates into
   a pip-installable `clinreport-core` (own repo or subfolder), used by the desktop app (`pip install`) and by the module
   (`install_extension.py` pip-installs it into OC's Python instead of copying). Must stay Python 3.8-compatible.
3. **Sync script**: `tools/sync_from_clinreport.py` that copies the verbatim files, re-applies the import patch, and fails if other
   files changed since the recorded baseline.

## TODO

- [ ] Decide with the owner (1/2/3). Until then, follow the sync procedure in 09 and keep the baseline updated.

## Acceptance

One source of truth for report content, or an automated, documented sync.
