"""Report templates: the built-in ones shipped with the module plus the lab's own.

Built-in templates live in the module, one id per design and a file per format:

    templates/docx/<id>.docx            Word (docxtpl)                   -> format docx
    templates/html/<id>/template.html   Jinja HTML + CSS Paged Media     -> formats html and pdf
                       data/            fixed texts the report kind reads (screening: study.json, genes_acmg.json)

A template offers every format it has a file for (builtin_formats). How a document is made: output.py.
Custom templates (the lab's own, .docx only) live in `<conf dir>/clinreport/templates/` (`<id>.docx` +
`templates.json`), next to the settings, so reinstalling or updating the module keeps them.
Adding a template: docs/development/templates.md; fields: docs/reference/data-model.md section 4.

check() renders a template against an example report and lists every field the template
asks for that the report does not have — typos like `{{ patient.birth_dat }}` would
otherwise silently render as empty text.
"""

from __future__ import annotations

import difflib
import io
import json
import os
import re
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, Undefined
from jinja2.exceptions import TemplateError

BUILTIN_DIR = Path(__file__).resolve().parent.parent / 'templates'
DOCX_DIR = BUILTIN_DIR / 'docx'
HTML_DIR = BUILTIN_DIR / 'html'
# (id, title, kind); the formats come from the files (builtin_formats)
BUILTIN = (
    ('DZM', 'DZM', 'default'),
    ('FND', 'FND', 'default'),
    ('10x', '10x', '10x'),
    ('screening', 'Профилактический ДНК-скрининг', 'screening'),
)
KINDS = {
    'default': 'Стандартное заключение',
    '10x': 'LPWGS (технический документ)',
    'screening': 'Профилактический ДНК-скрининг',
}
DEFAULT_FOR_KIND = {'default': 'DZM', '10x': '10x', 'screening': 'screening'}
FORMAT_ORDER = ('pdf', 'html', 'docx')  # the page offers them in this order; the first is preselected


def builtin_formats(template_id: str) -> list:
    """Formats a built-in template has files for, in FORMAT_ORDER."""
    found = set()
    if (DOCX_DIR / f'{template_id}.docx').is_file():
        found.add('docx')
    if (HTML_DIR / template_id / 'template.html').is_file():
        found.update(('html', 'pdf'))
    return [f for f in FORMAT_ORDER if f in found]


def data_dir(kind: str) -> Path:
    """Fixed texts a report kind reads, shared by all its templates: data/ of the kind's built-in HTML template."""
    return HTML_DIR / DEFAULT_FOR_KIND[kind] / 'data'


MAX_TEMPLATE_BYTES = 10 * 1024 * 1024
MANIFEST = 'templates.json'

_lock = threading.Lock()


class TemplateProblem(ValueError):
    """A template cannot be stored or used; the message is shown to the user."""


# --- example report contexts (one row in every list, so loops are rendered too) ---


def _snv_row(gene):
    return {
        'gene': gene,
        'disease': 'Пример заболевания, 610798 (3), Autosomal recessive',
        'variation': 'chr1-156053689-T-G\nNM_020131.5:\nc.13A>C\np.(Ser5Arg)',
        'zygosity': 'Гомозигота\n(Аутосомно-рецессивный)',
        'frequency': '0.01%',
        'coverage': '135x/136x',
        'pathogenicity': 'Патогенный',
        'type': 'Каузативный',
        'manual_criteria': '',
    }


_TECH = {
    'method': 'полногеномное секвенирование (Whole Genome Sequencing)',
    'depth': '30x',
    'reads_nt': 'не менее 90 млрд',
    'read_type': 'парно-концевое',
    'read_length': '150',
    'library_type': 'PCR free',
}
_CNV_ROW = {
    'variation': 'chr1:100000-200000',
    'position': 'chr1:100000-200000',
    'disease': 'Пример',
    'genes': 'GENE1, GENE2',
    'copies': '1',
    'classification': 'Патогенный',
}
_MT_ROW = {
    'gene': 'MT-ND1',
    'disease': 'Пример',
    'variation': 'm.3460G>A',
    'classification': 'Патогенный',
    'coverage': '1000x/1000x',
}


def example_context(kind: str) -> dict:
    """A report context with every field the report builder produces (see docs/05-data-model.md §3)."""
    if kind == 'screening':
        import copy

        from .screening import EXAMPLE

        return copy.deepcopy(EXAMPLE)
    if kind == '10x':
        return {
            'sample': {'id': 'ПРИМЕР-2'},
            'patient': {'lab_number': 'ПРИМЕР-2', 'sex': 'ж', 'diagnosis': 'Пример диагноза'},
            'tech': dict(_TECH),
            'main_variants': [
                {
                    'gene': 'UBQLN4',
                    'hgvsg': 'chr1:g.156053689T>G',
                    'genotype': 'T/G',
                    'qual': '50',
                    'molecules': '11x/22x',
                    'interpretation': 'Пример',
                }
            ],
            'cnv_variants': [dict(_CNV_ROW)],
            'mt_variants': [dict(_MT_ROW)],
        }
    return {
        'patient': {'id': 'ПРИМЕР-1', 'sex': 'м', 'age': '5 лет', 'diagnosis': 'Пример диагноза'},
        'tech': dict(_TECH),
        'report_date': '15.10.2026',
        'clinician': 'Иванова И. И.',
        'p_variants': [_snv_row('UBQLN4')],
        'lp_variants': [_snv_row('GENE2')],
        'vus_variants': [_snv_row('GENE3')],
        'sf_variants': [_snv_row('GENE4')],
        'carrier_variants': [_snv_row('GENE5')],
        'cnv_variants': [dict(_CNV_ROW)],
        'mt_variants': [dict(_MT_ROW)],
        'str_variants': [
            {
                'gene': 'FMR1',
                'disease': 'Пример',
                'expansion': 'CGG',
                'repeat_count': '45',
                'classification': 'Промежуточный',
            }
        ],
        'interpretation': [
            {
                'gene': 'UBQLN4',
                'intro_pre': 'Обнаружен вариант в гене ',
                'intro_post': ', который приводит к аминокислотной замене p.(Ser5Arg).',
                'omim_pre': 'Патогенные варианты в гене ',
                'omim_post': ' приводят к заболеванию.',
                'body': ['Пример абзаца интерпретации.'],
            }
        ],
        'closing': 'Других значимых изменений, соответствующих критериям поиска, не обнаружено.',
    }


def field_paths(kind: str) -> list:
    """Every field of the example context as a template author writes it, e.g. 'patient.id', 'p_variants[].gene'."""
    paths = []

    def walk(value, prefix):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f'{prefix}.{key}' if prefix else key)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            walk(value[0], prefix + '[]')
        else:
            paths.append(prefix)

    walk(check_context(kind), '')
    return paths


# --- rendering ---

_RICHTEXT_FIELDS = ('variation', 'zygosity')


def _str_to_richtext(text: str):
    from docxtpl import RichText

    rt = RichText()
    for i, line in enumerate(str(text).split('\n')):
        rt.add(line if i == 0 else '\n' + line)
    return rt


def richtextify(context: dict) -> dict:
    """Return a render-ready copy with the line-break fields upgraded to RichText."""
    rendered = dict(context)
    for key, value in context.items():
        if isinstance(value, list):  # variant-row lists
            rendered[key] = [_richtextify_row(row) if isinstance(row, dict) else row for row in value]
    return rendered


def _richtextify_row(row: dict) -> dict:
    row = dict(row)
    for field in _RICHTEXT_FIELDS:
        if isinstance(row.get(field), str):
            row[field] = _str_to_richtext(row[field])
    return row


def check_context(kind: str) -> dict:
    """What a template of `kind` is rendered with, from the example report: the context itself, or for 'screening'
    the namespace screening.prepare() makes of it (the templates of that kind read the namespace)."""
    context = example_context(kind)
    if kind == 'screening':
        from .screening import prepare

        context = prepare(context, data_dir(kind))
        context.pop('warnings', None)
    return context


class _Recorder:
    """A Jinja Undefined that remembers which attribute was missing on which object (both checks use it)."""

    def __init__(self):
        self.missing = []
        recorder = self

        class Recording(Undefined):
            def __init__(self, hint=None, obj=None, name=None, exc=None):
                super().__init__(hint=hint, obj=obj, name=name)
                if name is not None:
                    recorder.missing.append((obj, name))

        self.undefined = Recording


def check_html(template_dir, kind: str) -> dict:
    """check() for an HTML template folder: render template.html with the example report of `kind`."""
    from . import output

    rendered = check_context(kind)
    recorder = _Recorder()
    try:
        output.html_document(rendered, Path(template_dir), undefined=recorder.undefined)
    except TemplateError as e:
        line = f' (строка {e.lineno})' if getattr(e, 'lineno', None) else ''
        return {'ok': False, 'error': f'Ошибка в шаблоне{line}: {e.message or e}', 'unknown': []}
    except (OSError, ValueError) as e:
        return {'ok': False, 'error': f'Шаблон не собирается: {e}', 'unknown': []}
    unknown = _unknown_fields(recorder.missing, rendered)
    return {'ok': not unknown, 'error': None, 'unknown': unknown}


def _unknown_fields(missing, rendered) -> list:
    owners = {}

    def index(value, prefix):
        if isinstance(value, dict):
            owners[id(value)] = (prefix, value)
            for key, item in value.items():
                index(item, f'{prefix}.{key}' if prefix else key)
        elif isinstance(value, list):
            for item in value:
                index(item, prefix + '[]')

    index(rendered, '')
    unknown, seen = [], set()
    for obj, name in missing:
        prefix, owner = owners.get(id(obj), ('', rendered if obj is None else None))
        if obj is not None and owner is None:
            continue
        field = f'{prefix}.{name}' if prefix else name
        if field in seen:
            continue
        seen.add(field)
        close = difflib.get_close_matches(name, list(owner.keys()) if isinstance(owner, dict) else [], n=1)
        unknown.append({'field': field, 'suggestion': (f'{prefix}.{close[0]}' if prefix else close[0]) if close else ''})
    return unknown


def check(source, kind: str) -> dict:
    """Render `source` (path or bytes of a .docx) with the example context of `kind`.

    Returns {'ok': bool, 'error': str|None, 'unknown': [{'field', 'suggestion'}]}.
    """
    from docxtpl import DocxTemplate

    context = check_context(kind)
    # Where each dict of the example lives, to name a missing attribute by its path.
    owners = {}

    def index(value, prefix):
        if isinstance(value, dict):
            owners[id(value)] = (prefix, value)
            for key, item in value.items():
                index(item, f'{prefix}.{key}' if prefix else key)
        elif isinstance(value, list):
            for item in value:
                index(item, prefix + '[]')

    if kind == 'screening':
        from .output import screening_docx_namespace

        rendered = screening_docx_namespace(context)
    else:
        rendered = richtextify(context)
    index(rendered, '')
    for key, rows in rendered.items():  # richtextify copied the rows; index the copies under the same names
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    owners[id(row)] = (key + '[]', row)

    missing = []

    class Recording(Undefined):
        def __init__(self, hint=None, obj=None, name=None, exc=None):
            super().__init__(hint=hint, obj=obj, name=name)
            if name is not None:
                missing.append((obj, name))

    try:
        document = DocxTemplate(io.BytesIO(source) if isinstance(source, bytes) else str(source))
        document.render(rendered, jinja_env=Environment(undefined=Recording))
        document.save(io.BytesIO())
    except TemplateError as e:
        line = f' (строка {e.lineno})' if getattr(e, 'lineno', None) else ''
        return {'ok': False, 'error': f'Ошибка в полях шаблона{line}: {e.message or e}', 'unknown': []}
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        return {'ok': False, 'error': f'Файл не похож на документ Word (.docx): {e}', 'unknown': []}

    unknown, seen = [], set()
    for obj, name in missing:
        prefix, owner = owners.get(id(obj), ('', rendered if obj is None else None))
        if obj is not None and owner is None:
            continue  # attribute of a value that is not part of the report (e.g. a string method)
        field = f'{prefix}.{name}' if prefix else name
        if field in seen:
            continue
        seen.add(field)
        choices = list(owner.keys()) if isinstance(owner, dict) else []
        close = difflib.get_close_matches(name, choices, n=1)
        unknown.append(
            {'field': field, 'suggestion': (f'{prefix}.{close[0]}' if prefix else close[0]) if close else ''}
        )
    return {'ok': not unknown, 'error': None, 'unknown': unknown}


# --- store ---


def _slug(title: str) -> str:
    base = re.sub(r'[^0-9A-Za-z]+', '-', title).strip('-').lower()[:40]
    return base or 'template'


class TemplateStore:
    def __init__(self, conf_dir):
        self.dir = Path(conf_dir) / 'clinreport' / 'templates'

    # manifest
    def _read(self) -> list:
        try:
            with open(self.dir / MANIFEST, encoding='utf-8') as fh:
                entries = json.load(fh).get('templates', [])
        except FileNotFoundError:
            return []
        return [e for e in entries if (self.dir / e.get('file', '')).is_file()]

    def _write(self, entries: list):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / (MANIFEST + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump({'templates': entries}, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.dir / MANIFEST)

    # queries
    def list(self) -> list:
        items = [
            {'id': tid, 'title': title, 'kind': kind, 'builtin': True, 'formats': builtin_formats(tid)}
            for tid, title, kind in BUILTIN
        ]
        for entry in self._read():
            items.append(
                {
                    'id': entry['id'],
                    'title': entry['title'],
                    'kind': entry['kind'],
                    'builtin': False,
                    'formats': ['docx'],
                    'added': entry.get('added', ''),
                    'check': entry.get('check'),
                }
            )
        return items

    def for_kind(self, kind: str) -> list:
        return [t for t in self.list() if t['kind'] == kind]

    def get(self, template_id: str) -> dict:
        for item in self.list():
            if item['id'] == template_id:
                return item
        raise TemplateProblem(f'Неизвестный шаблон: {template_id}')

    def sources(self, template_id: str) -> dict:
        """{'docx': path | None, 'html': template folder | None}."""
        for tid, _title, _kind in BUILTIN:
            if tid == template_id:
                formats = builtin_formats(tid)
                return {
                    'docx': DOCX_DIR / f'{tid}.docx' if 'docx' in formats else None,
                    'html': HTML_DIR / tid if 'html' in formats else None,
                }
        for entry in self._read():
            if entry['id'] == template_id:
                return {'docx': self.dir / entry['file'], 'html': None}
        raise TemplateProblem(f'Неизвестный шаблон: {template_id}')

    def path(self, template_id: str) -> Path:
        """The template's .docx, else its HTML folder (shown in Explorer / Finder, «Скачать образец»)."""
        sources = self.sources(template_id)
        return sources['docx'] or sources['html']

    # changes
    def add(self, title: str, kind: str, data: bytes, replace: str = '') -> dict:
        title = (title or '').strip()
        if not title:
            raise TemplateProblem('Укажите название шаблона.')
        if kind not in KINDS:
            raise TemplateProblem(f'Неизвестный тип шаблона: {kind}')
        if not data:
            raise TemplateProblem('Файл шаблона пуст.')
        if len(data) > MAX_TEMPLATE_BYTES:
            raise TemplateProblem(f'Файл больше {MAX_TEMPLATE_BYTES // (1024 * 1024)} МБ.')
        result = check(data, kind)
        if result['error']:
            raise TemplateProblem(result['error'])
        with _lock:
            entries = self._read()
            builtin_titles = {t.lower() for _i, t, _k in BUILTIN}
            if replace:
                entry = next((e for e in entries if e['id'] == replace), None)
                if entry is None:
                    raise TemplateProblem(f'Неизвестный шаблон: {replace}')
            else:
                if title.lower() in builtin_titles or any(e['title'].lower() == title.lower() for e in entries):
                    raise TemplateProblem(f'Шаблон «{title}» уже есть — выберите другое название.')
                taken = {e['id'] for e in entries} | {i for i, _t, _k in BUILTIN}
                base = template_id = 'u-' + _slug(title)
                n = 2
                while template_id in taken:
                    template_id, n = f'{base}-{n}', n + 1
                entry = {'id': template_id, 'file': f'{template_id}.docx'}
                entries.append(entry)
            entry.update(
                title=title,
                kind=kind,
                added=datetime.now().isoformat(timespec='seconds'),
                check={'ok': result['ok'], 'unknown': result['unknown']},
            )
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / entry['file']).write_bytes(data)
            self._write(entries)
        return dict(self.get(entry['id']), check=entry['check'])

    def delete(self, template_id: str):
        with _lock:
            entries = self._read()
            entry = next((e for e in entries if e['id'] == template_id), None)
            if entry is None:
                if any(template_id == tid for tid, _t, _k in BUILTIN):
                    raise TemplateProblem('Встроенные шаблоны удалить нельзя.')
                raise TemplateProblem(f'Неизвестный шаблон: {template_id}')
            entries.remove(entry)
            self._write(entries)
            try:
                (self.dir / entry['file']).unlink()
            except FileNotFoundError:
                pass

    def recheck(self, template_id: str) -> dict:
        item = self.get(template_id)
        sources = self.sources(template_id)
        results = [check(sources['docx'], item['kind'])] if sources['docx'] else []
        if sources['html']:
            results.append(check_html(sources['html'], item['kind']))
        result = {
            'ok': all(r['ok'] for r in results),
            'error': next((r['error'] for r in results if r['error']), None),
            'unknown': [u for r in results for u in r['unknown']],
        }
        if not item['builtin']:
            with _lock:
                entries = self._read()
                for entry in entries:
                    if entry['id'] == template_id:
                        entry['check'] = {'ok': result['ok'], 'unknown': result['unknown']}
                self._write(entries)
        return result
