from __future__ import annotations

import time
from typing import Any

from engine.action_registry import ActionMetadata
from engine.actions import _rpc_bootstrap
from engine.models.runtime import ActionResult, ErrorType, ExecutionContext
from hardware_adapters.mytRpc import MytRpc

APP_OPEN_METADATA = ActionMetadata(
    description="启动安卓应用",
    params_schema={
        "type": "object",
        "properties": {"package": {"type": "string", "description": "应用包名"}},
        "required": ["package"],
    },
    tags=["skill"],
)

APP_STOP_METADATA = ActionMetadata(
    description="强制停止安卓应用",
    params_schema={
        "type": "object",
        "properties": {"package": {"type": "string", "description": "应用包名"}},
        "required": ["package"],
    },
    tags=["skill"],
)

APP_ENSURE_RUNNING_METADATA = ActionMetadata(
    description="确保应用正在运行（如未运行则启动，并可选验证 PID）",
    params_schema={
        "type": "object",
        "properties": {
            "package": {"type": "string", "description": "应用包名"},
            "verify_timeout": {
                "type": "number",
                "default": 0,
                "description": "验证启动成功的超时时间 (秒)",
            },
        },
        "required": ["package"],
    },
)


def _get_rpc(
    params: dict[str, Any], context: ExecutionContext
) -> tuple[MytRpc | None, ActionResult | None]:
    return _rpc_bootstrap.bootstrap_rpc(
        params,
        context,
        is_enabled=lambda: (
            _rpc_bootstrap.is_rpc_enabled()
            if callable(_rpc_bootstrap.is_rpc_enabled)
            else _rpc_bootstrap.is_rpc_enabled
        ),
        resolve_params=_rpc_bootstrap.resolve_connection_params,
        result_factory=ActionResult,
        error_type_env=ErrorType.ENV_ERROR,
        error_type_business=ErrorType.BUSINESS_ERROR,
    )


def _close_rpc(rpc: MytRpc | None) -> None:
    _rpc_bootstrap.close_rpc(rpc)


def _resolve_package(params: dict[str, Any], context: ExecutionContext) -> str:
    return str(
        params.get("package")
        or context.get_session_default("package")
        or context.payload.get("package")
        or ""
    ).strip()


def app_open(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        package = _resolve_package(params, context)
        ok = rpc.openApp(package) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "app_open_failed")
    finally:
        _close_rpc(rpc)


def app_stop(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        package = _resolve_package(params, context)
        ok = rpc.stopApp(package) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "app_stop_failed")
    finally:
        _close_rpc(rpc)


def app_ensure_running(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    package = _resolve_package(params, context)
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        ok_open = bool(rpc.openApp(package)) if rpc is not None else False
        verify_timeout = float(params.get("verify_timeout", 0.0) or 0.0)
        if verify_timeout <= 0:
            return ActionResult(ok=ok_open, code="ok" if ok_open else "app_open_failed")

        deadline = time.time() + max(0.0, verify_timeout)
        while time.time() < deadline:
            context.check_cancelled()
            out, ok = rpc.exec_cmd(f"pidof {package}") if rpc is not None else ("", False)
            if ok and str(out).strip():
                return ActionResult(ok=True, code="ok", data={"pid": str(out).strip()})
            time.sleep(0.05)
        return ActionResult(
            ok=False, code="timeout", message=f"verify_timeout={verify_timeout}s exceeded"
        )
    finally:
        _close_rpc(rpc)


def app_grant_permissions(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    from core.app_config import AppConfigManager
    from engine.actions.android_api_actions import android_grant_app_permissions

    pkg = str(
        params.get("pkg")
        or params.get("package")
        or context.get_session_default("package")
        or context.payload.get("package")
        or ""
    ).strip()
    if not pkg:
        app_id = str(params.get("app_id") or context.payload.get("app_id") or "").strip()
        if app_id:
            config = AppConfigManager.load_app_config(app_id)
            pkg = str(config.get("package_name") or "").strip()
    if not pkg:
        return ActionResult(ok=True, code="ok", message="no package resolved, skipped")
    return android_grant_app_permissions({**params, "pkg": pkg}, context)


def app_dismiss_popups(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        back_presses = int(params.get("back_presses", 2))
        delay_ms = int(params.get("delay_ms", 0))
        for _ in range(max(0, back_presses)):
            context.check_cancelled()
            _ = rpc.keyPress(4) if rpc is not None else False
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)
        return ActionResult(ok=True, code="ok")
    finally:
        _close_rpc(rpc)
