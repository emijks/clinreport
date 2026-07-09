import json
import os
import shutil
import sys

# Single source of truth for the app config: the root config.json next to this
# module (dev/source run). When frozen by PyInstaller, config lives next to the
# exe, seeded from the bundled default on first run.
CONFIG_FILENAME = 'config.json'


def get_app_dir() -> str:
    """Папка, где лежит config.json: рядом с exe (frozen) или корень проекта."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_default_config_path(config_fname=CONFIG_FILENAME) -> str:
    """Путь к дефолтному конфигу внутри пакета PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath('.')
    return os.path.join(base_path, config_fname)


def ensure_config_exists(config_path, config_fname=CONFIG_FILENAME) -> None:
    if not os.path.exists(config_path):
        # Копируем дефолтный конфиг из ресурсов (только во frozen-сборке).
        default_config_path = get_default_config_path(config_fname)
        if os.path.abspath(default_config_path) != os.path.abspath(config_path):
            shutil.copyfile(default_config_path, config_path)


def get_config_path(config_fname=CONFIG_FILENAME) -> str:
    """Абсолютный путь к файлу настроек, гарантируя его существование."""
    config_path = os.path.join(get_app_dir(), config_fname)
    ensure_config_exists(config_path, config_fname)
    return config_path


def load_config(config_path=None) -> dict:
    """Загружает настройки из json."""
    if config_path is None:
        config_path = get_config_path()
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}  # Если файла нет, начинаем с пустого словаря
    return config
