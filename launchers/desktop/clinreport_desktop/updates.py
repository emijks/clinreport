"""Newer releases (GitHub releases tagged v* of the repository in bundle.json) and installing them.

Windows: the setup asset for this platform is downloaded into <data>/updates and started with /SILENT; the
installer closes this launcher (--quit), replaces the program files only (user data stays) and starts
ClinReport again (/RELAUNCH=1). Other platforms: the release page is opened.
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import paths

log = logging.getLogger('clinreport.updates')
TAG_PREFIX = 'v'
API = 'https://api.github.com/repos/{repo}/releases?per_page=30'
_VERSION = re.compile(r'^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$')


def version_key(version: str) -> tuple:
    """Semantic-version order: 3.0.0-rc1 < 3.0.0-rc2 < 3.0.0 < 3.0.1. Unparseable (dev builds) sort first."""
    match = _VERSION.match(version.strip().removeprefix(TAG_PREFIX))
    if not match:
        return (-1,)
    major, minor, patch, pre = match.groups()
    pre_key = tuple((0, int(p), '') if p.isdigit() else (1, 0, p) for p in re.split(r'[.-]', pre)) if pre else ()
    return (int(major), int(minor), int(patch), pre is None, pre_key)


def asset_suffix(platform_tag: str) -> str:
    """Release asset names from packaging/build.py: ClinReport-<version>-<platform>-setup.exe / .dmg / .tar.gz."""
    if platform_tag.startswith('win'):
        return f'-{platform_tag}-setup.exe'
    if platform_tag.startswith('macos'):
        return f'-{platform_tag}.dmg'
    return f'-{platform_tag}.tar.gz'


def pick(releases: list, current: str, platform_tag: str, include_prerelease: bool = False) -> dict:
    """The newest usable release: {'version', 'url', 'newer', 'prerelease', 'asset'}; raises if there is none."""
    candidates = [
        r
        for r in releases
        if r.get('tag_name', '').startswith(TAG_PREFIX)
        and not r.get('draft')
        and (include_prerelease or not r.get('prerelease'))
        and version_key(r['tag_name']) > (-1,)
    ]
    if not candidates:
        raise RuntimeError('no releases yet')
    release = max(candidates, key=lambda r: version_key(r['tag_name']))
    suffix = asset_suffix(platform_tag)
    asset = next((a for a in release.get('assets') or [] if a.get('name', '').endswith(suffix)), None)
    version = release['tag_name'].removeprefix(TAG_PREFIX)
    return {
        'version': version,
        'url': release.get('html_url', ''),
        'newer': version_key(version) > version_key(current),
        'prerelease': bool(release.get('prerelease')),
        'asset': {
            'name': asset['name'],
            'url': asset['browser_download_url'],
            'size': asset.get('size'),
            'sha256': (asset.get('digest') or '').removeprefix('sha256:') or None,
        }
        if asset
        else None,
    }


def _get(url: str, timeout: int):
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'ClinReport'})
    return urllib.request.urlopen(request, timeout=timeout)


def latest(include_prerelease: bool = False) -> dict:
    """pick() over the repository's releases; raises on network errors or a private/missing repository."""
    info = paths.bundle_info()
    repo = info.get('update_repo')
    if not repo:
        raise RuntimeError('repository for updates not configured')
    with _get(API.format(repo=repo), timeout=8) as response:
        releases = json.loads(response.read().decode('utf-8'))
    return pick(releases, info.get('version', '0'), info.get('platform', ''), include_prerelease)


def can_install() -> bool:
    return sys.platform == 'win32'


def updates_dir() -> Path:
    return paths.data_dir() / 'updates'


def clean_downloads():
    """Remove installers of earlier updates (they are only needed until the update has run)."""
    for item in updates_dir().glob('*'):
        try:
            item.unlink()
        except OSError:
            pass


def download(asset: dict, progress=lambda done, total: None) -> Path:
    """Download the asset next to the user data; checks the size and, when GitHub publishes it, the SHA-256."""
    folder = updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / Path(asset['name']).name
    partial = target.with_name(target.name + '.part')
    digest = hashlib.sha256()
    done, total = 0, asset.get('size') or 0
    with _get(asset['url'], timeout=60) as response, open(partial, 'wb') as out:
        while chunk := response.read(1 << 16):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            progress(done, total)
    if total and done != total:
        partial.unlink()
        raise RuntimeError(f'загрузка прервана: {done} из {total} байт')
    if asset.get('sha256') and digest.hexdigest() != asset['sha256']:
        partial.unlink()
        raise RuntimeError('контрольная сумма загруженного файла не совпадает')
    os.replace(partial, target)
    return target


def run_installer(setup: Path):
    """Start the setup detached; it closes this launcher itself and starts the new version when done."""
    log_file = paths.logs_dir() / 'update-setup.log'
    args = [str(setup), '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/RELAUNCH=1', f'/LOG={log_file}']
    log.info('starting %s', ' '.join(args))
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
    subprocess.Popen(args, close_fds=True, creationflags=flags)
