# 006 · «Обработать» again silently discards edits

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P2 | UX | `static/app.js` (`processResult`) |

## Problem

The page does not see Note changes made in the viewer after processing (it reads the file only on «Обработать»), so the
workflow is "change Notes → click «Обработать» again". That call replaces `state.reports` and throws away every edit without
asking. Also nothing tells the user the data is stale.

## TODO

- [ ] Track a `dirty` flag per report (set on any input); before re-processing, if any report is dirty →
      `confirm('Несохранённые правки будут потеряны. Продолжить?')`. Cheap, do it first.
- [ ] Staleness hint: return the result file's mtime (or `max(rowid)` of notes / a hash of `(base__uid, base__note)`) from
      `process`; poll `GET open` on window focus and show «Отметки в результате изменились — нажмите «Обработать»» when it differs.
- [ ] Long-term: merge instead of replace — see [005](005-review-edits-not-persisted.md).

## Acceptance

No edit is lost without an explicit confirmation; the page tells the user when Notes changed since processing.
