"""Configuration persistence using JSON."""

import json
import os
from typing import Any

DEFAULT_CONFIG = {
    "hotkey_pause": "F8",
    "scale_coordinates": False,
    "minimize_to_tray": True,
    "language": "ru",
    # Each group: {name, browser, start, end, url}
    "account_groups": [
        {"name": "Группа 1", "browser": "", "start": 1,  "end": 11, "url": ""},
        {"name": "Группа 2", "browser": "", "start": 12, "end": 22, "url": ""},
    ],
}

CONFIG_FILENAME = "mbo_config.json"


def _config_path() -> str:
    """Return path to config file next to the executable / script."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(base), CONFIG_FILENAME)


def load_config() -> dict[str, Any]:
    path = _config_path()
    config = dict(DEFAULT_CONFIG)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            config.update(stored)
        except (json.JSONDecodeError, OSError):
            pass
    return config


def save_config(config: dict[str, Any]):
    path = _config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
