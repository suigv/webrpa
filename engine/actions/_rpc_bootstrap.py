from __future__ import annotations

import os
from typing import Any, Callable, Dict

from core.port_calc import calculate_ports


RpcFactory = Callable[[], Any]
ResultFactory = Callable[..., Any]


def is_rpc_enabled() -> bool:
    # Allow MYT_ENABLE_RPC=0 to override (test framework and migration scripts use this)
    env_val = os.environ.get("MYT_ENABLE_RPC")
    if env_val is not None:
        return env_val.strip() not in ("0", "false", "False")
    from core.system_settings_loader import get_rpc_enabled
    return get_rpc_enabled()


def _normalize_runtime_target(context: Any) -> Dict[str, Any]:
    target = getattr(context, "target", None)
    if isinstance(target, dict):
        return target
    runtime = getattr(context, "runtime", None)
    if isinstance(runtime, dict):
        runtime_target = runtime.get("target")
        if isinstance(runtime_target, dict):
            return runtime_target
    payload = getattr(context, "payload", None)
    if isinstance(payload, dict):
        payload_target = payload.get("_target")
        if isinstance(payload_target, dict):
            return payload_target
    return {}


def _pick_connection_source(
    params: Dict[str, Any],
    session_defaults: Dict[str, Any],
    target: Dict[str, Any],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    if any(key in params for key in ("device_ip", "rpa_port", "cloud_index", "device_index", "cloud_machines_per_device")):
        return params
    if any(
        key in session_defaults for key in ("device_ip", "rpa_port", "cloud_index", "device_index", "cloud_machines_per_device")
    ):
        return session_defaults
    if target:
        return target
    return payload


def resolve_connection_params(params: Dict[str, Any], context: Any) -> tuple[str, int]:
    payload: Dict[str, Any] = dict(getattr(context, "payload", {}) or {})
    target = _normalize_runtime_target(context)
    if target and payload:
        if "device_ip" not in target and payload.get("device_ip"):
            merged_target = dict(target)
            merged_target["device_ip"] = payload.get("device_ip")
            target = merged_target
    session_defaults = getattr(context, "session_defaults", {})
    session_defaults = session_defaults if isinstance(session_defaults, dict) else {}
    source = _pick_connection_source(params, session_defaults, target, payload)

    device_ip = str(source.get("device_ip") or "").strip()
    if not device_ip:
        raise ValueError("device_ip is required")

    explicit_rpa_port = source.get("rpa_port")
    if explicit_rpa_port is not None:
        return device_ip, int(explicit_rpa_port)

    cloud_index = int(source.get("cloud_index") or source.get("cloud_id") or 1)
    device_index = int(source.get("device_index") or source.get("device_id") or 1)
    cloud_machines_per_device = int(source.get("cloud_machines_per_device") or 1)
    _, rpa_port = calculate_ports(
        device_index=device_index,
        cloud_index=cloud_index,
        cloud_machines_per_device=cloud_machines_per_device,
    )
    return device_ip, rpa_port


def bootstrap_rpc(
    params: Dict[str, Any],
    context: Any,
    *,
    is_enabled: Callable[[], bool],
    resolve_params: Callable[[Dict[str, Any], Any], tuple[str, int]],
    rpc_factory: RpcFactory,
    result_factory: ResultFactory,
    error_type_env: Any,
    error_type_business: Any,
) -> tuple[Any | None, Any | None]:
    if not is_enabled():
        return None, result_factory(
            ok=False,
            code="rpc_disabled",
            error_type=error_type_env,
            message="MYT_ENABLE_RPC=0",
        )

    try:
        device_ip, rpa_port = resolve_params(params, context)
    except ValueError as exc:
        return None, result_factory(
            ok=False,
            code="invalid_params",
            error_type=error_type_business,
            message=str(exc),
        )

    try:
        rpc = rpc_factory()
        if rpc is None:
            return None, result_factory(
                ok=False,
                code="rpc_driver_load_failed",
                error_type=error_type_env,
                message="Failed to load RPC native driver",
            )

        connected = rpc.init(device_ip, rpa_port, int(params.get("connect_timeout", 5)))
        if not connected:
            return None, result_factory(
                ok=False,
                code="rpc_connect_failed",
                error_type=error_type_env,
                message=f"connect failed: {device_ip}:{rpa_port}",
            )
        return rpc, None
    except Exception as exc:
        return None, result_factory(
            ok=False,
            code="rpc_unexpected_error",
            error_type=error_type_env,
            message=f"RPC error: {str(exc)}",
        )


def connect_rpc(
    params: Dict[str, Any],
    context: Any,
    *,
    rpc_factory: RpcFactory,
    result_factory: ResultFactory,
    error_type_env: Any,
    error_type_business: Any,
) -> tuple[Any | None, Any | None]:
    return bootstrap_rpc(
        params,
        context,
        is_enabled=is_rpc_enabled,
        resolve_params=resolve_connection_params,
        rpc_factory=rpc_factory,
        result_factory=result_factory,
        error_type_env=error_type_env,
        error_type_business=error_type_business,
    )


def close_rpc(rpc: Any | None) -> None:
    if rpc is not None:
        rpc.close()
