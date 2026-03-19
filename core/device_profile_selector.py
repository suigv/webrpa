from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.device_profile_inventory import PhoneModelSource, get_phone_models


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _sorted_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            _normalize_text(item.get("source")),
            _normalize_text(item.get("name")),
            _normalize_text(item.get("id")),
        ),
    )


def _match_exact(value: Any, expected: str | list[str]) -> bool:
    actual = _normalize_text(value)
    if isinstance(expected, list):
        return actual in {_normalize_text(item) for item in expected}
    return actual == _normalize_text(expected)


def _filter_phone_models(
    items: list[dict[str, Any]],
    filters: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(filters, dict) or not filters:
        return list(items)

    filtered: list[dict[str, Any]] = []
    ids = filters.get("ids")
    names = filters.get("names")
    name_contains = str(filters.get("name_contains") or "").strip().lower()
    name_prefix = str(filters.get("name_prefix") or "").strip().lower()
    name_regex = str(filters.get("name_regex") or "").strip()
    regex = re.compile(name_regex, re.IGNORECASE) if name_regex else None

    for item in items:
        name = str(item.get("name") or "").strip()
        if ids and not _match_exact(item.get("id"), ids):
            continue
        if names and not _match_exact(name, names):
            continue
        if name_contains and name_contains not in name.lower():
            continue
        if name_prefix and not name.lower().startswith(name_prefix):
            continue
        if regex and not regex.search(name):
            continue

        exact_failed = False
        for key, expected in filters.items():
            if key in {"ids", "names", "name_contains", "name_prefix", "name_regex"}:
                continue
            if not _match_exact(item.get(key), expected):
                exact_failed = True
                break
        if exact_failed:
            continue
        filtered.append(item)
    return filtered


def _seed_text(seed: str | None, candidates: list[dict[str, Any]]) -> str:
    base = str(seed or "").strip()
    if base:
        return base
    stable = [{"id": item.get("id"), "name": item.get("name")} for item in candidates]
    return json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _pick_index(seed: str, count: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % count


def select_phone_model(
    *,
    source: PhoneModelSource = "online",
    device_ip: str = "",
    sdk_port: int = 8000,
    refresh_inventory: bool = False,
    timeout_seconds: float = 30.0,
    retries: int = 3,
    items: list[dict[str, Any]] | None = None,
    filters: dict[str, Any] | None = None,
    seed: str | None = None,
) -> dict[str, Any]:
    if items is None:
        inventory = get_phone_models(
            source,
            device_ip=device_ip,
            sdk_port=sdk_port,
            refresh=refresh_inventory,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )
        if not inventory.get("ok"):
            return inventory
        inventory_data = inventory.get("data")
        loaded_items = inventory_data.get("items") if isinstance(inventory_data, dict) else None
        if not isinstance(loaded_items, list):
            loaded_items = []
        items = [item for item in loaded_items if isinstance(item, dict)]
    sorted_items = _sorted_items(items)
    candidates = _filter_phone_models(sorted_items, filters)
    if not candidates:
        return {
            "ok": False,
            "code": "no_candidates",
            "message": "no phone model matched the selector filters",
            "data": {
                "source": source,
                "filters": filters or {},
                "candidate_count": 0,
            },
        }

    seed_used = _seed_text(seed, candidates)
    selected_index = _pick_index(seed_used, len(candidates))
    selected = dict(candidates[selected_index])
    apply = {
        "source": str(selected.get("source") or source),
        "model_id": str(selected.get("id") or "") if source == "online" else "",
        "local_model": str(selected.get("name") or "") if source == "local" else "",
        "model_name": str(selected.get("name") or ""),
    }
    return {
        "ok": True,
        "code": "ok",
        "data": {
            "source": source,
            "seed": seed_used,
            "candidate_count": len(candidates),
            "selected_index": selected_index,
            "filters": filters or {},
            "selected": selected,
            "apply": apply,
        },
    }
