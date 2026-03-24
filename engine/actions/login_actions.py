from __future__ import annotations

from typing import cast

from engine.models.runtime import ActionResult, ExecutionContext


def _tap_fallback(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions.sdk_actions import get_sdk_action_bindings

    tap = get_sdk_action_bindings()["mytos.tap"]
    tap_params = {
        "device_ip": params.get("device_ip"),
        "x": params.get("fallback_x"),
        "y": params.get("fallback_y"),
    }
    return tap(tap_params, context)


def _fallback_coordinates(params: dict[str, object]) -> tuple[object, object]:
    fallback_x = params.get("fallback_x")
    fallback_y = params.get("fallback_y")
    if fallback_x is not None and fallback_y is not None:
        return fallback_x, fallback_y
    return params.get("x"), params.get("y")


def _selector_query_candidates(params: dict[str, object]) -> list[dict[str, object]]:
    if str(params.get("type") or "").strip():
        return [dict(params)]

    queries: list[dict[str, object]] = []
    raw_selectors = params.get("selectors")
    if not isinstance(raw_selectors, list):
        return queries

    mapping = {
        "text": ("text", "equal"),
        "text_contains": ("text", "contains"),
        "id": ("id", "equal"),
        "resource_id": ("id", "equal"),
        "class_name": ("class", "equal"),
        "desc": ("desc", "equal"),
        "content_desc": ("desc", "equal"),
        "desc_contain": ("desc", "contains"),
    }
    for item in raw_selectors:
        if not isinstance(item, dict):
            continue
        for key, (query_type, mode) in mapping.items():
            value = str(item.get(key) or "").strip()
            if not value:
                continue
            query = dict(params)
            query["type"] = query_type
            query["mode"] = mode
            query["value"] = value
            queries.append(query)
    return queries


def click_selector_or_tap(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    selector_result = ActionResult(ok=False, code="invalid_params", message="selector query is required")
    for query in _selector_query_candidates(params):
        selector_result = ui_actions.selector_click_one(query, context)
        if selector_result.ok:
            return selector_result

    fallback_x, fallback_y = _fallback_coordinates(params)
    if fallback_x is None or fallback_y is None:
        return selector_result

    fallback_result = _tap_fallback(
        {
            **params,
            "fallback_x": fallback_x,
            "fallback_y": fallback_y,
        },
        context,
    )
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


def input_text_with_shell_fallback(
    params: dict[str, object], context: ExecutionContext
) -> ActionResult:
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
        shell_data = cast(dict[str, object], shell_result.data or {})
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "used_shell_fallback": True,
                "primary_code": input_result.code,
                **shell_data,
            },
        )
    return shell_result


def focus_and_input_with_shell_fallback(
    params: dict[str, object], context: ExecutionContext
) -> ActionResult:
    focus_result = click_selector_or_tap(params, context)
    input_result = input_text_with_shell_fallback(params, context)
    if not input_result.ok:
        return input_result

    data = dict(cast(dict[str, object], input_result.data or {}))
    if focus_result.ok:
        if focus_result.data:
            focus_data = cast(dict[str, object], focus_result.data)
            data.update({f"focus_{key}": value for key, value in focus_data.items()})
    elif focus_result.code:
        data["focus_code"] = focus_result.code

    return ActionResult(ok=True, code=input_result.code, message=input_result.message, data=data)


def _ui_match_state(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions.ui_state_actions import ui_match_state

    return ui_match_state(params, context)


def _ui_wait_until(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions.ui_state_actions import ui_wait_until

    return ui_wait_until(params, context)


def _selector_read_one(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    selector_context = ExecutionContext(payload=context.payload, session=context.session)
    create_result = ui_actions.create_selector(params, selector_context)
    if not create_result.ok:
        return create_result

    add_query_result = ui_actions.selector_add_query(params, selector_context)
    if not add_query_result.ok:
        _ = ui_actions.selector_free({}, selector_context)
        return add_query_result

    try:
        return ui_actions.selector_exec_one({}, selector_context)
    finally:
        _ = ui_actions.selector_free({}, selector_context)


def _resolve_credential_value(field: dict[str, object], context: ExecutionContext) -> str:
    credential = str(field.get("credential") or field.get("credential_field") or "").strip().lower()
    if not credential:
        return str(field.get("text") or "").strip()

    if credential not in {"account", "username", "password"}:
        return ""

    default_keys = {
        "account": ("account", "username", "acc"),
        "username": ("username", "account", "acc"),
        "password": ("password", "pwd"),
    }[credential]
    for key in default_keys:
        value = cast(object, context.get_session_default(key))
        if isinstance(value, str) and value.strip():
            return value.strip()
        payload_value = context.payload.get(key)
        if isinstance(payload_value, str) and payload_value.strip():
            return payload_value.strip()
    return str(field.get("text") or "").strip()


def _resolve_field_text(
    field: dict[str, object], context: ExecutionContext
) -> tuple[str, str | None]:
    text = _resolve_credential_value(field, context)
    if text:
        return text, None

    field_id = str(field.get("field_id") or field.get("credential") or "field")
    return "", f"missing text for {field_id}"


def _clear_field(field: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    clear_raw = field.get("clear")
    if not clear_raw:
        return ActionResult(ok=True, code="ok")
    if not isinstance(clear_raw, dict):
        return ActionResult(ok=False, code="invalid_params", message="clear must be an object")
    clear_config = cast(dict[str, object], clear_raw)

    command = str(clear_config.get("command") or "").strip()
    if command:
        return ui_actions.exec_command(
            {"device_ip": field.get("device_ip"), "command": command}, context
        )

    key = str(clear_config.get("key") or "").strip().lower()
    if key:
        presses_raw = clear_config.get("presses", 1)
        if isinstance(presses_raw, bool):
            presses_value = 1
        elif isinstance(presses_raw, int):
            presses_value = presses_raw
        elif isinstance(presses_raw, str):
            presses_value = int(presses_raw or 1)
        else:
            presses_value = 1
        presses = max(presses_value, 1)
        result = ActionResult(ok=True, code="ok", data={"presses": 0})
        for _ in range(presses):
            result = ui_actions.key_press(
                {"device_ip": field.get("device_ip"), "key": key}, context
            )
            if not result.ok:
                return result
        return result

    return ActionResult(
        ok=False, code="invalid_params", message="clear.command or clear.key is required"
    )


def _masked_or_exact_match(expected: str, observed_values: list[str]) -> bool:
    for observed in observed_values:
        if observed == expected:
            return True
        if len(observed) != len(expected) or not observed:
            continue
        if observed.isalnum():
            continue
        if len(set(observed)) == 1:
            return True
    return False


def _verify_field_input(
    field: dict[str, object], text: str, context: ExecutionContext
) -> ActionResult:
    verify = field.get("verify")
    verify_config: dict[str, object] = (
        cast(dict[str, object], verify) if isinstance(verify, dict) else {}
    )
    mode = str(verify_config.get("mode") or "").strip().lower()
    if not mode:
        credential = str(field.get("credential") or "").strip().lower()
        mode = "masked_or_exact" if credential == "password" else "exact"

    read_result = _selector_read_one(field, context)
    if not read_result.ok:
        return ActionResult(
            ok=False,
            code="input_verification_failed",
            message=read_result.message or "unable to read field for verification",
            data={"field_id": field.get("field_id"), "read_code": read_result.code},
        )

    node = cast(dict[str, object], read_result.data.get("node") or {})
    observed_values = [str(node.get("text") or "").strip(), str(node.get("desc") or "").strip()]
    expected = str(verify_config.get("expected") or text).strip()

    matched = False
    if mode == "exact":
        matched = expected in observed_values
    elif mode == "contains":
        matched = any(expected and expected in value for value in observed_values)
    elif mode == "nonempty":
        matched = any(value for value in observed_values)
    elif mode == "masked_or_exact":
        matched = _masked_or_exact_match(expected, observed_values)
    else:
        return ActionResult(
            ok=False, code="invalid_params", message=f"unsupported verify.mode: {mode}"
        )

    if matched:
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "field_id": field.get("field_id"),
                "observed_text": observed_values[0],
                "observed_desc": observed_values[1],
                "verify_mode": mode,
            },
        )

    return ActionResult(
        ok=False,
        code="input_verification_failed",
        message=f"input verification failed for {field.get('field_id') or 'field'}",
        data={
            "field_id": field.get("field_id"),
            "expected": expected,
            "observed_text": observed_values[0],
            "observed_desc": observed_values[1],
            "verify_mode": mode,
        },
    )


def _run_allowed_state_check(
    params: dict[str, object], context: ExecutionContext
) -> ActionResult | None:
    allowed_state = params.get("allowed_state")
    if not allowed_state:
        return None
    if not isinstance(allowed_state, dict):
        return ActionResult(
            ok=False, code="invalid_params", message="allowed_state must be an object"
        )

    result = _ui_match_state(cast(dict[str, object], allowed_state), context)
    if result.ok:
        return result
    return ActionResult(
        ok=False,
        code="state_not_allowed",
        message=result.message or "current state is not allowed",
        data={"state_check_code": result.code, **cast(dict[str, object], result.data or {})},
    )


def _build_field_params(
    base_params: dict[str, object], field: dict[str, object], *, text: str
) -> dict[str, object]:
    field_params = dict(base_params)
    field_params.update(field)
    field_params["text"] = text
    return field_params


def _submit_form(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    from engine.actions import ui_actions

    submit = params.get("submit")
    if submit is None:
        return ActionResult(ok=True, code="ok")
    if not isinstance(submit, dict):
        return ActionResult(ok=False, code="invalid_params", message="submit must be an object")

    submit_params = dict(cast(dict[str, object], submit))
    _ = submit_params.setdefault("device_ip", params.get("device_ip"))
    if submit_params.get("type"):
        return click_selector_or_tap(submit_params, context)

    key = str(submit_params.get("key") or "").strip().lower()
    if key:
        return ui_actions.key_press(
            {"device_ip": submit_params.get("device_ip"), "key": key}, context
        )

    return ActionResult(ok=False, code="missing_submit_target", message="submit target is required")


def fill_form(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    raw_fields = params.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        return ActionResult(
            ok=False, code="invalid_params", message="fields must be a non-empty list"
        )

    allowed_state_result = _run_allowed_state_check(params, context)
    if allowed_state_result is not None and not allowed_state_result.ok:
        return allowed_state_result

    base_params = dict(params)
    field_results: list[dict[str, object]] = []
    for raw_field in cast(list[object], raw_fields):
        if not isinstance(raw_field, dict):
            return ActionResult(
                ok=False, code="invalid_params", message="each field must be an object"
            )
        field = dict(cast(dict[str, object], raw_field))
        text, error_message = _resolve_field_text(field, context)
        if error_message:
            return ActionResult(
                ok=False,
                code="missing_field_text",
                message=error_message,
                data={"field_id": field.get("field_id"), "credential": field.get("credential")},
            )

        field_params = _build_field_params(base_params, field, text=text)
        focus_result = click_selector_or_tap(field_params, context)
        if not focus_result.ok:
            return focus_result

        clear_result = _clear_field(field_params, context)
        if not clear_result.ok:
            return clear_result

        input_result = input_text_with_shell_fallback(field_params, context)
        if not input_result.ok:
            return input_result

        verify_result = _verify_field_input(field_params, text, context)
        if not verify_result.ok:
            return verify_result

        field_results.append(
            {
                "field_id": field.get("field_id"),
                "verify_mode": verify_result.data.get("verify_mode"),
                "observed_text": verify_result.data.get("observed_text"),
                "observed_desc": verify_result.data.get("observed_desc"),
            }
        )

    submit_result = _submit_form(base_params, context)
    if not submit_result.ok:
        return submit_result

    result_data: dict[str, object] = {"fields": field_results}
    if allowed_state_result is not None and allowed_state_result.data:
        result_data["allowed_state"] = allowed_state_result.data.get("state")
    if submit_result.data:
        result_data["submit"] = submit_result.data

    wait_for_state = params.get("wait_for_state")
    if wait_for_state:
        if not isinstance(wait_for_state, dict):
            return ActionResult(
                ok=False, code="invalid_params", message="wait_for_state must be an object"
            )
        wait_result = _ui_wait_until(cast(dict[str, object], wait_for_state), context)
        if not wait_result.ok:
            return wait_result
        result_data.update(wait_result.data or {})

    return ActionResult(ok=True, code="ok", data=result_data)
