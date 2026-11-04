# 0017 · HTML templates; PDF from WeasyPrint, else the browser

Status: accepted (2026-11-05)

## Context

Reports were Word only (docxtpl). The «Профилактический ДНК-скрининг» report arrived as a separate project
(KateAnpilogova/Secondary-findings: Jinja HTML + CSS Paged Media → WeasyPrint → PDF) and more such reports will follow.
The lab wants every report type in Word, HTML and PDF, chosen per report, in the desktop app (Windows, macOS, Linux)
and on the genlab server, with as few system dependencies as possible (pip rather than apt).

Measured on the screening report (2026-11-05):

| Engine | Result |
|---|---|
| WeasyPrint 69/70 (pip + system Pango) | pixel-exact with the authors' CSS, Russian hyphenation, 1.5–2.5 s; Pango is apt/brew/MSYS2, never pip |
| Typst (pip, self-contained) | 0.03 s, fine typography — but a second template language next to HTML |
| Chromium + Paged.js 0.4.3 | the same pages, headers and contents numbers as WeasyPrint; no hyphenation; needs a person to press «Сохранить» (or a headless Chromium) |
| xhtml2pdf | crashed on this CSS |
| html2pdf.js, Vivliostyle, PyMuPDF, Playwright | screenshot PDFs / AGPL / AGPL / apt + a downloaded Chromium |

## Decision

1. **Templates are Jinja HTML with standard CSS Paged Media**, next to the Word ones: one template id, a file per
   format (`templates/docx/<id>.docx`, `templates/html/<id>/`). A template offers the formats it has files for; the page
   has a format choice. HTML output is one self-contained file (CSS, fonts, images inlined; a Content-Security-Policy).
2. **PDF = that HTML through WeasyPrint** where Pango exists: the server (`pip install weasyprint==70.0` + three apt
   packages in the image), the Linux desktop (Pango comes with the desktop), the Windows desktop (WeasyPrint's official
   Windows build in the bundle, checksum-pinned). One WeasyPrint release everywhere.
3. **Otherwise the browser prints it**: the macOS desktop app (no Pango build fits macOS 10.15) and any machine without
   Pango get the HTML with Paged.js (MIT, vendored, sha256-pinned) and a print call; the user saves the PDF.
4. **Word stays for editing and CLINBIO** (office accepts `.docx` only); no Word→PDF conversion (it would need
   LibreOffice).
5. The lab's own uploaded templates stay Word only; HTML templates are built in (reviewed code, rendered on the server).

## Consequences

- A template is written once for both PDF engines; only features both implement may be used
  ([templates.md](../development/templates.md#css-what-both-engines-read)). The browser PDF has no hyphenation in some
  browsers.
- Bundles grow: Linux +~70 MB (WeasyPrint, fontTools, Pillow), Windows +~60 MB (the WeasyPrint build), macOS +1 MB.
- Module code imports WeasyPrint lazily; OpenCRAVAT installs without it (old Python, no Pango) fall back to the browser.
- The genlab server image gains three apt packages (Pango) — the one system dependency of this design.
- Security: report data reaches the HTML only escaped (`| rich` allows a few bare tags); generated HTML references
  nothing outside itself; WeasyPrint may fetch only `data:` URIs (no SSRF from report content).
- Revisit: a headless Chromium on the server (Gotenberg-style) would give the browser engine without a person; Typst if
  hyphenation-quality PDFs are needed without Pango.
