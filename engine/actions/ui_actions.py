from __future__ import annotations

from functools import wraps
from typing import Any

from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.mytRpc import MytRpc

# Import everything from specialized modules
from . import (
    _rpc_bootstrap,
    ui_app_actions,
    ui_device_actions,
    ui_input_actions,
    ui_selector_actions,
    ui_touch_actions,
)
from . import _ui_selector_support as _selector_support

# Re-export key classes for legacy monkeypatching support
MytSelector = _selector_support.MytSelector
# MytRpc is imported from hardware_adapters.mytRpc at top level

# Re-export ActionMetadata for action registry discovery.
APP_ENSURE_RUNNING_METADATA = ui_app_actions.APP_ENSURE_RUNNING_METADATA
APP_OPEN_METADATA = ui_app_actions.APP_OPEN_METADATA
APP_STOP_METADATA = ui_app_actions.APP_STOP_METADATA
CAPTURE_COMPRESSED_METADATA = ui_device_actions.CAPTURE_COMPRESSED_METADATA
CLICK_METADATA = ui_touch_actions.CLICK_METADATA
INPUT_TEXT_METADATA = ui_input_actions.INPUT_TEXT_METADATA
KEY_PRESS_METADATA = ui_input_actions.KEY_PRESS_METADATA
LONG_CLICK_METADATA = ui_touch_actions.LONG_CLICK_METADATA
SWIPE_METADATA = ui_touch_actions.SWIPE_METADATA


def _with_sync(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        _sync_late_patches()
        return f(*args, **kwargs)

    return wrapper


@_with_sync
def create_selector(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.create_selector(params, context)


@_with_sync
def selector_add_query(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.selector_add_query(params, context)


@_with_sync
def selector_click_one(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.selector_click_one(params, context)


@_with_sync
def selector_exec_one(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.selector_exec_one(params, context)


@_with_sync
def selector_find_nodes(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.selector_find_nodes(params, context)


@_with_sync
def node_get_text(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.node_get_text(params, context)


@_with_sync
def dump_node_xml_ex(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.dump_node_xml_ex(params, context)


@_with_sync
def selector_clear(
    params: dict[str, Any], context: ExecutionContext, *, close_rpc: Any = None
) -> ActionResult:
    # Use default from touch_actions if not provided
    close_rpc = close_rpc or ui_touch_actions._close_rpc
    return ui_selector_actions.selector_clear(params, context, close_rpc=close_rpc)


@_with_sync
def click(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_touch_actions.click(params, context)


@_with_sync
def touch_down(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_touch_actions.touch_down(params, context)


@_with_sync
def touch_move(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_touch_actions.touch_move(params, context)


@_with_sync
def touch_up(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_touch_actions.touch_up(params, context)


@_with_sync
def swipe(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_touch_actions.swipe(params, context)


@_with_sync
def long_click(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_touch_actions.long_click(params, context)


@_with_sync
def input_text(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_input_actions.input_text(params, context)


@_with_sync
def key_press(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_input_actions.key_press(params, context)


@_with_sync
def screenshot(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.screenshot(params, context)


@_with_sync
def capture_raw(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.capture_raw(params, context)


@_with_sync
def capture_compressed(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.capture_compressed(params, context)


@_with_sync
def check_connect_state(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.check_connect_state(params, context)


@_with_sync
def set_work_mode(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.set_work_mode(params, context)


@_with_sync
def use_new_node_mode(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.use_new_node_mode(params, context)


@_with_sync
def start_video_stream(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.start_video_stream(params, context)


@_with_sync
def stop_video_stream(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.stop_video_stream(params, context)


@_with_sync
def get_display_rotate(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.get_display_rotate(params, context)


@_with_sync
def get_sdk_version(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.get_sdk_version(params, context)


@_with_sync
def exec_command(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_device_actions.exec_command(params, context)


@_with_sync
def app_open(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_app_actions.app_open(params, context)


@_with_sync
def app_stop(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_app_actions.app_stop(params, context)


@_with_sync
def app_ensure_running(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_app_actions.app_ensure_running(params, context)


@_with_sync
def app_dismiss_popups(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_app_actions.app_dismiss_popups(params, context)


@_with_sync
def app_grant_permissions(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_app_actions.app_grant_permissions(params, context)


# Sync hooks and proxies

# Re-export selector support types/helpers for legacy imports
RpcNode = _selector_support.RpcNode
selector_exec_all = _selector_support.selector_exec_all
selector_free_nodes = _selector_support.selector_free_nodes
selector_get_nodes_size = _selector_support.selector_get_nodes_size
selector_get_node_by_index = _selector_support.selector_get_node_by_index


def selector_free(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return ui_selector_actions.selector_free(params, context)


selector_clear_orig = _selector_support.selector_clear  # Avoid name clash
node_get_parent = _selector_support.node_get_parent
node_get_child_count = _selector_support.node_get_child_count
node_get_child = _selector_support.node_get_child
node_get_json = _selector_support.node_get_json
node_get_desc = _selector_support.node_get_desc
node_get_package = _selector_support.node_get_package
node_get_class = _selector_support.node_get_class
node_get_id = _selector_support.node_get_id
node_get_bound = _selector_support.node_get_bound
node_get_bound_center = _selector_support.node_get_bound_center
node_click = _selector_support.node_click
node_long_click = _selector_support.node_long_click


@_with_sync
def release_selector_context(context: ExecutionContext, *, close_rpc: Any = None) -> ActionResult:
    # Handle default close_rpc from touch_actions if None
    close_rpc = close_rpc or ui_touch_actions._close_rpc
    return ui_selector_actions.release_selector_context(context, close_rpc=close_rpc)


@_with_sync
def dumpNodeXml(params: dict[str, Any], context: ExecutionContext) -> ActionResult:  # noqa: N802
    """Backward-compatible XML dump action (legacy name)."""
    return dump_node_xml_ex(params, context)


@_with_sync
def selector_click_with_fallback(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    """Legacy selector click with fallback command."""
    # This logic was in ui_actions.py; keeping it here for now or could move to ui_selector_actions.py
    selector_defs = params.get("selectors")
    if not isinstance(selector_defs, list) or not selector_defs:
        return ActionResult(
            ok=False, code="invalid_params", message="selectors must be a non-empty list"
        )

    base_params = {
        key: value for key, value in params.items() if key not in {"selectors", "fallback_command"}
    }
    last_result: ActionResult | None = None

    for index, selector in enumerate(selector_defs):
        if not isinstance(selector, dict):
            return ActionResult(
                ok=False, code="invalid_params", message="selector entries must be objects"
            )

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
        fb_res = exec_command(
            {
                "device_ip": base_params.get("device_ip"),
                "command": fallback_command,
            },
            context,
        )
        if fb_res.ok:
            data = dict(fb_res.data or {})
            data.update({"fallback_command": fallback_command})
            return ActionResult(ok=True, code="ok", data=data)
        return fb_res

    message = "all selector clicks failed"
    if last_result and last_result.message:
        message = f"{message}: {last_result.message}"
    return ActionResult(ok=False, code="all_failed", message=message)


# Propagate mocks/re-exports to specialized modules to support legacy test monkeypatching
# Baseline RPC enablement check
def _is_rpc_enabled() -> bool:
    return _rpc_bootstrap.os.environ.get("MYT_ENABLE_RPC", "1") == "1"


# Proxy for _get_rpc to support test monkeypatching
_get_rpc_orig = ui_touch_actions._get_rpc
_close_rpc = ui_touch_actions._close_rpc


def _get_rpc(
    params: dict[str, Any], context: ExecutionContext
) -> tuple[MytRpc | None, ActionResult | None]:
    """Dynamic proxy for _get_rpc to follow monkeypatches on this module."""
    import sys

    ua = sys.modules.get("engine.actions.ui_actions")
    if ua and hasattr(ua, "_get_rpc") and ua._get_rpc != _get_rpc:
        return ua._get_rpc(params, context)
    return _get_rpc_orig(params, context)


def _sync_late_patches():
    """Syncs potentially monkeypatched attributes to submodules."""
    import sys

    ua = sys.modules.get("engine.actions.ui_actions")
    if not ua:
        return

    # Sync MytRpc
    current_rpc = getattr(ua, "MytRpc", MytRpc)
    for mod in [
        ui_touch_actions,
        ui_input_actions,
        ui_selector_actions,
        ui_app_actions,
        ui_device_actions,
    ]:
        if hasattr(mod, "MytRpc") and mod.MytRpc != current_rpc:
            mod.MytRpc = current_rpc

    # Sync MytSelector
    current_selector = getattr(ua, "MytSelector", _selector_support.MytSelector)
    for mod in [_selector_support, ui_selector_actions]:
        if hasattr(mod, "MytSelector") and mod.MytSelector != current_selector:
            mod.MytSelector = current_selector

    # Sync RpcNode
    current_node = getattr(ua, "RpcNode", _selector_support.RpcNode)
    for mod in [_selector_support, ui_selector_actions]:
        if hasattr(mod, "RpcNode") and mod.RpcNode != current_node:
            mod.RpcNode = current_node

    # Sync internal helpers for test monkeypatching
    for helper_name in ["_get_rpc", "_close_rpc"]:
        if hasattr(ua, helper_name):
            current_helper = getattr(ua, helper_name)
            for mod in [
                ui_touch_actions,
                ui_input_actions,
                ui_selector_actions,
                ui_app_actions,
                ui_device_actions,
                _selector_support,
            ]:
                if hasattr(mod, helper_name) and getattr(mod, helper_name) != current_helper:
                    setattr(mod, helper_name, current_helper)

    # Sync _get_rpc proxy
    for mod in [
        ui_touch_actions,
        ui_input_actions,
        ui_selector_actions,
        ui_app_actions,
        ui_device_actions,
    ]:
        if hasattr(mod, "_get_rpc") and mod._get_rpc != _get_rpc:
            mod._get_rpc = _get_rpc


# Specifically fix _is_rpc_enabled for tests
def _sync_rpc_state():
    """
    Syncs the MytRpc mock and is_rpc_enabled state to all specialized submodules.
    This is called automatically when this module is imported to ensure legacy tests
    that monkeypatch this module work correctly.
    """
    import engine.actions._rpc_bootstrap as rb

    _sync_late_patches()

    # Override the bootstrap's enabled check to follow this module's re-export
    def dynamic_check():
        import sys

        # Look up _is_rpc_enabled in this module dynamically
        m = sys.modules.get("engine.actions.ui_actions")
        fn = getattr(m, "_is_rpc_enabled", None) if m else None
        if callable(fn):
            return fn()
        return _is_rpc_enabled()

    rb.is_rpc_enabled = dynamic_check


# Call sync on import to ensure test harness compatibility
_sync_rpc_state()
