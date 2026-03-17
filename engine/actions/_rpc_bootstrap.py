from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

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


class DummyRpc:
    """Dummy class for type checking or test safety."""

    pass


def is_mock(cls: type) -> bool:
    """Checks if the given class is likely a mock or test double."""
    if not cls or not hasattr(cls, "__name__"):
        return False
    if cls.__name__ == "DummyRpc":
        return False
    # Avoid circular import to get the real MytRpc for module comparison
    try:
        from hardware_adapters.mytRpc import MytRpc as RealMytRpc

        return cls.__module__ != RealMytRpc.__module__
    except ImportError:
        return True


def _normalize_runtime_target(context: Any) -> dict[str, Any]:
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
    params: dict[str, Any],
    session_defaults: dict[str, Any],
    target: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    if any(
        key in params
        for key in (
            "device_ip",
            "rpa_port",
            "cloud_index",
            "device_index",
            "cloud_machines_per_device",
        )
    ):
        return params
    if any(
        key in session_defaults
        for key in (
            "device_ip",
            "rpa_port",
            "cloud_index",
            "device_index",
            "cloud_machines_per_device",
        )
    ):
        return session_defaults
    if target:
        return target
    return payload


def resolve_connection_params(params: dict[str, Any], context: Any) -> tuple[str, int]:
    payload: dict[str, Any] = dict(getattr(context, "payload", {}) or {})
    target = _normalize_runtime_target(context)
    if target and payload and "device_ip" not in target and payload.get("device_ip"):
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


def get_rpc_class() -> Any:
    """Dynamically resolve MytRpc class, prioritizing ui_actions re-export for tests."""
    try:
        # Avoid circular import at top level
        import engine.actions.ui_actions as ua

        return ua.MytRpc
    except (ImportError, AttributeError):
        from hardware_adapters.mytRpc import MytRpc

        return MytRpc


def bootstrap_rpc(
    params: dict[str, Any],
    context: Any,
    *,
    is_enabled: Callable[[], bool],
    resolve_params: Callable[[dict[str, Any], Any], tuple[str, int]],
    rpc_factory: RpcFactory | None = None,
    result_factory: ResultFactory,
    error_type_env: Any,
    error_type_business: Any,
) -> tuple[Any | None, Any | None]:
    # Resolve the RPC class to use
    cls = rpc_factory if rpc_factory is not None else get_rpc_class()

    if not is_enabled():
        # Allow if we have an explicit factory or if it's not the dummy one.
        # For tests, we want to be very permissive if any mock is present.
        can_proceed = cls is not None and is_mock(cls)

        if not can_proceed:
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
        if cls is None:
            return None, result_factory(
                ok=False,
                code="rpc_driver_load_failed",
                error_type=error_type_env,
                message="Failed to load RPC native driver",
            )

        rpc = cls()
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
    params: dict[str, Any],
    context: Any,
    *,
    rpc_factory: RpcFactory | None = None,
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
