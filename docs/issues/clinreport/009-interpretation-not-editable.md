# 009 · Interpretation paragraphs cannot be seen or edited

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P2 | feature | `labels.LAYOUTS`, `static/app.js` |

## Problem

The largest part of the document — the interpretation paragraphs per variant (`context.interpretation[]`: `intro_pre`,
`intro_post`, `omim_pre`, `omim_post`, `body[]`) and `closing` — is generated and rendered, but the page shows none of it.
Same as the desktop app. Clinicians must fix the text in Word afterwards, e.g. the `_` placeholder in
"Обнаружен ранее _ описанный в литературе вариант" and the inherited defects in [012](012-inherited-narrative-bugs.md).

## TODO

- [ ] Add an «Интерпретация» section to the default panel: per item a heading (`gene`) and textareas for `intro_pre`,
      `intro_post`, `omim_pre`/`omim_post` (if present) and each `body` paragraph; plus `closing`.
      Bind to `context.interpretation[i][…]`, `context.interpretation[i].body[j]` and `context.closing` like the tables
      (arrays need index binding).
- [ ] Optional: add/remove body paragraphs.
- [ ] Keep the layout-driven approach: describe the section in `LAYOUTS['default']` (e.g. `"narrative": true`) rather than hard-coding.
- [ ] Test: edited paragraph text appears in the rendered .docx.

## Acceptance

Every text that ends up in the document can be reviewed and corrected on the page before saving.
