from __future__ import annotations

import os
from typing import Any, Callable, Dict

from core.port_calc import calculate_ports
from engine.models.runtime import ActionResult, ExecutionContext


RpcFactory = Callable[[], Any]


def is_rpc_enabled() -> bool:
    return os.getenv("MYT_ENABLE_RPC", "1") != "0"


def _normalize_runtime_target(context: ExecutionContext) -> Dict[str, Any]:
    target: Dict[str, Any] = context.target
    return target if isinstance(target, dict) else {}


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


def resolve_connection_params(params: Dict[str, Any], context: ExecutionContext) -> tuple[str, int]:
    payload: Dict[str, Any] = dict(context.payload) if isinstance(context.payload, dict) else {}
    target = _normalize_runtime_target(context)
    session_defaults = context.session_defaults
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
    context: ExecutionContext,
    *,
    is_enabled: Callable[[], bool],
    resolve_params: Callable[[Dict[str, Any], ExecutionContext], tuple[str, int]],
    rpc_factory: RpcFactory,
) -> tuple[Any | None, ActionResult | None]:
    if not is_enabled():
        return None, ActionResult(ok=False, code="rpc_disabled", message="MYT_ENABLE_RPC=0")
    try:
        device_ip, rpa_port = resolve_params(params, context)
    except ValueError as exc:
        return None, ActionResult(ok=False, code="invalid_params", message=str(exc))

    rpc = rpc_factory()
    connected = rpc.init(device_ip, rpa_port, int(params.get("connect_timeout", 5)))
    if not connected:
        return None, ActionResult(ok=False, code="rpc_connect_failed", message=f"connect failed: {device_ip}:{rpa_port}")
    return rpc, None


def connect_rpc(
    params: Dict[str, Any],
    context: ExecutionContext,
    *,
    rpc_factory: RpcFactory,
) -> tuple[Any | None, ActionResult | None]:
    return bootstrap_rpc(
        params,
        context,
        is_enabled=is_rpc_enabled,
        resolve_params=resolve_connection_params,
        rpc_factory=rpc_factory,
    )


def close_rpc(rpc: Any | None) -> None:
    if rpc is not None:
        rpc.close()
