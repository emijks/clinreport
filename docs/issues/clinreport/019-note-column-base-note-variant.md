# 019 · Notes written to `base__note_variant` (OC ≥ 2.3.1) are not read

| Status | Priority | Type | Area |
|---|---|---|---|
| done (3.0.2) | **P1** | bug / compatibility | `clinreport_core/database.py` (`VariantSource.get_variants`) |

## Problem

Notes are saved by the `wgnote` widget, not by the viewer core ([opencravat-integration](../../reference/opencravat-integration.md#notes-base__note-are-written-by-the-wgnote-widget-not-by-the-viewer-core)).
`wgnote` 3.0.0 (current in the KarchinLab repo; release note: "uses base__note_variant and base__note_gene, new columns in 2.3.1")
writes to **`base__note_variant`** when that column exists and only falls back to `base__note`.

ClinReport (and the desktop app it was ported from) reads only `base__note`:

```python
rows = cur.execute('select * from variant where base__note is not null;')  # new schema
rows = cur.execute('select * from variant where base__note in (1,2,3,4,5,6,7,8);')  # legacy
```

and `SampleProcessor` filters on `variant['base__note']`.

## Impact

On a result created by — or upgraded with `oc util update-result` to — OpenCRAVAT ≥ 2.3.1, the clinician's marks go to
`base__note_variant`; the report then contains **no variants**, silently. Both example results (OC 2.2.9) have only
`base__note`, so this was not visible in testing. Unknown which OC version clinicians run ([003](003-python-version-constraints.md)).

## TODO

- [x] In `VariantSource.get_variants`, detect `base__note_variant` in `pragma table_info(variant)`; if present, select rows where
      `coalesce(nullif(base__note_variant, ''), base__note) is not null` and set `variant['base__note']` to that coalesced value
      so `process.py` stays unchanged.
- [x] Legacy branch: same coalescing before the `in (1..8)` filter (compare as text: `in ('1',…,'8')`).
- [x] Produce a test fixture: copy `pah2`, `alter table variant add column base__note_variant text`, move a note there; test both columns.
- [ ] Verify with a real OC ≥ 2.3.1 install + `wgnote` 3.0.0 (mark a variant, process). Not done: the fix is covered by
      `tests/core/test_note_columns.py` (synthetic results of each schema, and `pah2` with its marks moved to `base__note_variant`).

## Acceptance

A note saved through `wgnote` on OC 2.2.9 **and** on OC ≥ 2.3.1 appears in the report; tests cover both columns.
