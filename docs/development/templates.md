# Report templates: formats, adding one, PDF

How a report becomes a document, and the recipes for adding a template. Decision record:
[ADR 0017](../decisions/0017-html-templates-and-pdf.md). Fields: [data model §3–4](../reference/data-model.md).

## The model

- A **report kind** is what the review page edits: `default` (DZM/FND), `10x` (LPWGS), `screening`
  («Профилактический ДНК-скрининг»). A kind = a context builder + a page layout (+ checks, for `screening`).
- A **template** is one design of a kind, with **a file per format**. One id, up to two files:

```
modules/webapps/clinreport/templates/
├── docx/<id>.docx                Word, docxtpl                          → format docx
└── html/<id>/                    Jinja HTML + CSS Paged Media           → formats html and pdf
    ├── template.html             the entry point (includes partials)
    ├── partials/*.html           sections (optional)
    ├── style.css                 inlined by {{ inline_css('style.css') }}
    ├── fonts/*.woff2 + OFL.txt   referenced from style.css, embedded
    ├── images/*                  {{ asset('images/x.png') }}, embedded
    ├── data/*.json               fixed texts the kind reads (screening: study.json, genes_acmg.json)
    ├── template.json             {"title", "kind"} (documentation; BUILTIN is the registry)
    └── NOTICE.txt                origin and licenses (not *.md: the desktop build drops *.md)
```

- `templates.BUILTIN` lists `(id, title, kind)`; `builtin_formats(id)` finds the formats from the files present.
  The page offers them in the order PDF, HTML, Word and preselects the first («Формат ▾» next to «Шаблон ▾»).
- The lab's own templates (uploaded on the page / in the app) are **Word only** (`<conf>/clinreport/templates/`).
  HTML templates are built in: they can carry CSS and are rendered on the server, so they go through review.

## How a document is made — `clinreport_core/output.py`

```
context (from the page) ──► output.namespace_for(kind)   screening: screening.prepare() — «_» for empty fields, numbered citations
                                │                         other kinds: the context as is
              ┌─────────────────┼──────────────────────────────┐
           docx: docxtpl     html: Jinja → one .html file     pdf: that HTML → pdf_engine()
                             (CSS, fonts, images inlined,       weasyprint-exe │ weasyprint │ browser
                              CSP, no outside references)
```

HTML modes (`output.html_document(mode=…)`): `static` — no script: the HTML download and what WeasyPrint reads;
`print` — the browser PDF: Paged.js lays out the pages (`PAGEDJS_FIX_CSS` after it), then the print dialog. The
template decides how its HTML file looks in a browser with an `@media screen` block (screening: one A4-wide column on a
light background, no pages, no headers or page numbers); WeasyPrint reads print media, and the `print` mode switches
`@media screen` off, because Paged.js lays out on screen.

**PDF engines** (`pdf_engine()`, decided once per process; the page learns it as `layouts[kind].pdf_mode`):

| Where | Engine | How |
|---|---|---|
| genlab server (Docker) | `weasyprint` package | `pip install weasyprint==70.0` + `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0` |
| Linux desktop app | `weasyprint` package in the bundle | Pango comes with the desktop |
| Windows desktop app | `weasyprint-exe` | WeasyPrint's official Windows build in `<bundle>/weasyprint/` (stack.toml `[weasyprint_windows]`); the launcher sets `CLINREPORT_WEASYPRINT` |
| macOS desktop app, anything without Pango | `browser` | the server returns the HTML with Paged.js + a print call (`X-ClinReport-Print: 1`); the page lays it out in a hidden frame, the print dialog opens, the user saves the PDF |

`CLINREPORT_PDF_ENGINE=browser` forces the browser path (tests, support). One WeasyPrint release everywhere
(`test_weasyprint_is_one_release_everywhere`); the browser path is checked to print the same pages (below).

## CSS: what both engines read

Write **standard CSS Paged Media**; WeasyPrint implements it natively and Paged.js 0.4.3 polyfills it in the browser.
Used and verified in `html/screening/style.css` (same 10 pages, same contents page numbers in both):

- `@page { size: A4; margin: … }`, named pages (`section.cover { page: cover }` + `@page cover { … }`)
- margin boxes `@top-left`, `@top-right`, `@bottom-left` with `content: string(x)`, `counter(page, decimal-leading-zero)`
- `string-set: runhead attr(data-runhead)` (section name in the header)
- `position: running(fnote)` + `content: element(fnote)` (footnote in a page margin)
- `target-counter(attr(href), page)` (contents page numbers), `break-before/after/inside`, `@font-face` (woff2)

Rules: put `white-space: nowrap` on short margin-box text (Paged.js boxes are narrower: «СТР. 02» wrapped); no
`url(...)` to anything outside the template folder; no `<script>`, no external fonts/images/links — the Content-Security-
Policy that `output.html_document` writes blocks them, and on the server WeasyPrint refuses them
(`test_weasyprint_fetches_nothing_outside_the_document`). Hyphenation (`hyphens: auto`) works in WeasyPrint; browsers
hyphenate Russian on some systems only — the browser PDF may show wider word gaps.

## Jinja in HTML templates

- Autoescape is on; a missing variable is an **error** (`StrictUndefined`) — `check_html()` and the tests list them.
- `{{ text | rich }}`: the clinician's rich text — everything escaped, then `<i> <b> <em> <strong> <sup> <sub> <br>`
  (no attributes) allowed back (`screening.rich_html`). Never `| safe` on report data.
- `{{ value | freq }}`: gnomAD frequency, `0,0384` / `3,2×10⁻⁵` / `—`.
- `{{ asset('images/x.png') }}` → `data:` URI; `{{ inline_css('style.css') }}` → the stylesheet with its `url()`s inlined
  (CSS comments are dropped first). `template.html` must contain `<meta http-equiv="Content-Security-Policy"
  content="{{ csp }}">` and a `</head>` (the browser path inserts its scripts there).
- In Word templates the same rich text arrives as docxtpl `RichText`: `{{r par }}` (`output.richtext`).

## Recipe 1 — another Word template for an existing kind (e.g. a clinic's DZM)

Usually **no code**: an admin adds the `.docx` on the page («Шаблоны» → «Добавить шаблон…»), [guide](../guides/templates.md).
Built in for everyone: put `templates/docx/<ID>.docx`, add `('<ID>', '<title>', '<kind>')` to `BUILTIN`, run the tests
(`test_builtin_templates_use_only_known_fields` checks it); for `default`, also add it to `tests/e2e/smoke_http.py`.

## Recipe 2 — an HTML (PDF) template for an existing kind

1. Copy `templates/html/screening/` to `templates/html/<id>/`; keep `template.html`'s head (CSP meta, `inline_css`).
2. Write the sections with the kind's fields (`«Список полей»`, or `templates.field_paths(kind)` / data model §4);
   for `default` / `10x` the namespace is the context itself (`p_variants[].gene`, …).
3. Add `('<id>', '<title>', '<kind>')` to `BUILTIN`. A Word file `templates/docx/<id>.docx` under the same id adds the
   Word format to the same choice.
4. `python -m pytest tests/core/test_templates.py tests/core/test_screening.py` — the built-in check renders every
   format of every template with the kind's example and fails on unknown fields.
5. Look at it: the PDF (WeasyPrint) and the browser path (below). Fonts: WOFF2 + their license file; `NOTICE.txt`.

## Recipe 3 — a new report kind (worked example: `screening`)

| Step | `screening` did |
|---|---|
| Context builder: `clinreport_core/<kind>.py` `build_context(processor)` — **strings only** (the page edits them) | `screening.build_context`: Notes 1/2, structured fields from the raw OpenCRAVAT row |
| Hook it: `ClinReport.build_context(sample, '<kind>')`, a `mode` in `service.MODES` / `process()`, a button in `index.html` + `processResult('<mode>')` in `app.js` | «Обработать как скрининг» |
| Empty fields + namespace: `missing(context)` (Russian lines; `report_check`, layout `check_missing`) and `prepare(context, data_dir)` — never refuses, prints `_` for empty fields | filled values printed as written |
| `output.namespace_for(kind)`; Word needs rich text as `RichText` (`screening_docx_namespace`) | |
| `templates.KINDS`, `DEFAULT_FOR_KIND`, `example_context(kind)` (one row in every list; `check_context` makes the namespace the templates read) | `screening.EXAMPLE` |
| Page layout: `labels.LAYOUTS['<kind>']` — `common`, `tables`; `add_rows` (tables the user extends), `lists` (paragraph lists), `subtitle`; `service.REPORT_NAMES[kind]` (file name) | variants, references, interpretation, recommendations |
| Templates: `templates/html/<id>/`, `templates/docx/<id>.docx` (generated: `packaging/make_screening_docx.py`) | |
| Tests: `tests/core/test_<kind>.py` — builder on `trio1`, every check, every format through `service.render` | `test_screening.py` |
| Docs: data model §3/§4, http-api (`mode`), the guide, CHANGELOG | |

What the kind may **not** do: write to the result `.sqlite`, import pandas, use syntax newer than Python 3.8 (module code,
AGENTS rule 2), or fetch anything at run time.

## Checking by eye

```text
python -m pytest tests/core/test_screening.py                       # every format; PDF if WeasyPrint+Pango are here
packaging/dist/ClinReport/python/bin/python3 -I packaging/check_pdf.py packaging/dist/ClinReport /tmp/pdf   # a bundle's engine
CLINREPORT_PDF_ENGINE=browser … --headless                          # then «Сохранить как…» with PDF: the browser path
```

For the browser path, open the review page in Chrome/Edge/Yandex (Firefox works; Safari is the least tested), choose PDF,
«Сохранить как…»: Paged.js lays out the pages in a hidden frame, the print dialog appears — compare the pages with the
WeasyPrint PDF (page count, contents numbers, headers). After a Paged.js update, also check that the tab shows no CSP
errors in the console (`vendor/pagedjs/README.md`).
