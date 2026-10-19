from pathlib import Path

import pytest
from helpers import SINGLE, TRIO


def _example(path):
    if not path.exists():
        pytest.skip(f'example result {path} not found (set CLINREPORT_EXAMPLES)')
    return str(path)


@pytest.fixture
def trio_db():
    return _example(TRIO)


@pytest.fixture
def single_db():
    return _example(SINGLE)


class FakeAdminUtil:
    def __init__(self, root):
        self.root = Path(root)

    def get_conf_dir(self):
        return str(self.root / 'conf')

    def get_jobs_dir(self):
        return str(self.root / 'jobs')

    def get_system_conf(self):
        return {'admin_list': ['admin']}


@pytest.fixture
def service(tmp_path, monkeypatch):
    """clinreport_core.service with a temporary conf/jobs dir and no network."""
    from clinreport_core import service

    fake = FakeAdminUtil(tmp_path)
    for key in service.DB_KEYS:
        monkeypatch.delenv(service.DB_ENV_PREFIX + key.upper(), raising=False)
    monkeypatch.setattr(service, '_admin_util', lambda: fake)
    monkeypatch.setattr(service, 'ru_annotations', lambda: (None, None))
    service._databases.clear()
    return service
