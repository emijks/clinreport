# Data model

Source files: [database.py](../../modules/webapps/clinreport/clinreport_core/database.py) (reading),
[process.py](../../modules/webapps/clinreport/clinreport_core/process.py) (context building),
[labels.py](../../modules/webapps/clinreport/clinreport_core/labels.py) (page layout, DB payload),
[templates/](../../modules/webapps/clinreport/templates/).

## 1. Note codes

`SampleProcessor.NOTE_TO_NAME_MAP` maps the **string** in `base__note` to a context list:

| Note | Context key | Section title (page) | In DZM | In FND | Pathogenicity text | `type` (DB) |
|---|---|---|---|---|---|---|
| `1` | `p_variants` | Патогенные варианты | ✅ | ✅ | «Патогенный» | Каузативный |
| `2` | `lp_variants` | Вероятно патогенные варианты | ✅ | ✅ | «Вероятно патогенный» | Каузативный |
| `3` | `vus_variants` | Варианты с неопределённой клинической значимостью | ✅ | ✅ | «Вариант с неизвестной…» | Каузативный |
| `4` | `cnv_variants` | — (always empty) | table | table | — | — |
| `5` | `mt_variants` | — (always empty) | table | table | — | — |
| `6` | `str_variants` | — (always empty) | table | table | — | — |
| `7` | `sf_variants` | Клинически значимые варианты, не связанные с основным диагнозом | ✅ | ✅ | from ClinVar | Не связан с основным диагнозом |
| `8` | `carrier_variants` | Носительство | ✅ | ❌ **no table in FND** | from ClinVar | Носительство |

Anything else in the Note column (free text, e.g. `trio1` has `108735951,C,G|IRS4,…`) is ignored.
Notes `1`/`2`/`3`/`7` also produce an interpretation paragraph.

## 2. Reading the result `.sqlite`

`VariantSource` ([database.py](../../modules/webapps/clinreport/clinreport_core/database.py)):

- **Samples**: `select distinct base__sample_id from sample` (can be a single `NULL` for single-sample VCFs).
- **Schema detection**: the result is "new" if the `variant` table has `vep_csq__symbol`, else "legacy".
- **Rows**: new → `where base__note is not null`; legacy → `where base__note in (1,…,8)`. Only marked rows are loaded.
- Notes are read from **`base__note` only** ([issue 019](../issues/clinreport/019-note-column-base-note-variant.md): OC ≥ 2.3.1 results use `base__note_variant`).

### Columns used by `process.py` (new schema)

| Group (annotator) | Columns |
|---|---|
| base | `base__note`, `base__chrom`, `base__ref_base`, `base__alt_base` |
| extra_vcf_info (converter) | `extra_vcf_info__pos`, `extra_vcf_info__ref`, `extra_vcf_info__alt` |
| vep_csq | `symbol`, `transcript`, `refseq`, `hgvsc`, `hgvsp`, `hgvsg`, `consequence`, `exon`, `intron` |
| vep_omim_pheno | `pheno`, `id`, `inher` |
| tagsampler_new (per-sample, `;`-joined, aligned by index) | `samples`, `zygosity`, `ad` (per sample `ref,alt` → last value used), `dp`, `filter` |
| clinvar_new | `sig`, `sig_subs` (`"Pathogenic (3); Likely_pathogenic (1)"`) |
| gnomad4genomes / gnomad4exomes | `AN`, `AC` (summed; AF = ΣAC/ΣAN) |
| dbsnp | `rsid` |
| gerp | `gerp_rs` |
| in-silico | `dbscsnv__ada_score`, `metarnn__score`, `revel__score`, `alphamissense__score`, `phylop100__score` |

### Legacy schema bridge (`_annotate_legacy`)

Legacy results (`trio1.sqlite`) lack `vep_csq`/`tagsampler_new`/`clinvar_new`. They are synthesised per row:

| New column | Legacy source |
|---|---|
| `vep_csq__*` | the `extra_vcf_info__CSQ_*` block (`;`-separated per transcript) whose `CSQ_PICK == '1'`; `hgvsc`/`hgvsp` stripped of the `ENST…:` prefix; `refseq` = `CSQ_MANE_SELECT` |
| `vep_omim_pheno__inher` | parsed from `vep_omim_pheno__pheno` text (Autosomal dominant → AD, …) |
| `tagsampler_new__{filter,zygosity,ad,dp,samples}` | `vevatacmg_postaggregator__{filter,zygosity,ad,dp,sample}` |
| `clinvar_new__{id,sig}` | `clinvar__{id,sig}`; `sig_subs` = None |

Known inherited defects here: [issue 011](../issues/clinreport/011-inherited-legacy-schema-bugs.md).

## 3. Report contexts

Built by `SampleProcessor.build_default_context()` / `build_10x_context()`; returned by `POST process` as
`report.context`, edited by the page, sent back to `render`/`upload`. All leaf values are strings.

### Default (DZM / FND) — real example from `trio1.sqlite`, sample1 (trimmed)

```json
{
  "patient": {"id": "sample1", "sex": "_", "age": "_", "diagnosis": "_"},
  "tech": {"method": "полногеномное секвенирование (Whole Genome Sequencing)", "depth": "_x",
           "reads_nt": "не менее 90 млрд", "read_type": "парно-концевое", "read_length": "150", "library_type": "PCR free"},
  "report_date": "25.09.2026",
  "clinician": "Иванова И.И.",
  "p_variants": [{
    "gene": "UBQLN4",
    "disease": "Immunodeficiency due to defect in MAPBP-interacting protein, 610798 (3), Autosomal recessive|",
    "variation": "chr1-156053689-T-G\nNM_020131.5:\nc.13A>C\np.(Ser5Arg)",
    "zygosity": "Гомозигота\n(Аутосомно-рецессивный)",
    "frequency": "н/д",
    "coverage": "135x/136x",
    "pathogenicity": "Патогенный",
    "type": "Каузативный",
    "manual_criteria": ""
  }],
  "lp_variants": ["…"], "vus_variants": ["…"],
  "cnv_variants": [], "mt_variants": [], "str_variants": [], "sf_variants": [], "carrier_variants": [],
  "interpretation": [{
    "gene": "UBQLN4",
    "intro_pre": "Обнаружен ранее _ описанный в литературе вариант (chr1:g.156053689T>G, NM_020131.5:c.13A>C) в гомозиготном состоянии в 1 экзоне из 11 экзонов гена ",
    "intro_post": ", который приводит к аминокислотной замене p.(Ser5Arg). Глубина покрытия в данной позиции составляет 136х, из них 135 прочтений соответствуют альтернативному аллелю.",
    "omim_pre": "Патогенные варианты в гене ",
    "omim_post": " приводят к Immunodeficiency due to … (610389|).",
    "body": ["Вариант встречается в базе данных популяционных частот gnomAD v4.1.0 с частотой  ().", "…",
             "Вариант обнаружен у sample2, sample3", "По совокупности сведений вариант расценивается как патогенный.", "…"]
  }],
  "closing": "Других значимых изменений, соответствующих критериям поиска, не обнаружено."
}
```

(`"с частотой  ()"`, the trailing `|`, and the unconditional "Вариант обнаружен у …" are inherited defects —
[issue 012](../issues/clinreport/012-inherited-narrative-bugs.md). `"_"` values are intentional placeholders for the clinician to fill.)

Variant row derivation (`_process_variant`):

| Field | Built from |
|---|---|
| `gene` | `vep_csq__symbol` |
| `disease` | `vep_omim_pheno__pheno`, overridden by the Russian sheet (see §6) |
| `variation` | lines: `chrom-pos-ref-alt`, `<refseq or transcript>:`, `hgvsc`, `p.(<hgvsp>)`, `rsid` (empty lines dropped) |
| `zygosity` | `Гетерозигота`/`Гомозигота`/`-` + `\n(` inheritance in Russian `)` |
| `frequency` | gnomAD4 aggregated AF → `float2percent` (2 significant digits for leading 1, else 1), or `н/д` |
| `coverage` | `<alt reads>x/<depth>x` for this sample |
| `pathogenicity` | notes 1–3: fixed text, capitalised; notes 7/8: ClinVar `sig` in Russian (`-` if none) |
| `type`, `manual_criteria` | DB payload only (not shown in templates or page) |

Server-side post-processing in `service._report`: a sample number of literally `"None"` (`patient.id`,
`patient.lab_number`, `sample.id`) is replaced by the file-name label.

### 10x (LPWGS, non-target samples) — real example from `trio1.sqlite`, sample2

```json
{
  "sample": {"id": "sample2"},
  "patient": {"lab_number": "sample2", "sex": "_", "diagnosis": "_"},
  "tech": {"…": "same as default"},
  "main_variants": [{"gene": "UBQLN4", "hgvsg": "chr1:g.156053689T>G", "genotype": "T/G",
                     "qual": "", "molecules": "11x/22x", "interpretation": ""}],
  "cnv_variants": [], "mt_variants": []
}
```

`main_variants` = every **target-sample** variant with Note 1/2/3, looked up in this sample by
`(chrom, pos, ref, alt)`: found → `genotype = ref/alt`, `molecules = "<ad>x/<dp>x"`; absent → `ref/ref`, `0x/-`.
`qual` and `interpretation` are left for the clinician.

## 4. Template variables (docxtpl / Jinja)

Extracted per loop from `word/document.xml` and the headers/footers of each `.docx` (re-extract with the snippet in
[extending](../development/extending.md#inspect-a-templates-variables)). `{%tr …%}` = table-row loop (each has a `{%tr else %}`
row for the empty case), `{%p …%}` = paragraph loop, `{{r …}}` = RichText value (`variation`, `zygosity`).

Scalars:

| Template | Variables |
|---|---|
| DZM, FND | `patient.{id,sex,age,diagnosis}`, `tech.depth`, `report_date`, `clinician`, `closing` |
| 10x | `patient.{lab_number,sex,diagnosis}`, `tech.depth`, **`sample.id` (in both footers)** |

Table loops (row fields, in column order):

| Loop | DZM | FND | 10x |
|---|---|---|---|
| `p_variants`, `lp_variants`, `vus_variants` | gene, disease, variation, zygosity, frequency, coverage | same | — |
| `sf_variants` | gene, disease, variation, zygosity, frequency, **pathogenicity**, coverage | same | — |
| `carrier_variants` | gene, disease, variation, zygosity, frequency, pathogenicity, coverage | **no table** | — |
| `cnv_variants` | variation, disease, genes, copies, classification | same | **position**, disease, genes, copies, classification |
| `mt_variants` | gene, disease, variation, classification, coverage | same | gene, disease, variation, classification |
| `str_variants` | gene, disease, expansion, repeat_count, classification | same | — |
| `main_variants` | — | — | gene, hgvsg, genotype, qual, molecules, interpretation |

Paragraph loop `interpretation` (DZM, FND): `intro_pre`, `gene` (italic), `intro_post`, `{%p if omim_pre %}` `omim_pre`,
`gene`, `omim_post`, then `{%p for para in body %}`.

The CNV/MT/STR row fields are what future implementations must produce ([issue 010](../issues/clinreport/010-cnv-mt-str-sections-empty.md)).
`sf_variants.pathogenicity` is rendered but not editable on the page ([issue 020](../issues/clinreport/020-review-page-parity-gaps.md)).
Unknown variables render as empty strings (docxtpl default), so a context missing a key does not fail.

## 5. Page layouts (`labels.LAYOUTS`)

Sent with every `process` response; the page renders purely from it.

```json
{
  "default": {
    "common": [{"section": "patient", "key": "id", "label": "Номер образца"}, "… sex, age, diagnosis, tech.depth"],
    "tables": [{"key": "p_variants", "title": "Патогенные варианты",
                "columns": [{"field": "gene", "label": "Ген"}, "… disease, variation, zygosity, frequency, coverage"]},
               "… lp, vus, sf (same columns), carrier (+ pathogenicity)"],
    "similar": true, "upload": true, "templates": ["DZM", "FND"]
  },
  "10x": {
    "common": ["patient.lab_number «Лабораторный номер», patient.sex «Пол», patient.diagnosis «Направительный диагноз ребенка»"],
    "tables": [{"key": "main_variants", "title": "Результаты исследования",
                "columns": ["gene, hgvsg, genotype, qual, molecules, interpretation"]}],
    "similar": false, "upload": false, "templates": ["10x"]
  }
}
```

## 6. Russian annotation overrides

Public Google Sheet `1Zj_Gw-TolcoKljqfk4eCrQ1hyhlZDs44UOZbFTVTfes`, fetched as CSV (`/export?format=csv&gid=…`):

| Name | gid | Index column | Columns used | Applied to |
|---|---|---|---|---|
| `omim` | `0` | gene symbol | `Ассоциированное заболевание` | `disease` of notes ≠ 7 |
| `secondary` | `706494431` | gene symbol | `Disease/Phentyope` (typo is in the sheet), `Inheritance` | `disease` and inheritance of note 7 |

Parsed into `{column: {gene: value}}` like `pandas.read_csv(index_col=0).to_dict()`, **except empty cells are skipped**
(fall back to the OpenCRAVAT value). Only the table rows use the overrides; interpretation paragraphs use the raw
OpenCRAVAT phenotype. Cached 10 min per GUI process; see [issue 015](../issues/clinreport/015-russian-annotations-online-only.md).

## 7. Postgres `ReportedVariants` payload

`labels.context_to_payload_records(context)` → one record per row of `p/lp/vus/sf/carrier_variants`:

| Column | Value |
|---|---|
| `Номер образца`, `Пол пациента`, `Возраст пациента`, `Предварительный диагноз` | `patient.id/sex/age/diagnosis` |
| `Клиницист` | `context.clinician` |
| `Дата заключения` | today, ISO `YYYY-MM-DD` (not the displayed `report_date`) |
| `Ген`, `Ассоциированное заболевание (OMIM)`, `Изменение ДНК (HG38) (Изменение белка)`, `Зиготность (Тип наследования)`, `Частота*`, `Кол-во прочтений (АЛТ/ОБЩ)`, `Ручные критерии`, `Патогенность`, `Тип` | row `gene, disease, variation, zygosity, frequency, coverage, manual_criteria, pathogenicity, type` |

Insert: `insert into "ReportedVariants" ("<col>", …) values (:p0, …)` executemany, one transaction. The table must exist
(the Tk app's `pandas.to_sql` would have created it). Whoever deploys a server creates it; GenLab Services (the `genlab-services` repository) does so with
database `clinreport` and this table (all columns `text`, as `to_sql` makes them; index on `"Номер образца"`) and passes
the connection as `CLINREPORT_DB_*`. Postgres cuts identifiers at 63 bytes, so the stored name of
`"Изменение ДНК (HG38) (Изменение белка)"` (2 bytes per Cyrillic letter) loses its last `)`; Postgres cuts the name in
every query the same way, so inserts and «Похожие» still match (GenLab Services' `tests/test_clinreport_db.py` covers it).

Columns added by server deployments next to the Tk-era ones: `id` (identity, primary key), `uploaded_at` (default
`now()`), `uploaded_by` (OpenCRAVAT login) and `upload_id` (one UUID per press of «Выгрузить в базу»). ClinReport writes
`uploaded_by` and `upload_id`, so the table must have them; GenLab Services' office app lists uploads by `upload_id`. Duplicate check: `select 1 … where "Номер образца" = :sample limit 1`.
Similar: `… where "Изменение ДНК (HG38) (Изменение белка)" like :pattern` with `%<first line of variation>%`.

## 8. Settings files

Two scopes (`service.py`, "settings" section):

| Scope | Keys | Where | Who may change |
|---|---|---|---|
| Server: Postgres connection | `host, port, name, user, pass` | env `CLINREPORT_DB_HOST` … `CLINREPORT_DB_PASS` only | whoever deploys the server; nobody through the page or the API |
| User | `clinician, template` (`DZM`/`FND`), `auto_upload` | local mode: `<OC conf dir>/clinreport.json`; login mode: `<OC conf dir>/clinreport-users.json` | the user themselves |

```json
// clinreport.json (local mode); DB keys left there by older versions are ignored
{"clinician": "", "template": "DZM", "auto_upload": false}
// clinreport-users.json (login mode), keyed by OpenCRAVAT login
{"alice@lab": {"clinician": "Иванова И.И.", "template": "FND", "auto_upload": false}}
```

Unknown keys are ignored. No file holds the database password any more (the desktop app kept it in `config.json`; here
it is only in the server's environment). In login mode users start from the defaults, since a local file's clinician would put the wrong
name on their reports. Both files are written atomically (temp file + `os.replace`) under a lock.
