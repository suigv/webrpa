from __future__ import annotations

import time
from typing import Any, Dict

from engine.actions import _rpc_bootstrap
from engine.actions import _ui_selector_support as _selector_support
from engine.models.runtime import ActionResult, ErrorType, ExecutionContext
from hardware_adapters import mytRpc as _myt_rpc_module
from hardware_adapters.mytRpc import MytRpc


def _is_rpc_enabled() -> bool:
    return _rpc_bootstrap.is_rpc_enabled()


def _resolve_connection_params(params: Dict[str, Any], context: ExecutionContext) -> tuple[str, int]:
    return _rpc_bootstrap.resolve_connection_params(params, context)


def _get_rpc(params: Dict[str, Any], context: ExecutionContext) -> tuple[MytRpc | None, ActionResult | None]:
    def _is_enabled_for_factory() -> bool:
        if _is_rpc_enabled():
            return True
        return MytRpc is not _myt_rpc_module.MytRpc

    rpc, err = _rpc_bootstrap.bootstrap_rpc(
        params,
        context,
        is_enabled=_is_enabled_for_factory,
        resolve_params=_resolve_connection_params,
        rpc_factory=MytRpc,
        result_factory=ActionResult,
        error_type_env=ErrorType.ENV_ERROR,
        error_type_business=ErrorType.BUSINESS_ERROR,
    )
    return rpc, err


def _close_rpc(rpc: MytRpc | None) -> None:
    _rpc_bootstrap.close_rpc(rpc)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        finger_id = int(params.get("finger_id", 0))
        helper = context.humanized

        if helper is not None:
            # 1. 坐标随机偏移
            x, y = helper.apply_click_offset(x, y)
            
            # 2. 检查取消 + 点击前停顿
            context.check_cancelled()
            helper.sleep_before_click()
            context.check_cancelled()

        # 3. 按压时长模拟
        hold_time = helper.get_click_hold_time() if helper is not None else 0.01
        
        # 4. 发送拟人化审计事件
        if context.emit_event:
            context.emit_event("humanized.click", {
                "actual": (x, y),
                "hold_ms": int(hold_time * 1000)
            })

        ok_down = rpc.touchDown(finger_id, x, y) if rpc is not None else False
        if ok_down and hold_time > 0:
            time.sleep(hold_time)
            # 持续期间也检查取消
            context.check_cancelled()
            
        ok_up = rpc.touchUp(finger_id, x, y) if rpc is not None else False

        if helper is not None:
            # 5. 点击后停顿
            helper.sleep_after_click()
            context.check_cancelled()

        ok = bool(ok_down and ok_up)
        return ActionResult(ok=ok, code="ok" if ok else "click_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)


def touch_down(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        finger_id = int(params.get("finger_id", 0))
        ok = rpc.touchDown(finger_id, x, y) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "touch_down_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)


def touch_up(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        finger_id = int(params.get("finger_id", 0))
        ok = rpc.touchUp(finger_id, x, y) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "touch_up_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)


def touch_move(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        finger_id = int(params.get("finger_id", 0))
        ok = rpc.touchMove(finger_id, x, y) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "touch_move_failed", data={"x": x, "y": y, "finger_id": finger_id})
    finally:
        _close_rpc(rpc)


def swipe(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        finger_id = int(params.get("finger_id", 0))
        x0 = int(params.get("x0", 0))
        y0 = int(params.get("y0", 0))
        x1 = int(params.get("x1", 0))
        y1 = int(params.get("y1", 0))
        duration = int(params.get("duration", 300))
        raw_result = rpc.swipe(finger_id, x0, y0, x1, y1, duration) if rpc is not None else False
        assumed_ok = False
        if isinstance(raw_result, bool):
            ok = raw_result
            raw_code = int(raw_result)
        else:
            try:
                raw_code = int(raw_result)
            except Exception:
                raw_code = 1 if raw_result else 0
            if raw_code == 0:
                ok = True
                assumed_ok = True
            else:
                ok = raw_code > 0
        return ActionResult(
            ok=bool(ok),
            code="ok" if ok else "swipe_failed",
            data={
                "finger_id": finger_id,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "duration": duration,
                "raw_ret": raw_code,
                "assumed_ok": assumed_ok,
            },
        )
    finally:
        _close_rpc(rpc)


def long_click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        finger_id = int(params.get("finger_id", 0))
        duration = float(params.get("duration", 0.5))
        ok = rpc.longClick(finger_id, x, y, duration) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "long_click_failed")
    finally:
        _close_rpc(rpc)


def input_text(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        text = str(params.get("text") or "")
        if not text:
            return ActionResult(ok=False, code="invalid_params", message="text is required")
        
        helper = context.humanized
        # 如果拟人化未开启，直接发送全文本
        if helper is None or not helper.config.enabled:
            ok = rpc.sendText(text) if rpc is not None else False
            return ActionResult(ok=ok, code="ok" if ok else "send_text_failed")
            
        # 拟人化输入：逐字发送并带上延迟
        sequence = helper.get_typing_sequence(text)
        
        # 发送拟人化审计事件
        if context.emit_event:
            delays = [d for _, d in sequence if d > 0]
            avg_delay = sum(delays)/len(delays) if delays else 0
            context.emit_event("humanized.typing", {
                "text_length": len(text),
                "avg_delay_ms": int(avg_delay * 1000)
            })

        ok = True
        for char, delay in sequence:
            context.check_cancelled() # 每一个字符输入前都检查取消
            if delay > 0:
                time.sleep(delay)
            char_ok = rpc.sendText(char) if rpc is not None else False
            if not char_ok:
                ok = False
                break
                
        return ActionResult(ok=ok, code="ok" if ok else "send_text_failed")
    finally:
        _close_rpc(rpc)


KEY_CODE_MAP = {
    "back": 4,
    "home": 3,
    "enter": 66,
    "recent": 82,
}


def key_press(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        key = str(params.get("key", "")).lower()
        code = KEY_CODE_MAP.get(key)
        if code is None:
            return ActionResult(ok=False, code="invalid_key", message=f"unsupported key: {key}")
        ok = rpc.keyPress(code) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "key_press_failed", data={"key": key, "code": code})
    finally:
        _close_rpc(rpc)


def app_open(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        package = str(params.get("package") or context.get_session_default("package") or "").strip()
        if not package:
            return ActionResult(ok=False, code="invalid_params", message="package is required")
        ok = rpc.openApp(package) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "app_open_failed", data={"package": package})
    finally:
        _close_rpc(rpc)


def app_stop(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        package = str(params.get("package") or context.get_session_default("package") or "").strip()
        if not package:
            return ActionResult(ok=False, code="invalid_params", message="package is required")
        ok = rpc.stopApp(package) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "app_stop_failed", data={"package": package})
    finally:
        _close_rpc(rpc)


def app_ensure_running(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    package = str(params.get("package") or context.get_session_default("package") or "").strip()
    if not package:
        return ActionResult(ok=False, code="invalid_params", message="package is required")

    rpc, err = _get_rpc(params, context)
    if err:
        if err.code == "rpc_disabled":
            return ActionResult(ok=True, code="ok", data={"package": package, "skipped": "rpc_disabled"})
        return err
    try:
        verify_timeout = float(params.get("verify_timeout", 3.0))
        verify_interval = float(params.get("verify_interval", 0.5))
        ok = rpc.openApp(package) if rpc is not None else False
        if not ok:
            return ActionResult(ok=False, code="timeout", message=f"failed to launch app: {package}")

        deadline = time.monotonic() + max(verify_timeout, 0.0)
        while time.monotonic() <= deadline:
            if rpc is None:
                break
            output, cmd_ok = rpc.exec_cmd(f"pidof {package}")
            if cmd_ok and str(output).strip():
                return ActionResult(ok=True, code="ok", data={"package": package, "pid": str(output).strip()})
            time.sleep(max(verify_interval, 0.1))
        return ActionResult(ok=False, code="timeout", message=f"app not running within timeout: {package}")
    finally:
        _close_rpc(rpc)


def app_grant_permissions(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        package = str(params.get("package") or context.get_session_default("package") or "").strip()
        permissions = params.get("permissions")
        if not package:
            return ActionResult(ok=False, code="invalid_params", message="package is required")
        if not isinstance(permissions, list) or not permissions:
            return ActionResult(ok=False, code="invalid_params", message="permissions is required")

        failed: list[str] = []
        for perm in permissions:
            value = str(perm).strip()
            if not value:
                continue
            output, cmd_ok = rpc.exec_cmd(f"pm grant {package} {value}") if rpc is not None else ("", False)
            if not cmd_ok:
                failed.append(value)

        if failed:
            return ActionResult(ok=False, code="grant_failed", message=f"failed permissions: {','.join(failed)}")
        return ActionResult(ok=True, code="ok", data={"package": package, "granted": len(permissions)})
    finally:
        _close_rpc(rpc)


def app_dismiss_popups(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        back_presses = int(params.get("back_presses", 2))
        delay_ms = int(params.get("delay_ms", 200))
        if back_presses < 1:
            return ActionResult(ok=False, code="invalid_params", message="back_presses must be >= 1")

        for _ in range(back_presses):
            ok = rpc.keyPress(4) if rpc is not None else False
            if not ok:
                return ActionResult(ok=False, code="dismiss_failed", message="failed to send back key")
            time.sleep(max(delay_ms, 0) / 1000)
        return ActionResult(ok=True, code="ok", data={"back_presses": back_presses})
    finally:
        _close_rpc(rpc)


def screenshot(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
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
    if err:
        return err
    try:
        left_raw = params.get("left")
        top_raw = params.get("top")
        right_raw = params.get("right")
        bottom_raw = params.get("bottom")
        if left_raw is not None and top_raw is not None and right_raw is not None and bottom_raw is not None:
            left = _to_int(left_raw)
            top = _to_int(top_raw)
            right = _to_int(right_raw)
            bottom = _to_int(bottom_raw)
            payload = rpc.take_capture_ex(left, top, right, bottom) if rpc is not None else None
        else:
            payload = rpc.take_capture() if rpc is not None else None
        if payload is None:
            return ActionResult(ok=False, code="capture_failed", message="raw capture failed")
        payload_dict = payload if isinstance(payload, dict) else {}
        data = payload_dict.get("data")
        length = len(data) if isinstance(data, (bytes, bytearray)) else 0
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "width": _to_int(payload_dict.get("width", 0)),
                "height": _to_int(payload_dict.get("height", 0)),
                "stride": _to_int(payload_dict.get("stride", 0)),
                "byte_length": _to_int(length),
            },
        )
    finally:
        _close_rpc(rpc)


def capture_compressed(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        image_type = _to_int(params.get("image_type", 0))
        quality = _to_int(params.get("quality", 80))
        save_path = str(params.get("save_path") or "").strip()
        left_raw = params.get("left")
        top_raw = params.get("top")
        right_raw = params.get("right")
        bottom_raw = params.get("bottom")

        if left_raw is not None and top_raw is not None and right_raw is not None and bottom_raw is not None:
            left = _to_int(left_raw)
            top = _to_int(top_raw)
            right = _to_int(right_raw)
            bottom = _to_int(bottom_raw)
            payload = (
                rpc.take_capture_compress_ex(left, top, right, bottom, image_type, quality)
                if rpc is not None
                else None
            )
        else:
            payload = rpc.take_capture_compress(image_type, quality) if rpc is not None else None

        if payload is None:
            return ActionResult(ok=False, code="capture_failed", message="compressed capture failed")

        if save_path:
            try:
                with open(save_path, "wb") as file_obj:
                    file_obj.write(payload)
            except Exception as exc:
                return ActionResult(ok=False, code="save_failed", message=str(exc))

        # 从图片字节解析真实屏幕尺寸（用于 VLM 坐标补偿）
        screen_width: int | None = None
        screen_height: int | None = None
        try:
            if len(payload) >= 24 and payload[:8] == b'\x89PNG\r\n\x1a\n':
                screen_width = int.from_bytes(payload[16:20], "big")
                screen_height = int.from_bytes(payload[20:24], "big")
            elif len(payload) >= 4 and payload[:2] == b'\xff\xd8':
                i = 2
                while i < len(payload) - 8:
                    if payload[i] == 0xff and payload[i+1] in (0xc0, 0xc2):
                        screen_height = int.from_bytes(payload[i+5:i+7], "big")
                        screen_width = int.from_bytes(payload[i+7:i+9], "big")
                        break
                    length = int.from_bytes(payload[i+2:i+4], "big")
                    i += 2 + length
        except Exception:
            pass

        return ActionResult(ok=True, code="ok", data={
            "byte_length": len(payload),
            "save_path": save_path or None,
            "screen_width": screen_width,
            "screen_height": screen_height,
        })
    finally:
        _close_rpc(rpc)


def get_display_rotate(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        rotate = rpc.get_display_rotate() if rpc is not None else None
        if rotate is None:
            return ActionResult(ok=False, code="rotate_failed", message="getDisplayRotate failed")
        return ActionResult(ok=True, code="ok", data={"rotate": _to_int(rotate)})
    finally:
        _close_rpc(rpc)


def get_sdk_version(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        version_raw = rpc.get_sdk_version() if rpc is not None else b""
        if isinstance(version_raw, (bytes, bytearray)):
            version = bytes(version_raw).decode("utf-8", errors="ignore")
        else:
            version = str(version_raw or "")
        if not version:
            return ActionResult(ok=False, code="version_failed", message="get_sdk_version returned empty")
        return ActionResult(ok=True, code="ok", data={"version": version})
    finally:
        _close_rpc(rpc)


def check_connect_state(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        connected = bool(rpc.check_connect_state()) if rpc is not None else False
        return ActionResult(ok=connected, code="ok" if connected else "not_connected", data={"connected": connected})
    finally:
        _close_rpc(rpc)


def set_work_mode(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        mode = _to_int(params.get("mode", 1), 1)
        ok = rpc.set_rpa_work_mode(mode) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "set_mode_failed", data={"mode": mode})
    finally:
        _close_rpc(rpc)


def use_new_node_mode(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        enabled = bool(params.get("enabled", True))
        ok = rpc.use_new_node_mode(enabled) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "set_mode_failed", data={"enabled": enabled})
    finally:
        _close_rpc(rpc)


def start_video_stream(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        width = _to_int(params.get("width", 400), 400)
        height = _to_int(params.get("height", 720), 720)
        bitrate = _to_int(params.get("bitrate", 20000), 20000)
        ok = rpc.start_video_stream(width, height, bitrate) if rpc is not None else False
        return ActionResult(
            ok=ok,
            code="ok" if ok else "video_stream_start_failed",
            data={"width": width, "height": height, "bitrate": bitrate},
        )
    finally:
        _close_rpc(rpc)


def stop_video_stream(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        ok = rpc.stop_video_stream() if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "video_stream_stop_failed")
    finally:
        _close_rpc(rpc)


def exec_command(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        command = str(params.get("command") or "")
        if not command:
            return ActionResult(ok=False, code="invalid_params", message="command is required")
        output, ok = rpc.exec_cmd(command) if rpc is not None else ("", False)
        return ActionResult(ok=ok, code="ok" if ok else "exec_failed", data={"output": output})
    finally:
        _close_rpc(rpc)


def dumpNodeXml(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        dump_all = bool(params.get("dump_all", False))
        xml = rpc.dump_node_xml(dump_all) if rpc is not None else None
        if xml is None:
            return ActionResult(ok=False, code="dump_failed", message="dump_node_xml returned no data")
        return ActionResult(ok=True, code="ok", data={"xml": xml})
    finally:
        _close_rpc(rpc)


def dump_node_xml_ex(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        work_mode = bool(params.get("work_mode", False))
        timeout_ms = int(params.get("timeout_ms", 3000))
        xml = rpc.dump_node_xml_ex(work_mode, timeout_ms) if rpc is not None else None
        if xml is None:
            return ActionResult(ok=False, code="dump_failed", message="dump_node_xml_ex returned no data")
        return ActionResult(ok=True, code="ok", data={"xml": xml})
    finally:
        _close_rpc(rpc)


MytSelector = _selector_support.MytSelector
RpcNode = _selector_support.RpcNode


def _selector_from_context(context: ExecutionContext) -> MytSelector | None:
    return _selector_support._selector_from_context(context)


def _resolve_handle_value(raw: Any) -> int | None:
    return _selector_support._resolve_handle_value(raw)


def _resolve_nodes_handle(params: Dict[str, Any], context: ExecutionContext) -> int | None:
    return _selector_support._resolve_nodes_handle(params, context)


def _resolve_node_handle(params: Dict[str, Any], context: ExecutionContext) -> int | None:
    return _selector_support._resolve_node_handle(params, context)


def _tracked_nodes_vars(context: ExecutionContext) -> set[str]:
    return _selector_support._tracked_nodes_vars(context)


def _track_nodes_var(context: ExecutionContext, var_name: str) -> None:
    _selector_support._track_nodes_var(context, var_name)


def _untrack_nodes_var(context: ExecutionContext, var_name: str) -> None:
    _selector_support._untrack_nodes_var(context, var_name)


def _free_nodes_handle(rpc: MytRpc | None, handle: int | None) -> bool:
    return _selector_support._free_nodes_handle(rpc, handle)


def _release_tracked_node_handles(context: ExecutionContext, selector: MytSelector | None) -> bool:
    return _selector_support._release_tracked_node_handles(context, selector)


def _serialize_node(node: Any, rpc: MytRpc | None = None) -> Dict[str, Any]:
    return _selector_support._serialize_node(node, rpc)


def create_selector(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.create_selector(
        params,
        context,
        get_rpc=_get_rpc,
        close_rpc=_close_rpc,
        selector_cls=MytSelector,
    )


def _apply_selector_query(selector: MytSelector, params: Dict[str, Any]) -> tuple[bool, str | None, str | None]:
    return _selector_support._apply_selector_query(selector, params)


def selector_add_query(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_add_query(params, context)


def selector_exec_one(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_exec_one(params, context)


def selector_click_one(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_click_one(
        params,
        context,
        get_rpc=_get_rpc,
        close_rpc=_close_rpc,
        selector_cls=MytSelector,
    )


def selector_click_with_fallback(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector_defs = params.get("selectors")
    if not isinstance(selector_defs, list) or not selector_defs:
        return ActionResult(ok=False, code="invalid_params", message="selectors must be a non-empty list")

    base_params = {
        key: value
        for key, value in params.items()
        if key not in {"selectors", "fallback_command"}
    }
    last_result: ActionResult | None = None

    for index, selector in enumerate(selector_defs):
        if not isinstance(selector, dict):
            return ActionResult(ok=False, code="invalid_params", message="selector entries must be objects")

        merged = dict(base_params)
        merged["type"] = selector.get("type")
        merged["mode"] = selector.get("mode")
        merged["value"] = selector.get("value")
        result = selector_click_one(merged, context)
        last_result = result
        if result.ok:
            data = dict(result.data or {})
            data.update({"selector_index": index, "selector": selector})
            return ActionResult(ok=True, code="ok", data=data)

    fallback_command = params.get("fallback_command")
    if fallback_command:
        fallback_result = exec_command(
            {
                "device_ip": base_params.get("device_ip"),
                "command": fallback_command,
            },
            context,
        )
        if fallback_result.ok:
            data = dict(fallback_result.data or {})
            data.update({"fallback_command": fallback_command})
            return ActionResult(ok=True, code="ok", data=data)
        return fallback_result

    message = "all selector clicks failed"
    if last_result and last_result.message:
        message = f"{message}: {last_result.message}"
    return ActionResult(ok=False, code="selector_click_failed", message=message)


def selector_exec_all(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_exec_all(params, context)


def selector_find_nodes(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_find_nodes(params, context)


def selector_free_nodes(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_free_nodes(params, context)


def selector_get_nodes_size(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_get_nodes_size(params, context)


def selector_get_node_by_index(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_get_node_by_index(params, context)


def node_get_parent(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_parent(params, context)


def node_get_child_count(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_child_count(params, context)


def node_get_child(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_child(params, context)


def node_get_json(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_json(params, context)


def node_get_text(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_text(params, context)


def node_get_desc(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_desc(params, context)


def node_get_package(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_package(params, context)


def node_get_class(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_class(params, context)


def node_get_id(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_id(params, context)


def node_get_bound(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_bound(params, context)


def node_get_bound_center(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_bound_center(params, context)


def node_click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_click(params, context)


def node_long_click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_long_click(params, context)


def release_selector_context(context: ExecutionContext) -> bool:
    return _selector_support.release_selector_context(context, close_rpc=_close_rpc)


def selector_free(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_free(params, context, close_rpc=_close_rpc)


def selector_clear(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_clear(params, context, close_rpc=_close_rpc)
