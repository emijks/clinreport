"""Is a newer desktop release published? (GitHub releases tagged v* of the repository in bundle.json)."""

import json
import re
import urllib.request

from . import paths

TAG_PREFIX = 'v'


def _parse(version: str):
    return tuple(int(x) for x in re.findall(r'\d+', version)[:3]) or (0,)


def latest() -> dict:
    """{'version', 'url', 'newer'}; raises on network errors or a private/missing repository."""
    info = paths.bundle_info()
    repo = info.get('update_repo')
    if not repo:
        raise RuntimeError('repository for updates not configured')
    request = urllib.request.Request(
        f'https://api.github.com/repos/{repo}/releases?per_page=30',
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'ClinReport'},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        releases = json.loads(response.read().decode('utf-8'))
    desktop = [r for r in releases if r.get('tag_name', '').startswith(TAG_PREFIX) and not r.get('draft')]
    if not desktop:
        raise RuntimeError('no desktop releases yet')
    release = max(desktop, key=lambda r: _parse(r['tag_name']))
    version = release['tag_name'][len(TAG_PREFIX) :]
    return {
        'version': version,
        'url': release.get('html_url', f'https://github.com/{repo}/releases'),
        'newer': _parse(version) > _parse(info.get('version', '0')),
    }
