"""«Профилактический ДНК-скрининг» — the report kind 'screening'.

Ported from KateAnpilogova/Secondary-findings (render.py, commit 058240c): the checks, the frequency format and the
citation numbering are the same; the context comes from the OpenCRAVAT result instead of a hand-written JSON.

The context (POST process → the review page edits it → render) holds strings only, so every value is editable:

    patient:         {id, participant, sex, date, mean_depth}
    variants:        [{gene, disease, omim, position, hgvs_c, hgvs_p, classification, zygosity, inheritance,
                       frequency, reads_alt, reads_total}]
    interpretation:  [paragraph]  — may contain <i> <b> <em> <strong> <sup> <sub> <br>; cites extra sources as [@key]
    recommendations: [text]       — empty: the template's default recommendations (data/study.json)
    references:      [{key, text}] — extra sources for [@key]; numbered after the template's fixed list

prepare() turns it into what the templates read (every format: html, pdf, docx); the template's data/ folder
(study.json, genes_acmg.json) supplies the fixed texts. Variants: Notes 1 (P) and 2 (LP) of the sample.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

NOTES = {'1': 'патогенный', '2': 'вероятно патогенный'}
ZYGOSITY = ('гетерозигота', 'гомозигота', 'гемизигота', 'компаунд-гетерозигота')
INHERITANCE = {
    'АД': 'аутосомно-доминантный',
    'АР': 'аутосомно-рецессивный',
    'ХД': 'Х-сцепленный доминантный',
    'ХР': 'Х-сцепленный рецессивный',
    'ХС': 'Х-сцепленный',
}
CLASSIFICATION = ('патогенный', 'вероятно патогенный')
REQUIRED_PATIENT = (('participant', 'участник исследования'), ('sex', 'пол'), ('date', 'дата исследования'),
                    ('mean_depth', 'средняя глубина прочтения'))
REQUIRED_VARIANT = ('gene', 'disease', 'position', 'hgvs_c', 'zygosity', 'inheritance', 'reads_alt', 'reads_total')
VARIANT_FIELDS = ('gene', 'disease', 'omim', 'position', 'hgvs_c', 'hgvs_p', 'classification', 'zygosity',
                  'inheritance', 'frequency', 'reads_alt', 'reads_total')
PLACEHOLDER = '_'  # what the clinician still has to fill in (as in the other reports)

_ZYGOSITY_FROM_OC = {'het': 'гетерозигота', 'hom': 'гомозигота', 'hemi': 'гемизигота'}
_INHERITANCE_FROM_OC = {'AD': 'АД', 'AR': 'АР', 'XD': 'ХД', 'XR': 'ХР', 'XL': 'ХС'}
_MIM = re.compile(r'(?<!\d)(\d{6})(?!\d)')


class ReportProblem(ValueError):
    """The report cannot be made; .problems lists why (Russian, shown on the page)."""

    def __init__(self, problems):
        super().__init__('\n'.join(problems))
        self.problems = list(problems)


# --- the context, from an OpenCRAVAT result ---


def build_context(processor) -> dict:
    """The screening context of processor.sample_id (a process.SampleProcessor)."""
    sample_variants = processor.filter_variants(processor.raw_variants, by_sample=processor.sample_id)
    variants, paragraphs = [], []
    for note in NOTES:
        for variant in processor.filter_variants(sample_variants, by_note=note):
            variants.append(_variant_row(processor, variant, note))
            paragraphs.append(_paragraph(processor, variant))
    return {
        'patient': {
            'id': processor.sample_name,
            'participant': PLACEHOLDER,
            'sex': PLACEHOLDER,
            'date': date.today().strftime('%d.%m.%Y'),
            'mean_depth': PLACEHOLDER + '×',
        },
        'variants': variants,
        'interpretation': paragraphs,
        'recommendations': [],
        'references': [],
    }


def _variant_row(processor, variant: dict, note: str) -> dict:
    symbol = variant['vep_csq__symbol'] or ''
    hgvsc = variant['vep_csq__hgvsc'] or ''
    transcript = variant['vep_csq__refseq'] or variant['vep_csq__transcript'] or ''
    hgvsp = (variant['vep_csq__hgvsp'] or '').replace('%3D', '=')
    pheno = variant['vep_omim_pheno__pheno'] or ''
    inheritance = _inheritance(variant['vep_omim_pheno__inher'])
    sheet = (processor.ru_annotations or {}).get('secondary', {})  # the lab's sheet of ACMG SF genes
    disease = sheet.get('Disease/Phentyope', {}).get(symbol) or pheno
    if sheet.get('Inheritance', {}).get(symbol):
        inheritance = _inheritance(sheet['Inheritance'][symbol]) or inheritance
    mim = _MIM.search(pheno) or _MIM.search(str(variant.get('vep_omim_pheno__id') or ''))
    agg = processor.get_gnomad4aggregated(variant)
    zygosity = variant['tagsampler_new__zygosity'] or ''
    return {
        'gene': symbol,
        'disease': _strip_omim(disease),
        'omim': mim.group(1) if mim else '',
        'position': f"{variant['base__chrom']}:{variant['extra_vcf_info__pos']} "
        f"{variant['extra_vcf_info__ref']}>{variant['extra_vcf_info__alt']}",
        'hgvs_c': f'{transcript}:{hgvsc}' if transcript and hgvsc else hgvsc,
        'hgvs_p': hgvsp,
        'classification': NOTES[note],
        'zygosity': _ZYGOSITY_FROM_OC.get(zygosity, zygosity or PLACEHOLDER),
        'inheritance': inheritance or PLACEHOLDER,
        'frequency': fmt_freq(agg['AF'] or None),  # 0 = not seen in gnomAD: «—», as upstream
        'reads_alt': str(variant['tagsampler_new__ad'] or PLACEHOLDER),
        'reads_total': str(variant['tagsampler_new__dp'] or PLACEHOLDER),
    }


def _inheritance(value) -> str:
    """One code (АД, АР, …) or '' when OpenCRAVAT gives none or several — the clinician decides then."""
    codes = {_INHERITANCE_FROM_OC.get(part.strip().upper(), part.strip()) for part in str(value or '').split(',')}
    codes.discard('')
    return codes.pop() if len(codes) == 1 and next(iter(codes)) in INHERITANCE else ''


def _strip_omim(disease: str) -> str:
    """'Hemochromatosis, type 1, 235200 (3), Autosomal recessive' → 'Hemochromatosis, type 1' (OMIM has its own column)."""
    text = str(disease).split('|')[0]
    match = _MIM.search(text)
    return text[: match.start()].rstrip(' ,;') if match else text.strip()


def _paragraph(processor, variant: dict) -> str:
    """The diagnostic report's narrative for this variant as one paragraph (a draft for the clinician to edit),
    without the sentence about the patient's phenotype: a screening participant has no diagnosis. Plain text plus
    <i> around the gene: what the clinician sees and edits; rich_html() escapes the rest when the report is made."""
    n = processor._variant_narrative(variant)
    gene = f"<i>{n['gene'] or ''}</i>"
    parts = [n['intro_pre'] + gene + n['intro_post']]
    if n['omim_pre']:
        parts.append(n['omim_pre'] + gene + n['omim_post'])
    parts += [s for s in n['body'] if 'фенотипа пациента' not in s]
    return re.sub(r'\s+', ' ', ' '.join(parts)).strip()


def fmt_freq(value) -> str:
    """0.0384 → «0,0384»; 3.2e-05 → «3,2×10⁻⁵»; None → «—»; a string stays as it is (the page edits strings)."""
    if value is None or value == '':
        return '—'
    if isinstance(value, str):
        return value
    if value == 0:
        return '0'
    if value >= 1e-4:
        return f'{value:.4g}'.replace('.', ',')
    mantissa, exponent = f'{value:.1e}'.split('e')
    superscript = str.maketrans('-0123456789', '⁻⁰¹²³⁴⁵⁶⁷⁸⁹')
    return f"{mantissa.replace('.', ',')}×10{str(int(exponent)).translate(superscript)}"


# --- checks (a typo in a clinical report must stop it, not print) ---


def validate(context: dict, acmg_genes=()) -> tuple:
    """(errors, warnings) in Russian. Any error: no document."""
    errors, warnings = [], []
    patient = context.get('patient') or {}
    for key, label in REQUIRED_PATIENT:
        if _missing(patient.get(key)):
            errors.append(f'Не заполнено поле «{label}».')
    variants = context.get('variants') or []
    for i, v in enumerate(variants, start=1):
        tag = f'Вариант {i} ({v.get("gene") or "?"})'
        for key in REQUIRED_VARIANT:
            if _missing(v.get(key)):
                errors.append(f'{tag}: не заполнено поле «{key}».')
        if v.get('zygosity') and not _missing(v['zygosity']) and v['zygosity'] not in ZYGOSITY:
            errors.append(f'{tag}: зиготность «{v["zygosity"]}» — допустимо: {", ".join(ZYGOSITY)}.')
        if v.get('inheritance') and not _missing(v['inheritance']) and v['inheritance'] not in INHERITANCE:
            errors.append(f'{tag}: тип наследования «{v["inheritance"]}» — допустимо: {", ".join(INHERITANCE)}.')
        if v.get('classification') and v['classification'] not in CLASSIFICATION:
            errors.append(f'{tag}: классификация «{v["classification"]}» — допустимо: {", ".join(CLASSIFICATION)}.')
        try:
            if int(v.get('reads_alt')) > int(v.get('reads_total')):
                errors.append(f'{tag}: альтернативных прочтений больше, чем всего.')
        except (TypeError, ValueError):
            if not _missing(v.get('reads_alt')) and not _missing(v.get('reads_total')):
                errors.append(f'{tag}: число прочтений должно быть целым.')
        if acmg_genes and v.get('gene') and v['gene'] not in acmg_genes:
            warnings.append(f'{tag}: ген {v["gene"]} не входит в список ACMG.')
    paragraphs = [p for p in context.get('interpretation') or [] if str(p).strip()]
    if variants and not paragraphs:
        errors.append('Есть варианты, но нет интерпретации.')
    for p in paragraphs:
        if PLACEHOLDER in re.sub(r'\[@[^\]]*\]', '', p).split():
            errors.append('В интерпретации остался пропуск «_»: заполните его или удалите.')
            break
    keys = [str(r.get('key') or '').strip() for r in context.get('references') or []]
    for key in {k for k in keys if keys.count(k) > 1 and k}:
        errors.append(f'Источник [@{key}] указан дважды.')
    return errors, warnings


def _missing(value) -> bool:
    text = str(value if value is not None else '').strip()
    return not text or text.strip('_×x ') == ''


# --- citations: [@key] → [12], numbered after the template's fixed references ---

_CITE = re.compile(r'\[@([^\]]+)\]')


def _compress(numbers: list) -> str:
    """[12, 13, 14, 16] → «12–14, 16»."""
    numbers = sorted(set(numbers))
    parts, start = [], numbers[0]
    for prev, cur in zip(numbers, numbers[1:] + [None]):
        if cur != prev + 1:
            parts.append(str(start) if start == prev else f'{start}, {prev}' if prev == start + 1 else f'{start}–{prev}')
            start = cur
    return ', '.join(parts)


def resolve_citations(texts: list, first_number: int, extra: dict) -> tuple:
    """(texts with numbers, extra sources in the order first cited, errors)."""
    errors, numbers, cited = [], {}, []

    def replace(match):
        found = []
        for key in (k.strip().lstrip('@').strip() for k in match.group(1).split(';')):
            if key not in extra:
                errors.append(f'Ссылка [@{key}] есть в тексте, но нет в списке источников.')
                continue
            if key not in numbers:
                cited.append(extra[key])
                numbers[key] = first_number + len(cited) - 1
            found.append(numbers[key])
        return f'[{_compress(found)}]' if found else match.group(0)

    return [_CITE.sub(replace, t) for t in texts], cited, errors


# --- what the templates read ---


def load_data(data_dir) -> tuple:
    """(study, gene_groups) from a template's data/ folder."""
    data_dir = Path(data_dir)
    study = json.loads((data_dir / 'study.json').read_text(encoding='utf-8'))
    groups = json.loads((data_dir / 'genes_acmg.json').read_text(encoding='utf-8'))
    return study, groups


def prepare(context: dict, data_dir) -> dict:
    """The namespace every screening template gets. Raises ReportProblem when validate() finds errors."""
    study, groups = load_data(data_dir)
    acmg_genes = sorted({g for group in groups for g in group['genes']})
    errors, warnings = validate(context, set(acmg_genes))
    variants = [{k: str(v.get(k) if v.get(k) is not None else '') for k in VARIANT_FIELDS} for v in context.get('variants') or []]
    interpretation = [str(p) for p in context.get('interpretation') or [] if str(p).strip()] if variants else []
    recommendations = [str(r) for r in context.get('recommendations') or [] if str(r).strip()]
    recommendations = recommendations or list(study['default_recommendations'])
    extra = {str(r.get('key') or '').strip(): str(r.get('text') or '') for r in context.get('references') or []}
    extra.pop('', None)
    texts, cited, citation_errors = resolve_citations(interpretation + recommendations, len(study['references']) + 1, extra)
    errors += citation_errors
    if errors:
        raise ReportProblem(errors)
    used = [k for k in INHERITANCE if any(v['inheritance'] == k for v in variants)]
    return {
        'patient': dict(context.get('patient') or {}),
        'variants': variants,
        'interpretation': texts[: len(interpretation)],
        'recommendations': texts[len(interpretation):],
        'references': list(study['references']) + cited,
        'study': study,
        'gene_groups': groups,
        'acmg_genes': acmg_genes,
        'inheritance_legend': '; '.join(f'{k} – {INHERITANCE[k]}' for k in used) + '.' if used else '',
        'warnings': warnings,
    }


# --- rich text: the few tags a clinician may use, nothing else ---

RICH_TAGS = ('i', 'b', 'em', 'strong', 'sup', 'sub', 'br')
_ESCAPED_TAG = re.compile(r'&lt;(/?)(' + '|'.join(RICH_TAGS) + r')\s*/?&gt;', re.IGNORECASE)


def rich_html(text) -> str:
    """Escape everything, then allow back <i> <b> <em> <strong> <sup> <sub> <br> without attributes."""
    return _ESCAPED_TAG.sub(lambda m: f'<{m.group(1)}{m.group(2).lower()}>', html.escape(str(text), quote=False))


_TAG = re.compile(r'<(/?)(' + '|'.join(RICH_TAGS) + r')\s*/?>', re.IGNORECASE)


def rich_runs(text) -> list:
    """[(text, {'italic': True, …})] for Word: the same tags as rich_html, other markup dropped."""
    runs, style, pos = [], {'italic': 0, 'bold': 0, 'superscript': 0, 'subscript': 0}, 0
    names = {'i': 'italic', 'em': 'italic', 'b': 'bold', 'strong': 'bold', 'sup': 'superscript', 'sub': 'subscript'}
    text = str(text)

    def emit(chunk):
        chunk = html.unescape(re.sub(r'<[^>]*>', '', chunk))
        if chunk:
            runs.append((chunk, {k: True for k, v in style.items() if v > 0}))

    for match in _TAG.finditer(text):
        emit(text[pos: match.start()])
        pos = match.end()
        tag = match.group(2).lower()
        if tag == 'br':
            runs.append(('\n', {}))
        else:
            style[names[tag]] += -1 if match.group(1) else 1
    emit(text[pos:])
    return runs


# --- an example report: the template checks and «Список полей» use it ---

EXAMPLE = {
    'patient': {'id': 'ПРИМЕР-1', 'participant': 'Петрова Анна Сергеевна', 'sex': 'женский', 'date': '01.10.2026',
                'mean_depth': '36×'},
    'variants': [{
        'gene': 'HFE', 'disease': 'Гемохроматоз, тип 1', 'omim': '235200', 'position': 'chr6:26092913 G>A',
        'hgvs_c': 'NM_000410.4:c.845G>A', 'hgvs_p': 'p.Cys282Tyr', 'classification': 'патогенный',
        'zygosity': 'гомозигота', 'inheritance': 'АР', 'frequency': '0,0384', 'reads_alt': '38', 'reads_total': '38',
    }],
    'interpretation': ['В гене <i>HFE</i> выявлен вариант c.845G>A (p.Cys282Tyr) в гомозиготном состоянии [@feder1997].'],
    'recommendations': [],
    'references': [{'key': 'feder1997', 'text': 'Feder JN, et al. <i>J Biol Chem</i>. 1997;272(22):14025-14028.'}],
}
