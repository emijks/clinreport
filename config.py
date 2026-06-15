import json

def load_config(config_path) -> dict:
    """Загружает настройки из json."""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}  # Если файла нет, начинаем с пустого словаря
    return config