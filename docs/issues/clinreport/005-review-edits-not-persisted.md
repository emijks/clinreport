# 005 · Review edits are lost when the page is closed

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P2 | feature | `service.py`, `static/app.js` |

## Problem

Edits (sex, age, diagnosis, depth, cell corrections) live only in the page's memory (`state.reports[*].context`), exactly like
the desktop app's windows. Closing the tab, reloading, a browser crash, or re-processing ([006](006-reprocess-discards-edits.md))
loses them. A clinician who saves a draft `.docx`, fixes Notes and re-processes must retype everything.

## Proposed design

Store review state **in the result file itself**, so it travels with the `.sqlite` (the unit clinicians pass around):

- table `clinreport_review(sample_key text, kind text, context_json text, saved_at text, primary key (sample_key, kind))`
  — `sample_key` = sample id or `''` for `NULL`;
- on every edit (debounced) or on «Сохранить как…»: `POST save_review {dbpath, sample_index, kind, context}`;
- on `process`: if a stored context exists, **merge**: take patient/tech fields from the stored one; for variant rows, match by
  `variation` first line (`chr-pos-ref-alt`) and keep edited cells; new rows come fresh; removed rows are dropped;
  return a flag so the page can say «Восстановлены правки от <date>» with an option to discard.

Caveats: this is the first **write** by the webapp into the result (rule 3 in [AGENTS.md](../../../AGENTS.md) must be revised);
the viewer holds the file open — use short transactions; OC's `oc util update-result` must not choke on an extra table
(check). Alternative without touching the file: a sidecar JSON in the OC conf dir keyed by file path + sample (does not travel).

## TODO

- [ ] Agree on the storage location with the users (in-file vs sidecar).
- [ ] Implement `save_review` / load-and-merge in `service.py`, page autosave + restore banner.
- [ ] Tests: merge rules (edited row kept, new row added, removed row dropped).

## Acceptance

Close the page after editing, reopen, «Обработать» → edits are back; changed Notes are reflected without losing unrelated edits.
