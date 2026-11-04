"""Linux: the whole app in one folder — install, applications-menu entry, uninstall, in-app update.

    ~/.local/share/clinreport/          paths.data_dir()
    ├── app/                            the program (bundle.json, python/, modules/, clinreport) — replaced on update
    ├── conf/ modules/ jobs/ logs/ …    the user's data (as on Windows/macOS)
    ├── cache/  tmp/                    caches and temporary files (isolation.py)
    └── .clinreport-data                marks the folder as ours (--purge refuses a folder without it)

Outside it, only: ~/.local/share/applications/clinreport.desktop, the ~/.local/bin/clinreport link and, when
«Запускать при входе» is on, ~/.config/autostart/clinreport.desktop. Uninstalling removes those and the program;
--purge removes the data folder too.
"""

import json
import logging
import os
import shutil
import tarfile
from pathlib import Path

from . import autostart, isolation, paths

log = logging.getLogger('clinreport.linuxapp')

DESKTOP_FILE = 'clinreport.desktop'
DESKTOP_MARK = 'X-ClinReport-Bundle'  # our .desktop files carry it; anything else of that name is not ours
DATA_MARKER = '.clinreport-data'
WM_CLASS = 'clinreport'  # GLib.set_prgname() in the launcher, StartupWMClass in the .desktop file
START_SCRIPT = 'clinreport'
ICON = 'clinreport.png'
# Removed by --uninstall without --purge: the program and what is rebuilt on demand. Everything else in the data folder
# stays — conf (settings, the lab's templates), modules (Store installs with their databases), jobs, logs,
# python-packages, launcher.json, environments.json, module-backups.
PROGRAM_PARTS = ('app', '.app.new', '.app.old', 'cache', 'tmp', 'updates', 'bin', 'webview', 'workspace')

# $1 launcher pid, $2 staging, $3 app, $4 .app.old. `kill -0` would also succeed for a zombie (exited, not yet reaped by
# its parent), so the state letter in /proc/<pid>/stat (after the "(comm)" field) decides.
UPDATE_SCRIPT = r'''
alive() { s=$(sed 's/.*) //' "/proc/$1/stat" 2>/dev/null | cut -c1); [ -n "$s" ] && [ "$s" != Z ]; }
while alive "$1"; do sleep 0.3; done
rm -rf "$4"
if mv "$3" "$4"; then
  if mv "$2" "$3"; then rm -rf "$4"; else mv "$4" "$3"; fi
fi
exec "$3/clinreport"
'''


class InstallError(Exception):
    pass


# --- where ---


def applications_dir() -> Path:
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'applications'


def desktop_file() -> Path:
    return applications_dir() / DESKTOP_FILE


def bin_link() -> Path:
    return Path.home() / '.local' / 'bin' / START_SCRIPT


def staging_dir() -> Path:
    return paths.install_dir().with_name('.app.new')


def old_dir() -> Path:
    return paths.install_dir().with_name('.app.old')


def is_installed(bundle: Path = None) -> bool:
    try:
        bundle = Path(bundle or paths.bundle_dir())
    except SystemExit:  # no bundle (development)
        return False
    return bundle.resolve() == paths.install_dir().resolve()


def mark_data_dir():
    folder = paths.data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / DATA_MARKER
    if not marker.exists():
        marker.write_text('ClinReport data folder. Removing ClinReport: clinreport --uninstall [--purge]\n', encoding='utf-8')


def clean_leftovers():
    """Folders left by an update that was interrupted."""
    for folder in (staging_dir(), old_dir()):
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
            log.info('removed %s left by an interrupted update', folder)


# --- the applications menu ---


def _exec_arg(value: str) -> str:
    """Quote one argument for a .desktop Exec line (Desktop Entry Specification, "The Exec key")."""
    if not any(c in value for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return value
    return '"' + ''.join('\\' + c if c in '"`$\\' else c for c in value) + '"'


def desktop_entry(bundle: Path) -> str:
    info = json.loads((bundle / 'bundle.json').read_text(encoding='utf-8'))
    script = _exec_arg(str(bundle / START_SCRIPT)).replace('%', '%%')
    return '\n'.join(
        [
            '[Desktop Entry]',
            'Type=Application',
            'Version=1.5',
            'Name=ClinReport',
            'GenericName=Клинические отчёты',
            'Comment=Отчёты .docx по результатам OpenCRAVAT',
            f'Exec={script} %f',
            f'Icon={bundle / ICON}',
            'Terminal=false',
            'Categories=Science;MedicalSoftware;',
            'MimeType=application/vnd.sqlite3;application/x-sqlite3;',
            'StartupNotify=true',
            f'StartupWMClass={WM_CLASS}',
            f'{DESKTOP_MARK}={bundle}',
            f'X-ClinReport-Version={info.get("version", "")}',
            '',
        ]
    )


def _ours(desktop: Path) -> bool:
    try:
        return f'\n{DESKTOP_MARK}=' in desktop.read_text(encoding='utf-8')
    except OSError:
        return False


def write_entries(bundle: Path) -> list:
    """The applications-menu entry and the ~/.local/bin/clinreport link (kept if it is someone else's file)."""
    written = []
    desktop = desktop_file()
    if desktop.exists() and not _ours(desktop):
        raise InstallError(f'{desktop} принадлежит другой программе; не трогаю его.')
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(desktop_entry(bundle), encoding='utf-8')
    written.append(desktop)
    link = bin_link()
    if link.is_symlink() or not link.exists():
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        link.symlink_to(bundle / START_SCRIPT)
        written.append(link)
    else:
        log.warning('%s exists and is not a link; leaving it', link)
    return written


def remove_entries() -> list:
    removed = []
    desktop = desktop_file()
    if desktop.exists() and _ours(desktop):
        desktop.unlink()
        removed.append(desktop)
    link = bin_link()
    if link.is_symlink() and _inside(Path(os.readlink(link)), paths.data_dir()):
        link.unlink()
        removed.append(link)
    if autostart.is_enabled():
        autostart.set_enabled(False)
        removed.append(autostart._posix_file())
    return removed


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


# --- install / uninstall ---


def check_bundle(bundle: Path) -> dict:
    try:
        info = json.loads((bundle / 'bundle.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        raise InstallError(f'{bundle} — не сборка ClinReport (нет bundle.json): {e}') from e
    if not (bundle / START_SCRIPT).is_file():
        raise InstallError(f'в {bundle} нет файла {START_SCRIPT}')
    if not str(info.get('platform', '')).startswith('linux'):
        raise InstallError(f'это сборка для {info.get("platform")}, а не для Linux')
    return info


def install(source: Path, stop_running=lambda: None) -> Path:
    """Copy the bundle `source` into the data folder (replacing an older copy) and add it to the applications menu."""
    source = Path(source)
    target = paths.install_dir()
    check_bundle(source)
    mark_data_dir()
    if source.resolve() != target.resolve():
        if _inside(target, source) or _inside(source, target):
            raise InstallError(f'{source} и {target} вложены друг в друга')
        stop_running()  # its files are about to be replaced
        staging = staging_dir()
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(source, staging, symlinks=True)
        old = old_dir()
        shutil.rmtree(old, ignore_errors=True)
        if target.exists():
            target.rename(old)
        staging.rename(target)
        shutil.rmtree(old, ignore_errors=True)
        log.info('installed %s into %s', source, target)
    write_entries(target)
    return target


def uninstall(purge: bool = False, stop_running=lambda: None) -> list:
    """Remove the program and its menu entries; with purge, the whole data folder (only if it carries our marker)."""
    data = paths.data_dir()
    if purge:
        if not (data / DATA_MARKER).is_file():
            raise InstallError(f'{data} не похожа на папку данных ClinReport (нет {DATA_MARKER}); удалите её вручную.')
        if data.resolve() in (Path.home().resolve(), Path('/')):
            raise InstallError(f'отказываюсь удалять {data}')
    stop_running()
    removed = remove_entries()
    if purge:
        shutil.rmtree(data)
        removed.append(data)
    else:
        for name in PROGRAM_PARTS:
            part = data / name
            if part.is_symlink() or part.is_file():
                part.unlink()
            elif part.is_dir():
                shutil.rmtree(part)
            else:
                continue
            removed.append(part)
    return removed


def folder_sizes() -> dict:
    """Bytes in the program, the caches/temporary files, and the user's data (the rest of the data folder)."""
    data = paths.data_dir()
    sizes = {'program': 0, 'cache': 0, 'data': 0}
    if not data.is_dir():
        return sizes
    for item in data.iterdir():
        kind = 'program' if item.name in ('app', '.app.new', '.app.old') else 'cache' if item.name in (
            'cache', 'tmp', 'updates', 'workspace'
        ) else 'data'
        sizes[kind] += _size(item)
    return sizes


def _size(path: Path) -> int:
    if path.is_symlink():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def clear_cache():
    """Empty cache/ (WebKit, Mesa, pip) and remove downloaded updates; the running WebKit recreates what it needs."""
    for folder in (paths.cache_dir(), paths.data_dir() / 'updates'):
        if folder.is_dir():
            for item in folder.iterdir():
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)


# --- in-app update ---


def unpack_update(archive: Path) -> Path:
    """Unpack a release archive (ClinReport-<version>-linux-<arch>.tar.gz, one top folder) next to app/."""
    staging = staging_dir()
    shutil.rmtree(staging, ignore_errors=True)
    unpacked = staging.with_name('.app.unpack')
    shutil.rmtree(unpacked, ignore_errors=True)
    unpacked.mkdir(parents=True)
    try:
        with tarfile.open(archive) as tar:
            tar.extractall(unpacked, filter='data')
        tops = [p for p in unpacked.iterdir()]
        if len(tops) != 1 or not tops[0].is_dir():
            raise InstallError('в архиве обновления ожидалась одна папка ClinReport')
        info = check_bundle(tops[0])
        current = paths.bundle_info().get('platform')
        if current and info.get('platform') != current:
            raise InstallError(f'архив для {info.get("platform")}, а эта программа — {current}')
        tops[0].rename(staging)
    finally:
        shutil.rmtree(unpacked, ignore_errors=True)
    return staging


def apply_update(archive: Path, pid: int = None):
    """Unpack the new version, then let a detached shell swap it in once this launcher (pid) has exited and start it.
    The caller closes the window. Running processes keep their files: the swap happens after they are gone."""
    if not is_installed():
        raise InstallError('обновлять можно только установленную копию (clinreport --install)')
    staging = unpack_update(archive)
    target = paths.install_dir()
    args = ['sh', '-c', UPDATE_SCRIPT, 'clinreport-update', str(pid or os.getpid()), str(staging), str(target), str(old_dir())]
    log.info('update unpacked into %s; swapping it in after this launcher exits', staging)
    isolation.popen_for_user(args)
