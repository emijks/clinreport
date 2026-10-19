#! /usr/bin/env python3
"""Generate ClinReport .docx files from an OpenCRAVAT result without the GUI.

Uses the same code as the review page (clinreport_core.service), so the documents
are identical to «Сохранить как…» without edits. Needs docxtpl; OpenCRAVAT itself
is only used to find its conf dir (settings, custom templates).

    python cli.py RESULT.sqlite [-m default|lpwgs|10x] [-t SAMPLE] [--template ID] [-o DIR]
                                [--conf-dir DIR] [--no-ru-annotations] [--list-templates]
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

WEBAPP_DIR = Path(__file__).resolve().parents[2] / 'modules' / 'webapps' / 'clinreport'
sys.path.insert(0, str(WEBAPP_DIR))

from clinreport_core import service  # noqa: E402


def resolve_conf_dir(arg):
    if arg:
        return arg
    if os.environ.get('CLINREPORT_CONF_DIR'):
        return os.environ['CLINREPORT_CONF_DIR']
    try:
        from cravat import admin_util
        return admin_util.get_conf_dir()
    except Exception:
        return tempfile.mkdtemp(prefix='clinreport-')  # no OpenCRAVAT: built-in templates, empty settings


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('sqlite', nargs='?', help='OpenCRAVAT result .sqlite')
    parser.add_argument('-m', '--mode', choices=('default', 'lpwgs', '10x'), default='default',
                        help='default: a report per sample; lpwgs: target → report, others → 10x; 10x: 10x for every sample')
    parser.add_argument('-t', '--target-sample', help='main sample in a duo/trio (label as shown in the review page)')
    parser.add_argument('--template', help='template id for standard reports (default: the one from the settings, else DZM)')
    parser.add_argument('-o', '--output-dir', default='.', help='directory to write .docx into')
    parser.add_argument('--conf-dir', help='settings/templates folder (default: OpenCRAVAT conf dir)')
    parser.add_argument('--no-ru-annotations', action='store_true', help='skip the Russian OMIM/secondary-findings sheet')
    parser.add_argument('--list-templates', action='store_true', help='print the available templates and exit')
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    os.environ['CLINREPORT_CONF_DIR'] = resolve_conf_dir(args.conf_dir)
    if args.no_ru_annotations:
        service.ru_annotations = lambda: (None, None)

    if args.list_templates:
        for t in service.list_templates({})['templates']:
            print(f"{t['id']:<24} {t['kind']:<8} {t['title']}{'' if t['builtin'] else '  (свой)'}")
        return
    if not args.sqlite:
        parser.error('the result .sqlite is required')

    labels = []
    try:
        opened = service.open_result({'dbpath': args.sqlite})
        labels = [s['label'] for s in opened['samples']]
        target = labels.index(args.target_sample) if args.target_sample else 0
    except service.ClientError as e:
        sys.exit(str(e))
    except ValueError:
        sys.exit(f'Sample {args.target_sample!r} not found; samples: {", ".join(labels)}')

    if args.mode == '10x':
        reports, warnings = _tenx_reports(args.sqlite, target)
    else:
        result = service.process({'dbpath': args.sqlite, 'mode': args.mode, 'target': target})
        reports, warnings = result['reports'], result['warnings']
    for warning in warnings:
        print(f'Warning: {warning}', file=sys.stderr)

    default_template = args.template or service.layouts()['default']['template_default']
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for report in reports:
        template = default_template if report['kind'] == 'default' else None
        try:
            document = service.render({'context': report['context'], 'kind': report['kind'], 'template': template,
                                       'filename': report['filename']})
        except service.ClientError as e:
            sys.exit(str(e))
        path = out / document.filename
        path.write_bytes(document.data)
        print(f'Saved {path}')


def _tenx_reports(dbpath, target):
    """A 10x document for every sample, relative to the target (the old desktop CLI's `-r 10x`)."""
    from clinreport_core import ClinReport
    annotations, warning = service.ru_annotations()
    clinician = service.load_user_settings()['clinician']
    clinreport = ClinReport(dbpath, clinician=clinician, ru_annotations=annotations)
    clinreport.target_sample = clinreport.all_samples[target]
    reports = [service._report(clinreport, sample, '10x', dbpath) for sample in clinreport.all_samples]
    return reports, [warning] if warning else []


if __name__ == '__main__':
    main()
