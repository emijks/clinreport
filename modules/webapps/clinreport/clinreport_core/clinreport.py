from __future__ import annotations

from pathlib import Path

from docxtpl import DocxTemplate

from .database import VariantSource
from .process import SampleProcessor
from .templates import BUILTIN, BUILTIN_DIR, richtextify

TEMPLATES_DIR = BUILTIN_DIR
TEMPLATES = {tid: BUILTIN_DIR / f'{tid}.docx' for tid, _title, _kind in BUILTIN}
DEFAULT_TEMPLATES = tuple(tid for tid, _title, kind in BUILTIN if kind == 'default')


def render_context(context: dict, template='DZM') -> DocxTemplate:
    """Render a (possibly GUI-edited) context with a built-in template id ('DZM' | 'FND' | '10x') or a .docx path."""
    path = TEMPLATES[template] if template in TEMPLATES else Path(template)
    document = DocxTemplate(str(path))
    document.render(richtextify(context))
    return document


class ClinReport:
    """Session for one OpenCRAVAT SQLite."""

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
        return render_context(context, template)
