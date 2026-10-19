"""Display labels, the review-page layout and the Postgres payload mapping.

Ported from clinreport/ui/labels.py (the Tk-free part). The review page gets
LAYOUTS from the server, so column titles live only here.
"""

from __future__ import annotations

from datetime import date

FIELD_LABELS = {
    'gene': 'Ген',
    'disease': 'Ассоциированное заболевание (OMIM)',
    'variation': 'Изменение ДНК (HG38) (Изменение белка)',
    'zygosity': 'Зиготность (Тип наследования)',
    'frequency': 'Частота*',
    'coverage': 'Кол-во прочтений (АЛТ/ОБЩ)',
    'manual_criteria': 'Ручные критерии',
    'pathogenicity': 'Патогенность',
    'type': 'Тип',
}

SNV_FIELDS = ('gene', 'disease', 'variation', 'zygosity', 'frequency', 'coverage')
CARRIER_FIELDS = SNV_FIELDS + ('pathogenicity',)

# (context key, section title, fields) for the default report's variant tables.
DEFAULT_VARIANT_TABLES = (
    ('p_variants', 'Патогенные варианты', SNV_FIELDS),
    ('lp_variants', 'Вероятно патогенные варианты', SNV_FIELDS),
    ('vus_variants', 'Варианты с неопределённой клинической значимостью', SNV_FIELDS),
    ('sf_variants', 'Клинически значимые варианты, не связанные с основным диагнозом', SNV_FIELDS),
    ('carrier_variants', 'Носительство', CARRIER_FIELDS),
)

# Patient/tech common table: (context section, key, label).
COMMON_FIELDS = (
    ('patient', 'id', 'Номер образца'),
    ('patient', 'sex', 'Пол пациента'),
    ('patient', 'age', 'Возраст пациента'),
    ('patient', 'diagnosis', 'Предварительный диагноз'),
    ('tech', 'depth', 'Средняя глубина прочтения генома после секвенирования'),
)

# --- 10x / LPWGS technical report ---
MAIN_VARIANT_FIELDS = ('gene', 'hgvsg', 'genotype', 'qual', 'molecules', 'interpretation')
MAIN_VARIANT_LABELS = {
    'gene': 'Ген',
    'hgvsg': 'HGVSg',
    'genotype': 'Генотип',
    'qual': 'Качество определения альтернативного аллеля (QUAL)',
    'molecules': 'Количество молекул в позиции (альтернатиный/общий)',
    'interpretation': 'Интерпретация',
}
TEN_X_COMMON_FIELDS = (
    ('patient', 'lab_number', 'Лабораторный номер'),
    ('patient', 'sex', 'Пол'),
    ('patient', 'diagnosis', 'Направительный диагноз ребенка'),
)


def _layout(common_fields, tables, field_labels, *, similar, upload, templates):
    return {
        'common': [{'section': s, 'key': k, 'label': label} for s, k, label in common_fields],
        'tables': [
            {
                'key': key,
                'title': title,
                'columns': [{'field': f, 'label': field_labels[f]} for f in fields],
            }
            for key, title, fields in tables
        ],
        'similar': similar,
        'upload': upload,
        'templates': templates,
    }


LAYOUTS = {
    'default': _layout(
        COMMON_FIELDS,
        DEFAULT_VARIANT_TABLES,
        FIELD_LABELS,
        similar=True,
        upload=True,
        templates=['DZM', 'FND'],
    ),
    '10x': _layout(
        TEN_X_COMMON_FIELDS,
        (('main_variants', 'Результаты исследования', MAIN_VARIANT_FIELDS),),
        MAIN_VARIANT_LABELS,
        similar=False,
        upload=False,
        templates=['10x'],
    ),
}


# --- Postgres ReportedVariants payload (context dict -> records) ---
PAYLOAD_COMMON = (
    ('patient', 'id', 'Номер образца'),
    ('patient', 'sex', 'Пол пациента'),
    ('patient', 'age', 'Возраст пациента'),
    ('patient', 'diagnosis', 'Предварительный диагноз'),
)
PAYLOAD_VARIANT_FIELDS = (
    'gene',
    'disease',
    'variation',
    'zygosity',
    'frequency',
    'coverage',
    'manual_criteria',
    'pathogenicity',
    'type',
)
PAYLOAD_SECTIONS = ('p_variants', 'lp_variants', 'vus_variants', 'sf_variants', 'carrier_variants')


def context_to_payload_records(context):
    """Flatten a default-report context into Postgres ReportedVariants records.

    One record per variant across the uploaded sections, each carrying the shared
    patient/clinician columns. 'Дата заключения' is ISO (matches the DB column),
    not the dd.mm.yyyy display date in context['report_date'].
    """
    common = {label: context[section][key] for section, key, label in PAYLOAD_COMMON}
    common['Клиницист'] = context.get('clinician', '')
    common['Дата заключения'] = date.today().isoformat()

    records = []
    for section in PAYLOAD_SECTIONS:
        for row in context.get(section, []):
            record = dict(common)
            for field in PAYLOAD_VARIANT_FIELDS:
                record[FIELD_LABELS[field]] = row.get(field, '')
            records.append(record)
    return records
