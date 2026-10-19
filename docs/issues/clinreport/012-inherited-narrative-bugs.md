# 012 · Inherited text defects in the generated report

| Status | Priority | Type | Area |
|---|---|---|---|
| open | P2 | bug (inherited from the Tk app), needs lab decisions | `process.SampleProcessor`, templates |

All in `process.py` (verbatim copy). Seen with the example results on 2026-09-25.

## Defects

1. **"с частотой  ()"** — `_variant_narrative`: if gnomAD `AN` > 0 but `AC` is 0/None, `af_msg` and `ac_msg` are empty and the
   sentence becomes "Вариант встречается в базе данных популяционных частот gnomAD v4.1.0 с частотой  ()." — it should say the
   variant is not found (AC = 0). Seen for 2 of 3 variants of `trio1.sqlite`. Table cell shows `н/д` for the same variants.
2. **"Вариант обнаружен у sample2, sample3"** — `_other_samples_msg` lists *all* other samples of the file for *every* variant,
   regardless of whether they carry it, and the sentence has no final period. For a trio this is wrong for variants absent in
   relatives. The per-sample genotype is available (`tagsampler_new__samples` / `__zygosity`).
3. **FND template has no «Носительство» table** — Note `8` variants never appear in FND documents (DZM has the table). Could be
   intentional (different customer) — **ask the lab**.
4. **`sf_variants` pathogenicity** is rendered in both templates but not editable on the page ([020](020-review-page-parity-gaps.md)).
5. Placeholders by design: "Обнаружен ранее _ описанный…", `patient.*` = `_`, `tech.depth` = `_x` — the clinician must fill them;
   [009](009-interpretation-not-editable.md) would let them do it on the page.

## TODO

- [ ] (1) Treat `AC` falsy as "не встречается" (or print `0%`) — decide wording with the lab.
- [ ] (2) Build the list per variant: samples whose genotype at that position is non-reference; add the period.
- [ ] (3) Confirm with the lab whether FND should include carriers; if yes, add the table to `FND.docx`.
- [ ] Implement in `process.py` (its only home since 3.0), or post-process in `service._report`
      if the desktop app is retired.
- [ ] Tests asserting the corrected sentences for `trio1`.

## Acceptance

No empty "()" sentences; sample lists reflect actual carriers; FND carrier behaviour is confirmed.
