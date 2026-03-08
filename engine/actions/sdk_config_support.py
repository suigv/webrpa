from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Any

import yaml

from core.data_store import _resolve_root_path, write_json_atomic


def ui_config_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [Path(_resolve_root_path()) / "config" / "x_ui.yaml", repo_root / "config" / "x_ui.yaml"]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path_str = str(path.resolve()) if path.exists() else os.path.abspath(str(path))
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def load_ui_config_document() -> dict[str, Any]:
    for path in ui_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"x_ui config must be a mapping: {path}")
    raise FileNotFoundError("config/x_ui.yaml not found")


def strategy_config_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [Path(_resolve_root_path()) / "config" / "strategies" / "nurture_keywords.yaml", repo_root / "config" / "strategies" / "nurture_keywords.yaml"]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path_str = str(path.resolve()) if path.exists() else os.path.abspath(str(path))
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def load_strategy_document() -> dict[str, Any]:
    for path in strategy_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"nurture strategy config must be a mapping: {path}")
    raise FileNotFoundError("config/strategies/nurture_keywords.yaml not found")


def interaction_text_config_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        Path(_resolve_root_path()) / "config" / "strategies" / "interaction_texts.yaml",
        repo_root / "config" / "strategies" / "interaction_texts.yaml",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path_str = str(path.resolve()) if path.exists() else os.path.abspath(str(path))
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def load_interaction_text_document() -> dict[str, Any]:
    for path in interaction_text_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"interaction text config must be a mapping: {path}")
    raise FileNotFoundError("config/strategies/interaction_texts.yaml not found")


def daily_counter_path() -> Path:
    return Path(_resolve_root_path()) / "config" / "data" / "daily_counters.json"


def read_daily_counters() -> dict[str, Any]:
    path = daily_counter_path()
    if not path.exists():
        return {"date": datetime.now().strftime("%Y-%m-%d"), "counts": {}}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {"date": datetime.now().strftime("%Y-%m-%d"), "counts": {}}
    if not isinstance(payload, dict):
        return {"date": datetime.now().strftime("%Y-%m-%d"), "counts": {}}
    counts = payload.get("counts")
    if not isinstance(counts, dict):
        counts = {}
    return {"date": str(payload.get("date") or ""), "counts": counts}


def write_daily_counters(payload: dict[str, Any]) -> None:
    path = daily_counter_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, payload)


def resolve_ui_key(source: Any, key: str) -> Any:
    if not key:
        return None
    if isinstance(source, dict) and key in source:
        return source[key]

    current = source
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def resolve_localized_entry(entry: Any, locale: str) -> Any:
    if not isinstance(entry, dict):
        return entry
    if "type" in entry or "value" in entry or "template" in entry:
        return entry
    locale_key = str(locale or "").strip().lower()
    if locale_key and locale_key in entry:
        return entry[locale_key]
    if "default" in entry:
        return entry["default"]
    for value in entry.values():
        if isinstance(value, dict):
            return value
    return entry


def select_interaction_template(section: str, ai_type: str) -> str:
    document = load_interaction_text_document()
    section_doc = document.get(section)
    if not isinstance(section_doc, dict):
        raise ValueError(f"interaction text section missing: {section}")
    pool = section_doc.get(ai_type)
    if not isinstance(pool, list) or not pool:
        pool = section_doc.get("default")
    if not isinstance(pool, list) or not pool:
        raise ValueError(f"interaction text pool missing: {section}/{ai_type}")
    return str(__import__("random").choice(pool)).strip()
