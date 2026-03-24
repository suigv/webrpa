from __future__ import annotations

import os
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pyotp

from core.app_config import resolve_app_id
from engine.models.runtime import ActionResult, ExecutionContext


def _resolve_app(params: dict[str, Any], payload: dict[str, Any]) -> str:
    """从 params.app_id/app > payload.app_id/app > payload.package 顺序推断 app 配置名。"""
    default_app = str(os.getenv("MYT_DEFAULT_APP", "default") or "default").strip().lower()
    return resolve_app_id(payload, params=params, default_app=default_app)


def extract_cloud_status_payload(result: dict[str, Any]) -> tuple[str, Any]:
    payload = result.get("data")
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict):
            return str(payload[0].get("status") or "").strip().lower(), payload
        return "", payload
    if isinstance(payload, dict):
        if "status" in payload:
            return str(payload.get("status") or "").strip().lower(), payload
        items = payload.get("items")
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return str(items[0].get("status") or "").strip().lower(), payload
        data = payload.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return str(data[0].get("status") or "").strip().lower(), payload
    return "", payload


def wait_cloud_status_action(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    sdk_client: Callable[[dict[str, Any], ExecutionContext], Any],
    time_module: Any,
) -> ActionResult:
    client = sdk_client(params, context)
    if client is None:
        return ActionResult(ok=False, code="invalid_params", message="device_ip is required")

    name = str(params.get("name", "")).strip()
    if not name:
        return ActionResult(ok=False, code="invalid_params", message="name is required")

    target_status = str(params.get("target_status", "running") or "running").strip().lower()
    timeout_ms = max(int(params.get("timeout_ms", 180000) or 180000), 0)
    interval_ms = max(int(params.get("interval_ms", 5000) or 5000), 100)
    deadline = time_module.monotonic() + timeout_ms / 1000.0

    last_result: dict[str, Any] = {}
    last_status = ""

    while True:
        if context.should_cancel is not None and bool(context.should_cancel()):
            return ActionResult(
                ok=False,
                code="cancelled",
                message="task cancelled by user",
                data={"name": name, "target_status": target_status, "last_status": last_status},
            )

        try:
            result = client.get_cloud_status(name)
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}

        if isinstance(result, dict):
            last_result = result
            last_status, payload = extract_cloud_status_payload(result)
            if bool(result.get("ok")) and last_status == target_status:
                return ActionResult(
                    ok=True,
                    code="ok",
                    message=f"cloud status reached {target_status}",
                    data={
                        "name": name,
                        "status": last_status,
                        "target_status": target_status,
                        "result": result,
                        "payload": payload,
                    },
                )

        if time_module.monotonic() >= deadline:
            return ActionResult(
                ok=False,
                code="cloud_status_timeout",
                message=f"cloud status did not reach {target_status} within {timeout_ms}ms",
                data={
                    "name": name,
                    "target_status": target_status,
                    "last_status": last_status,
                    "result": last_result,
                },
            )
        time_module.sleep(interval_ms / 1000.0)


def resolve_first_non_empty_action(params: dict[str, Any]) -> ActionResult:
    values = params.get("values")
    if not isinstance(values, list):
        return ActionResult(ok=False, code="invalid_params", message="values must be a list")
    for index, value in enumerate(values):
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return ActionResult(ok=True, code="ok", data={"value": stripped, "index": index})
            continue
        if value:
            return ActionResult(ok=True, code="ok", data={"value": value, "index": index})
    return ActionResult(ok=False, code="value_missing", message="no non-empty value found")


def plan_follow_rounds_action(params: dict[str, Any]) -> ActionResult:
    target_follow_count = max(int(params.get("target_follow_count", 5) or 5), 1)
    first_round_cap = max(int(params.get("first_round_cap", 3) or 3), 1)
    round_one = min(target_follow_count, first_round_cap)
    round_two = max(target_follow_count - round_one, 0)
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "target_follow_count": target_follow_count,
            "round_one": round_one,
            "round_two": round_two,
        },
    )


def generate_totp_action(params: dict[str, Any]) -> ActionResult:
    secret = str(params.get("secret") or "").strip()
    if not secret:
        return ActionResult(ok=False, code="invalid_params", message="secret is required")
    try:
        token = pyotp.TOTP(secret).now()
    except Exception as exc:
        return ActionResult(ok=False, code="totp_failed", message=str(exc))
    return ActionResult(ok=True, code="ok", data={"token": token})


def resolve_daily_counter_key(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    resolve_shared_key: Callable[[dict[str, Any], ExecutionContext | None], str],
) -> str:
    base_key = str(params.get("key") or "daily_count").strip()
    resolved = resolve_shared_key(
        {"key": base_key, "scope": params.get("scope"), "scope_value": params.get("scope_value")},
        context,
    )
    return resolved or base_key


def check_daily_limit_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    read_daily_counters: Callable[[], dict[str, Any]],
    resolve_daily_counter_key: Callable[[dict[str, Any], ExecutionContext | None], str],
) -> ActionResult:
    limit = int(params.get("limit", 5) or 5)
    today = str(params.get("date") or datetime.now().strftime("%Y-%m-%d"))
    key = resolve_daily_counter_key(params, context)
    store = read_daily_counters()
    if store.get("date") != today:
        store = {"date": today, "counts": {}}
    counts_obj = store.get("counts")
    counts: dict[str, Any] = counts_obj if isinstance(counts_obj, dict) else {}
    try:
        current = int(counts.get(key, 0))
    except Exception:
        current = 0
    if current >= limit:
        return ActionResult(
            ok=False,
            code="daily_limit_reached",
            message=f"daily limit reached: {current}/{limit}",
            data={"key": key, "count": current, "limit": limit, "date": today},
        )
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "key": key,
            "count": current,
            "limit": limit,
            "remaining": max(limit - current, 0),
            "date": today,
        },
    )


def increment_daily_counter_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    read_daily_counters: Callable[[], dict[str, Any]],
    write_daily_counters: Callable[[dict[str, Any]], None],
    resolve_daily_counter_key: Callable[[dict[str, Any], ExecutionContext | None], str],
) -> ActionResult:
    amount = int(params.get("amount", 1) or 1)
    today = str(params.get("date") or datetime.now().strftime("%Y-%m-%d"))
    key = resolve_daily_counter_key(params, context)
    store = read_daily_counters()
    if store.get("date") != today:
        store = {"date": today, "counts": {}}
    counts_obj = store.get("counts")
    counts: dict[str, Any] = counts_obj if isinstance(counts_obj, dict) else {}
    try:
        current = int(counts.get(key, 0))
    except Exception:
        current = 0
    current += amount
    counts[key] = current
    store["date"] = today
    store["counts"] = counts
    write_daily_counters(store)
    return ActionResult(
        ok=True, code="ok", data={"key": key, "count": current, "amount": amount, "date": today}
    )


def load_ui_value_action(
    params: dict[str, Any],
    *,
    load_ui_config_document: Callable[[], dict[str, Any]],
    load_app_config_document: Callable[[str], dict[str, Any]],
    resolve_ui_key: Callable[[Any, str], Any],
    context: Any = None,
) -> ActionResult:
    key = str(params.get("key") or "").strip()
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    payload = (
        context.payload
        if context is not None and isinstance(getattr(context, "payload", None), dict)
        else {}
    )
    app = _resolve_app(params, payload)
    try:
        document = load_app_config_document(app)
    except Exception as exc:
        return ActionResult(ok=False, code="ui_config_unavailable", message=str(exc))

    value = resolve_ui_key(document, key)
    if value is None:
        if "default" in params:
            return ActionResult(
                ok=True,
                code="ok",
                data={"key": key, "value": params.get("default"), "exists": False},
            )
        return ActionResult(ok=False, code="ui_value_missing", message=f"ui value not found: {key}")
    return ActionResult(ok=True, code="ok", data={"key": key, "value": value, "exists": True})


def load_ui_selector_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    load_ui_config_document: Callable[[], dict[str, Any]],
    load_app_config_document: Callable[[str], dict[str, Any]],
    resolve_ui_key: Callable[[Any, str], Any],
    resolve_localized_entry: Callable[[Any, str], Any],
) -> ActionResult:
    key = str(params.get("key") or "").strip()
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    payload = context.payload if context is not None and isinstance(context.payload, dict) else {}
    locale = str(params.get("locale") or payload.get("locale") or "default").strip().lower()
    app = _resolve_app(params, payload)
    try:
        document = load_app_config_document(app)
    except Exception as exc:
        return ActionResult(ok=False, code="ui_config_unavailable", message=str(exc))

    selectors = document.get("selectors", {})
    entry = resolve_localized_entry(resolve_ui_key(selectors, key), locale)
    if not isinstance(entry, dict):
        return ActionResult(
            ok=False, code="ui_selector_missing", message=f"ui selector not found: {key}"
        )

    selector_type = str(entry.get("type") or "").strip().lower()
    mode = str(entry.get("mode") or "equal").strip().lower()
    value = entry.get("value")
    if not selector_type or value in (None, ""):
        return ActionResult(
            ok=False, code="ui_selector_invalid", message=f"ui selector invalid: {key}"
        )
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "key": key,
            "locale": locale,
            "type": selector_type,
            "mode": mode,
            "value": value,
        },
    )


def load_ui_selectors_action(
    params: dict[str, Any],
    context: ExecutionContext | None,
    *,
    load_ui_config_document: Callable[[], dict[str, Any]],
    load_app_config_document: Callable[[str], dict[str, Any]],
    resolve_ui_key: Callable[[Any, str], Any],
    resolve_localized_entry: Callable[[Any, str], Any],
) -> ActionResult:
    selector_defs = params.get("selectors")
    if not isinstance(selector_defs, list) or not selector_defs:
        return ActionResult(
            ok=False, code="invalid_params", message="selectors must be a non-empty list"
        )
    payload = context.payload if context is not None and isinstance(context.payload, dict) else {}
    locale = str(params.get("locale") or payload.get("locale") or "default").strip().lower()
    app = _resolve_app(params, payload)
    try:
        document = load_app_config_document(app)
    except Exception as exc:
        return ActionResult(ok=False, code="ui_config_unavailable", message=str(exc))

    selectors = document.get("selectors", {})
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    invalid: list[str] = []

    for entry in selector_defs:
        if isinstance(entry, str):
            key = entry.strip()
            alias = key
        elif isinstance(entry, dict):
            key = str(entry.get("key") or "").strip()
            alias = str(entry.get("alias") or entry.get("name") or key).strip()
        else:
            invalid.append(str(entry))
            continue

        if not key:
            invalid.append(str(entry))
            continue
        if not alias:
            alias = key
        if alias in resolved:
            return ActionResult(
                ok=False, code="invalid_params", message=f"duplicate selector alias: {alias}"
            )

        selector_entry = resolve_localized_entry(resolve_ui_key(selectors, key), locale)
        if not isinstance(selector_entry, dict):
            missing.append(key)
            continue

        selector_type = str(selector_entry.get("type") or "").strip().lower()
        mode = str(selector_entry.get("mode") or "equal").strip().lower()
        value = selector_entry.get("value")
        if not selector_type or value in (None, ""):
            invalid.append(key)
            continue

        resolved[alias] = {
            "key": key,
            "locale": locale,
            "type": selector_type,
            "mode": mode,
            "value": value,
        }

    if missing or invalid:
        message_parts: list[str] = []
        if missing:
            message_parts.append(f"missing selectors: {', '.join(missing)}")
        if invalid:
            message_parts.append(f"invalid selectors: {', '.join(invalid)}")
        return ActionResult(ok=False, code="ui_selector_missing", message="; ".join(message_parts))

    return ActionResult(ok=True, code="ok", data=resolved)


def load_ui_scheme_action(
    params: dict[str, Any],
    *,
    load_ui_config_document: Callable[[], dict[str, Any]],
    load_app_config_document: Callable[[str], dict[str, Any]],
    resolve_ui_key: Callable[[Any, str], Any],
    context: ExecutionContext | None = None,
    rpc: Any | None = None,
) -> ActionResult:
    key = str(params.get("key") or "").strip()
    if not key:
        return ActionResult(ok=False, code="invalid_params", message="key is required")
    payload = context.payload if context is not None and isinstance(context.payload, dict) else {}
    if "package" in params:
        payload = dict(payload)
        payload["package"] = params.get("package")
    app = _resolve_app(params, payload)
    try:
        document = load_app_config_document(app)
    except Exception as exc:
        return ActionResult(ok=False, code="ui_config_unavailable", message=str(exc))

    schemes = document.get("schemes", {})
    entry = resolve_ui_key(schemes, key)
    if entry is None:
        return ActionResult(
            ok=False, code="ui_scheme_missing", message=f"ui scheme not found: {app}.{key}"
        )

    template = entry.get("template") if isinstance(entry, dict) else entry
    if not isinstance(template, str) or not template.strip():
        return ActionResult(
            ok=False, code="ui_scheme_invalid", message=f"ui scheme invalid: {app}.{key}"
        )

    args = params.get("args")
    kwargs = params.get("kwargs")
    if not isinstance(kwargs, dict) and isinstance(args, dict):
        # Distilled plugins may serialize named format args under `args`.
        kwargs = args
    url = template
    try:
        if isinstance(kwargs, dict) and kwargs:
            safe_kwargs = {
                name: urllib.parse.quote(str(value), safe="") for name, value in kwargs.items()
            }
            url = template.format(**safe_kwargs)
        elif isinstance(args, list) and args:
            safe_args = [urllib.parse.quote(str(value), safe="") for value in args]
            url = template.format(*safe_args)
    except Exception as exc:
        return ActionResult(ok=False, code="ui_scheme_format_failed", message=str(exc))

    cmd = f'am start -a android.intent.action.VIEW -d "{url}"'
    if rpc is not None:
        try:
            _output, ok = rpc.exec_cmd(cmd)
            if not ok:
                return ActionResult(
                    ok=False, code="scheme_launch_failed", message=f"exec_cmd failed: {_output}"
                )
        except Exception as exc:
            return ActionResult(ok=False, code="scheme_launch_failed", message=str(exc))

    return ActionResult(
        ok=True,
        code="ok",
        data={
            "app": app,
            "key": key,
            "url": url,
            "executed": rpc is not None,
        },
    )
