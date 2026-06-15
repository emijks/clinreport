#! /usr/bin/env python3

import argparse
from pathlib import Path

from clinreport import ClinReport


def main():
    parser = argparse.ArgumentParser(description='Generate report(s) from GenLab OpenCRAVAT SQLite')
    parser.add_argument('sqlite', help='Path to OpenCRAVAT SQLite')
    parser.add_argument('-t', '--target-sample', help='Main sample in duo/trio')
    parser.add_argument('-r', '--report', choices=('default', '10x'), default='default', help='Report context to build')
    parser.add_argument('--template', choices=('DZM', 'FND'), default='DZM', help='Template for default reports')
    parser.add_argument('-o', '--output-dir', default='.', help='Directory to write .docx into')
    args = parser.parse_args()

    clinreport = ClinReport(args.sqlite, target_sample=args.target_sample)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sqlite_stem = Path(args.sqlite).stem.split('.')[0]

    for sample in clinreport.all_samples:
        if args.report == '10x':
            document = clinreport.render(clinreport.build_context(sample, '10x'), '10x')
            suffix = '10x'
        else:
            document = clinreport.render(clinreport.build_context(sample, 'default'), args.template)
            suffix = args.template.lower()

        sample_name = str(sample).split('.')[0]
        if not sample_name or sample_name == 'None':
            sample_name = sqlite_stem
        output_path = output_dir / f'{sample_name}_{suffix}.docx'
        document.save(str(output_path))
        print(f'Saved {output_path}')


if __name__ == '__main__':
    main()
