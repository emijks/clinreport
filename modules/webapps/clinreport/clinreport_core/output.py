"""Documents in every format: DOCX (docxtpl), HTML (Jinja, one self-contained file) and PDF (from that HTML).

    render(context, kind, template_dir_or_docx, fmt) -> Document(data, content_type, extension, print_in_browser)

PDF engine, first that works (pdf_engine()):
  1. CLINREPORT_WEASYPRINT = path of a WeasyPrint executable — the Windows desktop app ships the official build;
  2. the weasyprint package (server: pip + Pango from the system; Linux desktop: Pango comes with the desktop);
  3. 'browser': the HTML comes back with Paged.js and a print call; the page opens it and the user saves the PDF
     (macOS desktop app, or a computer without Pango). CLINREPORT_PDF_ENGINE=browser forces it (tests, support).
The same CSS Paged Media rules drive WeasyPrint and Paged.js, so a template is written once (docs/development/templates.md).

Generated HTML never refers to anything outside itself: CSS, fonts and images are inlined (inline_css, asset) and a
Content-Security-Policy forbids any other source, so WeasyPrint fetches nothing (server: no SSRF) and an opened report
cannot load or send anything.
"""

from __future__ import annotations

import base64
import hashlib
import io
import mimetypes
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
FORMATS = {  # format: (content type, extension, label on the page)
    'pdf': ('application/pdf', '.pdf', 'PDF'),
    'html': ('text/html; charset=utf-8', '.html', 'HTML'),
    'docx': (DOCX_MIME, '.docx', 'Word (.docx)'),
}
PAGEDJS = Path(__file__).resolve().parent.parent / 'vendor' / 'pagedjs' / 'paged.polyfill.js'
CSP_STATIC = "default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:"
PRINT_SCRIPT = (
    # Paged.js reads window.PagedConfig before it lays out the pages; after that, the print dialog.
    'window.PagedConfig = {auto: true, after: function () { setTimeout(function () { window.print(); }, 300); }};'
)
WEASYPRINT_TIMEOUT = 180


class Document:
    def __init__(self, data: bytes, fmt: str, print_in_browser: bool = False):
        self.data = data
        self.format = fmt
        self.content_type, self.extension, _label = FORMATS[fmt]
        self.print_in_browser = print_in_browser
        if print_in_browser:  # PDF requested, HTML returned: the page prints it
            self.content_type, self.extension = FORMATS['html'][0], '.html'


class PdfUnavailable(RuntimeError):
    pass


# --- HTML ---


def jinja_environment(template_dir: Path, undefined=None):
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    from markupsafe import Markup

    from . import screening

    template_dir = Path(template_dir).resolve()

    def inside(name: str) -> Path:
        path = (template_dir / name).resolve()
        if template_dir not in path.parents:
            raise ValueError(f'{name}: outside the template folder')
        return path

    def asset(name: str) -> str:
        """data: URI of a file of the template (image, font)."""
        path = inside(name)
        mime = mimetypes.guess_type(path.name)[0] or ('font/woff2' if path.suffix == '.woff2' else 'application/octet-stream')
        return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode('ascii')

    def inline_css(name: str) -> Markup:
        """The stylesheet with every url(...) inside the template folder turned into a data: URI."""
        path = inside(name)
        css = re.sub(r'/\*.*?\*/', '', path.read_text(encoding='utf-8'), flags=re.S)  # comments: not the report's business

        def replace(match):
            url = match.group(2)
            if url.startswith('data:'):
                return match.group(0)
            return 'url("' + asset(str((path.parent / url).relative_to(template_dir))) + '")'

        return Markup(re.sub(r'url\((["\']?)([^)"\']+)\1\)', replace, css))

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
        undefined=undefined or StrictUndefined,  # a forgotten field is an error, not an empty place
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters['rich'] = lambda text: Markup(screening.rich_html(text))
    env.filters['freq'] = screening.fmt_freq
    env.globals.update(asset=asset, inline_css=inline_css)
    return env


def html_document(namespace: dict, template_dir: Path, *, for_print: bool = False, undefined=None) -> str:
    """template.html of template_dir rendered with namespace; for_print adds Paged.js and the print call."""
    scripts = [PRINT_SCRIPT, PAGEDJS.read_text(encoding='utf-8')] if for_print else []
    csp = CSP_STATIC + "; script-src " + (' '.join(f"'sha256-{_sha256(s)}'" for s in scripts) or "'none'")
    page = jinja_environment(template_dir, undefined).get_template('template.html').render(dict(namespace, csp=csp))
    if scripts:
        tags = ''.join(f'<script>{s}</script>\n' for s in scripts)
        page = page.replace('</head>', tags + '</head>', 1) if '</head>' in page else tags + page
    return page


def _sha256(text: str) -> str:
    return base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode('ascii')


# --- PDF ---

_engine_lock = threading.Lock()
_engine = None


def pdf_engine() -> str:
    """'weasyprint-exe' | 'weasyprint' | 'browser' (decided once per process)."""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = _find_engine()
        return _engine


def _find_engine() -> str:
    forced = os.environ.get('CLINREPORT_PDF_ENGINE', '').strip().lower()
    if forced == 'browser':
        return 'browser'
    exe = os.environ.get('CLINREPORT_WEASYPRINT', '')
    if exe and os.path.isfile(exe):
        return 'weasyprint-exe'
    try:
        import weasyprint  # noqa: F401 - loads Pango; OSError when the system has none
    except (ImportError, OSError):
        return 'browser'
    return 'weasyprint'


def _data_only_fetcher(weasyprint):
    """Everything a report needs is inlined; WeasyPrint may open data: URIs and nothing else (server: no SSRF, no
    local files). WeasyPrint >= 70 takes a URLFetcher object, older versions a function."""
    fetcher_class = getattr(getattr(weasyprint, 'urls', None), 'URLFetcher', None)
    if fetcher_class is not None:
        return fetcher_class(allowed_protocols=('data',), fail_on_errors=True)

    def fetch(url, *args, **kwargs):
        if url.startswith('data:'):
            return weasyprint.default_url_fetcher(url, *args, **kwargs)
        raise ValueError(f'external resource refused: {url[:80]}')

    return fetch


def html_to_pdf(page: str) -> bytes:
    engine = pdf_engine()
    if engine == 'weasyprint':
        import weasyprint

        # WeasyPrint >= 70 stops on a refused resource with FatalURLFetchingError, a BaseException (so that nothing
        # swallows it): turn it into the user-facing error here, or it would get past every `except Exception`.
        fatal = getattr(getattr(weasyprint, 'urls', None), 'FatalURLFetchingError', None) or Exception
        try:
            return weasyprint.HTML(string=page, url_fetcher=_data_only_fetcher(weasyprint)).write_pdf()
        except fatal as e:
            raise PdfUnavailable(f'шаблон ссылается на внешний файл, а встраивать нужно всё ({e})') from None
    if engine == 'weasyprint-exe':
        with tempfile.TemporaryDirectory(prefix='clinreport-pdf-') as work:
            source, target = Path(work) / 'report.html', Path(work) / 'report.pdf'
            source.write_text(page, encoding='utf-8')
            done = subprocess.run(
                [os.environ['CLINREPORT_WEASYPRINT'], str(source), str(target)],
                capture_output=True, timeout=WEASYPRINT_TIMEOUT, stdin=subprocess.DEVNULL,
                **({'creationflags': 0x08000000} if os.name == 'nt' else {}),  # CREATE_NO_WINDOW
            )
            if done.returncode != 0 or not target.is_file():
                tail = (done.stderr or b'').decode('utf-8', 'replace').strip().splitlines()[-3:]
                raise PdfUnavailable('WeasyPrint не сделал PDF: ' + ' '.join(tail))
            return target.read_bytes()
    raise PdfUnavailable('browser')


# --- DOCX ---


def docx_document(namespace: dict, docx_path: Path) -> bytes:
    from docxtpl import DocxTemplate

    document = DocxTemplate(str(docx_path))
    document.render(namespace)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def richtext(text):
    """Rich text (screening.RICH_TAGS) as a docxtpl RichText: italics, bold, superscript survive in Word."""
    from docxtpl import RichText

    from .screening import rich_runs

    rt = RichText()
    for chunk, style in rich_runs(text):
        rt.add(chunk, **style)
    return rt


def screening_docx_namespace(namespace: dict) -> dict:
    ns = dict(namespace)
    for field in ('interpretation', 'recommendations', 'references'):
        ns[field] = [richtext(t) for t in ns.get(field) or []]
    ns['gene_groups'] = [dict(g, text=[richtext(t) for t in g.get('text') or []]) for g in ns.get('gene_groups') or []]
    return ns


# --- one entry point ---


def namespace_for(kind: str, context: dict) -> dict:
    """What the templates of a report kind read: 'screening' → screening.prepare() («_» for empty fields, numbered
    citations); the other kinds read the context as it is."""
    if kind == 'screening':
        from . import screening, templates

        return screening.prepare(context, templates.data_dir('screening'))
    return context


def render(context: dict, kind: str, sources: dict, fmt: str) -> Document:
    """sources: {'docx': path | None, 'html': template folder | None} of the chosen template."""
    if fmt not in FORMATS:
        raise ValueError(f'unknown format {fmt}')
    if fmt == 'docx':
        if kind == 'screening':
            return Document(docx_document(screening_docx_namespace(namespace_for(kind, context)), sources['docx']), fmt)
        from .templates import richtextify

        return Document(docx_document(richtextify(context), sources['docx']), fmt)
    namespace = namespace_for(kind, context)
    if fmt == 'html':
        return Document(html_document(namespace, sources['html']).encode('utf-8'), fmt)
    if pdf_engine() == 'browser':
        return Document(html_document(namespace, sources['html'], for_print=True).encode('utf-8'), fmt, print_in_browser=True)
    return Document(html_to_pdf(html_document(namespace, sources['html'])), fmt)
