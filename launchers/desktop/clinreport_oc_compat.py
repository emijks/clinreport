r"""OpenCRAVAT 3.x fixes for the desktop app, applied at interpreter start-up (clinreport_oc_compat.pth).

Active only in processes started by the launcher (CLINREPORT_DESKTOP=1), so builds and tools are unaffected.
Patches modules right after they are imported, without editing OpenCRAVAT's files:

- cravat.constants: OpenCRAVAT *reads* the system conf from OPENCRAVAT_SYSTEM_CONF_PATH but *writes* it
  (Settings, the user-email prompt, `update_system_conf_file`) to its default path — `C:\open-cravat\conf` or
  `/Users/Shared/open-cravat/conf` — so saved settings never came back, and our folders leaked into the conf of any
  other OpenCRAVAT on the computer. Point the write path at the same file.

- cravat.gui.config: `CELERY_RESULTS_PATH = f'/{work_dir}/…'` turns `C:/…` into `/C:/…` on Windows
  (WinError 123 at start-up; OpenCRAVAT 3.1.1–3.2.3).
- celery.app.base: OpenCRAVAT starts its Celery workers with the default `prefork` pool, which cannot work on
  Windows (spawned children must pickle a local FlaskTask class). The desktop app uses the `solo` pool on every
  platform: each OpenCRAVAT queue already runs in its own worker process, and `solo` executes its tasks on that
  process's main thread — like a prefork child. (`threads` is not enough: OpenCRAVAT's install_module installs a
  SIGINT handler, which Python allows only on the main thread, so every Store install failed.) One task at a time
  per queue is fine for one desktop user.
"""

import importlib.abc
import importlib.machinery
import os
import sys

_PATCHES = {}


def _patch(name):
    def register(func):
        _PATCHES[name] = func
        return func

    return register


@_patch('cravat.constants')
def _write_conf_where_it_is_read(module):
    path = os.environ.get(module.system_conf_path_env_key)
    if path:
        module.system_conf_path = path


@_patch('cravat.gui.config')
def _fix_celery_paths(module):
    if sys.platform != 'win32':
        return
    work_dir = module.CRAVAT_SYSCONF['work_dir']
    results = f'{work_dir}/celery/results'
    module.CELERY_RESULTS_PATH = results
    module.CELERY['result_backend'] = 'file:///' + results.replace('\\', '/')


@_patch('celery.app.base')
def _solo_pool(module):
    original = module.Celery.config_from_object

    def config_from_object(self, obj, *args, **kwargs):
        result = original(self, obj, *args, **kwargs)
        self.conf.worker_pool = 'solo'
        return result

    module.Celery.config_from_object = config_from_object


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name not in _PATCHES:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        loader, patch = spec.loader, _PATCHES.pop(name)
        original_exec = loader.exec_module

        def exec_module(module):
            original_exec(module)
            patch(module)

        loader.exec_module = exec_module
        return spec


if os.environ.get('CLINREPORT_DESKTOP') == '1':
    sys.meta_path.insert(0, _Finder())
