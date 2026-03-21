from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from engine.models.runtime import ActionResult, ExecutionContext

logger = logging.getLogger(__name__)
_MISSING = object()


def _log_recoverable(message: str, *, exc: Exception | None = None, **details: object) -> None:
    parts = [f"{key}={value!r}" for key, value in details.items() if value is not None]
    if exc is not None:
        parts.append(f"exc={exc!r}")
    suffix = f" ({', '.join(parts)})" if parts else ""
    logger.debug("%s%s", message, suffix)


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


def serialize_node(node: Any, rpc: Any = None) -> dict[str, Any]:
    wrapped = RpcNode(node, rpc=rpc)
    return {
        "text": wrapped.get_node_text(),
        "id": wrapped.get_node_id(),
        "class_name": wrapped.get_node_class(),
        "package": wrapped.get_node_package(),
        "desc": wrapped.get_node_desc(),
        "bound": wrapped.get_node_bound(),
    }


def node_value_action(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    method_name: str,
    key: str,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    selector = selector_from_context(context)
    if selector is None:
        return ActionResult(ok=False, code="selector_missing", message="selector not initialized")
    node_handle = resolve_node_handle(params, context)
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


def node_get_json(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_json",
        key="json",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )


def node_get_text(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_text",
        key="text",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )


def node_get_desc(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_desc",
        key="desc",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )


def node_get_package(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_package",
        key="package",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )


def node_get_class(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_class",
        key="class_name",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )


def node_get_id(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_id",
        key="id",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )


def node_get_bound(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_bound",
        key="bound",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )


def node_get_bound_center(
    params: dict[str, Any],
    context: ExecutionContext,
    *,
    selector_from_context: Callable[[ExecutionContext], Any],
    resolve_node_handle: Callable[[dict[str, Any], ExecutionContext], int | None],
) -> ActionResult:
    return node_value_action(
        params,
        context,
        method_name="get_node_bound_center",
        key="center",
        selector_from_context=selector_from_context,
        resolve_node_handle=resolve_node_handle,
    )
