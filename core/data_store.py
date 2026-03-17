from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from core.paths import data_dir

DATA_TYPES = {
    "accounts": "accounts.json",
    "location": "location.json",
    "website": "website.json",
}


def _data_dir() -> str:
    return str(data_dir())


def _json_path(data_type: str) -> str:
    return os.path.join(_data_dir(), DATA_TYPES[data_type])


def _normalize_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def write_json_atomic(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    temp_file = Path(temp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, target)
    finally:
        if temp_file.exists():
            temp_file.unlink()


def read_lines(data_type: str) -> list[str]:
    path = _json_path(data_type)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    lines = payload.get("lines") if isinstance(payload, dict) else None
    if not isinstance(lines, list):
        return []
    return [str(line).strip() for line in lines if str(line).strip()]


def write_lines(data_type: str, lines: list[str]) -> None:
    path = _json_path(data_type)
    payload = {
        "type": data_type,
        "encoding": "utf-8",
        "lines": [line for line in (str(x).strip() for x in lines) if line],
    }
    write_json_atomic(path, payload)


def read_text(data_type: str) -> str:
    return "\n".join(read_lines(data_type))


def write_text(data_type: str, content: str) -> None:
    write_lines(data_type, _normalize_lines(content or ""))
