from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from core.app_config import get_app_config
from core.paths import project_root

DEFAULT_BRANCH_ID = "default"

_BRANCH_LABELS = {
    "default": "默认分支",
    "volc": "交友",
    "part_time": "兼职",
}
_BRANCH_ALIASES = {
    "dating": "volc",
    "friendship": "volc",
    "friend": "volc",
    "volc": "volc",
    "part_time": "part_time",
    "part-time": "part_time",
    "job": "part_time",
    "兼职": "part_time",
    "交友": "volc",
    "默认": "default",
}


def normalize_branch_id(value: Any, *, default: str = DEFAULT_BRANCH_ID) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not raw:
        return default
    return _BRANCH_ALIASES.get(raw, raw)


def branch_label(branch_id: str) -> str:
    normalized = normalize_branch_id(branch_id)
    return _BRANCH_LABELS.get(normalized, normalized or DEFAULT_BRANCH_ID)


def coerce_role_tags(value: Any) -> list[str]:
    raw_items: Iterable[Any]
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, dict)):
        raw_items = value
    else:
        raw_items = []

    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def raw_branch_value_from_payload(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("branch_id", "business_branch", "ai_type"):
        raw = str(payload.get(key) or "").strip()
        if raw:
            return raw
    return ""


def branch_id_from_payload(payload: dict[str, Any] | None) -> str:
    raw = raw_branch_value_from_payload(payload)
    return normalize_branch_id(raw) if raw else DEFAULT_BRANCH_ID


def inject_branch_payload(payload: dict[str, Any] | None, *, default: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    resolved = dict(payload)
    raw = raw_branch_value_from_payload(resolved)
    if raw:
        resolved["branch_id"] = normalize_branch_id(raw)
    elif default not in (None, ""):
        resolved["branch_id"] = normalize_branch_id(default)
    if "ai_type" in resolved and not str(resolved.get("ai_type") or "").strip():
        resolved.pop("ai_type", None)
    return resolved


def collect_known_branch_ids(app_id: str) -> list[str]:
    config = get_app_config(app_id)
    seen: set[str] = set()
    result: list[str] = []

    def _add(raw: Any) -> None:
        branch_id = normalize_branch_id(raw, default="")
        if not branch_id or branch_id in seen:
            return
        seen.add(branch_id)
        result.append(branch_id)

    _add(config.get("default_branch"))

    branches = config.get("branches")
    if isinstance(branches, dict):
        for key in branches:
            _add(key)

    for legacy_key in ("nurture_keywords", "quote_texts"):
        section = config.get(legacy_key)
        if isinstance(section, dict):
            for key in section:
                _add(key)

    for path in _legacy_strategy_paths():
        if not path.exists():
            continue
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        for key in ("strategies", "search_query", "dm_reply", "quote_text"):
            section = payload.get(key)
            if isinstance(section, dict):
                for candidate in section:
                    _add(candidate)

    if DEFAULT_BRANCH_ID not in seen:
        result.insert(0, DEFAULT_BRANCH_ID)
    return result


def resolve_branch_profile(
    *,
    app_id: str,
    requested_branch: Any = None,
    account_default_branch: Any = None,
) -> dict[str, Any]:
    config = get_app_config(app_id)
    known_branch_ids = collect_known_branch_ids(app_id)
    configured_default = normalize_branch_id(config.get("default_branch"), default="")
    default_branch = configured_default or (
        known_branch_ids[0] if known_branch_ids else DEFAULT_BRANCH_ID
    )
    branch_id = normalize_branch_id(
        requested_branch or account_default_branch or default_branch,
        default=default_branch,
    )
    if branch_id not in known_branch_ids:
        known_branch_ids.append(branch_id)
    return {
        "branch_id": branch_id,
        "default_branch": default_branch,
        "label": branch_label(branch_id),
        "branches": [
            {"branch_id": item, "label": branch_label(item), "is_default": item == default_branch}
            for item in known_branch_ids
        ],
    }


def _legacy_strategy_paths() -> list[Path]:
    base = project_root() / "config" / "strategies"
    return [
        base / "nurture_keywords.yaml",
        base / "interaction_texts.yaml",
    ]
