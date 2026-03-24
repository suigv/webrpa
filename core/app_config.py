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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_package_name(value: Any) -> str:
    return _normalize_text(value)


def _coerce_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif value is None:
        raw_items = []
    else:
        raw_items = [value]
    items: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _normalize_text(item)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        items.append(text)
    return items


def _alias_candidates(value: Any) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []
    candidates = [text.lower()]
    safe = _app_id_safe(text)
    if safe and safe not in candidates:
        candidates.append(safe)
    return candidates


def _package_names_from_document(document: dict[str, Any]) -> list[str]:
    package_names: list[str] = []
    seen: set[str] = set()
    for item in [document.get("package_name"), *(_coerce_text_list(document.get("package_names")))]:
        package_name = _normalize_package_name(item)
        if not package_name:
            continue
        lowered = package_name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        package_names.append(package_name)
    return package_names


def _identity_from_document(path: Path, document: dict[str, Any]) -> dict[str, Any]:
    app_id = _app_id_safe(document.get("app_id") or path.stem or "")
    display_name = _normalize_text(document.get("display_name") or document.get("name") or "")
    aliases = _coerce_text_list(document.get("aliases"))
    package_names = _package_names_from_document(document)
    if not display_name and app_id:
        display_name = app_id.upper()
    return {
        "app_id": app_id,
        "display_name": display_name,
        "aliases": aliases,
        "package_names": package_names,
        "package_name": package_names[0] if package_names else "",
        "path": path,
        "document": document,
    }


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
    document = _read_yaml_dict(_app_config_path(app_key))
    if document and not document.get("app_id"):
        document = {**document, "app_id": app_key}
    return document


def resolve_app_id(
    payload: dict[str, Any] | None = None,
    *,
    params: dict[str, Any] | None = None,
    default_app: str = "default",
) -> str:
    sources = (
        params if isinstance(params, dict) else {},
        payload if isinstance(payload, dict) else {},
    )
    for source in sources:
        package_name = source.get("package_name") or source.get("package")
        for key in ("app_id", "app", "app_name", "display_name", "name"):
            raw = _normalize_text(source.get(key))
            if raw:
                identity = AppConfigManager.resolve_app_identity(
                    app_id=raw,
                    display_name=None,
                    package_name=package_name,
                )
                if identity.get("app_id"):
                    return str(identity["app_id"])
        if package_name:
            mapped = AppConfigManager.find_app_by_package(str(package_name))
            if mapped:
                return mapped

    return str(default_app or "default").strip().lower() or "default"


def resolve_app_payload(app_id: str, current_payload: dict[str, Any]) -> dict[str, Any]:
    config = get_app_config(app_id)
    resolved = dict(current_payload)
    if app_id:
        resolved["app_id"] = app_id
    if "app" in resolved and resolved.get("app") == app_id:
        resolved.pop("app", None)
    if not config:
        return resolved

    package_names = _package_names_from_document(config)
    if not resolved.get("package") and package_names:
        resolved["package"] = package_names[0]
    if config.get("states"):
        resolved["_app_states"] = config["states"]
    if config.get("stage_patterns"):
        resolved["_app_stage_patterns"] = config["stage_patterns"]
    if config.get("selectors"):
        resolved["_app_selectors"] = config["selectors"]
    return resolved


def get_app_agent_hint(app_id: str) -> str:
    config = get_app_config(app_id)
    raw = str(config.get("agent_hint") or "").strip()
    return raw


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
    def list_apps(cls, *, include_default: bool = False) -> list[dict[str, Any]]:
        apps: list[dict[str, Any]] = []
        if include_default:
            apps.append(
                {
                    "app_id": "default",
                    "display_name": "默认 (系统)",
                    "aliases": [],
                    "package_names": [],
                    "package_name": "",
                    "path": cls.app_config_path("default"),
                    "document": get_app_config("default"),
                }
            )
        for path in sorted(cls.apps_dir().glob("*.yaml")):
            document = _read_yaml_dict(path)
            identity = _identity_from_document(path, document)
            if not identity["app_id"]:
                continue
            if identity["app_id"] == "default" and include_default:
                continue
            apps.append(identity)
        return apps

    @classmethod
    def resolve_known_app_id(cls, value: Any) -> str:
        candidates = _alias_candidates(value)
        if not candidates:
            return ""
        for app in cls.list_apps():
            tokens = {
                *(_alias_candidates(app.get("app_id"))),
                *(_alias_candidates(app.get("display_name"))),
            }
            for alias in app.get("aliases") or []:
                tokens.update(_alias_candidates(alias))
            if any(candidate in tokens for candidate in candidates):
                return str(app["app_id"])
        return ""

    @classmethod
    def resolve_app_identity(
        cls,
        *,
        app_id: str | None = None,
        display_name: str | None = None,
        package_name: str | None = None,
    ) -> dict[str, Any]:
        package = _normalize_package_name(package_name)
        package_match = cls.find_app_by_package(package) if package else ""
        app_match = cls.resolve_known_app_id(app_id) if app_id else ""
        name_match = cls.resolve_known_app_id(display_name) if display_name else ""
        if package_match and app_match and package_match != app_match:
            raise ValueError(f"package {package} is already bound to app {package_match}")
        if package_match and name_match and package_match != name_match:
            raise ValueError(f"package {package} is already bound to app {package_match}")

        resolved_app_id = package_match or app_match or name_match
        if not resolved_app_id:
            resolved_app_id = (
                _app_id_safe(app_id or "")
                or _app_id_safe(display_name or "")
                or _app_id_safe(package.split(".")[-1] if package else "")
                or "default"
            )
        config = cls.load_app_config(resolved_app_id)
        configured_display_name = _normalize_text(
            config.get("display_name") or config.get("name") or ""
        )
        configured_package_names = _package_names_from_document(config)
        return {
            "app_id": resolved_app_id,
            "display_name": configured_display_name
            or _normalize_text(display_name)
            or resolved_app_id.upper(),
            "package_name": package
            or (configured_package_names[0] if configured_package_names else ""),
            "package_names": configured_package_names or ([package] if package else []),
            "exists": bool(config),
        }

    @classmethod
    def ensure_app_config(
        cls,
        *,
        app_id: str | None = None,
        display_name: str | None = None,
        package_name: str | None = None,
        aliases: list[str] | None = None,
    ) -> dict[str, Any]:
        identity = cls.resolve_app_identity(
            app_id=app_id,
            display_name=display_name,
            package_name=package_name,
        )
        resolved_app_id = str(identity["app_id"])
        path = cls.app_config_path(resolved_app_id)
        document = cls.load_app_config(resolved_app_id)
        created = not path.exists()
        if not document:
            document = {
                "version": "v1",
                "xml_filter": {"max_text_len": 60, "max_desc_len": 100},
                "states": [],
                "stage_patterns": {},
                "schemes": {},
                "selectors": {},
            }
        changed = False
        if document.get("app_id") != resolved_app_id:
            document["app_id"] = resolved_app_id
            changed = True

        normalized_display_name = _normalize_text(display_name)
        if normalized_display_name and document.get("display_name") != normalized_display_name:
            document["display_name"] = normalized_display_name
            changed = True

        package_names = _package_names_from_document(document)
        normalized_package = _normalize_package_name(package_name)
        if normalized_package and normalized_package.lower() not in {
            item.lower() for item in package_names
        }:
            package_names.append(normalized_package)
            changed = True
        if package_names:
            if document.get("package_name") != package_names[0]:
                document["package_name"] = package_names[0]
                changed = True
            if len(package_names) > 1:
                if document.get("package_names") != package_names:
                    document["package_names"] = package_names
                    changed = True
            elif "package_names" in document:
                document.pop("package_names", None)
                changed = True

        merged_aliases = _coerce_text_list(
            [*(_coerce_text_list(document.get("aliases"))), *(aliases or [])]
        )
        if merged_aliases:
            if document.get("aliases") != merged_aliases:
                document["aliases"] = merged_aliases
                changed = True
        elif "aliases" in document:
            document.pop("aliases", None)
            changed = True

        if created or changed:
            cls.write_app_config(resolved_app_id, document)

        return {
            "app_id": resolved_app_id,
            "display_name": _normalize_text(
                document.get("display_name") or resolved_app_id.upper()
            ),
            "package_name": str(document.get("package_name") or "").strip(),
            "package_names": _package_names_from_document(document),
            "created": created,
            "path": path,
        }

    @classmethod
    def get_package_to_app_map(cls) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for app in cls.list_apps():
            for package_name in app.get("package_names") or []:
                mapping[str(package_name)] = str(app["app_id"])
        return mapping

    @classmethod
    def find_app_by_package(cls, package_name: str) -> str:
        package = _normalize_package_name(package_name)
        if not package:
            return ""
        return cls.get_package_to_app_map().get(package, "")

    @classmethod
    def bootstrap_app_config(cls, package_name: str) -> Path | None:
        package = _normalize_package_name(package_name)
        if not package:
            return None
        result = cls.ensure_app_config(package_name=package)
        logger.info("Bootstrapped app config for %s at %s", package, result["path"])
        return result["path"]
