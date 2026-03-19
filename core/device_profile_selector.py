from __future__ import annotations

import hashlib
import json
import re
from contextlib import suppress
from typing import Any

from core.device_profile_inventory import PhoneModelSource, get_phone_models
from hardware_adapters.myt_client import MytSdkClient


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


def _extract_android_list(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data")
    containers: list[Any] = []
    if isinstance(data, list):
        containers.append(data)
    if isinstance(data, dict):
        containers.extend([data.get("list"), data.get("items"), data.get("rows"), data.get("data")])
        nested = data.get("data")
        if isinstance(nested, dict):
            containers.extend([nested.get("list"), nested.get("items"), nested.get("rows")])
    for candidate in containers:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _extract_ports(candidate: Any) -> set[int]:
    ports: set[int] = set()
    if isinstance(candidate, dict):
        for key in ("hostPort", "containerPort", "port", "host_port", "container_port"):
            value = candidate.get(key)
            if isinstance(value, (int, float, str)) and str(value).strip():
                with suppress(ValueError):
                    ports.add(int(str(value)))
        for value in candidate.values():
            ports.update(_extract_ports(value))
    elif isinstance(candidate, list):
        for item in candidate:
            ports.update(_extract_ports(item))
    elif isinstance(candidate, (int, float, str)) and str(candidate).strip().isdigit():
        ports.add(int(str(candidate)))
    return ports


def _guessed_container_name(cloud_id: int | None) -> str:
    if cloud_id is None:
        return ""
    resolved = int(cloud_id)
    if resolved < 1:
        return ""
    return f"android-{resolved:02d}"


def _fallback_container_resolution(
    *,
    device_ip: str,
    sdk_port: int,
    cloud_id: int | None,
    api_port: int | None,
    reason: str,
) -> dict[str, Any] | None:
    container_name = _guessed_container_name(cloud_id)
    if not container_name:
        return None
    return {
        "ok": True,
        "code": "ok",
        "data": {
            "device_ip": device_ip,
            "sdk_port": int(sdk_port),
            "cloud_id": cloud_id,
            "api_port": api_port,
            "container_name": container_name,
            "selected": {
                "name": container_name,
                "indexNum": cloud_id,
                "resolution": "guessed_from_cloud_id",
            },
            "candidate_count": 1,
            "degraded": True,
            "fallback_reason": reason,
        },
    }


def resolve_cloud_container(
    *,
    device_ip: str,
    sdk_port: int = 8000,
    cloud_id: int | None = None,
    api_port: int | None = None,
    timeout_seconds: float = 30.0,
    retries: int = 3,
) -> dict[str, Any]:
    client = MytSdkClient(
        device_ip=device_ip,
        sdk_port=int(sdk_port),
        timeout_seconds=float(timeout_seconds),
        retries=int(retries),
    )
    result = client.list_androids()
    if not result.get("ok"):
        fallback = _fallback_container_resolution(
            device_ip=device_ip,
            sdk_port=int(sdk_port),
            cloud_id=cloud_id,
            api_port=api_port,
            reason=str(result.get("message") or result.get("error") or "failed to list androids"),
        )
        if fallback is not None:
            return fallback
        return {
            "ok": False,
            "code": str(result.get("code") or "container_list_failed"),
            "message": str(
                result.get("message") or result.get("error") or "failed to list androids"
            ),
            "data": {},
        }
    items = _extract_android_list(result)
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        score = 0
        index_num_raw = item.get("indexNum") or item.get("index_num")
        try:
            index_num = int(index_num_raw) if index_num_raw is not None else None
        except (TypeError, ValueError):
            index_num = None
        ports = _extract_ports(item.get("portBindings")) | _extract_ports(item.get("portMappings"))
        ports |= _extract_ports(item.get("ports"))
        if api_port is not None and int(api_port) in ports:
            score += 100
        if cloud_id is not None and index_num == int(cloud_id):
            score += 50
        if api_port is not None:
            for key in ("apiPort", "api_port"):
                value = item.get(key)
                if value is not None and str(value).strip():
                    try:
                        if int(str(value)) == int(api_port):
                            score += 100
                    except ValueError:
                        pass
        if score > 0:
            scored.append((score, item))
    if not scored:
        fallback = _fallback_container_resolution(
            device_ip=device_ip,
            sdk_port=int(sdk_port),
            cloud_id=cloud_id,
            api_port=api_port,
            reason="failed to resolve cloud container from current target",
        )
        if fallback is not None:
            return fallback
        return {
            "ok": False,
            "code": "container_not_found",
            "message": "failed to resolve cloud container from current target",
            "data": {
                "device_ip": device_ip,
                "sdk_port": int(sdk_port),
                "cloud_id": cloud_id,
                "api_port": api_port,
            },
        }
    scored.sort(
        key=lambda item: (
            -item[0],
            str(item[1].get("name") or "").lower(),
        )
    )
    selected = dict(scored[0][1])
    return {
        "ok": True,
        "code": "ok",
        "data": {
            "device_ip": device_ip,
            "sdk_port": int(sdk_port),
            "cloud_id": cloud_id,
            "api_port": api_port,
            "container_name": str(selected.get("name") or ""),
            "selected": selected,
            "candidate_count": len(scored),
        },
    }
