#! /usr/bin/env python3
"""Build the ClinReport desktop app (OpenCRAVAT + ClinReport, nothing else to install) for this machine's platform.

    python packaging/build.py [--version 3.0.0] [--package] [--out packaging/dist]

The stack is pinned in packaging/stack.toml:
1. python-build-standalone CPython (`python`, `pbs_release`; checksum-verified) → <out>/ClinReport/python
2. pip: open-cravat==`opencravat` + packaging/requirements.txt;
   the launcher package and the OpenCRAVAT compatibility patches (clinreport_oc_compat)
3. base modules from KarchinLab at `karchinlab_modules_ref`, and our modules
   (modules/<type>/<module>) → <out>/ClinReport/modules
4. bundle.json (versions, managed modules, update source)
5. --package: Windows → Inno Setup installer (needs ISCC); macOS → ClinReport.app in a .dmg; Linux → .tar.gz

Run it with any Python ≥ 3.12; nothing is installed into that Python.
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MODULES = REPO / 'modules'
LAUNCHER = REPO / 'launchers' / 'desktop'
STACK = tomllib.loads((HERE / 'stack.toml').read_text(encoding='utf-8'))
PBS_URL = 'https://github.com/astral-sh/python-build-standalone/releases/download/{rel}/{name}'
TAG_PREFIX = 'v'


def target_triple() -> str:
    machine = platform.machine().lower()
    arch = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}[machine]
    if sys.platform == 'win32':
        return f'{arch}-pc-windows-msvc'
    if sys.platform == 'darwin':
        return f'{arch}-apple-darwin'
    return f'{arch}-unknown-linux-gnu'


def platform_tag() -> str:
    arch = 'arm64' if target_triple().startswith('aarch64') else 'x64'
    return {'win32': 'win', 'darwin': 'macos'}.get(sys.platform, 'linux') + '-' + arch


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'clinreport-desktop-build'})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def fetch_python(cache: Path, version: str) -> Path:
    release = STACK['pbs_release']
    name = f'cpython-{version}+{release}-{target_triple()}-install_only_stripped.tar.gz'
    archive = cache / name
    if not archive.exists():
        print(f'downloading {name}')
        cache.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(get(PBS_URL.format(rel=release, name=name)))
    sums = get(PBS_URL.format(rel=release, name='SHA256SUMS')).decode()
    expected = next((line.split()[0] for line in sums.splitlines() if line.endswith(name)), None)
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if expected != actual:
        archive.unlink()
        sys.exit(f'checksum mismatch for {name}: expected {expected}, got {actual}')
    return archive


# --- macOS: oldest supported system (stack.toml [macos_minimum]) ---

_MAC_PLATFORM = re.compile(r'^macosx_(\d+)_(\d+)_\w+$')
_MACHO_MAGIC = {b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'}


def macos_minimum() -> str:
    return STACK['macos_minimum']['arm64' if target_triple().startswith('aarch64') else 'x64']


def version_tuple(version: str) -> tuple:
    return tuple(int(x) for x in version.split('.'))


def wheel_macos_minimum(wheel_text: str) -> str | None:
    """Oldest macOS a wheel runs on, from the Tag: lines of its .dist-info/WHEEL; None for non-macOS wheels."""
    found = []
    for line in wheel_text.splitlines():
        if line.startswith('Tag:'):
            for platform in line.split('-')[-1].strip().split('.'):
                match = _MAC_PLATFORM.match(platform)
                if match:
                    found.append((int(match.group(1)), int(match.group(2))))
    return '.'.join(map(str, min(found))) if found else None


def wheels_too_new(purelib: Path, minimum: str) -> list:
    """(name, version) of installed packages whose wheel needs a newer macOS than `minimum`."""
    result = []
    for dist_info in sorted(purelib.glob('*.dist-info')):
        try:
            needs = wheel_macos_minimum((dist_info / 'WHEEL').read_text(encoding='utf-8'))
            metadata = (dist_info / 'METADATA').read_text(encoding='utf-8')
        except OSError:
            continue
        if needs and version_tuple(needs) > version_tuple(minimum):
            name = re.search(r'^Name: (.+)$', metadata, re.M).group(1).strip()
            version = re.search(r'^Version: (.+)$', metadata, re.M).group(1).strip()
            result.append((name, version))
    return result


def otool_minimum(otool_output: str) -> str | None:
    """Newest macOS a Mach-O file requires, from `otool -l` (LC_BUILD_VERSION minos / LC_VERSION_MIN_MACOSX)."""
    found = []
    for block in otool_output.split('Load command'):
        if 'LC_BUILD_VERSION' in block:
            match = re.search(r'\bminos (\d+(?:\.\d+)*)', block)
        elif 'LC_VERSION_MIN_MACOSX' in block:
            match = re.search(r'\bversion (\d+(?:\.\d+)*)', block)
        else:
            continue
        if match:
            found.append(match.group(1))
    return max(found, key=version_tuple) if found else None


def refetch_old_wheels(python: Path, purelib: Path, env: dict):
    """pip on a new macOS prefers wheels for that system (e.g. numpy's Accelerate build needs macOS 14):
    replace them by the same version built for the oldest supported macOS."""
    minimum = macos_minimum()
    arch = 'arm64' if target_triple().startswith('aarch64') else 'x86_64'
    too_new = wheels_too_new(purelib, minimum)
    if not too_new:
        return
    wheels = HERE / 'dist' / '.old-macos-wheels'
    shutil.rmtree(wheels, ignore_errors=True)
    for name, version in too_new:
        print(f'{name} {version}: wheel needs a macOS newer than {minimum}; fetching one for {minimum}')
        run(python, '-I', '-m', 'pip', 'download', '--no-deps', '--only-binary=:all:',
            '--platform', f'macosx_{minimum.replace(".", "_")}_{arch}', '-d', wheels, f'{name}=={version}', env=env)
    run(python, '-I', '-m', 'pip', 'install', '--force-reinstall', '--no-deps', *sorted(wheels.glob('*.whl')), env=env)
    shutil.rmtree(wheels, ignore_errors=True)
    left = wheels_too_new(purelib, minimum)
    if left:
        sys.exit(f'no macOS {minimum} wheels for: {left}')


def verify_macos_minimum(app: Path):
    """Fail the build if any binary in the bundle needs a newer macOS than stack.toml promises."""
    minimum = macos_minimum()
    offenders = []
    for path in app.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        with open(path, 'rb') as fh:
            if fh.read(4) not in _MACHO_MAGIC:
                continue
        needs = otool_minimum(subprocess.run(['otool', '-l', str(path)], capture_output=True, text=True).stdout)
        if needs and version_tuple(needs) > version_tuple(minimum):
            offenders.append(f'{path.relative_to(app)} needs macOS {needs}')
    if offenders:
        sys.exit(f'{len(offenders)} file(s) need a macOS newer than {minimum}:\n  ' + '\n  '.join(offenders[:30]))
    print(f'all binaries run on macOS {minimum}+')


def bundled_python(app: Path) -> Path:
    return app / 'python' / ('python.exe' if sys.platform == 'win32' else 'bin/python3')


def run(*args, **kwargs):
    print('$', ' '.join(str(a) for a in args))
    subprocess.check_call([str(a) for a in args], **kwargs)


def version_default() -> str:
    try:
        tag = subprocess.check_output(
            ['git', 'describe', '--tags', '--match', f'{TAG_PREFIX}[0-9]*', '--always', '--dirty'],
            cwd=REPO,
            text=True,
        ).strip()
        return tag.removeprefix(TAG_PREFIX)
    except (OSError, subprocess.CalledProcessError):
        return 'dev'


def our_modules() -> list:
    """modules/<type>/<module> folders that have a <module>.yml."""
    return sorted(
        f'{t.name}/{m.name}'
        for t in MODULES.iterdir()
        if t.is_dir() and not t.name.startswith('.')  # e.g. .ruff_cache
        for m in t.iterdir()
        if (m / f'{m.name}.yml').is_file()
    )


def build(out: Path, version: str) -> Path:
    app = out / 'ClinReport'
    if app.exists():
        shutil.rmtree(app)
    app.mkdir(parents=True)

    python_version = STACK['python']
    oc_version = STACK['opencravat']
    modules_ref = STACK['karchinlab_modules_ref']

    with tarfile.open(fetch_python(out.parent / '.cache', python_version)) as tar:
        tar.extractall(app, filter='data')
    python = bundled_python(app)
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK='1', PYTHONNOUSERSITE='1')
    env.pop('PYTHONPATH', None)
    run(
        python,
        '-I',
        '-m',
        'pip',
        'install',
        '--no-warn-script-location',
        f'open-cravat=={oc_version}',
        '-r',
        HERE / 'requirements.txt',
        env=env,
    )

    purelib = Path(
        subprocess.check_output(
            [str(python), '-I', '-c', 'import sysconfig; print(sysconfig.get_paths()["purelib"])'], text=True
        ).strip()
    )
    if sys.platform == 'darwin':
        refetch_old_wheels(python, purelib, env)
    target = purelib / 'clinreport_desktop'
    shutil.copytree(LAUNCHER / 'clinreport_desktop', target, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(HERE / 'icon.png', target / 'ui' / 'icon.png')
    shutil.copy2(HERE / 'windows' / 'clinreport.ico', target / 'ui' / 'icon.ico')
    # Start-up patches for OpenCRAVAT 3.x on Windows; active only in processes the launcher starts.
    shutil.copy2(LAUNCHER / 'clinreport_oc_compat.py', purelib / 'clinreport_oc_compat.py')
    (purelib / 'clinreport_oc_compat.pth').write_text('import clinreport_oc_compat\n', encoding='utf-8')

    # Base modules are pinned to one commit: fetch once into the cache, so rebuilds need no GitHub access.
    cached = out.parent / '.cache' / f'modules-{modules_ref}'
    if not cached.is_dir():
        partial = cached.with_name(cached.name + '.partial')
        shutil.rmtree(partial, ignore_errors=True)
        run(
            python,
            '-I',
            HERE / 'fetch_modules.py',
            modules_ref,
            *STACK['base_modules'],
            env=dict(env, OC_MODULES_DIR=str(partial)),
        )
        partial.rename(cached)
    modules = app / 'modules'
    shutil.copytree(cached, modules)
    managed = our_modules()
    for rel in managed:
        if (modules / rel).exists():
            sys.exit(f'module {rel}: already a base module')
        shutil.copytree(
            MODULES / rel, modules / rel, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.md')
        )
        print(f'our module: {rel}')

    (app / 'bundle.json').write_text(
        json.dumps(
            {
                'version': version,
                'opencravat': oc_version,
                'python': python_version,
                'platform': platform_tag(),
                'built': datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
                'update_repo': STACK.get('update_repo', ''),
                'modules_ref': modules_ref,
                'managed': managed,
            },
            indent=2,
        ),
        encoding='utf-8',
    )
    if sys.platform == 'win32':
        shutil.copy2(HERE / 'windows' / 'clinreport.ico', app / 'clinreport.ico')
    if sys.platform == 'darwin':
        verify_macos_minimum(app)
    print(f'built {app}')
    return app


# --- packaging ---


def package_windows(app: Path, version: str, out: Path) -> Path:
    iscc = shutil.which('ISCC') or next(
        (
            str(p)
            for p in (
                Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Inno Setup 6' / 'ISCC.exe',
                Path(r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'),
                Path(r'C:\Program Files\Inno Setup 6\ISCC.exe'),
            )
            if p.exists()
        ),
        None,
    )
    if not iscc:
        sys.exit('Inno Setup (ISCC.exe) not found: install it from https://jrsoftware.org/isinfo.php')
    numeric = '.'.join((re.findall(r'\d+', version) + ['0', '0', '0'])[:3])
    name = f'ClinReport-{version}-{platform_tag()}-setup'
    run(
        iscc,
        f'/DAppVersion={version}',
        f'/DAppVersionNumeric={numeric}',
        f'/DOpenCravatVersion={STACK["opencravat"]}',
        f'/DPythonVersion={STACK["python"]}',
        f'/DSourceDir={app}',
        f'/DOutputDir={out}',
        f'/DOutputName={name}',
        HERE / 'windows' / 'ClinReport.iss',
    )
    return out / f'{name}.exe'


def package_macos(app: Path, version: str, out: Path) -> Path:
    bundle = out / 'ClinReport.app'
    if bundle.exists():
        shutil.rmtree(bundle)
    contents = bundle / 'Contents'
    (contents / 'MacOS').mkdir(parents=True)
    resources = contents / 'Resources'
    resources.mkdir()
    shutil.move(str(app), str(resources / 'ClinReport'))
    launcher = contents / 'MacOS' / 'ClinReport'
    shutil.copy2(HERE / 'macos' / 'ClinReport', launcher)
    launcher.chmod(0o755)
    plist = (HERE / 'macos' / 'Info.plist').read_text(encoding='utf-8')
    plist = plist.replace('@VERSION@', version).replace('@MINOS@', macos_minimum())
    (contents / 'Info.plist').write_text(plist, encoding='utf-8')
    shutil.copy2(HERE / 'macos' / 'ClinReport.icns', resources / 'ClinReport.icns')
    # Ad-hoc signature: Apple Silicon refuses unsigned code; Gatekeeper still asks once (README.md).
    run('codesign', '--force', '--deep', '--sign', '-', bundle)
    dmg = out / f'ClinReport-{version}-{platform_tag()}.dmg'
    if dmg.exists():
        dmg.unlink()
    staging = out / 'dmg'
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    shutil.move(str(bundle), str(staging / 'ClinReport.app'))
    os.symlink('/Applications', staging / 'Applications')
    run('hdiutil', 'create', '-volname', 'ClinReport', '-srcfolder', staging, '-ov', '-format', 'UDZO', dmg)
    return dmg


def package_linux(app: Path, version: str, out: Path) -> Path:
    archive = out / f'ClinReport-{version}-{platform_tag()}.tar.gz'
    start = app / 'clinreport'
    start.write_text(
        '#!/bin/sh\nexec "$(dirname "$(readlink -f "$0")")/python/bin/python3" -I -m clinreport_desktop "$@"\n',
        encoding='utf-8',
    )
    start.chmod(0o755)
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(app, arcname='ClinReport')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', default=None, help='app version (default: git describe of v* tags)')
    parser.add_argument('--out', type=Path, default=HERE / 'dist')
    parser.add_argument('--package', action='store_true', help='also build the installer / disk image / archive')
    args = parser.parse_args()
    version = args.version or version_default()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = build(out, version)
    if args.package:
        packager = {'win32': package_windows, 'darwin': package_macos}.get(sys.platform, package_linux)
        print(f'packaged {packager(app, version, out)}')


if __name__ == '__main__':
    main()
