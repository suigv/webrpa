from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List


DATA_TYPES = {
    "accounts": "accounts.json",
    "location": "location.json",
    "website": "website.json",
}

def _resolve_root_path() -> str:
    env_root = os.environ.get("MYT_NEW_ROOT")
    if env_root:
        return env_root
    return str(Path(__file__).resolve().parents[1])


def _data_dir() -> str:
    path = os.path.join(_resolve_root_path(), "config", "data")
    os.makedirs(path, exist_ok=True)
    return path


def _json_path(data_type: str) -> str:
    return os.path.join(_data_dir(), DATA_TYPES[data_type])


def _normalize_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def read_lines(data_type: str) -> List[str]:
    path = _json_path(data_type)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    lines = payload.get("lines") if isinstance(payload, dict) else None
    if not isinstance(lines, list):
        return []
    return [str(line).strip() for line in lines if str(line).strip()]


def write_lines(data_type: str, lines: List[str]) -> None:
    path = _json_path(data_type)
    payload = {
        "type": data_type,
        "encoding": "utf-8",
        "lines": [line for line in (str(x).strip() for x in lines) if line],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_text(data_type: str) -> str:
    return "\n".join(read_lines(data_type))


def write_text(data_type: str, content: str) -> None:
    write_lines(data_type, _normalize_lines(content or ""))
