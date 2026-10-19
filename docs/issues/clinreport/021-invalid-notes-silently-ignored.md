# 021 · Invalid Note values are silently ignored

| Status | Priority | Type | Area |
|---|---|---|---|
| open | **P1** | UX / bug | `service.process`, `static/app.js`, `database.VariantSource` |

## Problem

Only an exact single code (`1`–`8`) in the Note column places a variant into a section. Anything else — `2 3 8`, `2,3`,
` 1`, `1.`, `P`, free text — is dropped without any feedback. The page shows fewer variants than the clinician marked,
and nothing says why.

## Evidence

Observed in real use of the demo on 2026-09-25 (`C:\open-cravat\logs\wcravat.log`, `GET /result/runwidget/note`):
the clinician-side browser saved Notes `2`, then **`2 3 8`**, then `8` on `demo\trio1.sqlite`. The `2 3 8` variant
would not appear in any section. `trio1.sqlite` also contains a free-text note (`108735951,C,G|IRS4,IRS4-AS1|0/1|10,10`).

Mechanics: new schema loads `base__note is not null` then `filter_variants(by_note=…)` does exact string equality;
legacy schema filters `base__note in (1,…,8)` in SQL (free text never loaded).

## TODO

- [ ] Decide the rule with the lab: trim whitespace (`' 1'` → `'1'`)? allow multiple codes in one note (`'2 8'` → which section)?
      Recommendation: trim; treat anything else as invalid and report it.
- [ ] `service.process`: collect marked-but-unused variants (note not in `NOTE_TO_NAME_MAP` after trimming) and return them,
      e.g. `"ignored": [{"gene", "variation", "note"}]` (needs a raw query, since legacy loading filters them out in SQL).
- [ ] Page: show a warning banner listing them («Не распознаны отметки: … — используйте один код 1–8»).
- [ ] Also show per-section counts vs. total marked in the process card.
- [ ] Tests with a fixture that has `' 1'`, `'2 3 8'` and free text.

## Acceptance

Every variant with a non-empty Note either appears in a section or is listed in a visible warning.
