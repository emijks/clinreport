"""Paths shared by the tests (tests/ is on pytest's pythonpath, see pyproject.toml)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP_DIR = ROOT / 'modules' / 'webapps' / 'clinreport'
CLI = ROOT / 'launchers' / 'cli' / 'cli.py'

# Example results contain patient-like data and are never committed: CLINREPORT_EXAMPLES points at them,
# default tests/examples (git-ignored *.sqlite). Tests that need them are skipped otherwise.
EXAMPLES_DIR = Path(os.environ.get('CLINREPORT_EXAMPLES', ROOT / 'tests' / 'examples'))
TRIO = EXAMPLES_DIR / 'trio1.sqlite'
SINGLE = EXAMPLES_DIR / 'pah2.vevat_annotated.sqlite'


def load_route_module():
    """modules/webapps/clinreport/route.py as OpenCRAVAT loads it (a plain file, not a package)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location('route', WEBAPP_DIR / 'route.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
