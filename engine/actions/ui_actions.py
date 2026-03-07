from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict

from core.port_calc import calculate_ports
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.mytRpc import MytRpc


def _is_rpc_enabled() -> bool:
    return os.getenv("MYT_ENABLE_RPC", "1") != "0"


def _resolve_connection_params(params: Dict[str, Any], context: ExecutionContext) -> tuple[str, int]:
    payload: Dict[str, Any] = dict(context.payload) if isinstance(context.payload, dict) else {}
    target_obj = payload.get("_target")
    target: Dict[str, Any] = target_obj if isinstance(target_obj, dict) else {}

    device_ip = str(params.get("device_ip") or payload.get("device_ip") or target.get("device_ip") or "").strip()
    if not device_ip:
        raise ValueError("device_ip is required")

    if "rpa_port" in params:
        return device_ip, int(params["rpa_port"])
    target_rpa_port = target.get("rpa_port")
    if target_rpa_port is not None:
        return device_ip, int(target_rpa_port)

    cloud_index = int(params.get("cloud_index") or payload.get("cloud_index") or target.get("cloud_id") or 1)
    device_index = int(params.get("device_index") or payload.get("device_index") or target.get("device_id") or 1)
    cloud_machines_per_device = int(
        params.get("cloud_machines_per_device") or payload.get("cloud_machines_per_device") or 1
    )
    _, rpa_port = calculate_ports(
        device_index=device_index,
        cloud_index=cloud_index,
        cloud_machines_per_device=cloud_machines_per_device,
    )
    return device_ip, rpa_port


def _get_rpc(params: Dict[str, Any], context: ExecutionContext) -> tuple[MytRpc | None, ActionResult | None]:
    if not _is_rpc_enabled():
        return None, ActionResult(ok=False, code="rpc_disabled", message="MYT_ENABLE_RPC=0")
    try:
        device_ip, rpa_port = _resolve_connection_params(params, context)
    except ValueError as exc:
        return None, ActionResult(ok=False, code="invalid_params", message=str(exc))

    rpc = MytRpc()
    connected = rpc.init(device_ip, rpa_port, int(params.get("connect_timeout", 5)))
    if not connected:
        return None, ActionResult(ok=False, code="rpc_connect_failed", message=f"connect failed: {device_ip}:{rpa_port}")
    return rpc, None


def _close_rpc(rpc: MytRpc | None) -> None:
    if rpc is not None:
        rpc.close()


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
        ok = rpc.touchClick(finger_id, x, y) if rpc is not None else False
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
        ok = rpc.swipe(finger_id, x0, y0, x1, y1, duration) if rpc is not None else False
        return ActionResult(
            ok=bool(ok),
            code="ok" if ok else "swipe_failed",
            data={"finger_id": finger_id, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "duration": duration},
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
        ok = rpc.sendText(text) if rpc is not None else False
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
        package = str(params.get("package") or "")
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
        package = str(params.get("package") or "")
        if not package:
            return ActionResult(ok=False, code="invalid_params", message="package is required")
        ok = rpc.stopApp(package) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "app_stop_failed", data={"package": package})
    finally:
        _close_rpc(rpc)


def app_ensure_running(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        package = str(params.get("package") or "")
        if not package:
            return ActionResult(ok=False, code="invalid_params", message="package is required")

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
        package = str(params.get("package") or "")
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

        return ActionResult(ok=True, code="ok", data={"byte_length": len(payload), "save_path": save_path or None})
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


@dataclass
class MytSelector:
    rpc: MytRpc
    selector: Any = None

    def __post_init__(self) -> None:
        if self.selector is None:
            self.selector = self.rpc.create_selector()

    def _call(self, method_name: str, *args: object) -> bool:
        method = getattr(self.rpc, method_name, None)
        if method is None:
            return False
        try:
            result = method(self.selector, *args)
        except TypeError:
            result = method(*args)
        return bool(result) if isinstance(result, (bool, int)) else result is not None

    def addQuery_Text(self, value: str) -> bool:
        return self._call("addQuery_Text", value)

    def addQuery_TextStartWith(self, value: str) -> bool:
        return self._call("addQuery_TextStartWith", value)

    def addQuery_TextEndWith(self, value: str) -> bool:
        return self._call("addQuery_TextEndWith", value)

    def addQuery_TextMatchWith(self, value: str) -> bool:
        return self._call("addQuery_TextMatchWith", value)

    def addQuery_TextContain(self, value: str) -> bool:
        return self._call("addQuery_TextContain", value)

    def addQuery_TextContainWith(self, value: str) -> bool:
        return self._call("addQuery_TextContainWith", value)

    def addQuery_Clickable(self, clickable: bool = True) -> bool:
        return self._call("addQuery_Clickable", int(clickable))

    def addQuery_Id(self, value: str) -> bool:
        return self._call("addQuery_Id", value)

    def addQuery_IdStartWith(self, value: str) -> bool:
        return self._call("addQuery_IdStartWith", value)

    def addQuery_IdEndWith(self, value: str) -> bool:
        return self._call("addQuery_IdEndWith", value)

    def addQuery_IdContainWith(self, value: str) -> bool:
        return self._call("addQuery_IdContainWith", value)

    def addQuery_IdMatchWith(self, value: str) -> bool:
        return self._call("addQuery_IdMatchWith", value)

    def addQuery_Class(self, value: str) -> bool:
        return self._call("addQuery_Class", value)

    def addQuery_ClassStartWith(self, value: str) -> bool:
        return self._call("addQuery_ClassStartWith", value)

    def addQuery_ClassEndWith(self, value: str) -> bool:
        return self._call("addQuery_ClassEndWith", value)

    def addQuery_ClassContainWith(self, value: str) -> bool:
        return self._call("addQuery_ClassContainWith", value)

    def addQuery_ClassMatchWith(self, value: str) -> bool:
        return self._call("addQuery_ClassMatchWith", value)

    def addQuery_Desc(self, value: str) -> bool:
        return self._call("addQuery_Desc", value)

    def addQuery_DescStartWith(self, value: str) -> bool:
        return self._call("addQuery_DescStartWith", value)

    def addQuery_DescEndWith(self, value: str) -> bool:
        return self._call("addQuery_DescEndWith", value)

    def addQuery_DescContainWith(self, value: str) -> bool:
        return self._call("addQuery_DescContainWith", value)

    def addQuery_DescMatchWith(self, value: str) -> bool:
        return self._call("addQuery_DescMatchWith", value)

    def addQuery_Package(self, value: str) -> bool:
        return self._call("addQuery_Package", value)

    def addQuery_PackageStartWith(self, value: str) -> bool:
        return self._call("addQuery_PackageStartWith", value)

    def addQuery_PackageEndWith(self, value: str) -> bool:
        return self._call("addQuery_PackageEndWith", value)

    def addQuery_PackageContainWith(self, value: str) -> bool:
        return self._call("addQuery_PackageContainWith", value)

    def addQuery_PackageMatchWith(self, value: str) -> bool:
        return self._call("addQuery_PackageMatchWith", value)

    def addQuery_Bounds(self, left: int, top: int, right: int, bottom: int) -> bool:
        return self._call("addQuery_Bounds", left, top, right, bottom)

    def addQuery_BoundsInside(self, left: int, top: int, right: int, bottom: int) -> bool:
        return self._call("addQuery_BoundsInside", left, top, right, bottom)

    def addQuery_Enable(self, enabled: bool) -> bool:
        return self._call("addQuery_Enable", int(enabled))

    def addQuery_Checkable(self, enabled: bool) -> bool:
        return self._call("addQuery_Checkable", int(enabled))

    def addQuery_Focusable(self, enabled: bool) -> bool:
        return self._call("addQuery_Focusable", int(enabled))

    def addQuery_Focused(self, enabled: bool) -> bool:
        return self._call("addQuery_Focused", int(enabled))

    def addQuery_Scrollable(self, enabled: bool) -> bool:
        return self._call("addQuery_Scrollable", int(enabled))

    def addQuery_LongClickable(self, enabled: bool) -> bool:
        return self._call("addQuery_LongClickable", int(enabled))

    def addQuery_Password(self, enabled: bool) -> bool:
        return self._call("addQuery_Password", int(enabled))

    def addQuery_Selected(self, enabled: bool) -> bool:
        return self._call("addQuery_Selected", int(enabled))

    def addQuery_Visible(self, enabled: bool) -> bool:
        return self._call("addQuery_Visible", int(enabled))

    def addQuery_Index(self, index: int) -> bool:
        return self._call("addQuery_Index", index)

    def execQueryOne(self) -> ActionResult:
        method = getattr(self.rpc, "execQueryOne", None)
        if method is None:
            return ActionResult(ok=False, code="not_supported", message="execQueryOne not available")
        try:
            node = method(self.selector)
        except TypeError:
            node = method()
        return ActionResult(ok=node is not None, code="ok" if node is not None else "query_empty", data={"node": node})

    def execQueryAll(self) -> ActionResult:
        method = getattr(self.rpc, "execQueryAll", None)
        if method is None:
            return ActionResult(ok=False, code="not_supported", message="execQueryAll not available")
        try:
            nodes = method(self.selector)
        except TypeError:
            nodes = method()
        if nodes is None:
            return ActionResult(ok=False, code="query_empty", data={"nodes": []})
        if isinstance(nodes, list):
            return ActionResult(ok=True, code="ok", data={"nodes": nodes})
        return ActionResult(ok=True, code="ok", data={"nodes": [nodes]})

    def clear_selector(self) -> bool:
        return self._call("clear_selector")

    def free_selector(self) -> bool:
        return self._call("free_selector")


@dataclass
class RpcNode:
    node: Any
    rpc: MytRpc | None = None

    def _is_handle(self) -> bool:
        return isinstance(self.node, int)

    def _method(self, name: str, default: Any = None) -> Any:
        attr = getattr(self.node, name, None)
        if callable(attr):
            try:
                return attr()
            except Exception:
                return default
        if attr is not None:
            return attr
        return default

    def get_node_text(self) -> str:
        if self._is_handle() and self.rpc is not None:
            value = self.rpc.get_node_text(int(self.node))
            return str(value or "")
        return str(self._method("get_node_text", self._method("text", "")))

    def get_node_id(self) -> str:
        if self._is_handle() and self.rpc is not None:
            value = self.rpc.get_node_id(int(self.node))
            return str(value or "")
        return str(self._method("get_node_id", self._method("id", "")))

    def get_node_class(self) -> str:
        if self._is_handle() and self.rpc is not None:
            value = self.rpc.get_node_class(int(self.node))
            return str(value or "")
        return str(self._method("get_node_class", self._method("class_name", "")))

    def get_node_package(self) -> str:
        if self._is_handle() and self.rpc is not None:
            value = self.rpc.get_node_package(int(self.node))
            return str(value or "")
        return str(self._method("get_node_package", self._method("package", "")))

    def get_node_desc(self) -> str:
        if self._is_handle() and self.rpc is not None:
            value = self.rpc.get_node_desc(int(self.node))
            return str(value or "")
        return str(self._method("get_node_desc", self._method("desc", "")))

    def get_node_bound(self) -> Dict[str, int]:
        if self._is_handle() and self.rpc is not None:
            bound = self.rpc.get_node_bound(int(self.node))
            if isinstance(bound, dict):
                return {
                    "left": int(bound.get("left", 0)),
                    "top": int(bound.get("top", 0)),
                    "right": int(bound.get("right", 0)),
                    "bottom": int(bound.get("bottom", 0)),
                }
        bound = self._method("get_node_bound", self._method("bound", {"left": 0, "top": 0, "right": 0, "bottom": 0}))
        return dict(bound)

    def get_node_bound_center(self) -> Dict[str, int]:
        bound = self.get_node_bound()
        return {"x": int((bound.get("left", 0) + bound.get("right", 0)) / 2), "y": int((bound.get("top", 0) + bound.get("bottom", 0)) / 2)}

    def get_node_parent(self) -> Any:
        if self._is_handle() and self.rpc is not None:
            return self.rpc.get_node_parent(int(self.node))
        return self._method("get_node_parent")

    def get_node_child(self, index: int) -> Any:
        if self._is_handle() and self.rpc is not None:
            return self.rpc.get_node_child(int(self.node), int(index))
        method = getattr(self.node, "get_node_child", None)
        if callable(method):
            try:
                return method(index)
            except Exception:
                return None
        children = self._method("children", [])
        if isinstance(children, list) and 0 <= index < len(children):
            return children[index]
        return None

    def get_node_child_count(self) -> int:
        if self._is_handle() and self.rpc is not None:
            return int(self.rpc.get_node_child_count(int(self.node)))
        value = self._method("get_node_child_count", None)
        if value is not None:
            return int(value)
        children = self._method("children", [])
        return len(children) if isinstance(children, list) else 0

    def click_events(self) -> bool:
        if self._is_handle() and self.rpc is not None:
            return bool(self.rpc.click_node(int(self.node)))
        method = getattr(self.node, "Click_events", None)
        if callable(method):
            try:
                return bool(method())
            except Exception:
                return False
        method = getattr(self.node, "click", None)
        if callable(method):
            try:
                method()
                return True
            except Exception:
                return False
        return False

    def long_click_events(self) -> bool:
        if self._is_handle() and self.rpc is not None:
            return bool(self.rpc.long_click_node(int(self.node)))
        method = getattr(self.node, "longClick_events", None)
        if callable(method):
            try:
                return bool(method())
            except Exception:
                return False
        return False

    def get_node_json(self) -> str:
        if self._is_handle() and self.rpc is not None:
            value = self.rpc.get_node_json(int(self.node))
            return str(value or "")
        value = self._method("get_node_json", self._method("getNodeJson", ""))
        return str(value)


def _selector_from_context(context: ExecutionContext) -> MytSelector | None:
    value = context.vars.get("selector")
    if isinstance(value, MytSelector):
        return value
    return None


def _resolve_handle_value(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        value = int(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _resolve_nodes_handle(params: Dict[str, Any], context: ExecutionContext) -> int | None:
    direct = _resolve_handle_value(params.get("nodes_handle"))
    if direct is not None:
        return direct
    var_name = str(params.get("nodes_var") or "nodes_handle").strip()
    if not var_name:
        return None
    return _resolve_handle_value(context.vars.get(var_name))


def _resolve_node_handle(params: Dict[str, Any], context: ExecutionContext) -> int | None:
    direct = _resolve_handle_value(params.get("node_handle"))
    if direct is not None:
        return direct
    var_name = str(params.get("node_var") or "node_handle").strip()
    if not var_name:
        return None
    return _resolve_handle_value(context.vars.get(var_name))


def _serialize_node(node: Any, rpc: MytRpc | None = None) -> Dict[str, Any]:
    wrapped = RpcNode(node, rpc=rpc)
    return {
        "text": wrapped.get_node_text(),
        "id": wrapped.get_node_id(),
        "class_name": wrapped.get_node_class(),
        "package": wrapped.get_node_package(),
        "desc": wrapped.get_node_desc(),
        "bound": wrapped.get_node_bound(),
    }


def create_selector(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    previous = context.vars.get("selector")
    if isinstance(previous, MytSelector):
        _ = previous.clear_selector()
        _close_rpc(previous.rpc)
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    if rpc is None:
        return ActionResult(ok=False, code="rpc_unavailable", message="rpc unavailable")
    assert rpc is not None
    try:
        method = getattr(rpc, "create_selector", None)
        if method is None:
            return ActionResult(ok=False, code="not_supported", message="create_selector not available")
        selector_handle = method()
        selector = MytSelector(rpc=rpc, selector=selector_handle)
        context.vars["selector"] = selector
        return ActionResult(ok=selector.selector is not None, code="ok" if selector.selector is not None else "selector_failed")
    except Exception as exc:
        _close_rpc(rpc)
        return ActionResult(ok=False, code="selector_failed", message=str(exc))


def _apply_selector_query(selector: MytSelector, params: Dict[str, Any]) -> tuple[bool, str | None, str | None]:
    query_type = str(params.get("type") or "").strip().lower()
    mode = str(params.get("mode") or "equal").strip().lower()
    value = str(params.get("value") or "")

    text_handlers = {
        "equal": selector.addQuery_Text,
        "contains": selector.addQuery_TextContain,
        "start_with": selector.addQuery_TextStartWith,
        "end_with": selector.addQuery_TextEndWith,
        "match": selector.addQuery_TextMatchWith,
    }
    id_handlers = {
        "equal": selector.addQuery_Id,
        "contains": selector.addQuery_IdContainWith,
        "start_with": selector.addQuery_IdStartWith,
        "end_with": selector.addQuery_IdEndWith,
        "match": selector.addQuery_IdMatchWith,
    }
    class_handlers = {
        "equal": selector.addQuery_Class,
        "contains": selector.addQuery_ClassContainWith,
        "start_with": selector.addQuery_ClassStartWith,
        "end_with": selector.addQuery_ClassEndWith,
        "match": selector.addQuery_ClassMatchWith,
    }
    desc_handlers = {
        "equal": selector.addQuery_Desc,
        "contains": selector.addQuery_DescContainWith,
        "start_with": selector.addQuery_DescStartWith,
        "end_with": selector.addQuery_DescEndWith,
        "match": selector.addQuery_DescMatchWith,
    }
    package_handlers = {
        "equal": selector.addQuery_Package,
        "contains": selector.addQuery_PackageContainWith,
        "start_with": selector.addQuery_PackageStartWith,
        "end_with": selector.addQuery_PackageEndWith,
        "match": selector.addQuery_PackageMatchWith,
    }

    if query_type == "text_contains":
        ok = selector.addQuery_TextContain(value)
    elif query_type == "text":
        handler = text_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported text mode: {mode}"
        ok = handler(value)
    elif query_type == "id":
        handler = id_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported id mode: {mode}"
        ok = handler(value)
    elif query_type == "class":
        handler = class_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported class mode: {mode}"
        ok = handler(value)
    elif query_type == "desc":
        handler = desc_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported desc mode: {mode}"
        ok = handler(value)
    elif query_type == "package":
        handler = package_handlers.get(mode)
        if handler is None:
            return False, "invalid_query_mode", f"unsupported package mode: {mode}"
        ok = handler(value)
    elif query_type == "bounds":
        left = _to_int(params.get("left"))
        top = _to_int(params.get("top"))
        right = _to_int(params.get("right"))
        bottom = _to_int(params.get("bottom"))
        ok = selector.addQuery_Bounds(left, top, right, bottom)
    elif query_type == "bounds_inside":
        left = _to_int(params.get("left"))
        top = _to_int(params.get("top"))
        right = _to_int(params.get("right"))
        bottom = _to_int(params.get("bottom"))
        ok = selector.addQuery_BoundsInside(left, top, right, bottom)
    elif query_type == "clickable":
        ok = selector.addQuery_Clickable(bool(params.get("enabled", True)))
    elif query_type == "enabled":
        ok = selector.addQuery_Enable(bool(params.get("enabled", True)))
    elif query_type == "checkable":
        ok = selector.addQuery_Checkable(bool(params.get("enabled", True)))
    elif query_type == "focusable":
        ok = selector.addQuery_Focusable(bool(params.get("enabled", True)))
    elif query_type == "focused":
        ok = selector.addQuery_Focused(bool(params.get("enabled", True)))
    elif query_type == "scrollable":
        ok = selector.addQuery_Scrollable(bool(params.get("enabled", True)))
    elif query_type == "long_clickable":
        ok = selector.addQuery_LongClickable(bool(params.get("enabled", True)))
    elif query_type == "password":
        ok = selector.addQuery_Password(bool(params.get("enabled", True)))
    elif query_type == "selected":
        ok = selector.addQuery_Selected(bool(params.get("enabled", True)))
    elif query_type == "visible":
        ok = selector.addQuery_Visible(bool(params.get("enabled", True)))
    elif query_type == "index":
        ok = selector.addQuery_Index(_to_int(params.get("index"), 0))
    else:
        return False, "invalid_query_type", f"unsupported selector query type: {query_type}"

    if not ok:
        return False, "query_add_failed", "failed to add selector query"
    return True, None, None


def selector_add_query(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")

    ok, error_code, error_message = _apply_selector_query(selector, params)
    if not ok:
        return ActionResult(ok=False, code=str(error_code), message=str(error_message))
    query_type = str(params.get("type") or "").strip().lower()
    mode = str(params.get("mode") or "equal").strip().lower()
    value = str(params.get("value") or "")
    return ActionResult(ok=True, code="ok", data={"type": query_type, "mode": mode, "value": value})


def selector_exec_one(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    result = selector.execQueryOne()
    node = result.data.get("node") if isinstance(result.data, dict) else None
    if not result.ok or node is None:
        return ActionResult(ok=False, code="not_found", message="selector query returned no node")
    return ActionResult(ok=True, code="ok", data={"node": _serialize_node(node, selector.rpc)})


def selector_click_one(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    if rpc is None:
        return ActionResult(ok=False, code="rpc_unavailable", message="rpc unavailable")
    try:
        selector = MytSelector(rpc=rpc)
        query_type = str(params.get("type") or "").strip().lower()
        if not query_type:
            return ActionResult(ok=False, code="invalid_params", message="type is required")

        ok, error_code, error_message = _apply_selector_query(selector, params)
        if not ok:
            return ActionResult(ok=False, code=str(error_code), message=str(error_message))

        result = selector.execQueryOne()
        node = result.data.get("node") if isinstance(result.data, dict) else None
        if node is None:
            return ActionResult(ok=False, code="not_found", message="selector query returned no node")

        clicked = RpcNode(node, rpc=rpc).click_events()
        if not clicked:
            return ActionResult(ok=False, code="click_failed", message="node click failed")
        return ActionResult(ok=True, code="ok")
    finally:
        _close_rpc(rpc)


def selector_exec_all(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    result = selector.execQueryAll()
    nodes = result.data.get("nodes") if isinstance(result.data, dict) else None
    if not result.ok or not nodes:
        return ActionResult(ok=False, code="not_found", message="selector query returned no nodes")
    serialized = [_serialize_node(node, selector.rpc) for node in nodes]
    return ActionResult(ok=True, code="ok", data={"nodes": serialized, "count": len(serialized)})


def selector_find_nodes(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    max_count = _to_int(params.get("max_count", 20), 20)
    timeout_ms = _to_int(params.get("timeout_ms", 2000), 2000)
    handle = selector.rpc.find_nodes(selector.selector, max_count, timeout_ms)
    if handle is None:
        return ActionResult(ok=False, code="find_nodes_failed", message="find_nodes returned no handle")

    save_as = str(params.get("save_as") or "nodes_handle").strip()
    if save_as:
        context.vars[save_as] = int(handle)
    count = int(selector.rpc.get_nodes_size(int(handle)))
    return ActionResult(ok=True, code="ok", data={"nodes_handle": int(handle), "count": count, "saved_as": save_as or None})


def selector_free_nodes(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    handle = _resolve_nodes_handle(params, context)
    if handle is None:
        return ActionResult(ok=False, code="invalid_params", message="nodes_handle or nodes_var is required")
    ok = selector.rpc.free_nodes(handle)
    nodes_var = str(params.get("nodes_var") or "nodes_handle").strip()
    if ok and nodes_var and _resolve_handle_value(context.vars.get(nodes_var)) == handle:
        context.vars.pop(nodes_var, None)
    return ActionResult(ok=ok, code="ok" if ok else "free_nodes_failed", data={"nodes_handle": handle})


def selector_get_nodes_size(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    handle = _resolve_nodes_handle(params, context)
    if handle is None:
        return ActionResult(ok=False, code="invalid_params", message="nodes_handle or nodes_var is required")
    count = int(selector.rpc.get_nodes_size(handle))
    return ActionResult(ok=True, code="ok", data={"nodes_handle": handle, "count": count})


def selector_get_node_by_index(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    handle = _resolve_nodes_handle(params, context)
    if handle is None:
        return ActionResult(ok=False, code="invalid_params", message="nodes_handle or nodes_var is required")
    index = _to_int(params.get("index"), -1)
    if index < 0:
        return ActionResult(ok=False, code="invalid_params", message="index must be >= 0")

    node = selector.rpc.get_node_by_index(handle, index)
    node_handle = _resolve_handle_value(node)
    if node_handle is None:
        return ActionResult(ok=False, code="not_found", message="node not found at index")

    save_as = str(params.get("save_as") or "node_handle").strip()
    if save_as:
        context.vars[save_as] = node_handle
    return ActionResult(
        ok=True,
        code="ok",
        data={
            "nodes_handle": handle,
            "index": index,
            "node_handle": node_handle,
            "node": _serialize_node(node_handle, selector.rpc),
            "saved_as": save_as or None,
        },
    )


def node_get_parent(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    parent = selector.rpc.get_node_parent(node_handle)
    parent_handle = _resolve_handle_value(parent)
    if parent_handle is None:
        return ActionResult(ok=False, code="not_found", message="parent node not found")
    save_as = str(params.get("save_as") or "node_parent_handle").strip()
    if save_as:
        context.vars[save_as] = parent_handle
    return ActionResult(
        ok=True,
        code="ok",
        data={"node_handle": node_handle, "parent_handle": parent_handle, "saved_as": save_as or None, "node": _serialize_node(parent_handle, selector.rpc)},
    )


def node_get_child_count(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    count = int(selector.rpc.get_node_child_count(node_handle))
    return ActionResult(ok=True, code="ok", data={"node_handle": node_handle, "count": count})


def node_get_child(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    index = _to_int(params.get("index"), -1)
    if index < 0:
        return ActionResult(ok=False, code="invalid_params", message="index must be >= 0")
    child = selector.rpc.get_node_child(node_handle, index)
    child_handle = _resolve_handle_value(child)
    if child_handle is None:
        return ActionResult(ok=False, code="not_found", message="child node not found")
    save_as = str(params.get("save_as") or "node_child_handle").strip()
    if save_as:
        context.vars[save_as] = child_handle
    return ActionResult(
        ok=True,
        code="ok",
        data={"node_handle": node_handle, "index": index, "child_handle": child_handle, "saved_as": save_as or None, "node": _serialize_node(child_handle, selector.rpc)},
    )


def node_get_json(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_json(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "json": value or ""})


def node_get_text(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_text(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "text": value or ""})


def node_get_desc(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_desc(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "desc": value or ""})


def node_get_package(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_package(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "package": value or ""})


def node_get_class(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_class(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "class_name": value or ""})


def node_get_id(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_id(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "id": value or ""})


def node_get_bound(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_bound(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "bound": value or {}})


def node_get_bound_center(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = selector.rpc.get_node_bound_center(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, "center": value or {}})


def node_click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    ok = bool(selector.rpc.click_node(node_handle))
    return ActionResult(ok=ok, code="ok" if ok else "click_failed", data={"node_handle": node_handle})


def node_long_click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    ok = bool(selector.rpc.long_click_node(node_handle))
    return ActionResult(ok=ok, code="ok" if ok else "long_click_failed", data={"node_handle": node_handle})


def selector_free(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    ok = selector.free_selector()
    _close_rpc(selector.rpc)
    context.vars.pop("selector", None)
    return ActionResult(ok=ok, code="ok" if ok else "selector_free_failed")


def selector_clear(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    ok = selector.clear_selector()
    _close_rpc(selector.rpc)
    context.vars.pop("selector", None)
    return ActionResult(ok=ok, code="ok" if ok else "selector_clear_failed")
