from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from engine.actions import _ui_selector_query_dispatch
from engine.models.runtime import ActionResult, ExecutionContext

logger = logging.getLogger(__name__)

_QUERY_INT_BOOL_METHODS = {
    "addQuery_Clickable",
    "addQuery_Enable",
    "addQuery_Checkable",
    "addQuery_Focusable",
    "addQuery_Focused",
    "addQuery_Scrollable",
    "addQuery_LongClickable",
    "addQuery_Password",
    "addQuery_Selected",
    "addQuery_Visible",
}
_QUERY_BOOL_RESULT_METHODS = {"addQuery_BoundsInside"}
_MISSING = object()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _log_recoverable(message: str, *, exc: Exception | None = None, **details: object) -> None:
    parts = [f"{key}={value!r}" for key, value in details.items() if value is not None]
    if exc is not None:
        parts.append(f"exc={exc!r}")
    suffix = f" ({', '.join(parts)})" if parts else ""
    logger.debug("%s%s", message, suffix)


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

    def __getattr__(self, name: str) -> Any:
        if not name.startswith("addQuery_"):
            raise AttributeError(name)

        def _query_method(*args: object) -> Any:
            normalized_args = args
            if name in _QUERY_INT_BOOL_METHODS:
                normalized_args = tuple(int(bool(arg)) for arg in args)
            result = self._call(name, *normalized_args)
            if name in _QUERY_BOOL_RESULT_METHODS:
                return bool(result)
            return result

        return _query_method

    def execQueryOne(self) -> ActionResult:
        method = getattr(self.rpc, "execQueryOne", None)
        if method is None:
            return ActionResult(
                ok=False, code="not_supported", message="execQueryOne not available"
            )
        try:
            node = method(self.selector)
        except TypeError:
            node = method()
        return ActionResult(
            ok=node is not None,
            code="ok" if node is not None else "query_empty",
            data={"node": node},
        )

    def execQueryAll(self) -> ActionResult:
        method = getattr(self.rpc, "execQueryAll", None)
        if method is None:
            return ActionResult(
                ok=False, code="not_supported", message="execQueryAll not available"
            )
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

    def _handle_call(self, method_name: str, *args: object) -> Any:
        return getattr(self.rpc, method_name)(int(self.node), *args)

    def _call_node_method(
        self,
        name: str,
        *args: object,
        default: Any = None,
        missing: Any = _MISSING,
        log_message: str = "rpc node callable failed",
        **details: object,
    ) -> Any:
        attr = getattr(self.node, name, None)
        if not callable(attr):
            return missing
        try:
            return attr(*args)
        except Exception as exc:
            _log_recoverable(log_message, exc=exc, method=name, **details)
            return default

    def _method(self, name: str, default: Any = None) -> Any:
        result = self._call_node_method(
            name, default=_MISSING, log_message="rpc node callable failed"
        )
        if result is not _MISSING:
            return result
        attr = getattr(self.node, name, None)
        if attr is not None:
            return attr
        return default

    def _string_value(self, rpc_method_name: str, *fallback_names: str) -> str:
        if self._is_handle() and self.rpc is not None:
            value = self._handle_call(rpc_method_name)
            return str(value or "")
        fallback: Any = ""
        for name in reversed(fallback_names):
            fallback = self._method(name, fallback)
        return str(fallback)

    def _bound_value(self, bound: Any) -> dict[str, int]:
        if not isinstance(bound, dict):
            bound = {}
        return {
            "left": int(bound.get("left", 0)),
            "top": int(bound.get("top", 0)),
            "right": int(bound.get("right", 0)),
            "bottom": int(bound.get("bottom", 0)),
        }

    def get_node_text(self) -> str:
        return self._string_value("get_node_text", "get_node_text", "text")

    def get_node_id(self) -> str:
        return self._string_value("get_node_id", "get_node_id", "id")

    def get_node_class(self) -> str:
        return self._string_value("get_node_class", "get_node_class", "class_name")

    def get_node_package(self) -> str:
        return self._string_value("get_node_package", "get_node_package", "package")

    def get_node_desc(self) -> str:
        return self._string_value("get_node_desc", "get_node_desc", "desc")

    def get_node_bound(self) -> dict[str, int]:
        if self._is_handle() and self.rpc is not None:
            return self._bound_value(self._handle_call("get_node_bound"))
        bound = self._method(
            "get_node_bound", self._method("bound", {"left": 0, "top": 0, "right": 0, "bottom": 0})
        )
        return self._bound_value(bound)

    def get_node_bound_center(self) -> dict[str, int]:
        bound = self.get_node_bound()
        return {
            "x": int((bound.get("left", 0) + bound.get("right", 0)) / 2),
            "y": int((bound.get("top", 0) + bound.get("bottom", 0)) / 2),
        }

    def get_node_parent(self) -> Any:
        if self._is_handle() and self.rpc is not None:
            return self._handle_call("get_node_parent")
        return self._method("get_node_parent")

    def get_node_child(self, index: int) -> Any:
        if self._is_handle() and self.rpc is not None:
            return self._handle_call("get_node_child", int(index))
        child = self._call_node_method(
            "get_node_child",
            index,
            default=None,
            log_message="rpc node child lookup failed",
            index=index,
        )
        if child is not _MISSING:
            return child
        children = self._method("children", [])
        if isinstance(children, list) and 0 <= index < len(children):
            return children[index]
        return None

    def get_node_child_count(self) -> int:
        if self._is_handle() and self.rpc is not None:
            return int(self._handle_call("get_node_child_count"))
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
            except Exception as exc:
                _log_recoverable("rpc node click via Click_events failed", exc=exc)
                return False
        method = getattr(self.node, "click", None)
        if callable(method):
            try:
                method()
                return True
            except Exception as exc:
                _log_recoverable("rpc node click via click() failed", exc=exc)
                return False
        return False

    def long_click_events(self) -> bool:
        if self._is_handle() and self.rpc is not None:
            return bool(self.rpc.long_click_node(int(self.node)))
        method = getattr(self.node, "longClick_events", None)
        if callable(method):
            try:
                return bool(method())
            except Exception as exc:
                _log_recoverable("rpc node long click failed", exc=exc)
                return False
        return False

    def get_node_json(self) -> str:
        return self._string_value("get_node_json", "get_node_json", "getNodeJson")


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


def _resolve_nodes_handle(params: dict[str, Any], context: ExecutionContext) -> int | None:
    direct = _resolve_handle_value(params.get("nodes_handle"))
    if direct is not None:
        return direct
    var_name = str(params.get("nodes_var") or "nodes_handle").strip()
    if not var_name:
        return None
    return _resolve_handle_value(context.vars.get(var_name))


def _resolve_node_handle(params: dict[str, Any], context: ExecutionContext) -> int | None:
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
    except Exception as exc:
        _log_recoverable("free_nodes failed", exc=exc, handle=resolved)
        return False


def _cleanup_selector(
    selector: MytSelector | None,
    *,
    close_rpc: Any | None = None,
    close_connection: bool = True,
) -> None:
    if selector is None:
        return
    if hasattr(selector, "clear_selector"):
        try:
            selector.clear_selector()
        except Exception as exc:
            _log_recoverable("selector clear failed during cleanup", exc=exc)
    if hasattr(selector, "free_selector"):
        try:
            selector.free_selector()
        except Exception as exc:
            _log_recoverable("selector free failed during cleanup", exc=exc)
    rpc = getattr(selector, "rpc", None)
    if close_connection and callable(close_rpc) and rpc is not None:
        try:
            close_rpc(rpc)
        except Exception as exc:
            _log_recoverable("rpc close failed during selector cleanup", exc=exc)


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


def _serialize_node(node: Any, rpc: Any = None) -> dict[str, Any]:
    wrapped = RpcNode(node, rpc=rpc)
    return {
        "text": wrapped.get_node_text(),
        "id": wrapped.get_node_id(),
        "class_name": wrapped.get_node_class(),
        "package": wrapped.get_node_package(),
        "desc": wrapped.get_node_desc(),
        "bound": wrapped.get_node_bound(),
    }


def _node_handle_result(
    *,
    raw_handle: Any,
    rpc: Any,
    context: ExecutionContext,
    save_as: str,
    handle_key: str,
    not_found_message: str,
    extra_data: dict[str, Any],
) -> ActionResult:
    resolved_handle = _resolve_handle_value(raw_handle)
    if resolved_handle is None:
        return ActionResult(ok=False, code="not_found", message=not_found_message)
    if save_as:
        context.vars[save_as] = resolved_handle
    return ActionResult(
        ok=True,
        code="ok",
        data={
            **extra_data,
            handle_key: resolved_handle,
            "node": _serialize_node(resolved_handle, rpc),
            "saved_as": save_as or None,
        },
    )


def create_selector(
    params: dict[str, Any],
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
    if isinstance(previous, MytSelector):
        _cleanup_selector(previous, close_rpc=close_rpc)
    rpc, err = get_rpc(params, context)
    if err:
        return err
    if rpc is None:
        return ActionResult(ok=False, code="rpc_unavailable", message="rpc unavailable")
    try:
        method = getattr(rpc, "create_selector", None)
        if method is None:
            return ActionResult(
                ok=False, code="not_supported", message="create_selector not available"
            )
        selector_handle = method()
        selector = selector_cls(rpc=rpc, selector=selector_handle)
        context.vars["selector"] = selector
        return ActionResult(
            ok=selector.selector is not None,
            code="ok" if selector.selector is not None else "selector_failed",
        )
    except Exception as exc:
        close_rpc(rpc)
        return ActionResult(ok=False, code="selector_failed", message=str(exc))


def _apply_selector_query(
    selector: MytSelector, params: dict[str, Any]
) -> tuple[bool, str | None, str | None]:
    return _ui_selector_query_dispatch.apply_selector_query(selector, params, to_int=_to_int)


def selector_add_query(
    params: dict[str, Any],
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
    params: dict[str, Any],
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
    params: dict[str, Any],
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
            return ActionResult(
                ok=False, code="not_found", message="selector query returned no node"
            )

        clicked = RpcNode(node, rpc=rpc).click_events()
        if not clicked:
            return ActionResult(ok=False, code="click_failed", message="node click failed")
        return ActionResult(ok=True, code="ok")
    finally:
        _cleanup_selector(selector, close_rpc=close_rpc)


def selector_exec_all(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
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
    params: dict[str, Any],
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
        return ActionResult(
            ok=False, code="find_nodes_failed", message="find_nodes returned no handle"
        )

    save_as = str(params.get("save_as") or "nodes_handle").strip()
    if save_as:
        context.vars[save_as] = int(handle)
        _track_nodes_var(context, save_as)
    count = int(selector.rpc.get_nodes_size(int(handle)))
    return ActionResult(
        ok=True,
        code="ok",
        data={"nodes_handle": int(handle), "count": count, "saved_as": save_as or None},
    )


def selector_free_nodes(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    handle = _resolve_nodes_handle(params, context)
    if handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="nodes_handle or nodes_var is required"
        )
    ok = selector.rpc.free_nodes(handle)
    nodes_var = str(params.get("nodes_var") or "nodes_handle").strip()
    if ok:
        _untrack_nodes_var(context, nodes_var)
        if nodes_var and _resolve_handle_value(context.vars.get(nodes_var)) == handle:
            context.vars.pop(nodes_var, None)
    return ActionResult(
        ok=ok, code="ok" if ok else "free_nodes_failed", data={"nodes_handle": handle}
    )


def selector_get_nodes_size(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    handle = _resolve_nodes_handle(params, context)
    if handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="nodes_handle or nodes_var is required"
        )
    count = int(selector.rpc.get_nodes_size(handle))
    return ActionResult(ok=True, code="ok", data={"nodes_handle": handle, "count": count})


def selector_get_node_by_index(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    handle = _resolve_nodes_handle(params, context)
    if handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="nodes_handle or nodes_var is required"
        )
    index = _to_int(params.get("index"), -1)
    if index < 0:
        return ActionResult(ok=False, code="invalid_params", message="index must be >= 0")

    save_as = str(params.get("save_as") or "node_handle").strip()
    return _node_handle_result(
        raw_handle=selector.rpc.get_node_by_index(handle, index),
        rpc=selector.rpc,
        context=context,
        save_as=save_as,
        handle_key="node_handle",
        not_found_message="node not found at index",
        extra_data={"nodes_handle": handle, "index": index},
    )


def node_get_parent(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="node_handle or node_var is required"
        )
    save_as = str(params.get("save_as") or "node_parent_handle").strip()
    return _node_handle_result(
        raw_handle=selector.rpc.get_node_parent(node_handle),
        rpc=selector.rpc,
        context=context,
        save_as=save_as,
        handle_key="parent_handle",
        not_found_message="parent node not found",
        extra_data={"node_handle": node_handle},
    )


def node_get_child_count(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="node_handle or node_var is required"
        )
    count = int(selector.rpc.get_node_child_count(node_handle))
    return ActionResult(ok=True, code="ok", data={"node_handle": node_handle, "count": count})


def node_get_child(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="node_handle or node_var is required"
        )
    index = _to_int(params.get("index"), -1)
    if index < 0:
        return ActionResult(ok=False, code="invalid_params", message="index must be >= 0")
    save_as = str(params.get("save_as") or "node_child_handle").strip()
    return _node_handle_result(
        raw_handle=selector.rpc.get_node_child(node_handle, index),
        rpc=selector.rpc,
        context=context,
        save_as=save_as,
        handle_key="child_handle",
        not_found_message="child node not found",
        extra_data={"node_handle": node_handle, "index": index},
    )


def _node_value_action(
    params: dict[str, Any], context: ExecutionContext, *, method_name: str, key: str
) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="node_handle or node_var is required"
        )
    value = getattr(selector.rpc, method_name)(node_handle)
    return ActionResult(
        ok=value is not None,
        code="ok" if value is not None else "node_query_failed",
        data={"node_handle": node_handle, key: value or ({} if key in {"bound", "center"} else "")},
    )


def node_get_json(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_json", key="json")


def node_get_text(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_text", key="text")


def node_get_desc(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_desc", key="desc")


def node_get_package(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_package", key="package")


def node_get_class(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_class", key="class_name")


def node_get_id(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_id", key="id")


def node_get_bound(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_bound", key="bound")


def node_get_bound_center(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _node_value_action(params, context, method_name="get_node_bound_center", key="center")


def node_click(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="node_handle or node_var is required"
        )
    ok = bool(selector.rpc.click_node(node_handle))
    return ActionResult(
        ok=ok, code="ok" if ok else "click_failed", data={"node_handle": node_handle}
    )


def node_long_click(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = _resolve_node_handle(params, context)
    if node_handle is None:
        return ActionResult(
            ok=False, code="invalid_params", message="node_handle or node_var is required"
        )
    ok = bool(selector.rpc.long_click_node(node_handle))
    return ActionResult(
        ok=ok, code="ok" if ok else "long_click_failed", data={"node_handle": node_handle}
    )


def release_selector_context(context: ExecutionContext, *, close_rpc: Any) -> bool:
    selector = context.vars.get("selector")
    if not isinstance(selector, MytSelector):
        return False
    _release_tracked_node_handles(context, selector)
    context.vars.pop("selector", None)
    _cleanup_selector(selector, close_rpc=close_rpc)
    return True


def selector_free(
    params: dict[str, Any], context: ExecutionContext, *, close_rpc: Any
) -> ActionResult:
    _ = params
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    ok = selector.free_selector()
    close_rpc(selector.rpc)
    context.vars.pop("selector", None)
    return ActionResult(ok=ok, code="ok" if ok else "selector_free_failed")


def selector_clear(
    params: dict[str, Any], context: ExecutionContext, *, close_rpc: Any
) -> ActionResult:
    _ = params
    selector = _selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    ok = selector.clear_selector()
    close_rpc(selector.rpc)
    context.vars.pop("selector", None)
    return ActionResult(ok=ok, code="ok" if ok else "selector_clear_failed")
