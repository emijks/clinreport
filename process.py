from __future__ import annotations

from datetime import date

from utils import float2percent, predict_insilico


class SampleProcessor:
    
    note2clinsig = {
        '1': 'патогенный',
        '2': 'вероятно патогенный',
        '3': 'вариант с неизвестной клинической значимостью',
    }
    note2type = {
        '1': 'Каузативный',
        '2': 'Каузативный',
        '3': 'Каузативный',
        '7': 'Не связан с основным диагнозом',
        '8': 'Носительство',
    }
    clinsig2msg = {
        'Pathogenic': 'патогенный',
        'Pathogenic/Likely_pathogenic': 'патогенный / вероятно патогенный',
        'Pathogenic/Likely pathogenic': 'патогенный / вероятно патогенный',
        'Likely_pathogenic': 'вероятно патогенный',
        'Likely pathogenic': 'вероятно патогенный',
        'Uncertain_significance': 'вариант с неизвестной клинической значимостью',
        'Uncertain significance': 'вариант с неизвестной клинической значимостью',
        'Benign': 'доброкачественный',
        'Likely_benign': 'вероятно доброкачественный',
        'Likely benign': 'вероятно доброкачественный',
    }
    zygosity2msg = {
        'het': {1: 'Гетерозигота', 2: 'в гетерозиготном состоянии'},
        'hom': {1: 'Гомозигота', 2: 'в гомозиготном состоянии'},
    }
    inher2msg = {
        'AD': 'Аутосомно-доминантный',
        'XD': 'Х-сцепленный доминантный',
        'AR': 'Аутосомно-рецессивный',
        'XR': 'Х-сцепленный рецессивный',
    }

    NOTE_TO_NAME_MAP = {
        '1': 'p_variants', # 1 causative P; SNV_P_table_data
        '2': 'lp_variants', # 2 causative LP; SNV_LP_table_data
        '3': 'vus_variants', # 3 causative VUS; SNV_VUS_table_data
        '4': 'cnv_variants',
        '5': 'mt_variants',
        '6': 'str_variants',
        '7': 'sf_variants',
        '8': 'carrier_variants',
    }


    def __init__(
        self,
        raw_variants: list[dict],
        sample_id: str,
        *,
        target_sample: str | None = None,
        all_samples: list[str] | None = None,
        clinician: str | None = None,
        ru_annotations: dict | None = None,
    ) -> None:
        self.raw_variants = raw_variants
        self.sample_id = sample_id
        self.sample_name = str(sample_id).split('.')[0]
        self.target_sample = target_sample or sample_id
        self.all_samples = all_samples or [sample_id]
        self.clinician = clinician or ''
        self.ru_annotations = ru_annotations


    def filter_variants(self, variants_data: list, by_note: str | None = None, by_sample: str | None = None) -> list:
        variants_data = variants_data.copy()
        if by_note:
            variants_data = [v for v in variants_data if v['base__note'] == by_note]
        if by_sample:
            filtered = []
            for variant in variants_data:
                variant_copy = variant.copy()
                samples = variant_copy['tagsampler_new__samples'].split(';')
                if by_sample in samples:
                    idx = samples.index(by_sample)
                    if variant_copy['tagsampler_new__filter'].split(';')[idx] != 'PASS':
                        continue
                    variant_copy['tagsampler_new__zygosity'] = variant_copy['tagsampler_new__zygosity'].split(';')[idx]
                    variant_copy['tagsampler_new__ad'] = variant_copy['tagsampler_new__ad'].split(';')[idx].split(',')[-1]
                    variant_copy['tagsampler_new__dp'] = variant_copy['tagsampler_new__dp'].split(';')[idx]
                    filtered.append(variant_copy)
            return filtered
        return variants_data

    def get_gnomad4aggregated(self, variant_data: dict) -> dict:
        agg = {'AN': None, 'AC': None, 'AF': None}
        agg['AN'] = sum(v for v in [variant_data['gnomad4genomes__AN'], variant_data['gnomad4exomes__AN']] if v)
        if agg['AN']:
            agg['AC'] = sum(v for v in [variant_data['gnomad4genomes__AC'], variant_data['gnomad4exomes__AC']] if v)
            agg['AF'] = agg['AC'] / agg['AN']
        return agg


    def clinvar_sig_subs2msgs(self, clinvar_sig_subs) -> list:
        msgs = []
        if not clinvar_sig_subs:
            return msgs
        for sig_count in clinvar_sig_subs.split('; '):
            sig, count = sig_count[:-1].split(' (')
            msgs.append(f'как {self.clinsig2msg.get(sig, sig)} {count} лабораторией(ями)')
        return msgs

    def _clinvar_annotation_msg(self, clinvar_sig, clinvar_sig_subs) -> str:
        """ClinVar annotation phrase for the interpretation narrative."""
        if not clinvar_sig:
            return ''
        if 'Conflicting' in clinvar_sig and clinvar_sig_subs:
            # conflict: spell out the per-classification breakdown instead of
            # echoing "Conflicting classifications of pathogenicity".
            return self._clinvar_conflict_msg(clinvar_sig_subs)
        msgs = self.clinvar_sig_subs2msgs(clinvar_sig_subs) or [
            f'как {self.clinsig2msg.get(clinvar_sig, clinvar_sig)}'
        ]
        return ', '.join(msgs)

    def _clinvar_conflict_msg(self, clinvar_sig_subs) -> str:
        items = [
            f'как {self.clinsig2msg.get(sig, sig)} ({count})'
            for sig, count in (sc[:-1].split(' (') for sc in clinvar_sig_subs.split('; '))
        ]
        if len(items) <= 1:
            return ''.join(items)
        return ', '.join(items[:-1]) + ' и ' + items[-1]

    @staticmethod
    def _variation_str(spdi: str, transcript_msg: str, hgvsc: str, hgvsp_msg: str, rsid: str) -> str:
        return '\n'.join(p for p in (spdi, transcript_msg, hgvsc, hgvsp_msg, rsid) if p)

    @staticmethod
    def _zygosity_str(zygosity_msg: str, inher_msg: str) -> str:
        return f'{zygosity_msg}\n({inher_msg})'

    def _process_variant(self, variant: dict) -> dict:
        """Translate one raw variant dict into a template-facing row dict."""
        note = variant['base__note']
        symbol = variant['vep_csq__symbol']
        chrom = variant['base__chrom']
        pos = variant['extra_vcf_info__pos']
        ref = variant['extra_vcf_info__ref']
        alt = variant['extra_vcf_info__alt']
        spdi = f'{chrom}-{pos}-{ref}-{alt}'
        rsid = variant['dbsnp__rsid'] or ''
        hgvsc = variant['vep_csq__hgvsc'] or ''
        hgvsp = variant['vep_csq__hgvsp']
        hgvsp_msg = f"p.({hgvsp[2:].replace('%3D', '=')})" if hgvsp else ''
        transcript = variant['vep_csq__transcript']
        refseq = variant['vep_csq__refseq']
        transcript_msg = f'{refseq}:' if refseq else (f'{transcript}:' if transcript else '')

        zygosity = variant['tagsampler_new__zygosity']
        zygosity_msg = self.zygosity2msg.get(zygosity, {}).get(1, '-') if zygosity else '-'
        omim_pheno = variant['vep_omim_pheno__pheno']
        inher = variant['vep_omim_pheno__inher']
        inher_msg = ', '.join(self.inher2msg.get(i, i) for i in inher.split(',')) if inher else '-'

        agg = self.get_gnomad4aggregated(variant)
        af_msg = float2percent(agg['AF']) if agg['AF'] else 'н/д'
        ad = variant['tagsampler_new__ad'] or '_'
        dp = variant['tagsampler_new__dp'] or '_'
        coverage = f'{ad}x/{dp}x'

        if self.ru_annotations:
            if note == '7':
                omim_pheno = self.ru_annotations.get('secondary', {}).get('Disease/Phentyope', {}).get(symbol, omim_pheno)
                inher_msg  = self.ru_annotations.get('secondary', {}).get('Inheritance', {}).get(symbol, inher_msg)
            else:
                omim_pheno = self.ru_annotations.get('omim', {}).get('Ассоциированное заболевание', {}).get(symbol, omim_pheno)

        pathogenicity = (
            self.note2clinsig[note].capitalize()
            if note in ('1', '2', '3')
            else self.clinsig2msg.get(variant['clinvar_new__sig'], '-')
        )

        return {
            'gene': symbol,
            'disease': omim_pheno or '',
            'variation': self._variation_str(spdi, transcript_msg, hgvsc, hgvsp_msg, rsid),
            'zygosity': self._zygosity_str(zygosity_msg, inher_msg),
            'frequency': af_msg,
            'coverage': coverage,
            'pathogenicity': pathogenicity,
        }

    def _classification_msg(self, variant: dict) -> str:
        """Pathogenicity text shared by CNV/MT/STR rows."""
        note = variant.get('base__note')
        if note in ('1', '2', '3'):
            return self.note2clinsig[note].capitalize()
        return self.clinsig2msg.get(variant.get('clinvar_new__sig'), '-')


    def get_causative_variants(self, sample_variants: list) -> list:
        """Notes 1+2+3 (P, LP, VUS) flattened -- the 'causative' set used by 10x."""
        return sum(
            (self.filter_variants(sample_variants, by_note=note) for note in ('1', '2', '3')),
            [],
        )


    # gene is a separate field so the template tag {{ v.gene }} can be italic.
    INTERPRETATION_NOTES = ('1', '2', '3', '7')

    def _build_interpretation(self, sample_variants: list) -> tuple[list, str]:
        narrated = [
            self._variant_narrative(variant)
            for note in self.INTERPRETATION_NOTES
            for variant in self.filter_variants(sample_variants, by_note=note)
        ]
        closing = (
            'Других значимых изменений, соответствующих критериям поиска, не обнаружено.'
            if narrated
            else 'Значимых изменений, соответствующих критериям поиска, не обнаружено.'
        )
        return narrated, closing

    def _variant_narrative(self, variant: dict) -> dict:
        symbol = variant['vep_csq__symbol']
        transcript = variant['vep_csq__transcript']
        refseq = variant['vep_csq__refseq']
        hgvsg = variant['vep_csq__hgvsg']
        hgvsc = variant['vep_csq__hgvsc']
        hgvsc_msg = f'{refseq}:{hgvsc}' if refseq else f'{transcript}:{hgvsc}'
        hgvsp = variant['vep_csq__hgvsp']
        hgvsp_msg = f"p.({hgvsp[2:].replace('%3D', '=')})" if hgvsp else ''
        rsid = variant['dbsnp__rsid']
        variation_msg = ', '.join(m for m in (hgvsg, hgvsc_msg, rsid) if m)

        ref_base = variant.get('base__ref_base') or ''
        alt_base = variant.get('base__alt_base') or ''
        indel_size = len(alt_base.replace('-', '')) - len(ref_base.replace('-', ''))

        consequence = variant['vep_csq__consequence'] or ''
        exon, intron = variant['vep_csq__exon'], variant['vep_csq__intron']
        if exon:
            gene_part_msg = f"в {exon.split('/')[0]} экзоне из {exon.split('/')[1]} экзонов"
        elif intron:
            gene_part_msg = f"в {intron.split('/')[0]} интроне из {intron.split('/')[1]} интронов"
        else:
            gene_part_msg = ''

        if 'missense' in consequence:
            leading_to_msg = f', который приводит к аминокислотной замене {hgvsp_msg}. '
        elif 'synon' in consequence:
            leading_to_msg = f', который приводит / может приводить к аберрантному сплайсингу {hgvsp_msg}. '
        elif 'intron' in consequence:
            leading_to_msg = ', который приводит / может приводить к аберрантному сплайсингу. '
        elif 'shift' in consequence:
            indel_type = 'вставке' if indel_size > 0 else 'удалению'
            leading_to_msg = f', который приводит к {indel_type} {abs(indel_size)} нуклеотидов, сдвигу рамки считывания и образованию преждевременного стоп-кодона {hgvsp_msg}. '
        elif 'stop' in consequence:
            leading_to_msg = f', который приводит к образованию преждевременного стоп-кодона {hgvsp_msg}. '
        elif 'splice' in consequence:
            leading_to_msg = ', который приводит к разрушению канонического сайта сплайсинга. '
        else:
            leading_to_msg = '. '

        omim_pheno, omim_id = variant['vep_omim_pheno__pheno'], variant['vep_omim_pheno__id']
        agg = self.get_gnomad4aggregated(variant)
        af_msg = float2percent(agg['AF']) if agg['AF'] else ''
        ac_msg = f"{agg['AC']} аллел(ей)" if agg['AC'] else ''
        zygosity = variant['tagsampler_new__zygosity']
        zygosity_msg = self.zygosity2msg.get(zygosity, {}).get(2, '') if zygosity else ''
        dp = variant['tagsampler_new__dp'] or '_'
        ad = variant['tagsampler_new__ad']
        gerp_rs_score = variant['gerp__gerp_rs']
        insilico_prediction = predict_insilico(
            variant['dbscsnv__ada_score'], variant['metarnn__score'], variant['revel__score'],
            variant['alphamissense__score'], variant['phylop100__score'],
        )
        clinvar_msg = self._clinvar_annotation_msg(
            variant['clinvar_new__sig'], variant['clinvar_new__sig_subs']
        )
        clinsig = self.note2clinsig[variant['base__note']]

        body = []
        if agg['AN']:
            body.append(f'Вариант встречается в базе данных популяционных частот gnomAD v4.1.0 с частотой {af_msg} ({ac_msg}).')
        else:
            body.append('Вариант не встречается в базе данных популяционных частот gnomAD v4.1.0.')
        comp = self._computational_msg(consequence, gerp_rs_score, insilico_prediction)
        if comp:
            body.append(comp)
        if clinvar_msg:
            body.append(f'Вариант аннотирован {clinvar_msg} в базе данных ClinVar.')
        other_samples = self._other_samples_msg()
        if other_samples:
            body.append(other_samples)
        body.append(f'По совокупности сведений вариант расценивается как {clinsig}.')
        body.append('Рекомендуется сопоставление фенотипа пациента с фенотипом заболеваний, ассоциированных с геном.')
        body.append('Вариант требует обязательного подтверждения генотипа референсным методом (секвенирование по методу Сэнгера).')

        return {
            'gene': symbol,
            'intro_pre': f'Обнаружен ранее _ описанный в литературе вариант ({variation_msg}) {zygosity_msg} {gene_part_msg} гена ',
            'intro_post': f'{leading_to_msg}Глубина покрытия в данной позиции составляет {dp}х, из них {ad} прочтений соответствуют альтернативному аллелю.',
            'omim_pre': 'Патогенные варианты в гене ' if omim_pheno else '',
            'omim_post': f' приводят к {omim_pheno} ({omim_id}).' if omim_pheno else '',
            'body': body,
        }

    @staticmethod
    def _computational_msg(consequence: str, gerp_rs_score, insilico_prediction: bool) -> str:
        parts = []
        if 'missense' in consequence:
            if gerp_rs_score is not None:
                # GERP conservation buckets (boundaries 2 and 4 -> "умеренно").
                if gerp_rs_score > 4:
                    bucket = 'высококонсервативной'
                elif gerp_rs_score >= 2:
                    bucket = 'умеренно консервативной'
                else:
                    bucket = 'низкоконсервативной'
                parts.append(f'Вариант расположен в {bucket} позиции (GERP). ')
            if insilico_prediction:
                parts.append('Компьютерные алгоритмы предсказывают патогенный эффект варианта на белок.')
            else:
                parts.append('Компьютерные алгоритмы предсказывают нейтральный эффект варианта на белок.')
        elif 'shift' in consequence or 'stop' in consequence:
            parts.append('Вариант с большой долей вероятности приводит к потере функции соответствующей копии гена.')
        elif 'splice' in consequence:
            if insilico_prediction:
                parts.append('Вариант предсказан приводить к аберрантному сплайсингу компьютерными алгоритмами. ')
                parts.append('Вариант с большой долей вероятности приводит к потере функции соответствующей копии гена.')
            else:
                parts.append('Вариант не предсказан приводить к аберрантному сплайсингу компьютерными алгоритмами. ')
        elif 'synon' in consequence or 'intron' in consequence:
            if insilico_prediction:
                parts.append('Вариант предсказан приводить к аберрантному сплайсингу компьютерными алгоритмами. ')
            else:
                parts.append('Вариант не предсказан приводить к аберрантному сплайсингу компьютерными алгоритмами. ')
            parts.append('Требуется проведение функционального анализа.')
        return ''.join(parts)

    def _other_samples_msg(self) -> str:
        if not self.target_sample:
            return ''
        nontarget = [s for s in self.all_samples if s != self.sample_id]
        if not nontarget:
            return ''
        nontarget = [str(s).split('.')[0] for s in nontarget]
        return f'Вариант обнаружен у {", ".join(nontarget)}'


    def _build_10x_main_table_rows(self) -> list[dict]:
        target_sample_variants = self.filter_variants(self.raw_variants, by_sample=self.target_sample)
        target_causative = sum(
            (self.filter_variants(target_sample_variants, by_note=note) for note in ('1', '2', '3')),
            [],
        )
        # Look up this sample's filtered variants by key for genotype/coverage
        this_sample_filtered = self.filter_variants(self.raw_variants, by_sample=self.sample_id)
        by_key = {self._variant_key(v): v for v in this_sample_filtered}

        rows = []
        for tv in target_causative:
            here = by_key.get(self._variant_key(tv))
            ref = tv['extra_vcf_info__ref'] or ''
            alt = tv['extra_vcf_info__alt'] or ''
            if here:
                ad = here['tagsampler_new__ad'] or '_'
                dp = here['tagsampler_new__dp'] or '_'
                molecules = f'{ad}x/{dp}x'
                genotype = f'{ref}/{alt}'
            else:
                molecules = '0x/-'
                genotype = f'{ref}/{ref}'
            rows.append({
                'gene': tv.get('vep_csq__symbol', ''),
                'hgvsg': tv.get('vep_csq__hgvsg') or '',
                'genotype': genotype,
                'qual': '',
                'molecules': molecules,
                'interpretation': '',
            })
        return rows

    @staticmethod
    def _variant_key(v: dict) -> tuple:
        return (
            str(v.get('base__chrom', '')),
            str(v.get('extra_vcf_info__pos', '')),
            str(v.get('extra_vcf_info__ref', '')),
            str(v.get('extra_vcf_info__alt', '')),
        )

    # CNV(4)/MT(5)/STR(6) left empty for now.
    SNV_NOTES = ('1', '2', '3', '7', '8')

    def build_default_context(self) -> dict:
        sample_variants = self.filter_variants(self.raw_variants, by_sample=self.sample_id)

        context: dict = {
            'patient': {
                'id': self.sample_name,
                'sex': '_',
                'age': '_',
                'diagnosis': '_',
            },
            'tech': {
                'method': 'полногеномное секвенирование (Whole Genome Sequencing)',
                'depth': '_x',
                'reads_nt': 'не менее 90 млрд',
                'read_type': 'парно-концевое',
                'read_length': '150',
                'library_type': 'PCR free',
            },
            'report_date': date.today().strftime('%d.%m.%Y'),
            'clinician': self.clinician,
        }
        for name in self.NOTE_TO_NAME_MAP.values():
            context[name] = []
        for note in self.SNV_NOTES:
            name = self.NOTE_TO_NAME_MAP[note]
            context[name] = [self._process_variant(v) for v in self.filter_variants(sample_variants, by_note=note)]
        context['interpretation'], context['closing'] = self._build_interpretation(sample_variants)
        return context


    def build_10x_context(self) -> dict:
        context: dict = {
            'sample': {'id': self.sample_name},
            'patient': {
                'lab_number': self.sample_name,
                'sex': '_',
                'diagnosis': '_',
            },
            'tech': {
                'method': 'полногеномное секвенирование (Whole Genome Sequencing)',
                'depth': '_x',
                'reads_nt': 'не менее 90 млрд',
                'read_type': 'парно-концевое',
                'read_length': '150',
                'library_type': 'PCR free',
            },
            'main_variants': self._build_10x_main_table_rows(),
            # CNV(4)/MT(5) left empty for now.
            'cnv_variants': [],
            'mt_variants': [],
        }
        return context
