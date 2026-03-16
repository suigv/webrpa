from __future__ import annotations
import time
import re
from typing import Any, Dict

from engine.actions import _rpc_bootstrap
from engine.actions import _ui_selector_support as _selector_support
from engine.models.runtime import ActionResult, ErrorType, ExecutionContext
from hardware_adapters import mytRpc as _myt_rpc_module
from hardware_adapters.mytRpc import MytRpc
from engine.action_registry import ActionMetadata
from core.device_manager import get_device_manager

# Import from new specialized modules
from .ui_touch_actions import (
    click, touch_down, touch_move, touch_up, swipe, long_click,
    CLICK_METADATA, SWIPE_METADATA, LONG_CLICK_METADATA
)
from .ui_input_actions import (
    input_text, key_press,
    INPUT_TEXT_METADATA, KEY_PRESS_METADATA
)
from .ui_selector_actions import (
    create_selector, selector_add_query, selector_click_one, selector_exec_one,
    selector_find_nodes, selector_free, node_get_text, dump_node_xml_ex
)

# Keep remaining actions that didn't fit elsewhere or are glue
from .ui_touch_actions import _discover_physical_resolution, _get_rpc, _close_rpc, _to_int, _resolve_coords

CAPTURE_COMPRESSED_METADATA = ActionMetadata(
    description="Capture compressed screenshot (JPEG/PNG) and discover physical resolution",
    params_schema={
        "type": "object",
        "properties": {
            "image_type": {"type": "integer", "default": 0, "description": "0 for JPEG, 1 for PNG"},
            "quality": {"type": "integer", "default": 80, "description": "Compression quality (1-100)"},
            "save_path": {"type": "string", "description": "Optional local path to save the image"},
            "left": {"type": "integer", "description": "Optional crop left"},
            "top": {"type": "integer", "description": "Optional crop top"},
            "right": {"type": "integer", "description": "Optional crop right"},
            "bottom": {"type": "integer", "description": "Optional crop bottom"}
        }
    }
)

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
        left_raw = params.get("left")
        top_raw = params.get("top")
        right_raw = params.get("right")
        bottom_raw = params.get("bottom")
        if left_raw is not None and top_raw is not None and right_raw is not None and bottom_raw is not None:
            payload = rpc.take_capture_ex(_to_int(left_raw), _to_int(top_raw), _to_int(right_raw), _to_int(bottom_raw)) if rpc is not None else None
        else:
            payload = rpc.take_capture() if rpc is not None else None
        if payload is None:
            return ActionResult(ok=False, code="capture_failed", message="raw capture failed")
        payload_dict = payload if isinstance(payload, dict) else {}
        data = payload_dict.get("data")
        length = len(data) if isinstance(data, (bytes, bytearray)) else 0
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

APP_OPEN_METADATA = ActionMetadata(description="Start an Android application", params_schema={"type": "object", "properties": {"package": {"type": "string"}}, "required": ["package"]})
APP_STOP_METADATA = ActionMetadata(description="Force stop an Android application", params_schema={"type": "object", "properties": {"package": {"type": "string"}}, "required": ["package"]})
APP_ENSURE_RUNNING_METADATA = ActionMetadata(description="Ensure an application is running", params_schema={"type": "object", "properties": {"package": {"type": "string"}}, "required": ["package"]})

def app_open(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        package = str(params.get("package") or "")
        ok = rpc.openApp(package) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "app_open_failed")
    finally:
        _close_rpc(rpc)

def app_stop(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        package = str(params.get("package") or "")
        ok = rpc.stopApp(package) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "app_stop_failed")
    finally:
        _close_rpc(rpc)

def app_ensure_running(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    package = str(params.get("package") or "")
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        rpc.openApp(package)
        return ActionResult(ok=True, code="ok")
    finally:
        _close_rpc(rpc)

def app_grant_permissions(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ActionResult(ok=True, code="ok") # Simplified for now

def app_dismiss_popups(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        for _ in range(2): rpc.keyPress(4)
        return ActionResult(ok=True, code="ok")
    finally:
        _close_rpc(rpc)
