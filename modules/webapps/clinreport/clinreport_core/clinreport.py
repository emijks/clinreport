from datetime import date
from pathlib import Path

import pandas as pd
from docxtpl import DocxTemplate, RichText

from database import VariantSource
from process import SampleProcessor


TEMPLATES_DIR = Path(__file__).resolve().parent / 'templates'
TEMPLATES = {
    'DZM': TEMPLATES_DIR / 'DZM.docx',
    'FND': TEMPLATES_DIR / 'FND.docx',
    '10x': TEMPLATES_DIR / '10x.docx',
}

_RICHTEXT_FIELDS = ('variation', 'zygosity')


def _str_to_richtext(text: str) -> RichText:
    rt = RichText()
    for i, line in enumerate(str(text).split('\n')):
        rt.add(line if i == 0 else '\n' + line)
    return rt


def _richtextify(context: dict) -> dict:
    """Return a render-ready copy with the line-break fields upgraded to RichText."""
    rendered = dict(context)
    for key, value in context.items():
        if isinstance(value, list):  # variant-row lists
            rendered[key] = [_richtextify_row(row) for row in value]
    return rendered


def _richtextify_row(row: dict) -> dict:
    row = dict(row)
    for field in _RICHTEXT_FIELDS:
        if isinstance(row.get(field), str):
            row[field] = _str_to_richtext(row[field])
    return row


class ClinReport:
    """
    Session for one OpenCRAVAT SQLite, shared by the CLI (main.py) and the GUI.
    """

    def __init__(self, source, *, target_sample=None, clinician=None, ru_annotations=None):
        self.source = source if isinstance(source, VariantSource) else VariantSource(source)
        self.clinician = clinician
        self.ru_annotations = ru_annotations
        self.all_samples = self.source.get_all_samples()
        self.target_sample = target_sample or self.all_samples[0]
        self._raw_variants = None

    @property
    def raw_variants(self) -> list:
        if self._raw_variants is None:
            self._raw_variants = self.source.get_variants()
        return self._raw_variants

    def processor_for(self, sample) -> SampleProcessor:
        return SampleProcessor(
            self.raw_variants,
            sample,
            target_sample=self.target_sample,
            all_samples=self.all_samples,
            clinician=self.clinician,
            ru_annotations=self.ru_annotations,
        )

    def build_context(self, sample, report_type='default') -> dict:
        """Build the template context for one sample. report_type: 'default' | '10x'."""
        processor = self.processor_for(sample)
        if report_type == '10x':
            return processor.build_10x_context()
        return processor.build_default_context()

    def render(self, context: dict, template='DZM') -> DocxTemplate:
        """Render a (possibly GUI-edited) context. template: 'DZM' | 'FND' | '10x'."""
        document = DocxTemplate(str(TEMPLATES[template]))
        document.render(_richtextify(context))
        return document
