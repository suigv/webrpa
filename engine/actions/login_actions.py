from __future__ import annotations

from typing import Any

from engine.models.runtime import ActionResult, ExecutionContext


def _tap_fallback(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    from engine.actions.sdk_actions import get_sdk_action_bindings

    tap = get_sdk_action_bindings()["mytos.tap"]
    tap_params = {
        "device_ip": params.get("device_ip"),
        "x": params.get("fallback_x"),
        "y": params.get("fallback_y"),
    }
    return tap(tap_params, context)


def click_selector_or_tap(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    selector_result = ui_actions.selector_click_one(params, context)
    if selector_result.ok:
        return selector_result

    fallback_x = params.get("fallback_x")
    fallback_y = params.get("fallback_y")
    if fallback_x is None or fallback_y is None:
        return selector_result

    fallback_result = _tap_fallback(params, context)
    if fallback_result.ok:
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "used_tap_fallback": True,
                "selector_code": selector_result.code,
            },
        )
    return fallback_result


def input_text_with_shell_fallback(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    text = str(params.get("text") or "")
    if not text:
        return ActionResult(ok=False, code="invalid_params", message="text is required")

    input_result = ui_actions.input_text(params, context)
    if input_result.ok:
        return input_result

    shell_command = str(params.get("shell_command") or params.get("command") or "").strip()
    if not shell_command:
        shell_command = f"input text '{text}'"

    shell_result = ui_actions.exec_command(
        {"device_ip": params.get("device_ip"), "command": shell_command},
        context,
    )
    if shell_result.ok:
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "used_shell_fallback": True,
                "primary_code": input_result.code,
                **shell_result.data,
            },
        )
    return shell_result
