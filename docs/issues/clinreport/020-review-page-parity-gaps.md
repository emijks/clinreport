# 020 · Small gaps: some rendered fields are not editable

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P3 | UX | `labels.py`, `static/app.js` |

Same as the desktop app unless noted, but cheap to improve now that the page is layout-driven.

| Rendered in the document | Editable on the page? | Fix |
|---|---|---|
| `sf_variants[].pathogenicity` (DZM, FND) | ❌ (sf uses `SNV_FIELDS`) | use `CARRIER_FIELDS` for the sf table in `DEFAULT_VARIANT_TABLES` |
| `report_date` | ❌ | add a common field `('', 'report_date', 'Дата заключения')` — needs top-level binding support in `app.js` (`section` empty) |
| `clinician` | ❌ (from settings at processing time) | same as above, per report |
| 10x `sample.id` (both footers) | ❌ (only `patient.lab_number`) | add `('sample', 'id', 'Номер образца (колонтитул)')` to `TEN_X_COMMON_FIELDS` |
| `interpretation`, `closing` | ❌ | [009](009-interpretation-not-editable.md) |

Other page gaps:

- The yellow "edited" highlight is lost after switching tabs (edits themselves are kept).
- No per-report reset ("вернуть исходные значения").
- No keyboard shortcut for save.

## TODO

- [ ] Rows 1–4 above (+ tests that the edited values reach the document).
- [ ] Keep the original context per report to support highlight persistence and reset.

## Acceptance

Every scalar that appears in a document can be edited on the page.
