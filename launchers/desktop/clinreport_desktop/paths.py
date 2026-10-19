"""Where things are: the read-only bundle (Python, modules) and the per-user data folder."""

import json
import os
import sys
from pathlib import Path

APP_NAME = 'ClinReport'
BUNDLE_MARKER = 'bundle.json'


def bundle_dir() -> Path:
    """The folder with bundle.json: python/, modules/. CLINREPORT_BUNDLE_DIR overrides (development)."""
    if os.environ.get('CLINREPORT_BUNDLE_DIR'):
        return Path(os.environ['CLINREPORT_BUNDLE_DIR']).resolve()
    for parent in Path(sys.executable).resolve().parents:
        if (parent / BUNDLE_MARKER).is_file():
            return parent
    raise SystemExit(f'{BUNDLE_MARKER} not found above {sys.executable}; set CLINREPORT_BUNDLE_DIR')


def bundle_info() -> dict:
    try:
        return json.loads((bundle_dir() / BUNDLE_MARKER).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def data_dir() -> Path:
    """Per-user data: conf (OpenCRAVAT + ClinReport settings, custom templates), modules, jobs, logs.
    Kept when the app is updated or uninstalled."""
    if os.environ.get('CLINREPORT_DATA_DIR'):
        return Path(os.environ['CLINREPORT_DATA_DIR'])
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / APP_NAME
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / APP_NAME
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'clinreport'


def conf_dir() -> Path:
    return data_dir() / 'conf'


def logs_dir() -> Path:
    return data_dir() / 'logs'


def extension_dir() -> Path:
    """The ClinReport webapp inside the bundle (its clinreport_core is imported by the launcher)."""
    return bundle_dir() / 'modules' / 'webapps' / 'clinreport'
