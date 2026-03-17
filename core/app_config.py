from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from core.paths import config_dir

logger = logging.getLogger(__name__)


def _app_id_safe(app_id: str) -> str:
    raw = str(app_id or "").strip().lower()
    return "".join(ch for ch in raw if ch.isalnum() or ch in {"_", "-"})


def _app_config_path(app_id: str) -> Path:
    return config_dir() / "apps" / f"{_app_id_safe(app_id)}.yaml"


def _read_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load app config %s: %s", path, exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def get_app_config(app_id: str) -> dict[str, Any]:
    app_key = _app_id_safe(app_id)
    if not app_key:
        return {}
    return _read_yaml_dict(_app_config_path(app_key))


def resolve_app_payload(app_id: str, current_payload: dict[str, Any]) -> dict[str, Any]:
    config = get_app_config(app_id)
    if not config:
        return current_payload

    resolved = dict(current_payload)
    if not resolved.get("package") and config.get("package_name"):
        resolved["package"] = config["package_name"]
    if config.get("states"):
        resolved["_app_states"] = config["states"]
    if config.get("stage_patterns"):
        resolved["_app_stage_patterns"] = config["stage_patterns"]
    if config.get("selectors"):
        resolved["_app_selectors"] = config["selectors"]
    return resolved


class AppConfigManager:
    @staticmethod
    def apps_dir() -> Path:
        path = config_dir() / "apps"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def load_app_config(cls, app_id: str) -> dict[str, Any]:
        return get_app_config(app_id)

    @staticmethod
    def app_config_path(app_id: str) -> Path:
        return _app_config_path(app_id)

    @classmethod
    def write_app_config(cls, app_id: str, document: dict[str, Any]) -> Path:
        path = cls.app_config_path(app_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return path

    @classmethod
    def get_package_to_app_map(cls) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for path in sorted(cls.apps_dir().glob("*.yaml")):
            document = _read_yaml_dict(path)
            package_name = str(document.get("package_name") or "").strip()
            if not package_name:
                continue
            mapping[package_name] = path.stem
        return mapping

    @classmethod
    def find_app_by_package(cls, package_name: str) -> str:
        package = str(package_name or "").strip()
        if not package:
            return ""
        return cls.get_package_to_app_map().get(package, "")

    @classmethod
    def bootstrap_app_config(cls, package_name: str) -> Path | None:
        package = str(package_name or "").strip()
        if not package:
            return None
        existing = cls.find_app_by_package(package)
        if existing:
            return _app_config_path(existing)

        candidate = _app_id_safe(package.split(".")[-1] or package.replace(".", "_"))
        if not candidate:
            return None

        path = _app_config_path(candidate)
        if path.exists():
            return path

        skeleton = {
            "version": "v1",
            "package_name": package,
            "xml_filter": {"max_text_len": 60, "max_desc_len": 100},
            "states": [],
            "stage_patterns": {},
            "schemes": {},
            "selectors": {},
        }
        path.write_text(
            yaml.safe_dump(skeleton, allow_unicode=False, sort_keys=False), encoding="utf-8"
        )
        logger.info("Bootstrapped app config for %s at %s", package, path)
        return path
