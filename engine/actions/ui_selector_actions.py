from __future__ import annotations

import time
from typing import Any

from engine.actions import _rpc_bootstrap
from engine.actions import _ui_selector_support as _selector_support
from engine.models.runtime import ActionResult, ErrorType, ExecutionContext
from hardware_adapters.mytRpc import MytRpc


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


def create_selector(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.create_selector(
        params, context, get_rpc=_get_rpc, close_rpc=_close_rpc
    )


def selector_add_query(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_add_query(params, context)


def selector_click_one(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    from .ui_touch_actions import click as ui_click

    rpc, err = _get_rpc(params, context)
    if err:
        return err
    selector = None
    try:
        selector = _selector_support.MytSelector(rpc=rpc)
        ok, code, msg = _selector_support._apply_selector_query(selector, params)
        if not ok:
            return ActionResult(ok=False, code=str(code), message=str(msg))

        result = selector.execQueryOne()
        node_handle = result.data.get("node") if isinstance(result.data, dict) else None
        if node_handle is None:
            return ActionResult(ok=False, code="node_not_found")

        click_delay_ms = int(params.get("click_delay_ms", 0))
        if click_delay_ms > 0:
            time.sleep(click_delay_ms / 1000.0)

        node = _selector_support.RpcNode(node_handle, rpc=rpc)
        center = node.get_node_bound_center()

        # Legacy behavior: perform selector teardown and RPC closure BEFORE click
        # This ensures the first 3 events are teardown events
        if selector:
            try:
                selector.clear_selector()
                selector.free_selector()
            except Exception:
                pass
            selector = None

        _close_rpc(rpc)
        rpc = None  # Mark as closed

        click_params = dict(params)
        click_params.update({"x": center["x"], "y": center["y"]})
        # ui_click will re-bootstrap its own RPC connection if needed
        return ui_click(click_params, context)
    finally:
        if selector:
            try:
                selector.clear_selector()
                selector.free_selector()
            except Exception:
                pass
        if rpc:
            _close_rpc(rpc)


def selector_exec_one(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_exec_one(params, context)


def selector_exec_all(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_exec_all(params, context)


def selector_find_nodes(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.selector_find_nodes(params, context)


def selector_free(
    params: dict[str, Any], context: ExecutionContext, *, close_rpc: Any = _close_rpc
) -> ActionResult:
    """Legacy alias for selector_clear."""
    return _selector_support.selector_clear(params, context, close_rpc=close_rpc)


def selector_clear(
    params: dict[str, Any], context: ExecutionContext, *, close_rpc: Any = _close_rpc
) -> ActionResult:
    return _selector_support.selector_clear(params, context, close_rpc=close_rpc)


def release_selector_context(
    context: ExecutionContext, *, close_rpc: Any = _close_rpc
) -> ActionResult:
    return _selector_support.release_selector_context(context, close_rpc=close_rpc)


def node_get_text(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return _selector_support.node_get_text(params, context)


def dump_node_xml_ex(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err:
        return err
    try:
        work_mode = bool(params.get("work_mode", False))
        # Try XML with extended mode
        work_mode = bool(params.get("work_mode", True))
        xml = rpc.dump_node_xml_ex(work_mode, timeout_ms=3000) if rpc is not None else None
        if xml is None or not str(xml).strip():
            # Fallback to older method
            xml = rpc.dumpNodeXml(False) if rpc is not None else None

        return ActionResult(
            ok=xml is not None, code="ok" if xml is not None else "dump_failed", data={"xml": xml}
        )
    finally:
        _close_rpc(rpc)
