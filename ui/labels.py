"""Display labels and pure context<->tableview mapping for the GUI.

Variant-row context dicts use machine keys (gene, variation, ...); the UI shows
Russian column labels and edits plain strings. These helpers translate between
the two with no Tk dependency, so they are unit-testable headless.
"""

FIELD_LABELS = {
    'gene': 'Ген',
    'disease': 'Ассоциированное заболевание (OMIM)',
    'variation': 'Изменение ДНК (HG38) (Изменение белка)',
    'zygosity': 'Зиготность (Тип наследования)',
    'frequency': 'Частота*',
    'coverage': 'Кол-во прочтений (АЛТ/ОБЩ)',
    'pathogenicity': 'Патогенность',
}
LABEL_TO_FIELD = {label: field for field, label in FIELD_LABELS.items()}

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


def variant_rows_to_values(rows, fields):
    """Context variant rows -> list of ordered value lists for a Tableview."""
    return [[str(row.get(field, '')) for field in fields] for row in rows]


def apply_variant_edits(rows, fields, edited_values):
    """Write edited Tableview values back into the context rows, in place."""
    for row, values in zip(rows, edited_values):
        for field, value in zip(fields, values):
            row[field] = value


def common_values(context, common_fields=COMMON_FIELDS):
    """Single-row patient/tech values for the common Tableview."""
    return [[str(context[section][key]) for section, key, _ in common_fields]]


def apply_common_edits(context, edited_row, common_fields=COMMON_FIELDS):
    """Write edited common-table values back into the context, in place."""
    for (section, key, _), value in zip(common_fields, edited_row):
        context[section][key] = value
