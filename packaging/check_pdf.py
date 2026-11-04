#! /usr/bin/env python3
"""Check the PDF engine of a built bundle: render the example «Профилактический ДНК-скрининг» report.

    <bundle>/python/bin/python3 -I packaging/check_pdf.py <bundle> OUT_DIR     (Windows: <bundle>\\python\\python.exe)

Uses the engine the bundle promises (bundle.json "pdf"): the weasyprint package (Linux), weasyprint/weasyprint.exe
(Windows; the launcher passes it to OpenCRAVAT as CLINREPORT_WEASYPRINT, done here the same way) or the browser
(macOS: printable HTML with Paged.js). Writes OUT_DIR/screening.pdf or .html; exit 1 when the engine is not the
promised one or the document is wrong. CI runs it after the headless and window checks (.github/workflows/ci.yml).
"""

import copy
import json
import sys
from pathlib import Path


def main():
    bundle, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    promised = json.loads((bundle / 'bundle.json').read_text(encoding='utf-8')).get('pdf')
    exe = bundle / 'weasyprint' / 'weasyprint.exe'
    if exe.is_file():
        import os

        os.environ['CLINREPORT_WEASYPRINT'] = str(exe)
    sys.path.insert(0, str(bundle / 'modules' / 'webapps' / 'clinreport'))
    from clinreport_core import output, screening
    from clinreport_core import templates as tpl

    engine = output.pdf_engine()
    expected = {'weasyprint.exe': 'weasyprint-exe', 'weasyprint': 'weasyprint', 'browser': 'browser'}[promised]
    print(f'bundle promises {promised!r}; engine found: {engine!r}')
    if engine != expected:
        sys.exit(f'PDF engine {engine!r}, expected {expected!r}')
    store = tpl.TemplateStore(out / 'conf')
    document = output.render(copy.deepcopy(screening.EXAMPLE), 'screening', store.sources('screening'), 'pdf')
    out.mkdir(parents=True, exist_ok=True)
    target = out / ('screening' + document.extension)
    target.write_bytes(document.data)
    if document.print_in_browser:
        ok = b'PagedConfig' in document.data and b'Content-Security-Policy' in document.data
    else:
        ok = document.data[:5] == b'%PDF-' and len(document.data) > 100_000  # fonts embedded
    print(f'{target} ({len(document.data) // 1024} KB): {"ok" if ok else "WRONG"}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
