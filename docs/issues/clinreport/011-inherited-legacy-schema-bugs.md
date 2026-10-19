# 011 · Inherited bugs in the legacy-schema bridge

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P2 | bug (inherited from the Tk app) | `database.VariantSource._annotate_legacy`, `_extra_vcf_info` |

Applies only to **legacy** results (no `vep_csq__symbol` column; e.g. `trio1.sqlite`). Code is identical to the desktop app.

## Defects

1. **`UnboundLocalError` when no CSQ block has `PICK == '1'`.** `annotation` is assigned only inside the loop over CSQ blocks;
   the lines after the loop use it unconditionally → processing the whole file fails with a 500.
   If several blocks have `PICK == '1'`, the last one silently wins.
2. **`str.lstrip` used as "remove prefix".** `_extra_vcf_info` does `key.lstrip('extra_vcf_info__')`, which strips *characters*
   from the set `{e,x,t,r,a,_,v,c,f,i,n,o}`, not the prefix: `'extra_vcf_info__ref'` → `''`, `'extra_vcf_info__CSQ_PICK'` → `'CSQ_PICK'`
   (correct only because `C` is uppercase). Harmless today (only `CSQ_*` keys are read) but a trap for anyone adding a field.
3. **Multi-value separators leak into the text.** Legacy `vep_omim_pheno__pheno` / `__id` keep a trailing `|`
   (per-transcript separator): "…Autosomal recessive|" in «Ассоциированное заболевание», "(610389|)" in the interpretation
   (seen in `trio1.sqlite`, not in the new-schema `pah2`).
4. Legacy `base__note in (1,…,8)` compares a text column with integer literals — works through SQLite type affinity, but
   `'1 '` or `'01'` are dropped (see [021](021-invalid-notes-silently-ignored.md)).

## TODO

- [ ] (1) Initialise `annotation = {}` before the loop with the `vep_csq__*` keys set to `None` (or pick the first block as a fallback);
      decide what to show when no transcript is picked.
- [ ] (2) Replace with a real prefix removal (`key[len('extra_vcf_info__'):]`; `str.removeprefix` is 3.9+ — avoid for 3.8).
- [ ] (3) Strip/split `|`-separated values (use the picked block's index, or drop empty parts).
- [ ] Tests: synthetic legacy row without a picked block; a `|`-terminated phenotype.

## Acceptance

Legacy results without a picked transcript process without error; no `|` artefacts in the document.
