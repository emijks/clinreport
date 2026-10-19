"""Install OpenCRAVAT modules from KarchinLab/open-cravat-modules-karchinlab at a fixed commit.

Used when the OpenCRAVAT Store is unreachable. Copies the module's code files only
(no `test/` folders, no data from the Store), e.g.:

    python fetch_modules.py <commit> mappers/hg38 webviewerwidgets/wgnote
"""

import json
import os
import sys
import urllib.request

REPO = 'KarchinLab/open-cravat-modules-karchinlab'


def get(url):
    headers = {'User-Agent': 'clinreport-build'}
    if os.environ.get('GITHUB_TOKEN') and url.startswith('https://api.github.com/'):
        headers['Authorization'] = f'Bearer {os.environ["GITHUB_TOKEN"]}'  # 60 → 5000 API calls/hour
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def fetch(ref, module_path, modules_dir):
    listing = json.loads(get(f'https://api.github.com/repos/{REPO}/contents/{module_path}?ref={ref}'))
    target = os.path.join(modules_dir, *module_path.split('/'))
    os.makedirs(target, exist_ok=True)
    names = []
    for entry in listing:
        if entry['type'] != 'file':
            continue  # skip test/ and other folders
        with open(os.path.join(target, entry['name']), 'wb') as fh:
            fh.write(get(entry['download_url']))
        names.append(entry['name'])
    if not any(name.endswith('.yml') for name in names):
        sys.exit(f'{module_path}@{ref}: no .yml found — wrong path or ref?')
    print(f'{module_path}@{ref[:7]}: {", ".join(names)}')


def main():
    ref, module_paths = sys.argv[1], sys.argv[2:]
    modules_dir = os.environ.get('OC_MODULES_DIR', '/opt/opencravat/modules')
    for module_path in module_paths:
        fetch(ref, module_path, modules_dir)


if __name__ == '__main__':
    main()
