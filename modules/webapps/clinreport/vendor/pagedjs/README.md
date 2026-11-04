# Paged.js 0.4.3 (vendored)

`paged.polyfill.js` from the npm package `pagedjs@0.4.3` (https://cdn.jsdelivr.net/npm/pagedjs@0.4.3/dist/paged.polyfill.js),
unchanged. MIT, see LICENSE. sha256: `f59f361802416c770d549a647958649af2cf6601999924bc00e4f507dad5269f` (tests/core/test_output.py checks it).

Used only when a PDF is made in the browser (no WeasyPrint on the computer — the macOS desktop app): it lays the HTML
report out into pages with the same CSS Paged Media rules WeasyPrint follows (named pages, margin boxes, string-set,
running elements, target-counter), then the page opens the print dialog. clinreport_core/output.py inlines it.
Update: replace the file, the version here and the checksum; run the browser check in docs/development/templates.md.
