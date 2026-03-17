from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from core.app_config import AppConfigManager
from core.data_store import write_json_atomic
from core.paths import data_dir, project_root


def get_package_to_app_map() -> dict[str, str]:
    """向后兼容：从 core.app_config 获取映射。"""
    return AppConfigManager.get_package_to_app_map()


DEFAULT_APP_NAME = (
    os.getenv("MYT_DEFAULT_APP", "default") or "default"
).strip().lower() or "default"


def app_from_package(package: str) -> str:
    """从 Android package 名推断 app 配置文件名，未知 package 返回空字符串。"""
    pkg = str(package or "").strip()
    if not pkg:
        return ""
    return get_package_to_app_map().get(pkg, "")


def resolve_app(params: dict[str, Any], payload: dict[str, Any]) -> str:
    """从 params.app > payload.app > payload.package 顺序推断 app 名，默认 DEFAULT_APP_NAME。"""
    app = str(params.get("app") or payload.get("app") or "").strip().lower()
    if app:
        return app
    package = str(payload.get("package") or "").strip()
    if package:
        mapped = app_from_package(package)
        if mapped:
            return mapped
    return DEFAULT_APP_NAME


def app_config_path(app: str) -> Path:
    """返回 config/apps/{app}.yaml 的路径。"""
    return project_root() / "config" / "apps" / f"{app}.yaml"


def load_app_config_document(app: str) -> dict[str, Any]:
    """向后兼容：从 core.app_config 加载。"""
    conf = AppConfigManager.load_app_config(app)
    if not conf:
        raise FileNotFoundError(f"config/apps/{app}.yaml not found or invalid")
    return conf


def load_ui_config_document() -> dict[str, Any]:
    """向后兼容接口。"""
    return load_app_config_document(DEFAULT_APP_NAME)


def strategy_config_paths() -> list[Path]:
    return [project_root() / "config" / "strategies" / "nurture_keywords.yaml"]


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
    return [project_root() / "config" / "strategies" / "interaction_texts.yaml"]


def load_interaction_text_document() -> dict[str, Any]:
    for path in interaction_text_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"interaction text config must be a mapping: {path}")
    raise FileNotFoundError("config/strategies/interaction_texts.yaml not found")


def prompt_templates_config_paths() -> list[Path]:
    return [project_root() / "config" / "strategies" / "prompt_templates.yaml"]


def load_prompt_templates_document() -> dict[str, Any]:
    for path in prompt_templates_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"prompt templates config must be a mapping: {path}")
    raise FileNotFoundError("config/strategies/prompt_templates.yaml not found")


def login_stage_patterns_config_paths() -> list[Path]:
    return [project_root() / "config" / "strategies" / "login_stage_patterns.yaml"]


def load_login_stage_patterns_document() -> dict[str, Any]:
    for path in login_stage_patterns_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"login stage patterns config must be a mapping: {path}")
    return {}


def state_action_defaults_config_paths() -> list[Path]:
    return [project_root() / "config" / "strategies" / "state_action_defaults.yaml"]


def load_state_action_defaults_document() -> dict[str, Any]:
    for path in state_action_defaults_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"state action defaults config must be a mapping: {path}")
    return {}


def daily_counter_path() -> Path:
    return data_dir() / "daily_counters.json"


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
