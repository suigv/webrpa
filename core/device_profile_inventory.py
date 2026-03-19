from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from core.data_store import write_json_atomic
from core.paths import data_dir, now_iso
from hardware_adapters.myt_client import MytSdkClient

PhoneModelSource = Literal["online", "local"]


def _inventory_dir() -> Path:
    path = data_dir() / "inventory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_fragment(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(value or "").strip())
    return collapsed.strip("._") or "unknown"


def _cache_path(source: PhoneModelSource, device_ip: str, sdk_port: int) -> Path:
    filename = f"phone_models_{source}_{_safe_fragment(device_ip)}_{int(sdk_port)}.json"
    return _inventory_dir() / filename


def _sdk_client(
    device_ip: str,
    sdk_port: int = 8000,
    timeout_seconds: float = 30.0,
    retries: int = 3,
) -> MytSdkClient:
    return MytSdkClient(
        device_ip=device_ip,
        sdk_port=int(sdk_port),
        timeout_seconds=float(timeout_seconds),
        retries=int(retries),
    )


def _extract_phone_model_list(source: PhoneModelSource, result: dict[str, Any]) -> list[dict[str, Any]]:
    data = result.get("data")
    containers: list[Any] = []
    if isinstance(data, list):
        containers.append(data)
    if isinstance(data, dict):
        containers.extend(
            [
                data.get("list"),
                data.get("rows"),
                data.get("items"),
                data.get("data"),
            ]
        )
        nested = data.get("data")
        if isinstance(nested, dict):
            containers.extend([nested.get("list"), nested.get("rows"), nested.get("items")])
    for candidate in containers:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    if source == "local" and isinstance(data, dict):
        # Some upstream responses return a dict keyed by model name.
        dict_items = [value for value in data.values() if isinstance(value, dict)]
        if dict_items:
            return dict_items
    return []


def _normalize_phone_model(source: PhoneModelSource, item: dict[str, Any]) -> dict[str, Any]:
    name = str(
        item.get("name")
        or item.get("modelName")
        or item.get("title")
        or item.get("alias")
        or ""
    ).strip()
    model_id = str(item.get("id") or item.get("modelId") or "").strip()
    normalized = {
        "source": source,
        "id": model_id,
        "name": name,
        "status": str(item.get("status") or "").strip(),
        "sdk_ver": str(item.get("sdk_ver") or item.get("sdkVer") or "").strip(),
        "current_version": str(
            item.get("currentVersion") or item.get("current_version") or ""
        ).strip(),
        "created_at": str(item.get("createdAt") or item.get("created_at") or "").strip(),
        "md5": str(item.get("md5") or "").strip(),
        "raw": dict(item),
    }
    if source == "local" and not normalized["id"]:
        normalized["id"] = name
    return normalized


def _inventory_payload(
    source: PhoneModelSource,
    device_ip: str,
    sdk_port: int,
    items: list[dict[str, Any]],
    *,
    refreshed_at: str | None = None,
    from_cache: bool = False,
) -> dict[str, Any]:
    normalized_items = [_normalize_phone_model(source, item) for item in items]
    return {
        "inventory_type": "phone_models",
        "source": source,
        "device_ip": device_ip,
        "sdk_port": int(sdk_port),
        "count": len(normalized_items),
        "items": normalized_items,
        "refreshed_at": refreshed_at or now_iso(),
        "from_cache": from_cache,
    }


def refresh_phone_models(
    source: PhoneModelSource,
    *,
    device_ip: str,
    sdk_port: int = 8000,
    timeout_seconds: float = 30.0,
    retries: int = 3,
) -> dict[str, Any]:
    client = _sdk_client(
        device_ip=device_ip,
        sdk_port=sdk_port,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    result = (
        client.list_phone_models_online()
        if source == "online"
        else client.list_local_phone_models()
    )
    if not bool(result.get("ok", False)):
        message = str(result.get("message") or result.get("error") or result.get("reason") or "")
        return {
            "ok": False,
            "code": str(result.get("code") or "inventory_refresh_failed"),
            "message": message or f"failed to refresh {source} phone models",
            "data": {
                "source": source,
                "device_ip": device_ip,
                "sdk_port": int(sdk_port),
            },
        }

    items = _extract_phone_model_list(source, result)
    payload = _inventory_payload(source, device_ip, sdk_port, items, from_cache=False)
    write_json_atomic(_cache_path(source, device_ip, sdk_port), payload)
    return {"ok": True, "code": "ok", "data": payload}


def get_phone_models(
    source: PhoneModelSource,
    *,
    device_ip: str,
    sdk_port: int = 8000,
    refresh: bool = False,
    timeout_seconds: float = 30.0,
    retries: int = 3,
) -> dict[str, Any]:
    if refresh:
        return refresh_phone_models(
            source,
            device_ip=device_ip,
            sdk_port=sdk_port,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )

    path = _cache_path(source, device_ip, sdk_port)
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cached = None
        if isinstance(cached, dict):
            cached["from_cache"] = True
            return {"ok": True, "code": "ok", "data": cached}

    return refresh_phone_models(
        source,
        device_ip=device_ip,
        sdk_port=sdk_port,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
