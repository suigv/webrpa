from __future__ import annotations
import time
from typing import Any, Dict
from engine.actions import _rpc_bootstrap
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.mytRpc import MytRpc
from engine.action_registry import ActionMetadata
from core.device_manager import get_device_manager
import re

CLICK_METADATA = ActionMetadata(
    description="点击屏幕坐标 (x, y)",
    params_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X 坐标"},
            "y": {"type": "integer", "description": "Y 坐标"},
            "nx": {"type": "integer", "description": "归一化 X 坐标 (0-1000)"},
            "ny": {"type": "integer", "description": "归一化 Y 坐标 (0-1000)"},
            "finger_id": {"type": "integer", "default": 0, "description": "触控手指索引"}
        }
    },
    tags=["skill"]
)

SWIPE_METADATA = ActionMetadata(
    description="在屏幕上从 (x0, y0) 滑动到 (x1, y1)",
    params_schema={
        "type": "object",
        "properties": {
            "x0": {"type": "integer", "description": "起始 X 坐标"},
            "y0": {"type": "integer", "description": "起始 Y 坐标"},
            "nx0": {"type": "integer", "description": "归一化起始 X 坐标"},
            "ny0": {"type": "integer", "description": "归一化起始 Y 坐标"},
            "x1": {"type": "integer", "description": "结束 X 坐标"},
            "y1": {"type": "integer", "description": "结束 Y 坐标"},
            "nx1": {"type": "integer", "description": "归一化结束 X 坐标"},
            "ny1": {"type": "integer", "description": "归一化结束 Y 坐标"},
            "duration": {"type": "integer", "default": 300, "description": "滑动持续时间 (ms)"},
            "finger_id": {"type": "integer", "default": 0}
        }
    },
    tags=["skill"]
)

LONG_CLICK_METADATA = ActionMetadata(
    description="长按屏幕坐标 (x, y)",
    params_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "X 坐标"},
            "y": {"type": "integer", "description": "Y 坐标"},
            "nx": {"type": "integer", "description": "归一化 X 坐标"},
            "ny": {"type": "integer", "description": "归一化 Y 坐标"},
            "duration": {"type": "number", "default": 0.5, "description": "长按持续时间 (秒)"},
            "finger_id": {"type": "integer", "default": 0}
        }
    }
)

def _get_rpc(params: Dict[str, Any], context: ExecutionContext) -> tuple[MytRpc | None, ActionResult | None]:
    return _rpc_bootstrap.bootstrap_rpc(
        params,
        context,
        is_enabled=_rpc_bootstrap.is_rpc_enabled,
        resolve_params=_rpc_bootstrap.resolve_connection_params,
        rpc_factory=MytRpc,
        result_factory=ActionResult,
    )

def _close_rpc(rpc: MytRpc | None) -> None:
    _rpc_bootstrap.close_rpc(rpc)

def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _resolve_coords(params: Dict[str, Any], context: ExecutionContext, keys: list[str], rpc: MytRpc | None = None) -> Dict[str, int]:
    resolved = {}
    pw = context.physical_width
    ph = context.physical_height
    
    if (pw is None or ph is None):
        device_id = context.device_id
        if device_id > 0:
            if rpc:
                pw, ph = _discover_physical_resolution(rpc, device_id)
            if (pw is None or ph is None):
                res = get_device_manager().get_device_resolution(device_id)
                if res:
                    pw, ph = res
            if pw and ph:
                context.physical_width = pw
                context.physical_height = ph
    
    for k in keys:
        nk = f"n{k}"
        if nk in params and pw and ph:
            val = float(params[nk])
            if k.startswith('x'):
                resolved[k] = int(val * float(pw) / 1000.0)
            else:
                resolved[k] = int(val * float(ph) / 1000.0)
        else:
            resolved[k] = int(params.get(k, 0))
    return resolved

def _discover_physical_resolution(rpc: MytRpc, device_id: int) -> tuple[int, int] | tuple[None, None]:
    try:
        output, ok = rpc.exec_cmd("wm size")
        if not ok or not output:
            return None, None
        override_match = re.search(r"Override size:\s*(\d+)x(\d+)", str(output))
        if override_match:
            w, h = int(override_match.group(1)), int(override_match.group(2))
            get_device_manager().update_device_resolution(device_id, w, h)
            return w, h
        physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", str(output))
        if physical_match:
            w, h = int(physical_match.group(1)), int(physical_match.group(2))
            get_device_manager().update_device_resolution(device_id, w, h)
            return w, h
        return None, None
    except Exception:
        return None, None

def click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        coords = _resolve_coords(params, context, ["x", "y"], rpc=rpc)
        x, y = coords["x"], coords["y"]
        finger_id = int(params.get("finger_id", 0))
        helper = context.humanized
        if helper is not None:
            x, y = helper.apply_click_offset(x, y)
            context.check_cancelled()
            helper.sleep_before_click()
            context.check_cancelled()
        hold_time = helper.get_click_hold_time() if helper is not None else 0.01
        if context.emit_event:
            context.emit_event("humanized.click", {"actual": (x, y), "hold_ms": int(hold_time * 1000)})
        ok_down = rpc.touchDown(finger_id, x, y) if rpc is not None else False
        if ok_down and hold_time > 0:
            time.sleep(hold_time)
            context.check_cancelled()
        ok_up = rpc.touchUp(finger_id, x, y) if rpc is not None else False
        if helper is not None:
            helper.sleep_after_click()
            context.check_cancelled()
        ok = bool(ok_down and ok_up)
        return ActionResult(ok=ok, code="ok" if ok else "click_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)

def touch_down(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        coords = _resolve_coords(params, context, ["x", "y"], rpc=rpc)
        x, y = coords["x"], coords["y"]
        finger_id = int(params.get("finger_id", 0))
        ok = rpc.touchDown(finger_id, x, y) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "touch_down_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)

def touch_up(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        coords = _resolve_coords(params, context, ["x", "y"], rpc=rpc)
        x, y = coords["x"], coords["y"]
        finger_id = int(params.get("finger_id", 0))
        ok = rpc.touchUp(finger_id, x, y) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "touch_up_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)

def touch_move(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        coords = _resolve_coords(params, context, ["x", "y"], rpc=rpc)
        x, y = coords["x"], coords["y"]
        finger_id = int(params.get("finger_id", 0))
        ok = rpc.touchMove(finger_id, x, y) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "touch_move_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)

def swipe(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        finger_id = int(params.get("finger_id", 0))
        coords = _resolve_coords(params, context, ["x0", "y0", "x1", "y1"], rpc=rpc)
        x0, y0, x1, y1 = coords["x0"], coords["y0"], coords["x1"], coords["y1"]
        duration = int(params.get("duration", 300))
        raw_result = rpc.swipe(finger_id, x0, y0, x1, y1, duration) if rpc is not None else False
        ok = bool(raw_result)
        return ActionResult(ok=ok, code="ok" if ok else "swipe_failed", data={"x0": x0, "y0": y0, "x1": x1, "y1": y1, "duration": duration})
    finally:
        _close_rpc(rpc)

def long_click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        coords = _resolve_coords(params, context, ["x", "y"], rpc=rpc)
        x, y = coords["x"], coords["y"]
        finger_id = int(params.get("finger_id", 0))
        duration = float(params.get("duration", 0.5))
        ok = rpc.longClick(finger_id, x, y, duration) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "long_click_failed", data={"x": x, "y": y})
    finally:
        _close_rpc(rpc)
