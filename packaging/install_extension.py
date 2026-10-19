#! /usr/bin/env python3
"""Install, update or remove ClinReport (modules/webapps/clinreport + modules/webviewerwidgets/wgclinreport) in an
existing OpenCRAVAT. Without OpenCRAVAT, use the desktop app instead: it brings its own.

Run it with the Python that runs OpenCRAVAT, e.g.:

    <opencravat python> install_extension.py            # webapp + widget + docxtpl
    <opencravat python> install_extension.py --with-db  # also sqlalchemy/psycopg2 for Postgres upload
    <opencravat python> install_extension.py --uninstall

Running it again updates the modules. Settings and the lab's own templates live in the OpenCRAVAT conf dir
(clinreport.json, clinreport/templates/) and are never touched. Restart `oc gui` afterwards: OpenCRAVAT loads
webapp routes at start-up.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = {
    'webapps': 'clinreport',
    'webviewerwidgets': 'wgclinreport',
}
REQUIREMENTS = ['docxtpl']
DB_REQUIREMENTS = ['sqlalchemy', 'psycopg2-binary']


def source_dir() -> Path:
    """modules/ next to this script (the extension zip) or in the repository root (packaging/..)."""
    for candidate in (HERE / 'modules', HERE.parent / 'modules'):
        if (candidate / 'webapps' / 'clinreport').is_dir():
            return candidate
    sys.exit(f'modules/ not found next to {HERE}')


def modules_dir(override):
    if override:
        return Path(override)
    try:
        from cravat import admin_util
    except ImportError:
        sys.exit(
            f'OpenCRAVAT is not installed for {sys.executable}. '
            'Run this script with the Python that runs OpenCRAVAT (the one `oc` belongs to), '
            'or install the ClinReport desktop app, which includes OpenCRAVAT.'
        )
    return Path(admin_util.get_modules_dir())


def module_version(folder: Path) -> str:
    try:
        text = (folder / f'{folder.name}.yml').read_text(encoding='utf-8')
    except OSError:
        return ''
    match = re.search(r'^version:\s*(\S+)', text, re.M)
    return match.group(1) if match else ''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--md', help='OpenCRAVAT modules directory (default: `oc config md`)')
    parser.add_argument('--with-db', action='store_true', help='also install the Postgres client libraries')
    parser.add_argument('--no-deps', action='store_true', help='do not pip-install Python dependencies')
    parser.add_argument('--uninstall', action='store_true', help='remove ClinReport')
    args = parser.parse_args(argv)

    md = modules_dir(args.md)
    if not md.is_dir():
        sys.exit(f'Modules directory {md} does not exist.')
    source = None if args.uninstall else source_dir()

    for kind, name in MODULES.items():
        target = md / kind / name
        before = module_version(target)
        if target.exists():
            shutil.rmtree(target)
        if args.uninstall:
            print(f'Removed {target}' if before else f'Not installed: {target}')
            continue
        shutil.copytree(source / kind / name, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        after = module_version(target)
        print(f'Updated {target} ({before} -> {after})' if before else f'Installed {target} ({after})')

    if not args.uninstall and not args.no_deps:
        requirements = REQUIREMENTS + (DB_REQUIREMENTS if args.with_db else [])
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', *requirements])

    print('Done. Restart `oc gui` to load the changes.')


if __name__ == '__main__':
    main()
