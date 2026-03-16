from __future__ import annotations
from typing import Any, Dict
from engine.actions import _rpc_bootstrap
from engine.actions import _ui_selector_support as _selector_support
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.mytRpc import MytRpc
from engine.action_registry import ActionMetadata

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

def create_selector(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        handle = rpc.create_selector() if rpc is not None else -1
        return ActionResult(ok=handle >= 0, code="ok" if handle >= 0 else "selector_error", data={"handle": handle})
    finally:
        _close_rpc(rpc)

def selector_add_query(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        handle = int(params.get("handle", -1))
        query = str(params.get("query") or "")
        ok = rpc.selector_add_query(handle, query) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "selector_error")
    finally:
        _close_rpc(rpc)

def selector_click_one(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    # 代理到 _selector_support 逻辑，并使用 ui.click 进行点击以承接拟人化
    from .ui_touch_actions import click as ui_click
    return _selector_support.selector_click_one(params, context, click_handler=ui_click)

def selector_exec_one(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        handle = int(params.get("handle", -1))
        ok = rpc.selector_exec_one(handle) if rpc is not None else False
        return ActionResult(ok=ok, code="ok" if ok else "selector_error")
    finally:
        _close_rpc(rpc)

def selector_find_nodes(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        handle = int(params.get("handle", -1))
        nodes_handle = rpc.selector_find_nodes(handle) if rpc is not None else -1
        return ActionResult(ok=nodes_handle >= 0, code="ok" if nodes_handle >= 0 else "selector_error", data={"nodes_handle": nodes_handle})
    finally:
        _close_rpc(rpc)

def selector_free(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        handle = int(params.get("handle", -1))
        ok = rpc.selector_free(handle) if rpc is not None else False
        return ActionResult(ok=ok, code="ok")
    finally:
        _close_rpc(rpc)

def node_get_text(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        handle = int(params.get("handle", -1))
        text = rpc.node_get_text(handle) if rpc is not None else ""
        return ActionResult(ok=True, code="ok", data={"text": text})
    finally:
        _close_rpc(rpc)

def dump_node_xml_ex(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    rpc, err = _get_rpc(params, context)
    if err: return err
    try:
        xml = rpc.dump_node_xml_ex() if rpc is not None else ""
        return ActionResult(ok=True, code="ok", data={"xml": xml})
    finally:
        _close_rpc(rpc)
