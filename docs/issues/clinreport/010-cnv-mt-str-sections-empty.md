# 010 · CNV / MT / STR sections (Notes 4–6) always empty

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P3 | feature (upstream) | `process.py`, `labels.py`, templates |

## Problem

`NOTE_TO_NAME_MAP` reserves `4` → `cnv_variants`, `5` → `mt_variants`, `6` → `str_variants`, and all three templates contain
tables for them, but `SampleProcessor.SNV_NOTES = ('1','2','3','7','8')` — the lists are always empty (comment in the desktop app:
"CNV(4)/MT(5)/STR(6) left empty for now"). In the 10x context, `cnv_variants` and `mt_variants` are hard-coded empty.
Variants marked 4/5/6 are loaded but produce nothing, silently ([021](021-invalid-notes-silently-ignored.md)).

## What the templates expect

See [05 §4](../../reference/data-model.md#4-template-variables-docxtpl--jinja): DZM/FND CNV `variation, disease, genes, copies, classification`;
MT `gene, disease, variation, classification, coverage`; STR `gene, disease, expansion, repeat_count, classification`;
10x CNV `position, disease, genes, copies, classification`, MT `gene, disease, variation, classification`.

## TODO

- [ ] Clarify with the lab where CNV/MT/STR calls come from (separate OC results? other annotators/columns?) — the example
      results contain none.
- [ ] Implement row builders (upstream first), add `LAYOUTS` tables, decide Postgres storage.
- [ ] Recipe: [extending](../../development/extending.md#implement-cnv--mt--str-sections-notes-4-5-6).

## Acceptance

Variants marked 4/5/6 appear in the corresponding tables of all templates.
