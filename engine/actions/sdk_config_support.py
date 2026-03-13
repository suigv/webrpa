from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import time
from typing import Any, Dict

import yaml

from core.data_store import _resolve_root_path, write_json_atomic

# 动态缓存映射表
_cached_package_map: Dict[str, str] = {}
_last_scan_time: float = 0
_SCAN_TTL = 60.0  # 缓存 60 秒

def _scan_apps_for_packages() -> Dict[str, str]:
    """扫描 config/apps/*.yaml 并根据 package_name 字段构建映射表。"""
    mapping: Dict[str, str] = {}
    repo_root = Path(__file__).resolve().parents[2]
    
    # 搜索路径：优先 resolve_root_path()，回退 repo root
    search_dirs = [Path(_resolve_root_path()) / "config" / "apps", repo_root / "config" / "apps"]
    
    seen_apps = set()
    for apps_dir in search_dirs:
        if not apps_dir.exists():
            continue
        for yaml_path in apps_dir.glob("*.yaml"):
            app_name = yaml_path.stem
            if app_name in seen_apps:
                continue
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f)
                    if isinstance(doc, dict) and "package_name" in doc:
                        pkg = str(doc["package_name"]).strip()
                        if pkg:
                            mapping[pkg] = app_name
                seen_apps.add(app_name)
            except Exception:
                continue
    return mapping

def get_package_to_app_map() -> Dict[str, str]:
    """获取包名到 App 名的映射表（带缓存）。"""
    global _cached_package_map, _last_scan_time
    now = time.time()
    if not _cached_package_map or (now - _last_scan_time) > _SCAN_TTL:
        _cached_package_map = _scan_apps_for_packages()
        _last_scan_time = now
    return _cached_package_map

DEFAULT_APP_NAME = (os.getenv("MYT_DEFAULT_APP", "default") or "default").strip().lower() or "default"


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
    repo_root = Path(__file__).resolve().parents[2]
    for base in [Path(_resolve_root_path()), repo_root]:
        path = base / "config" / "apps" / f"{app}.yaml"
        if path.exists():
            return path
    return Path(_resolve_root_path()) / "config" / "apps" / f"{app}.yaml"


def load_app_config_document(app: str) -> dict[str, Any]:
    """加载 config/apps/{app}.yaml。"""
    path = app_config_path(app)
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"app config must be a mapping: {path}")
    raise FileNotFoundError(f"config/apps/{app}.yaml not found")


def load_ui_config_document() -> dict[str, Any]:
    """向后兼容接口。"""
    return load_app_config_document(DEFAULT_APP_NAME)


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


def prompt_templates_config_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        Path(_resolve_root_path()) / "config" / "strategies" / "prompt_templates.yaml",
        repo_root / "config" / "strategies" / "prompt_templates.yaml",
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        path_str = str(path.resolve()) if path.exists() else os.path.abspath(str(path))
        if path_str not in seen:
            seen.add(path_str)
            unique.append(path)
    return unique


def load_prompt_templates_document() -> dict[str, Any]:
    for path in prompt_templates_config_paths():
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        raise ValueError(f"prompt templates config must be a mapping: {path}")
    raise FileNotFoundError("config/strategies/prompt_templates.yaml not found")


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
