#! /usr/bin/env python3
"""Generate templates/docx/screening.docx: the Word version of «Профилактический ДНК-скрининг».

    python packaging/make_screening_docx.py        (needs python-docx: pip install -r requirements-dev.txt)

A basic layout with the sections, fields and loops of the HTML template (templates/html/screening/); the fixed texts
are taken from its partials, so the wording stays the same. It reads what screening.prepare() makes (fields:
«Список полей» or docs/reference/data-model.md). Rich-text values (interpretation, recommendations, references,
gene_groups[].text) arrive as docxtpl RichText — `{{r … }}`. Re-run after a text change in the partials and commit
the output; edit the result in Word only if you stop generating it (then delete this script).
"""

import html
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / 'modules' / 'webapps' / 'clinreport' / 'templates'
PARTIALS = TEMPLATE / 'html' / 'screening' / 'partials'
OUT = TEMPLATE / 'docx' / 'screening.docx'
MUTED = RGBColor(0x59, 0x59, 0x59)


def paragraphs_of(partial: str) -> list:
    """Text of every <p> of a partial: tags dropped, Jinja expressions kept (docxtpl reads them)."""
    source = (PARTIALS / partial).read_text(encoding='utf-8')
    found = []
    for body in re.findall(r'<p(?:\s[^>]*)?>(.*?)</p>', source, flags=re.S):
        text = re.sub(r'<sup[^>]*>.*?</sup>', '', body, flags=re.S)  # footnote calls
        text = html.unescape(re.sub(r'<[^>]+>', '', text))
        found.append(re.sub(r'\s+', ' ', text).strip())
    return found


def heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
    return p


def para(doc, text='', *, bold=False, italic=False, size=None, align=None, style=None, color=None):
    p = doc.add_paragraph(style=style)
    if text:
        run = p.add_run(text)
        run.bold, run.italic = bold, italic
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = color
    if align is not None:
        p.alignment = align
    return p


def cell_lines(cell, lines):
    """Lines in one table cell: [(text, {'bold','italic','small'})] — each line a paragraph."""
    cell.paragraphs[0].text = ''
    for i, (text, style) in enumerate(lines):
        p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        run = p.add_run(text)
        run.bold, run.italic = style.get('bold', False), style.get('italic', False)
        run.font.size = Pt(7.5 if style.get('small') else 9)
        if style.get('small'):
            run.font.color.rgb = MUTED


def page_number_field(paragraph):
    run = paragraph.add_run()
    for tag, text in (('begin', None), (None, 'PAGE'), ('end', None)):
        if tag:
            element = OxmlElement('w:fldChar')
            element.set(qn('w:fldCharType'), tag)
        else:
            element = OxmlElement('w:instrText')
            element.set(qn('xml:space'), 'preserve')
            element.text = text
        run._r.append(element)


def borders(table):
    tbl_pr = table._tbl.tblPr
    element = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        b = OxmlElement(f'w:{edge}')
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), '4')
        b.set(qn('w:color'), '1A1A1A')
        element.append(b)
    tbl_pr.append(element)


def main():
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(1.8)
    section.top_margin = section.bottom_margin = Cm(2.2)
    normal = doc.styles['Normal']
    normal.font.name, normal.font.size = 'Times New Roman', Pt(10.5)

    footer = section.footer.paragraphs[0]
    footer.text = ('*Научный отчет носит ознакомительный характер, не является диагнозом и рекомендацией. '
                   'По всем вопросам необходимо обратиться к Вашему лечащему врачу.   СТР. ')
    for run in footer.runs:
        run.italic, run.font.size, run.font.color.rgb = True, Pt(7.5), MUTED
    page_number_field(footer)

    # cover
    para(doc, 'Отчет по результатам исследования генетических вариантов', size=18, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, '{{ study.report_title }}', size=14, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc)
    for label, field in (('Участник исследования', 'participant'), ('Пол', 'sex'), ('Дата исследования', 'date')):
        p = para(doc, f'{label}: ', bold=True)
        p.add_run('{{ patient.' + field + ' }}')

    # results
    heading(doc, 'Результаты исследования')
    para(doc, 'Клинически значимые варианты в генах из списка ACMG*', bold=True)
    table = doc.add_table(rows=7, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    borders(table)
    for cell, title in zip(table.rows[0].cells, ('Ген', 'Ассоциированное заболевание (OMIM)',
                                                  'Изменение ДНК (GRCh38) (изменение белка)',
                                                  'Зиготность (тип наследования)', 'Частота**',
                                                  'Кол-во прочтений (альт./общ.)'), strict=True):
        cell_lines(cell, [(title, {'bold': True})])
    cell_lines(table.rows[1].cells[0], [('{%tr for v in variants %}', {})])
    row = table.rows[2].cells
    cell_lines(row[0], [('{{ v.gene }}', {'bold': True, 'italic': True}), ('{{ v.classification }}', {'small': True})])
    cell_lines(row[1], [('{{ v.disease }}', {}), ('{% if v.omim %}OMIM #{{ v.omim }}{% endif %}', {'small': True})])
    cell_lines(row[2], [('{{ v.position }}', {}), ('{{ v.hgvs_c }}', {'small': True}),
                        ('{% if v.hgvs_p %}({{ v.hgvs_p }}){% endif %}', {})])
    cell_lines(row[3], [('{{ v.zygosity }}', {}), ('({{ v.inheritance }})', {})])
    cell_lines(row[4], [('{{ v.frequency }}', {})])
    cell_lines(row[5], [('{{ v.reads_alt }}/{{ v.reads_total }}', {})])
    cell_lines(table.rows[3].cells[0], [('{%tr endfor %}', {})])
    cell_lines(table.rows[4].cells[0], [('{%tr if not variants %}', {})])
    empty = table.rows[5].cells[0].merge(table.rows[5].cells[5])
    cell_lines(empty, [('Не обнаружено.', {})])
    cell_lines(table.rows[6].cells[0], [('{%tr endif %}', {})])
    para(doc, '*{{ study.acmg_version }} list for reporting of secondary findings in clinical exome and genome '
         'sequencing: A policy statement of the American College of Medical Genetics and Genomics (ACMG): '
         '{{ acmg_genes|join(", ") }}.', size=7)
    para(doc, '** {{ study.gnomad_note }}', size=7)
    para(doc, '{{ inheritance_legend }}', size=7)

    heading(doc, 'Интерпретация вариантов')
    para(doc, '{%p if variants %}')
    para(doc, '{%p for par in interpretation %}')
    para(doc, '{{r par }}')
    para(doc, '{%p endfor %}')
    para(doc, '{%p else %}')
    para(doc, 'Значимых изменений, соответствующих критериям поиска, не обнаружено.')
    para(doc, '{%p endif %}')
    fixed = paragraphs_of('results.html')
    para(doc, next(t for t in fixed if t.startswith('Оценка клинической значимости')))
    para(doc, next(t for t in fixed if t.startswith('Результаты данного исследования')), bold=True)

    para(doc, 'Рекомендации:', bold=True)
    para(doc, '{%p for r in recommendations %}')
    para(doc, '{{r r }}', style='List Number')
    para(doc, '{%p endfor %}')

    # the fixed sections of the HTML template, same words
    heading(doc, 'Информация об исследовании')
    for text in paragraphs_of('info.html'):
        para(doc, text)
    footnote = re.search(r'<div class="fnote">(.*?)</div>', (PARTIALS / 'info.html').read_text(encoding='utf-8'), re.S)
    para(doc, html.unescape(re.sub(r'<[^>]+>', '', footnote.group(1))).strip(), size=8, color=MUTED)

    heading(doc, 'Список генов, входящих в программу профилактического ДНК-скрининга')
    para(doc, '{%p for g in gene_groups %}')
    para(doc, '{{ g.title }}', bold=True)
    para(doc, '{%p for par in g.text %}')
    para(doc, '{{r par }}')
    para(doc, '{%p endfor %}')
    para(doc, 'Гены: {{ g.genes|join(", ") }}', italic=True)
    para(doc, '{%p endfor %}')

    heading(doc, 'Ограничения исследования')
    for text in paragraphs_of('limitations.html'):
        para(doc, text)
    heading(doc, 'Описание методов исследования')
    for text in paragraphs_of('methods.html'):
        para(doc, text)

    heading(doc, 'Технические характеристики исследования')
    tech = doc.add_table(rows=6, cols=2)
    borders(tech)
    for r, (label, value) in enumerate((
        ('Метод исследования:', '{{ study.tech.method }}'),
        ('Средняя глубина прочтения генома после секвенирования:', '{{ patient.mean_depth }}'),
        ('Количество прочитанных нуклеотидов:', '{{ study.tech.bases }}'),
        ('Тип прочтения:', '{{ study.tech.read_type }}'),
        ('Длина прочтения:', '{{ study.tech.read_length }}'),
        ('Качество выходных данных секвенирования:',
         '{% for q in study.tech.quality %}{{ loop.index }}. {{ q }} {% endfor %}'),
    )):
        cell_lines(tech.rows[r].cells[0], [(label, {})])
        cell_lines(tech.rows[r].cells[1], [(value, {})])

    heading(doc, 'Список литературы и баз данных')
    para(doc, '{%p for r in references %}')
    para(doc, '{{r r }}', style='List Number')
    para(doc, '{%p endfor %}')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(f'wrote {OUT.relative_to(REPO)}')


if __name__ == '__main__':
    main()
