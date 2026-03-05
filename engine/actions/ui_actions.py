from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict

from ...core.port_calc import calculate_ports
from ..models.runtime import ActionResult, ExecutionContext
from ...hardware_adapters.mytRpc import MytRpc


def _is_rpc_enabled() -> bool:
    return os.getenv("MYT_ENABLE_RPC", "1") != "0"


def _resolve_connection_params(params: Dict[str, Any], context: ExecutionContext) -> tuple[str, int]:
    payload = context.payload if isinstance(context.payload, dict) else {}
    device_ip = str(params.get("device_ip") or payload.get("device_ip") or "").strip()
    if not device_ip:
        raise ValueError("device_ip is required")

    if "rpa_port" in params:
        return device_ip, int(params["rpa_port"])

    cloud_index = int(params.get("cloud_index") or payload.get("cloud_index") or 1)
    cloud_machines_per_device = int(
        params.get("cloud_machines_per_device") or payload.get("cloud_machines_per_device") or 1
    )
    _, rpa_port = calculate_ports(
        device_index=1,
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
        out = method()
        return ActionResult(ok=True, code="ok", data={"result": out})
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

    def addQuery_TextContain(self, value: str) -> bool:
        return self._call("addQuery_TextContain", value)

    def addQuery_TextContainWith(self, value: str) -> bool:
        return self._call("addQuery_TextContainWith", value)

    def addQuery_Clickable(self, clickable: bool = True) -> bool:
        return self._call("addQuery_Clickable", int(clickable))

    def addQuery_Id(self, value: str) -> bool:
        return self._call("addQuery_Id", value)

    def addQuery_Class(self, value: str) -> bool:
        return self._call("addQuery_Class", value)

    def addQuery_Desc(self, value: str) -> bool:
        return self._call("addQuery_Desc", value)

    def addQuery_Package(self, value: str) -> bool:
        return self._call("addQuery_Package", value)

    def addQuery_Bounds(self, left: int, top: int, right: int, bottom: int) -> bool:
        return self._call("addQuery_Bounds", left, top, right, bottom)

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


@dataclass
class RpcNode:
    node: Any

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
        return str(self._method("get_node_text", self._method("text", "")))

    def get_node_id(self) -> str:
        return str(self._method("get_node_id", self._method("id", "")))

    def get_node_class(self) -> str:
        return str(self._method("get_node_class", self._method("class_name", "")))

    def get_node_package(self) -> str:
        return str(self._method("get_node_package", self._method("package", "")))

    def get_node_desc(self) -> str:
        return str(self._method("get_node_desc", self._method("desc", "")))

    def get_node_bound(self) -> Dict[str, int]:
        bound = self._method("get_node_bound", self._method("bound", {"left": 0, "top": 0, "right": 0, "bottom": 0}))
        return dict(bound)

    def get_node_bound_center(self) -> Dict[str, int]:
        bound = self.get_node_bound()
        return {"x": int((bound.get("left", 0) + bound.get("right", 0)) / 2), "y": int((bound.get("top", 0) + bound.get("bottom", 0)) / 2)}

    def get_node_parent(self) -> Any:
        return self._method("get_node_parent")

    def get_node_child(self, index: int) -> Any:
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
        value = self._method("get_node_child_count", None)
        if value is not None:
            return int(value)
        children = self._method("children", [])
        return len(children) if isinstance(children, list) else 0

    def click_events(self) -> bool:
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
        method = getattr(self.node, "longClick_events", None)
        if callable(method):
            try:
                return bool(method())
            except Exception:
                return False
        return False

    def get_node_json(self) -> str:
        value = self._method("get_node_json", self._method("getNodeJson", ""))
        return str(value)


def _selector_from_context(context: ExecutionContext) -> MytSelector | None:
    value = context.vars.get("selector")
    if isinstance(value, MytSelector):
        return value
    return None


def _serialize_node(node: Any) -> Dict[str, Any]:
    wrapped = RpcNode(node)
    return {
        "text": wrapped.get_node_text(),
        "id": wrapped.get_node_id(),
        "class_name": wrapped.get_node_class(),
        "package": wrapped.get_node_package(),
        "desc": wrapped.get_node_desc(),
        "bound": wrapped.get_node_bound(),
    }


def create_selector(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
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
    finally:
        _close_rpc(rpc)


def selector_add_query(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")

    query_type = str(params.get("type") or "").strip().lower()
    value = str(params.get("value") or "")
    if query_type == "text":
        ok = selector.addQuery_Text(value)
    elif query_type == "id":
        ok = selector.addQuery_Id(value)
    elif query_type == "desc":
        ok = selector.addQuery_Desc(value)
    elif query_type == "text_contains":
        ok = selector.addQuery_TextContain(value)
    else:
        return ActionResult(ok=False, code="invalid_query_type", message=f"unsupported selector query type: {query_type}")
    return ActionResult(ok=ok, code="ok" if ok else "query_add_failed", data={"type": query_type, "value": value})


def selector_exec_one(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    result = selector.execQueryOne()
    node = result.data.get("node") if isinstance(result.data, dict) else None
    if not result.ok or node is None:
        return ActionResult(ok=False, code="not_found", message="selector query returned no node")
    return ActionResult(ok=True, code="ok", data={"node": _serialize_node(node)})


def selector_exec_all(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    result = selector.execQueryAll()
    nodes = result.data.get("nodes") if isinstance(result.data, dict) else None
    if not result.ok or not nodes:
        return ActionResult(ok=False, code="not_found", message="selector query returned no nodes")
    serialized = [_serialize_node(node) for node in nodes]
    return ActionResult(ok=True, code="ok", data={"nodes": serialized, "count": len(serialized)})


def selector_clear(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    ok = selector.clear_selector()
    return ActionResult(ok=ok, code="ok" if ok else "selector_clear_failed")
