"""Report templates: the built-in ones shipped with the module plus the lab's own.

Custom templates live in `<conf dir>/clinreport/templates/` (`<id>.docx` + `templates.json`),
next to the settings, so reinstalling or updating the module keeps them. Templates are
docxtpl (.docx with Jinja tags); see docs/05-data-model.md#4-template-variables.

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
# (id, title, kind)
BUILTIN = (
    ('DZM', 'DZM', 'default'),
    ('FND', 'FND', 'default'),
    ('10x', '10x', '10x'),
)
KINDS = {
    'default': 'Стандартное заключение',
    '10x': 'LPWGS (технический документ)',
}
DEFAULT_FOR_KIND = {'default': 'DZM', '10x': '10x'}
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

    walk(example_context(kind), '')
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


def check(source, kind: str) -> dict:
    """Render `source` (path or bytes) with the example context of `kind`.

    Returns {'ok': bool, 'error': str|None, 'unknown': [{'field', 'suggestion'}]}.
    """
    from docxtpl import DocxTemplate

    context = example_context(kind)
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
        items = [{'id': tid, 'title': title, 'kind': kind, 'builtin': True} for tid, title, kind in BUILTIN]
        for entry in self._read():
            items.append(
                {
                    'id': entry['id'],
                    'title': entry['title'],
                    'kind': entry['kind'],
                    'builtin': False,
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

    def path(self, template_id: str) -> Path:
        for tid, _title, _kind in BUILTIN:
            if tid == template_id:
                return BUILTIN_DIR / f'{tid}.docx'
        for entry in self._read():
            if entry['id'] == template_id:
                return self.dir / entry['file']
        raise TemplateProblem(f'Неизвестный шаблон: {template_id}')

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
        result = check(self.path(template_id), item['kind'])
        if not item['builtin']:
            with _lock:
                entries = self._read()
                for entry in entries:
                    if entry['id'] == template_id:
                        entry['check'] = {'ok': result['ok'], 'unknown': result['unknown']}
                self._write(entries)
        return result
