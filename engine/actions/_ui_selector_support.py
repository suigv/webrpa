from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from engine.models.runtime import ActionResult, ExecutionContext


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class MytSelector:
    rpc: Any
    selector: Any = None

    def __post_init__(self) -> None:
        if self.selector is None:
            self.selector = self.rpc.create_selector()

    def _call(self, method_name: str, *args: object) -> Any:
        method = getattr(self.rpc, method_name, None)
        if method is None:
            return False
        try:
            result = method(self.selector, *args)
        except TypeError:
            result = method(*args)
        return result

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
        return bool(self._call("addQuery_BoundsInside", left, top, right, bottom))

    def execQueryOne(self) -> Any:
        return self._call("execQueryOne")

    def execQueryAll(self) -> Any:
        return self._call("execQueryAll")

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
    rpc: Any = None

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


def _tracked_nodes_vars(context: ExecutionContext) -> set[str]:
    tracked = context.vars.get("_selector_nodes_vars")
    if isinstance(tracked, set):
        return tracked
    tracked = set()
    context.vars["_selector_nodes_vars"] = tracked
    return tracked


def _track_nodes_var(context: ExecutionContext, var_name: str) -> None:
    if var_name:
        _tracked_nodes_vars(context).add(var_name)


def _untrack_nodes_var(context: ExecutionContext, var_name: str) -> None:
    if not var_name:
        return
    tracked = context.vars.get("_selector_nodes_vars")
    if isinstance(tracked, set):
        tracked.discard(var_name)
        if not tracked:
            context.vars.pop("_selector_nodes_vars", None)


def _free_nodes_handle(rpc: Any, handle: int | None) -> bool:
    resolved = _resolve_handle_value(handle)
    if rpc is None or resolved is None:
        return False
    method = getattr(rpc, "free_nodes", None)
    if method is None:
        return False
    try:
        return bool(method(resolved))
    except Exception:
        return False


def _release_tracked_node_handles(context: ExecutionContext, selector: MytSelector | None) -> bool:
    if selector is None:
        return False
    released_any = False
    tracked = context.vars.get("_selector_nodes_vars")
    if not isinstance(tracked, set):
        return False
    for key in list(tracked):
        handle = _resolve_handle_value(context.vars.get(key))
        if handle is not None and _free_nodes_handle(selector.rpc, handle):
            context.vars.pop(key, None)
            released_any = True
        _untrack_nodes_var(context, key)
    return released_any


def _serialize_node(node: Any, rpc: Any = None) -> Dict[str, Any]:
    wrapped = RpcNode(node, rpc=rpc)
    return {
        "text": wrapped.get_node_text(),
        "id": wrapped.get_node_id(),
        "class_name": wrapped.get_node_class(),
        "package": wrapped.get_node_package(),
        "desc": wrapped.get_node_desc(),
        "bound": wrapped.get_node_bound(),
    }


def create_selector(
    params: Dict[str, Any],
    context: ExecutionContext,
    *,
    get_rpc: Any,
    close_rpc: Any,
    selector_cls: type[MytSelector] | None = None,
) -> ActionResult:
    # Resolve selector_cls at runtime to allow for late monkeypatching
    if selector_cls is None:
        selector_cls = MytSelector

    previous = context.vars.get("selector")
    if previous and hasattr(previous, "clear_selector"):
        try:
            previous.clear_selector()
            if hasattr(previous, "free_selector"):
                previous.free_selector()
        except Exception:
            pass
        if hasattr(previous, "rpc"):
            close_rpc(previous.rpc)
    rpc, err = get_rpc(params, context)
    if err:
        return err
    if rpc is None:
        return ActionResult(ok=False, code="rpc_unavailable", message="rpc unavailable")
    try:
        method = getattr(rpc, "create_selector", None)
        if method is None:
            return ActionResult(ok=False, code="not_supported", message="create_selector not available")
        selector_handle = method()
        selector = selector_cls(rpc=rpc, selector=selector_handle)
        context.vars["selector"] = selector
        return ActionResult(ok=selector.selector is not None, code="ok" if selector.selector is not None else "selector_failed")
    except Exception as exc:
        close_rpc(rpc)
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
        ok = selector.addQuery_Bounds(
            _to_int(params.get("left")),
            _to_int(params.get("top")),
            _to_int(params.get("right")),
            _to_int(params.get("bottom")),
        )
    elif query_type == "bounds_inside":
        ok = selector.addQuery_BoundsInside(
            _to_int(params.get("left")),
            _to_int(params.get("top")),
            _to_int(params.get("right")),
            _to_int(params.get("bottom")),
        )
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
        # Match legacy test expectations
        code = "invalid_params" if not query_type else "invalid_query_type"
        return False, code, f"unsupported selector query type: {query_type or 'empty'}"

    if not ok:
        return False, "query_add_failed", "failed to add selector query"
    return True, None, None


def selector_add_query(
    params: Dict[str, Any],
    context: ExecutionContext,
    selector_cls: type[MytSelector] | None = None,
) -> ActionResult:
    # Resolve selector_cls at runtime
    if selector_cls is None:
        selector_cls = MytSelector
        
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


def selector_exec_one(
    params: Dict[str, Any],
    context: ExecutionContext,
    selector_cls: type[MytSelector] | None = None,
) -> ActionResult:
    if selector_cls is None:
        selector_cls = MytSelector
        
    _ = params
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    result = selector.execQueryOne()
    node = result.data.get("node") if isinstance(result.data, dict) else None
    if not result.ok or node is None:
        return ActionResult(ok=False, code="not_found", message="selector query returned no node")
    return ActionResult(ok=True, code="ok", data={"node": _serialize_node(node, selector.rpc)})


def selector_click_one(
    params: Dict[str, Any],
    context: ExecutionContext,
    *,
    get_rpc: Any,
    close_rpc: Any,
    selector_cls: type[MytSelector] = MytSelector,
) -> ActionResult:
    rpc, err = get_rpc(params, context)
    if err:
        return err
    if rpc is None:
        return ActionResult(ok=False, code="rpc_unavailable", message="rpc unavailable")
    selector = selector_cls(rpc=rpc)
    try:
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
        try:
            _ = selector.clear_selector()
            _ = selector.free_selector()
        except Exception:
            pass
        close_rpc(rpc)


def selector_exec_all(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    _ = params
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    result = selector.execQueryAll()
    nodes = result.data.get("nodes") if isinstance(result.data, dict) else None
    if not result.ok or not nodes:
        return ActionResult(ok=False, code="not_found", message="selector query returned no nodes")
    serialized = [_serialize_node(node, selector.rpc) for node in nodes]
    return ActionResult(ok=True, code="ok", data={"nodes": serialized, "count": len(serialized)})


def selector_find_nodes(
    params: Dict[str, Any],
    context: ExecutionContext,
    selector_cls: type[MytSelector] | None = None,
) -> ActionResult:
    if selector_cls is None:
        selector_cls = MytSelector
        
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
        _track_nodes_var(context, save_as)
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
    if ok:
        _untrack_nodes_var(context, nodes_var)
        if nodes_var and _resolve_handle_value(context.vars.get(nodes_var)) == handle:
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
    return ActionResult(ok=True, code="ok", data={"node_handle": node_handle, "parent_handle": parent_handle, "saved_as": save_as or None, "node": _serialize_node(parent_handle, selector.rpc)})


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
    return ActionResult(ok=True, code="ok", data={"node_handle": node_handle, "index": index, "child_handle": child_handle, "saved_as": save_as or None, "node": _serialize_node(child_handle, selector.rpc)})


def _node_value_action(params: Dict[str, Any], context: ExecutionContext, *, method_name: str, key: str) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(ok=False, code="invalid_params", message="node_handle or node_var is required")
    value = getattr(selector.rpc, method_name)(node_handle)
    return ActionResult(ok=value is not None, code="ok" if value is not None else "node_query_failed", data={"node_handle": node_handle, key: value or ({} if key in {"bound", "center"} else "")})


def node_get_json(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_json", key="json")


def node_get_text(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_text", key="text")


def node_get_desc(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_desc", key="desc")


def node_get_package(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_package", key="package")


def node_get_class(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_class", key="class_name")


def node_get_id(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_id", key="id")


def node_get_bound(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_bound", key="bound")


def node_get_bound_center(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_bound_center", key="center")


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


def release_selector_context(context: ExecutionContext, *, close_rpc: Any) -> bool:
    selector = context.vars.get("selector")
    if not isinstance(selector, MytSelector):
        return False
    released_nodes = _release_tracked_node_handles(context, selector)
    context.vars.pop("selector", None)
    try:
        _ = selector.clear_selector()
        _ = selector.free_selector()
    except Exception:
        return released_nodes
    close_rpc(selector.rpc)
    return True or released_nodes


def selector_free(params: Dict[str, Any], context: ExecutionContext, *, close_rpc: Any) -> ActionResult:
    _ = params
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    ok = selector.free_selector()
    close_rpc(selector.rpc)
    context.vars.pop("selector", None)
    return ActionResult(ok=ok, code="ok" if ok else "selector_free_failed")


def selector_clear(params: Dict[str, Any], context: ExecutionContext, *, close_rpc: Any) -> ActionResult:
    _ = params
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    ok = selector.clear_selector()
    close_rpc(selector.rpc)
    context.vars.pop("selector", None)
    return ActionResult(ok=ok, code="ok" if ok else "selector_clear_failed")
