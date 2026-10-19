"""ClinReport core: OpenCRAVAT SQLite -> template context -> .docx (no GUI code)."""

from .clinreport import DEFAULT_TEMPLATES, TEMPLATES, ClinReport, render_context
from .database import Database, VariantSource, get_ru_annotations
from .labels import LAYOUTS, context_to_payload_records

__all__ = [
    'ClinReport',
    'DEFAULT_TEMPLATES',
    'TEMPLATES',
    'render_context',
    'Database',
    'VariantSource',
    'get_ru_annotations',
    'LAYOUTS',
    'context_to_payload_records',
]
