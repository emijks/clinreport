"""«Профилактический ДНК-скрининг» (clinreport_core/screening.py) and the HTML/PDF output (clinreport_core/output.py).

PDF tests need WeasyPrint with Pango (Linux dev machines, CI); they are skipped elsewhere.
"""

import copy
import hashlib
import html
import http.server
import io
import re
import threading

import pytest
from clinreport_core import output, screening
from clinreport_core import templates as tpl
from docx import Document

DATA = tpl.data_dir('screening')
SOURCES = {'docx': tpl.DOCX_DIR / 'screening.docx', 'html': tpl.HTML_DIR / 'screening'}


def example(**patient):
    context = copy.deepcopy(screening.EXAMPLE)
    context['patient'].update(patient)
    return context


@pytest.fixture
def engine(monkeypatch):
    """Set the PDF engine for one test (output caches the one it found)."""

    def use(name):
        monkeypatch.setattr(output, '_engine', name)

    return use


def weasyprint_or_skip():
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip('WeasyPrint with Pango is not available here')


# --- the context from a result ---


def test_context_from_notes_1_and_2(trio_db):
    from clinreport_core import ClinReport

    context = ClinReport(trio_db).build_context('sample1', 'screening')
    assert [(v['gene'], v['classification']) for v in context['variants']] == [
        ('UBQLN4', 'патогенный'), ('FAM20C', 'вероятно патогенный')]  # Note 3 (VUS) and the rest are not here
    v = context['variants'][0]
    assert v['position'] == 'chr1:156053689 T>G' and v['hgvs_c'] == 'NM_020131.5:c.13A>C' and v['hgvs_p'] == 'p.Ser5Arg'
    assert v['omim'] == '610798' and '610798' not in v['disease']
    assert (v['zygosity'], v['inheritance'], v['reads_alt'], v['reads_total']) == ('гомозигота', 'АР', '135', '136')
    assert v['frequency'] == '—', 'not in gnomAD: a dash, as upstream'
    assert all(isinstance(x, str) for row in context['variants'] for x in row.values()), 'the page edits strings'
    assert '<i>UBQLN4</i>' in context['interpretation'][0] and '&gt;' not in context['interpretation'][0]
    assert 'фенотипа пациента' not in ' '.join(context['interpretation']), 'a screening participant has no diagnosis'
    assert context['patient']['participant'] == '' and context['patient']['date'], 'left empty for the clinician'


@pytest.mark.parametrize(('value', 'code'), [('AR', 'АР'), ('AD', 'АД'), ('XL', 'ХС'), ('AD,AR', ''), ('', ''), (None, '')])
def test_inheritance_is_one_code_or_left_to_the_clinician(value, code):
    assert screening._inheritance(value) == code


@pytest.mark.parametrize(('value', 'text'), [
    (0.0384, '0,0384'), (3.2e-05, '3,2×10⁻⁵'), (None, '—'), (0, '0'), ('н/д', 'н/д')])
def test_frequency_format(value, text):
    assert screening.fmt_freq(value) == text


# --- empty fields: listed before saving, printed as «_»; anything filled in is printed as written ---


def test_the_example_misses_nothing():
    assert screening.missing(screening.EXAMPLE) == []


def test_missing_names_every_empty_field():
    context = example(participant='', sex=' ', mean_depth='')
    context['variants'][0].update(inheritance='', reads_total='')
    context['interpretation'] = ['Текст [@nosuch]']
    assert screening.missing(context) == [
        'Участник: Участник исследования, Пол, Средняя глубина прочтения',
        'Вариант 1 (HFE): тип наследования, прочтений всего',
        'Нет источника для ссылок [@nosuch] — останутся в тексте как есть',
    ]
    context['interpretation'] = []
    assert 'Интерпретация вариантов пуста' in screening.missing(context)


def test_empty_fields_print_an_underscore_and_never_stop_the_report():
    context = example(participant='', mean_depth='')
    context['variants'][0].update(inheritance='')
    context['interpretation'] = []
    ns = screening.prepare(context, DATA)
    assert ns['patient']['participant'] == '_' and ns['patient']['mean_depth'] == '_'
    assert ns['variants'][0]['inheritance'] == '_' and ns['interpretation'] == ['_']


def test_whatever_is_filled_in_is_printed_as_written():
    """No value checks: a filled field always goes into the document (the clinician's decision)."""
    context = example(sex='qweqe')
    context['variants'][0].update(zygosity='гомо', inheritance='AR', reads_alt='39', classification='VUS')
    context['interpretation'] = ['Вариант ранее _ описан [@unknown].']
    ns = screening.prepare(context, DATA)
    assert ns['patient']['sex'] == 'qweqe'
    assert (ns['variants'][0]['zygosity'], ns['variants'][0]['inheritance'], ns['variants'][0]['classification']) == ('гомо', 'AR', 'VUS')
    assert ns['interpretation'] == ['Вариант ранее _ описан [@unknown].'], 'a citation without a source stays as written'
    page = output.render(context, 'screening', SOURCES, 'html').data.decode('utf-8')
    assert 'qweqe' in page and 'гомо' in page


def test_no_variants_needs_no_interpretation_and_prints_none():
    context = example()
    context.update(variants=[], interpretation=['лишний текст'], references=[])
    ns = screening.prepare(context, DATA)
    assert ns['interpretation'] == [] and ns['variants'] == []


# --- citations ---


def test_citations_are_numbered_after_the_fixed_list_in_order_of_first_use():
    texts, cited, errors = screening.resolve_citations(
        ['a [@b] c [@a; @b]', 'd [@c]'], 12, {'a': 'A', 'b': 'B', 'c': 'C', 'unused': 'U'})
    assert texts == ['a [12] c [12, 13]', 'd [14]'] and cited == ['B', 'A', 'C'] and errors == []
    assert screening.resolve_citations(['[@x]'], 12, {}) == (['[@x]'], [], ['x'])


def test_compress():
    assert screening._compress([12, 13, 14, 16]) == '12–14, 16'
    assert screening._compress([3, 4]) == '3, 4'


def test_prepare_numbers_and_lists_the_extra_sources():
    ns = screening.prepare(example(), DATA)
    fixed = len(screening.load_data(DATA)[0]['references'])
    assert ns['interpretation'][0].endswith(f'[{fixed + 1}].')
    assert ns['references'][-1].startswith('Feder JN') and len(ns['references']) == fixed + 1
    assert ns['recommendations'] == screening.load_data(DATA)[0]['default_recommendations'], 'empty → the defaults'
    assert ns['inheritance_legend'] == 'АР – аутосомно-рецессивный.'


# --- rich text ---


def test_rich_html_allows_only_a_few_bare_tags():
    assert screening.rich_html('<i>HFE</i> <B>x</B> 10<sup>-5</sup>') == '<i>HFE</i> <b>x</b> 10<sup>-5</sup>'
    hostile = '<script>alert(1)</script><i onclick="x()">a</i><img src=x onerror=y><a href="http://e">l</a>'
    safe = screening.rich_html(hostile)
    assert not re.search(r'<(script|img|a)\b', safe) and '<i onclick' not in safe, 'no live markup but the bare tags'
    assert '&lt;i onclick' in safe and safe.count('</i>') == 1, 'a tag with attributes stays visible text'


def test_rich_runs_for_word():
    assert screening.rich_runs('В гене <i>HFE</i> c.845G&gt;A<br>10<sup>-5</sup>') == [
        ('В гене ', {}), ('HFE', {'italic': True}), (' c.845G>A', {}), ('\n', {}), ('10', {}), ('-5', {'superscript': True})]


# --- documents: every format of the built-in template ---


def test_html_is_one_file_with_nothing_outside(engine):
    page = output.render(example(), 'screening', SOURCES, 'html').data.decode('utf-8')
    page = html.unescape(page)  # the CSP's quotes are written as &#39; in the attribute; browsers read them back
    assert 'Петрова Анна Сергеевна' in page and '<i>HFE</i>' in page
    assert '<script' not in page and "script-src 'none'" in page, 'a document, not a program'
    assert '@media screen' in page, 'the template says how it looks in a browser (a column, no pages)'
    markup = re.sub(r'<script>.*?</script>', '', page, flags=re.S)  # Paged.js's own code mentions url( and src=
    assert not re.search(r'(src|href)="(?!data:|#)', markup), 'every image/link is embedded or in-page'
    assert not re.search(r'url\((?!"?data:)', markup), 'every CSS url() is embedded'
    assert '@font-face' in page and 'data:font/woff2;base64,' in page


def test_pdf_in_the_browser_prints_with_pagedjs(engine):
    engine('browser')
    document = output.render(example(), 'screening', SOURCES, 'pdf')
    assert document.print_in_browser and document.content_type.startswith('text/html') and document.extension == '.html'
    page = document.data.decode('utf-8')
    scripts = re.findall(r'<script>(.*?)</script>', page, flags=re.S)
    assert len(scripts) == 2 and 'window.print()' in scripts[0] and 'Paged' in scripts[1]
    assert 'max-width: none' in scripts[0], 'Paged.js margin-box fix'
    csp = html.unescape(re.search(r'Content-Security-Policy" content="([^"]+)"', page).group(1))
    for script in scripts:  # the page's own Content-Security-Policy allows exactly these two scripts
        assert output._sha256(script) in csp


def test_pagedjs_is_the_pinned_file():
    digest = hashlib.sha256(output.PAGEDJS.read_bytes()).hexdigest()
    assert digest == 'f59f361802416c770d549a647958649af2cf6601999924bc00e4f507dad5269f', 'update vendor/pagedjs/README.md too'
    assert (output.PAGEDJS.parent / 'LICENSE').is_file()


def test_weasyprint_gets_no_script():
    page = output.html_document(screening.prepare(example(), DATA), SOURCES['html'])  # mode 'pdf'
    assert '<script' not in page and "script-src 'none'" in html.unescape(page)


def test_pdf_with_weasyprint(engine):
    weasyprint_or_skip()
    engine('weasyprint')
    document = output.render(example(), 'screening', SOURCES, 'pdf')
    assert not document.print_in_browser and document.data[:5] == b'%PDF-'
    assert len(document.data) > 100_000, 'fonts are embedded'


def test_weasyprint_fetches_nothing_outside_the_document(engine):
    """Server: a report must not make the server request anything (no SSRF, no local files)."""
    weasyprint_or_skip()
    engine('weasyprint')
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_address[1]}'
    page = (f'<html><head><link rel="stylesheet" href="{url}/a.css"><style>@import url("{url}/b.css");'
            f'body {{ background: url("{url}/c.png") }}</style></head><body><img src="{url}/d.png">'
            f'<img src="file:///etc/hostname">x</body></html>')
    try:
        with pytest.raises(output.PdfUnavailable, match='внешний файл'):  # an ordinary error the page shows
            output.html_to_pdf(page)
    finally:
        server.shutdown()
    assert hits == []


def test_docx_with_italics_and_numbered_citations():
    document = Document(io.BytesIO(output.render(example(), 'screening', SOURCES, 'docx').data))
    rows = document.tables[0].rows
    assert len(rows) == 2 and rows[1].cells[0].text.startswith('HFE'), 'header + one variant, no empty-case row'
    paragraph = next(p for p in document.paragraphs if 'p.Cys282Tyr' in p.text)
    assert any(r.italic and r.text == 'HFE' for r in paragraph.runs) and paragraph.text.endswith('].')
    assert any('Feder JN' in p.text for p in document.paragraphs)


def test_docx_without_variants_says_so():
    context = example()
    context.update(variants=[], interpretation=[], references=[])
    document = Document(io.BytesIO(output.render(context, 'screening', SOURCES, 'docx').data))
    assert [c.text for c in document.tables[0].rows[1].cells][0] == 'Не обнаружено.'


# --- through the service: format, template and kind are checked ---


def test_service_renders_every_format(service, engine):
    engine('browser')
    for fmt, extension in (('docx', '.docx'), ('html', '.html'), ('pdf', '.html')):
        result = service.render({'context': example(), 'kind': 'screening', 'template': 'screening', 'format': fmt,
                                 'filename': 'Отчёт ДНК-скрининга (s1).docx'})
        assert result.filename == f'Отчёт ДНК-скрининга (s1){extension}'
        assert (result.headers.get('X-ClinReport-Print') == '1') == (fmt == 'pdf')


def test_service_refuses_what_a_template_cannot_make(service):
    with pytest.raises(service.ClientError, match='PDF'):
        service.render({'context': {}, 'kind': 'default', 'template': 'DZM', 'format': 'pdf'})
    with pytest.raises(service.ClientError, match='не подходит'):
        service.render({'context': example(), 'kind': 'default', 'template': 'screening', 'format': 'html'})


def test_report_check_before_saving(service):
    assert service.report_check({'context': example(), 'kind': 'screening'}) == {'missing': []}
    assert service.report_check({'context': example(participant=''), 'kind': 'screening'}) == {
        'missing': ['Участник: Участник исследования']}
    assert service.report_check({'context': {}, 'kind': 'default'}) == {'missing': []}
    result = service.render({'context': example(participant=''), 'kind': 'screening', 'template': 'screening', 'format': 'html'})
    assert 'Участник исследования:</span> _' in result.data.decode('utf-8'), 'saved anyway, with «_»'


def test_clinbio_gets_word_whatever_format_was_chosen(service, monkeypatch):
    seen = {}
    monkeypatch.setattr(service, 'render', lambda params, caller: seen.update(params) or (_ for _ in ()).throw(RuntimeError('stop')))
    monkeypatch.setattr(service, 'clinbio_configured', lambda caller: True)
    caller = service.Caller(name='alice', multiuser=True)
    with pytest.raises(RuntimeError):
        service.send_clinbio({'context': {}, 'kind': 'default', 'format': 'pdf', 'sample': 's1'}, caller)
    assert seen['format'] == 'docx'
    with pytest.raises(service.ClientError, match='скрининга'):
        service.send_clinbio({'context': {}, 'kind': 'screening', 'sample': 's1'}, caller)


def test_process_screening_and_layout(service, trio_db, engine):
    engine('weasyprint')
    result = service.process({'dbpath': trio_db, 'target': 0, 'mode': 'screening'})
    assert [r['kind'] for r in result['reports']] == ['screening'] * 3
    assert result['reports'][0]['name'] == 'Отчёт ДНК-скрининга (sample1)'
    layout = result['layouts']['screening']
    assert layout['templates'] == [{'id': 'screening', 'title': 'Профилактический ДНК-скрининг', 'formats': ['pdf', 'html', 'docx']}]
    assert layout['pdf_mode'] == 'server' and layout['add_rows'] == ['variants', 'references'] and layout['check_missing']
    assert [x['key'] for x in layout['lists']] == ['interpretation', 'recommendations']
    assert result['layouts']['default']['templates'][0]['formats'] == ['docx']


def test_template_download_of_an_html_template_is_a_zip(service, monkeypatch):
    import zipfile

    assert service.template_file({'id': 'screening'}).filename.endswith('.docx'), 'a template with a .docx gives it'
    real = tpl.TemplateStore.sources
    monkeypatch.setattr(tpl.TemplateStore, 'sources', lambda self, i: dict(real(self, i), docx=None))  # HTML only
    result = service.template_file({'id': 'screening'})
    assert result.filename.endswith('.zip') and result.content_type == 'application/zip'
    names = zipfile.ZipFile(io.BytesIO(result.data)).namelist()
    assert 'screening/template.html' in names and 'screening/fonts/OFL.txt' in names
