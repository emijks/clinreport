# 018 · Minor thread-safety gaps in service state

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P4 | robustness | `clinreport_core/service.py` |

## Problem

aiohttp runs handlers in the default thread pool, so they can overlap:

- `_databases` (engine cache) is a plain dict without a lock → two concurrent first uses may create two engines (harmless leak);
  `update_settings` clears it while another thread may be using an engine (the engine object stays valid).
- `update_settings` writes `clinreport.json` non-atomically; a concurrent `load_settings` could read a partial file →
  `json.JSONDecodeError` → 500.

Realistic impact with one clinician: negligible.

## TODO

- [ ] Guard `_databases` with a `threading.Lock`.
- [ ] Write settings to a temp file in the same dir and `os.replace` it.
- [ ] Treat a corrupt settings file as defaults + warning instead of 500.

## Acceptance

No partial reads of the settings file; single engine per credential set.
