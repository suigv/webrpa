from __future__ import annotations

import socket
import time
from datetime import UTC, datetime
from typing import Any, cast

from core.device_manager import get_device_manager
from core.device_profile_generator import (
    generate_contact,
    generate_env_bundle,
    generate_fingerprint,
)
from core.device_profile_inventory import get_phone_models, refresh_phone_models
from core.device_profile_selector import resolve_cloud_container, select_phone_model
from engine.action_registry import ActionMetadata
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.android_api_client import AndroidApiClient

from ._context_value_support import resolve_context_value, runtime_target

INVENTORY_PHONE_MODELS_METADATA = ActionMetadata(
    description="Fetch or read cached phone model inventory from MYT SDK.",
    params_schema={
        "type": "object",
        "properties": {
            "source": {"type": "string", "enum": ["online", "local"]},
            "device_ip": {"type": "string"},
            "sdk_port": {"type": "integer", "default": 8000},
            "refresh": {"type": "boolean", "default": False},
        },
        "required": ["device_ip"],
    },
)

SELECT_PHONE_MODEL_METADATA = ActionMetadata(
    description="Deterministically select one phone model from inventory using filters and seed.",
    params_schema={
        "type": "object",
        "properties": {
            "source": {"type": "string", "enum": ["online", "local"]},
            "device_ip": {"type": "string"},
            "sdk_port": {"type": "integer", "default": 8000},
            "refresh_inventory": {"type": "boolean", "default": False},
            "seed": {"type": "string"},
            "filters": {"type": "object"},
            "items": {"type": "array"},
        },
    },
)

SELECT_CLOUD_CONTAINER_METADATA = ActionMetadata(
    description="Resolve current runtime cloud target to the MYT SDK container name.",
    params_schema={
        "type": "object",
        "properties": {
            "device_ip": {"type": "string"},
            "sdk_port": {"type": "integer", "default": 8000},
            "cloud_id": {"type": "integer"},
            "api_port": {"type": "integer"},
        },
    },
)

GENERATE_FINGERPRINT_METADATA = ActionMetadata(
    description="Generate randomized anti-ban fingerprint payload for MYTOS modifydev cmd=7.",
    params_schema={
        "type": "object",
        "properties": {
            "country_profile": {"type": "string", "default": "jp_mobile"},
            "seed": {"type": "string"},
            "overrides": {"type": "object"},
        },
    },
)

GENERATE_CONTACT_METADATA = ActionMetadata(
    description="Generate randomized contacts payload for MYTOS add_contact.",
    params_schema={
        "type": "object",
        "properties": {
            "country_profile": {"type": "string", "default": "jp_mobile"},
            "seed": {"type": "string"},
            "count": {"type": "integer", "default": 1},
        },
    },
)

GENERATE_ENV_BUNDLE_METADATA = ActionMetadata(
    description="Generate a reusable environment bundle with language, fingerprint, Google ADID, and contacts.",
    params_schema={
        "type": "object",
        "properties": {
            "country_profile": {"type": "string", "default": "jp_mobile"},
            "seed": {"type": "string"},
            "contact_count": {"type": "integer", "default": 1},
            "language": {"type": "string"},
            "country": {"type": "string"},
            "timezone": {"type": "string"},
            "shake_enabled": {"type": "boolean", "default": False},
            "fingerprint_overrides": {"type": "object"},
        },
    },
)

APPLY_ENV_BUNDLE_METADATA = ActionMetadata(
    description="Apply language, fingerprint, Google ADID, contacts, shake, and optional screenshot to the current MYTOS cloud machine.",
    params_schema={
        "type": "object",
        "properties": {
            "language": {"type": "string"},
            "country": {"type": "string"},
            "fingerprint": {"type": "object"},
            "google_adid": {"type": "string"},
            "contacts": {"type": "array"},
            "set_google_id": {"type": "boolean", "default": True},
            "write_contacts": {"type": "boolean", "default": True},
            "shake_enabled": {"type": "boolean", "default": False},
            "take_screenshot": {"type": "boolean", "default": False},
            "screenshot_level": {"type": "integer", "default": 2},
        },
    },
)

WAIT_CLOUD_AVAILABLE_METADATA = ActionMetadata(
    description="Wait for the current cloud target to return available after a reboot-like operation.",
    params_schema={
        "type": "object",
        "properties": {
            "device_id": {"type": "integer"},
            "cloud_id": {"type": "integer"},
            "timeout_ms": {"type": "integer", "default": 180000},
            "transition_timeout_ms": {"type": "integer", "default": 30000},
            "poll_interval_ms": {"type": "integer", "default": 1000},
            "require_cycle": {"type": "boolean", "default": True},
        },
    },
)


def _ok(data: dict[str, Any]) -> ActionResult:
    return ActionResult(ok=True, code="ok", data=data)


def _err(code: str, message: str, data: dict[str, Any] | None = None) -> ActionResult:
    return ActionResult(ok=False, code=code, message=message, data=data or {})


def _probe_cloud_snapshot(
    context: ExecutionContext,
    *,
    device_id: int,
    cloud_id: int,
) -> dict[str, Any]:
    target = runtime_target(context)
    device_ip = str(target.get("device_ip") or "").strip()
    rpa_port_raw = target.get("rpa_port")
    if device_ip and rpa_port_raw is not None:
        checked_at = datetime.now(UTC).isoformat()
        try:
            started = time.monotonic()
            with socket.create_connection((device_ip, int(rpa_port_raw)), timeout=0.8):
                latency_ms = int((time.monotonic() - started) * 1000)
            return {
                "device_id": device_id,
                "cloud_id": cloud_id,
                "availability_state": "available",
                "availability_reason": "ok",
                "last_checked_at": checked_at,
                "latency_ms": latency_ms,
                "stale": False,
            }
        except Exception as exc:
            return {
                "device_id": device_id,
                "cloud_id": cloud_id,
                "availability_state": "unavailable",
                "availability_reason": str(exc),
                "last_checked_at": checked_at,
                "latency_ms": None,
                "stale": False,
            }
    return get_device_manager().get_cloud_probe_snapshot(device_id, cloud_id)


def _source(params: dict[str, Any]) -> str:
    source = str(params.get("source") or "online").strip().lower()
    return source if source in {"online", "local"} else "online"


def _device_ip(params: dict[str, Any], context: ExecutionContext) -> str:
    return str(
        resolve_context_value(
            params,
            context,
            "device_ip",
            "",
            source_order=("params", "payload", "target", "runtime"),
        )
        or ""
    ).strip()


def _sdk_port(params: dict[str, Any], context: ExecutionContext) -> int:
    raw = resolve_context_value(
        params,
        context,
        "sdk_port",
        8000,
        source_order=("params", "payload", "target", "runtime"),
    )
    return int(raw)


def _api_client(params: dict[str, Any], context: ExecutionContext) -> AndroidApiClient | None:
    device_ip = _device_ip(params, context)
    if not device_ip:
        return None
    api_port = int(
        resolve_context_value(
            params,
            context,
            "api_port",
            30001,
            source_order=("params", "target", "runtime"),
        )
    )
    return AndroidApiClient(
        device_ip=device_ip,
        api_port=api_port,
        timeout_seconds=float(params.get("timeout_seconds", 30.0)),
        retries=int(params.get("retries", 3)),
    )


def _result_to_action(result: dict[str, Any]) -> ActionResult:
    if not result.get("ok"):
        return _err(
            str(result.get("code") or "action_failed"),
            str(result.get("message") or "action failed"),
            cast(dict[str, Any], result.get("data") or {}),
        )
    data = result.get("data")
    if not isinstance(data, dict):
        data = {"result": data}
    return _ok(cast(dict[str, Any], data))


def inventory_get_phone_models(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    device_ip = _device_ip(params, context)
    if not device_ip:
        return _err("invalid_params", "device_ip is required")
    return _result_to_action(
        get_phone_models(
            cast(Any, _source(params)),
            device_ip=device_ip,
            sdk_port=_sdk_port(params, context),
            refresh=bool(params.get("refresh", False)),
            timeout_seconds=float(params.get("timeout_seconds", 30.0)),
            retries=int(params.get("retries", 3)),
        )
    )


def inventory_refresh_phone_models(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    device_ip = _device_ip(params, context)
    if not device_ip:
        return _err("invalid_params", "device_ip is required")
    return _result_to_action(
        refresh_phone_models(
            cast(Any, _source(params)),
            device_ip=device_ip,
            sdk_port=_sdk_port(params, context),
            timeout_seconds=float(params.get("timeout_seconds", 30.0)),
            retries=int(params.get("retries", 3)),
        )
    )


def selector_select_phone_model(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    items = params.get("items")
    normalized_items = items if isinstance(items, list) else None
    result = select_phone_model(
        source=cast(Any, _source(params)),
        device_ip=_device_ip(params, context),
        sdk_port=_sdk_port(params, context),
        refresh_inventory=bool(params.get("refresh_inventory", False)),
        timeout_seconds=float(params.get("timeout_seconds", 30.0)),
        retries=int(params.get("retries", 3)),
        items=cast(list[dict[str, Any]] | None, normalized_items),
        filters=cast(dict[str, Any] | None, params.get("filters")),
        seed=str(params.get("seed") or "").strip() or None,
    )
    return _result_to_action(result)


def selector_resolve_cloud_container(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    result = resolve_cloud_container(
        device_ip=_device_ip(params, context),
        sdk_port=_sdk_port(params, context),
        cloud_id=int(params.get("cloud_id") or context.cloud_id or 0) or None,
        api_port=int(
            resolve_context_value(
                params,
                context,
                "api_port",
                0,
                source_order=("params", "target", "runtime"),
            )
        )
        or None,
        timeout_seconds=float(params.get("timeout_seconds", 30.0)),
        retries=int(params.get("retries", 3)),
    )
    return _result_to_action(result)


def generator_generate_fingerprint(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    _ = context
    data = generate_fingerprint(
        country_profile=str(params.get("country_profile") or "jp_mobile"),
        seed=str(params.get("seed") or "").strip() or None,
        overrides=cast(dict[str, Any] | None, params.get("overrides")),
    )
    return _ok(data)


def generator_generate_contact(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    _ = context
    data = generate_contact(
        country_profile=str(params.get("country_profile") or "jp_mobile"),
        seed=str(params.get("seed") or "").strip() or None,
        count=int(params.get("count", 1)),
    )
    return _ok(data)


def generator_generate_env_bundle(
    params: dict[str, Any], context: ExecutionContext
) -> ActionResult:
    _ = context
    data = generate_env_bundle(
        country_profile=str(params.get("country_profile") or "jp_mobile"),
        seed=str(params.get("seed") or "").strip() or None,
        contact_count=int(params.get("contact_count", 1)),
        language=str(params.get("language") or "").strip() or None,
        country=str(params.get("country") or "").strip() or None,
        timezone=str(params.get("timezone") or "").strip() or None,
        shake_enabled=bool(params.get("shake_enabled", False)),
        fingerprint_overrides=cast(dict[str, Any] | None, params.get("fingerprint_overrides")),
    )
    return _ok(data)


def profile_apply_env_bundle(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    client = _api_client(params, context)
    if client is None:
        return _err("invalid_params", "device_ip is required")

    language = str(params.get("language") or "").strip()
    country = str(params.get("country") or "").strip()
    fingerprint = params.get("fingerprint")
    google_adid = str(params.get("google_adid") or "").strip()
    contacts = params.get("contacts")
    set_google_id = bool(params.get("set_google_id", True))
    write_contacts = bool(params.get("write_contacts", True))
    shake_enabled = bool(params.get("shake_enabled", False))
    take_screenshot = bool(params.get("take_screenshot", False))
    screenshot_level = int(params.get("screenshot_level", 2))

    if not language or not country:
        return _err("invalid_params", "language and country are required")
    if not isinstance(fingerprint, dict) or not fingerprint:
        return _err("invalid_params", "fingerprint is required")

    applied: list[str] = []

    def _call(step_name: str, result: dict[str, Any]) -> ActionResult | None:
        if result.get("ok"):
            applied.append(step_name)
            return None
        message = str(result.get("message") or result.get("reason") or result.get("error") or "")
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        return _err(
            str(result.get("code") or "api_error"),
            message or f"{step_name} failed",
            {"applied": applied, "step": step_name, **cast(dict[str, Any], data)},
        )

    failed = _call("set_language_country", client.set_language_country(language, country))
    if failed is not None:
        return failed
    failed = _call("set_device_fingerprint", client.set_device_fingerprint(fingerprint))
    if failed is not None:
        return failed
    if set_google_id and google_adid:
        failed = _call("set_google_id", client.set_google_id(google_adid))
        if failed is not None:
            return failed
    if write_contacts and isinstance(contacts, list) and contacts:
        failed = _call(
            "add_contact", client.add_contact(contacts=cast(list[dict[str, str]], contacts))
        )
        if failed is not None:
            return failed
    failed = _call("set_shake", client.set_shake(enabled=shake_enabled))
    if failed is not None:
        return failed

    result_data: dict[str, Any] = {"applied": applied}
    if take_screenshot:
        screenshot_result = client.screenshot(level=screenshot_level)
        if not screenshot_result.get("ok"):
            message = str(
                screenshot_result.get("message")
                or screenshot_result.get("reason")
                or screenshot_result.get("error")
                or ""
            )
            return _err(
                str(screenshot_result.get("code") or "api_error"),
                message or "screenshot failed",
                {"applied": applied, "step": "screenshot"},
            )
        applied.append("screenshot")
        screenshot_data = screenshot_result.get("data")
        result_data["screenshot"] = screenshot_data if isinstance(screenshot_data, dict) else {}
        result_data["applied"] = applied
    return _ok(result_data)


def profile_wait_cloud_available(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    target = runtime_target(context)
    device_id = int(params.get("device_id") or target.get("device_id") or context.device_id or 0)
    cloud_id = int(params.get("cloud_id") or target.get("cloud_id") or context.cloud_id or 0)
    if device_id < 1 or cloud_id < 1:
        return _err("invalid_params", "device_id and cloud_id are required")

    timeout_ms = max(1000, int(params.get("timeout_ms") or 180000))
    transition_timeout_ms = max(0, int(params.get("transition_timeout_ms") or 30000))
    poll_interval_ms = max(200, int(params.get("poll_interval_ms") or 1000))
    require_cycle = bool(params.get("require_cycle", True))

    started = time.monotonic()
    phase = "wait_transition" if require_cycle else "wait_available"
    transition_observed = False
    last_snapshot = _probe_cloud_snapshot(context, device_id=device_id, cloud_id=cloud_id)

    while True:
        context.check_cancelled()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        snapshot = _probe_cloud_snapshot(context, device_id=device_id, cloud_id=cloud_id)
        state = str(snapshot.get("availability_state") or "unknown")
        stale = bool(snapshot.get("stale", False))
        last_snapshot = snapshot

        if phase == "wait_transition":
            if state != "available" or stale:
                transition_observed = True
                phase = "wait_available"
            elif elapsed_ms >= transition_timeout_ms:
                phase = "wait_available"

        if phase == "wait_available" and state == "available" and not stale:
            return _ok(
                {
                    "device_id": device_id,
                    "cloud_id": cloud_id,
                    "transition_observed": transition_observed,
                    "waited_ms": elapsed_ms,
                    "snapshot": snapshot,
                }
            )

        if elapsed_ms >= timeout_ms:
            return _err(
                "target_wait_timeout",
                "cloud target did not become available before timeout",
                {
                    "device_id": device_id,
                    "cloud_id": cloud_id,
                    "phase": phase,
                    "transition_observed": transition_observed,
                    "waited_ms": elapsed_ms,
                    "snapshot": last_snapshot,
                },
            )

        time.sleep(poll_interval_ms / 1000.0)
