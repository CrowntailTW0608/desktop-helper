"""設定檔讀寫（%APPDATA%\\desktop-helper\\config.json）"""

import copy
import json
import os

CONFIG_DIR = os.path.join(os.environ["APPDATA"], "desktop-helper")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
MAX_LINKS = 8

DEFAULTS = {
    "gif_path": "",
    "gif_interval": 60,
    "position": {"x": 100, "y": 100},
    "auto_start": False,
    "links": [],
    "claude_usage": {"enabled": False, "session_key": "", "org_id": ""},
    "trigger": {"enabled": False, "dir": ""},
}


def load() -> dict:
    """讀取設定；檔案缺失或毀損時回傳預設值（NFR-4）。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {}
    cfg = copy.deepcopy(DEFAULTS)
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "claude_usage" and isinstance(value, dict):
                cfg["claude_usage"].update(value)
            elif key == "trigger" and isinstance(value, dict):
                cfg["trigger"].update(value)
            elif key in cfg:
                cfg[key] = value
    return cfg


def save(cfg: dict) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
