from __future__ import annotations

import os
from typing import Any, Callable, Dict

from core.port_calc import calculate_ports
from engine.models.runtime import ActionResult, ExecutionContext


RpcFactory = Callable[[], Any]


def is_rpc_enabled() -> bool:
    return os.getenv("MYT_ENABLE_RPC", "1") != "0"


def resolve_connection_params(params: Dict[str, Any], context: ExecutionContext) -> tuple[str, int]:
    payload: Dict[str, Any] = dict(context.payload) if isinstance(context.payload, dict) else {}
    target: Dict[str, Any] = context.target
    session_defaults = context.session_defaults

    device_ip = str(
        params.get("device_ip")
        or session_defaults.get("device_ip")
        or payload.get("device_ip")
        or target.get("device_ip")
        or ""
    ).strip()
    if not device_ip:
        raise ValueError("device_ip is required")

    if "rpa_port" in params:
        return device_ip, int(params["rpa_port"])
    session_rpa_port = session_defaults.get("rpa_port")
    if session_rpa_port is not None:
        return device_ip, int(session_rpa_port)
    target_rpa_port = target.get("rpa_port")
    if target_rpa_port is not None:
        return device_ip, int(target_rpa_port)

    cloud_index = int(params.get("cloud_index") or session_defaults.get("cloud_index") or payload.get("cloud_index") or target.get("cloud_id") or 1)
    device_index = int(params.get("device_index") or session_defaults.get("device_index") or payload.get("device_index") or target.get("device_id") or 1)
    cloud_machines_per_device = int(
        params.get("cloud_machines_per_device")
        or session_defaults.get("cloud_machines_per_device")
        or payload.get("cloud_machines_per_device")
        or 1
    )
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
