from __future__ import annotations

from typing import Any, cast

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


def _ok(data: dict[str, Any]) -> ActionResult:
    return ActionResult(ok=True, code="ok", data=data)


def _err(code: str, message: str, data: dict[str, Any] | None = None) -> ActionResult:
    return ActionResult(ok=False, code=code, message=message, data=data or {})


def _source(params: dict[str, Any]) -> str:
    source = str(params.get("source") or "online").strip().lower()
    return source if source in {"online", "local"} else "online"


def _device_ip(params: dict[str, Any], context: ExecutionContext) -> str:
    runtime_target = context.runtime.get("target")
    runtime_target_ip = (
        runtime_target.get("device_ip") if isinstance(runtime_target, dict) else None
    )
    return str(
        params.get("device_ip")
        or context.payload.get("device_ip")
        or runtime_target_ip
        or context.runtime.get("device_ip")
        or ""
    ).strip()


def _sdk_port(params: dict[str, Any], context: ExecutionContext) -> int:
    runtime_target = context.runtime.get("target")
    runtime_target_sdk_port = (
        runtime_target.get("sdk_port") if isinstance(runtime_target, dict) else None
    )
    raw = (
        params.get("sdk_port")
        or context.payload.get("sdk_port")
        or runtime_target_sdk_port
        or context.runtime.get("sdk_port")
        or 8000
    )
    return int(raw)


def _api_client(params: dict[str, Any], context: ExecutionContext) -> AndroidApiClient | None:
    device_ip = _device_ip(params, context)
    if not device_ip:
        return None
    runtime_target = context.runtime.get("target")
    runtime_target_api_port = (
        runtime_target.get("api_port") if isinstance(runtime_target, dict) else None
    )
    api_port = int(
        params.get("api_port")
        or runtime_target_api_port
        or context.runtime.get("api_port")
        or 30001
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
    runtime_target = context.runtime.get("target")
    runtime_target_api_port = (
        runtime_target.get("api_port") if isinstance(runtime_target, dict) else None
    )
    result = resolve_cloud_container(
        device_ip=_device_ip(params, context),
        sdk_port=_sdk_port(params, context),
        cloud_id=int(params.get("cloud_id") or context.cloud_id or 0) or None,
        api_port=int(
            params.get("api_port")
            or runtime_target_api_port
            or context.runtime.get("api_port")
            or 0
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
