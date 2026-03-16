from __future__ import annotations
from typing import Any, Dict
from engine.actions import _rpc_bootstrap
from engine.models.runtime import ActionResult, ErrorType, ExecutionContext
from hardware_adapters.mytRpc import MytRpc
from engine.action_registry import ActionMetadata

CAPTURE_COMPRESSED_METADATA = ActionMetadata(
    description="捕获压缩后的屏幕截图并动态感知分辨率",
    params_schema={
        "type": "object",
        "properties": {
            "image_type": {"type": "integer", "default": 0, "description": "0 for JPEG, 1 for PNG"},
            "quality": {"type": "integer", "default": 80, "description": "压缩质量 (1-100)"},
            "save_path": {"type": "string", "description": "保存路径"},
            "left": {"type": "integer"},
            "top": {"type": "integer"},
            "right": {"type": "integer"},
            "bottom": {"type": "integer"}
        }
    }
)

def _get_rpc(params: Dict[str, Any], context: ExecutionContext) -> tuple[MytRpc | None, ActionResult | None]:
    return _rpc_bootstrap.bootstrap_rpc(
        params,
        context,
        is_enabled=lambda: _rpc_bootstrap.is_rpc_enabled() if callable(_rpc_bootstrap.is_rpc_enabled) else _rpc_bootstrap.is_rpc_enabled,
        resolve_params=_rpc_bootstrap.resolve_connection_params,
        result_factory=ActionResult,
        error_type_env=ErrorType.ENV_ERROR,
        error_type_business=ErrorType.BUSINESS_ERROR,
    )

def _close_rpc(rpc: MytRpc | None) -> None:
    _rpc_bootstrap.close_rpc(rpc)

def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default

def screenshot(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        method = getattr(rpc, "screentshot", None) if rpc is not None else None
        if method is None:
            return ActionResult(ok=False, code="not_supported", message="screentshot is not available")
        image_type = int(params.get("image_type", 0))
        quality = int(params.get("quality", 80))
        save_path = str(params.get("save_path") or "")
        out = method(image_type, quality, save_path)
        return ActionResult(ok=True, code="ok", data={"result": out})
    finally:
        _close_rpc(rpc)

def capture_raw(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        left = params.get("left")
        top = params.get("top")
        right = params.get("right")
        bottom = params.get("bottom")
        if all(v is not None for v in (left, top, right, bottom)):
            payload = rpc.take_capture_ex(_to_int(left), _to_int(top), _to_int(right), _to_int(bottom)) if rpc is not None else None
        else:
            payload = rpc.take_capture() if rpc is not None else None
        if payload is None:
            return ActionResult(ok=False, code="capture_failed", message="raw capture failed")
        data = payload.get("data") if isinstance(payload, dict) else None
        length = len(data) if data is not None else 0
        return ActionResult(ok=True, code="ok", data={"byte_length": length})
    finally:
        _close_rpc(rpc)

def capture_compressed(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        image_type = _to_int(params.get("image_type", 0))
        quality = _to_int(params.get("quality", 80))
        save_path = str(params.get("save_path") or "").strip()
        payload = rpc.take_capture_compress(image_type, quality) if rpc is not None else None
        if payload is None:
            return ActionResult(ok=False, code="capture_failed", message="compressed capture failed")
        if save_path:
            with open(save_path, "wb") as f: f.write(payload)
        return ActionResult(ok=True, code="ok", data={"byte_length": len(payload), "save_path": save_path or None})
    finally:
        _close_rpc(rpc)

def check_connect_state(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        connected = bool(rpc.check_connect_state()) if rpc is not None else False
        return ActionResult(ok=connected, code="ok" if connected else "not_connected", data={"connected": connected})
    finally:
        _close_rpc(rpc)

def set_work_mode(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        mode = _to_int(params.get("mode", 1), 1)
        ok = rpc.set_rpa_work_mode(mode) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "set_mode_failed", data={"mode": mode})
    finally:
        _close_rpc(rpc)

def use_new_node_mode(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        enabled = bool(params.get("enabled", True))
        ok = rpc.use_new_node_mode(enabled) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "set_mode_failed", data={"enabled": enabled})
    finally:
        _close_rpc(rpc)

def start_video_stream(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        width = _to_int(params.get("width", 400), 400)
        height = _to_int(params.get("height", 720), 720)
        bitrate = _to_int(params.get("bitrate", 20000), 20000)
        ok = rpc.start_video_stream(width, height, bitrate) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "video_stream_start_failed")
    finally:
        _close_rpc(rpc)

def stop_video_stream(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        ok = rpc.stop_video_stream() if rpc is not None else False
        return ActionResult(ok=ok, code="ok")
    finally:
        _close_rpc(rpc)

def get_display_rotate(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        rotate = rpc.get_display_rotate() if rpc is not None else 0
        return ActionResult(ok=True, code="ok", data={"rotate": _to_int(rotate)})
    finally:
        _close_rpc(rpc)

def get_sdk_version(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        version = rpc.get_sdk_version() if rpc is not None else ""
        return ActionResult(ok=True, code="ok", data={"version": str(version)})
    finally:
        _close_rpc(rpc)

def exec_command(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        cmd = str(params.get("command") or "")
        out, ok = rpc.exec_cmd(cmd) if rpc is not None else ("", False)
        return ActionResult(ok=ok, code="ok" if ok else "exec_failed", data={"output": out})
    finally:
        _close_rpc(rpc)
