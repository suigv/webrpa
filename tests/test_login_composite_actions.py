# pyright: reportMissingImports=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false

from __future__ import annotations

import pytest
from typing import cast

from engine.action_registry import register_defaults, resolve_action
from engine.actions import ui_actions
from engine.models.runtime import ActionResult, ExecutionContext


def test_click_selector_or_tap_uses_tap_fallback(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    calls: list[tuple[str, dict[str, object]]] = []

    def selector_click_one(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        calls.append(("selector", params.copy()))
        return ActionResult(ok=False, code="not_found")

    monkeypatch.setattr(
        ui_actions,
        "selector_click_one",
        selector_click_one,
    )
    from engine.actions import login_actions

    def tap_fallback(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        return ActionResult(ok=True, code="ok", data={"x": params["fallback_x"], "y": params["fallback_y"]})

    monkeypatch.setattr(
        login_actions,
        "_tap_fallback",
        tap_fallback,
    )

    handler = resolve_action("ui.click_selector_or_tap")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "type": "text",
            "mode": "equals",
            "value": "Login",
            "fallback_x": 540,
            "fallback_y": 600,
        },
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is True
    assert result.data["used_tap_fallback"] is True
    assert calls == [
        (
            "selector",
            {
                "device_ip": "192.168.1.2",
                "type": "text",
                "mode": "equals",
                "value": "Login",
                "fallback_x": 540,
                "fallback_y": 600,
            },
        )
    ]


def test_input_text_with_shell_fallback_uses_exec_command(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    calls: list[tuple[str, dict[str, object]]] = []

    def input_text(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        calls.append(("input", params.copy()))
        return ActionResult(ok=False, code="send_text_failed")

    def exec_command(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        calls.append(("exec", params.copy()))
        return ActionResult(ok=True, code="ok", data={"output": "done"})

    monkeypatch.setattr(
        ui_actions,
        "input_text",
        input_text,
    )
    monkeypatch.setattr(
        ui_actions,
        "exec_command",
        exec_command,
    )

    handler = resolve_action("ui.input_text_with_shell_fallback")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "text": "alice",
            "command": "input text 'alice'",
        },
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is True
    assert result.data["used_shell_fallback"] is True
    assert calls == [
        ("input", {"device_ip": "192.168.1.2", "text": "alice", "command": "input text 'alice'"}),
        ("exec", {"device_ip": "192.168.1.2", "command": "input text 'alice'"}),
    ]


def test_focus_and_input_with_shell_fallback_ignores_focus_failure_when_input_succeeds(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import login_actions

    calls: list[tuple[str, dict[str, object]]] = []

    def click_selector_or_tap(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        calls.append(("focus", params.copy()))
        return ActionResult(ok=False, code="selector_missing")

    def input_text_with_shell_fallback(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        calls.append(("input", params.copy()))
        return ActionResult(ok=True, code="ok", data={"used_shell_fallback": True})

    monkeypatch.setattr(
        login_actions,
        "click_selector_or_tap",
        click_selector_or_tap,
    )
    monkeypatch.setattr(
        login_actions,
        "input_text_with_shell_fallback",
        input_text_with_shell_fallback,
    )

    handler = resolve_action("ui.focus_and_input_with_shell_fallback")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "type": "text",
            "mode": "equals",
            "value": "Username",
            "fallback_x": 540,
            "fallback_y": 600,
            "text": "alice",
            "command": "input text 'alice'",
        },
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is True
    assert result.data["used_shell_fallback"] is True
    assert result.data["focus_code"] == "selector_missing"
    assert [name for name, _ in calls] == ["focus", "input"]


def test_focus_and_input_with_shell_fallback_returns_input_failure(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import login_actions

    def click_selector_or_tap(_params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        return ActionResult(ok=True, code="ok")

    def input_text_with_shell_fallback(_params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        return ActionResult(ok=False, code="send_text_failed", message="failed to input")

    monkeypatch.setattr(
        login_actions,
        "click_selector_or_tap",
        click_selector_or_tap,
    )
    monkeypatch.setattr(
        login_actions,
        "input_text_with_shell_fallback",
        input_text_with_shell_fallback,
    )

    handler = resolve_action("ui.focus_and_input_with_shell_fallback")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "type": "text",
            "mode": "equals",
            "value": "Password",
            "fallback_x": 540,
            "fallback_y": 780,
            "text": "secret",
            "command": "input text 'secret'",
        },
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is False
    assert result.code == "send_text_failed"
    assert result.message == "failed to input"


def test_fill_form_successfully_inputs_submits_and_waits(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import login_actions

    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        login_actions,
        "click_selector_or_tap",
        lambda params, _context: calls.append(("focus_or_submit", params.copy())) or ActionResult(ok=True, code="ok"),
    )
    monkeypatch.setattr(
        login_actions,
        "input_text_with_shell_fallback",
        lambda params, _context: calls.append(("input", params.copy())) or ActionResult(ok=True, code="ok"),
    )
    monkeypatch.setattr(
        login_actions,
        "_selector_read_one",
        lambda params, _context: calls.append(("verify", params.copy())) or ActionResult(ok=True, code="ok", data={"node": {"text": str(params.get("text") or "")}}),
    )
    monkeypatch.setattr(
        login_actions,
        "_ui_match_state",
        lambda params, _context: calls.append(("allowed_state", params.copy())) or ActionResult(ok=True, code="ok", data={"state": {"state_id": "account"}}),
    )
    monkeypatch.setattr(
        login_actions,
        "_ui_wait_until",
        lambda params, _context: calls.append(("wait", params.copy())) or ActionResult(ok=True, code="ok", data={"state": {"state_id": "password"}}),
    )

    handler = resolve_action("ui.fill_form")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "allowed_state": {"binding_id": "login_stage", "expected_state_ids": ["account"]},
            "fields": [
                {
                    "field_id": "account",
                    "type": "id",
                    "mode": "equal",
                    "value": "username_input",
                    "fallback_x": 540,
                    "fallback_y": 600,
                    "text": "alice",
                }
            ],
            "submit": {
                "type": "text",
                "mode": "equal",
                "value": "Next",
                "fallback_x": 930,
                "fallback_y": 1830,
            },
            "wait_for_state": {"binding_id": "login_stage", "expected_state_ids": ["password"]},
        },
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is True
    assert result.data["state"]["state_id"] == "password"
    assert [name for name, _ in calls] == ["allowed_state", "focus_or_submit", "input", "verify", "focus_or_submit", "wait"]


def test_fill_form_returns_verification_failure(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import login_actions

    monkeypatch.setattr(login_actions, "click_selector_or_tap", lambda _params, _context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(login_actions, "input_text_with_shell_fallback", lambda _params, _context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(
        login_actions,
        "_selector_read_one",
        lambda _params, _context: ActionResult(ok=True, code="ok", data={"node": {"text": "wrong"}}),
    )

    handler = resolve_action("ui.fill_form")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "fields": [
                {
                    "field_id": "account",
                    "type": "id",
                    "mode": "equal",
                    "value": "username_input",
                    "text": "alice",
                }
            ],
        },
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is False
    assert result.code == "input_verification_failed"


def test_fill_form_returns_missing_submit_target_failure(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import login_actions

    monkeypatch.setattr(login_actions, "click_selector_or_tap", lambda _params, _context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(login_actions, "input_text_with_shell_fallback", lambda _params, _context: ActionResult(ok=True, code="ok"))
    monkeypatch.setattr(
        login_actions,
        "_selector_read_one",
        lambda params, _context: ActionResult(ok=True, code="ok", data={"node": {"text": str(params.get("text") or "")}}),
    )

    handler = resolve_action("ui.fill_form")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "fields": [{"field_id": "account", "type": "id", "mode": "equal", "value": "username_input", "text": "alice"}],
            "submit": {},
        },
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is False
    assert result.code == "missing_submit_target"


def test_fill_form_injects_session_credentials(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import login_actions

    seen_inputs: list[str] = []

    monkeypatch.setattr(login_actions, "click_selector_or_tap", lambda _params, _context: ActionResult(ok=True, code="ok"))

    def input_text_with_shell_fallback(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        seen_inputs.append(str(params.get("text") or ""))
        return ActionResult(ok=True, code="ok")

    monkeypatch.setattr(login_actions, "input_text_with_shell_fallback", input_text_with_shell_fallback)
    monkeypatch.setattr(
        login_actions,
        "_selector_read_one",
        lambda params, _context: ActionResult(ok=True, code="ok", data={"node": {"text": str(params.get("text") or "")}}),
    )

    handler = resolve_action("ui.fill_form")
    result = handler(
        {
            "device_ip": "192.168.1.2",
            "fields": [
                {"field_id": "account", "type": "id", "mode": "equal", "value": "username_input", "credential": "account"},
                {"field_id": "password", "type": "id", "mode": "equal", "value": "password_input", "credential": "password"},
            ],
        },
        ExecutionContext(
            payload={"device_ip": "192.168.1.2"},
            session={"defaults": {"acc": "demo_user", "pwd": "demo_pass"}},
        ),
    )

    assert result.ok is True
    assert seen_inputs == ["demo_user", "demo_pass"]


def test_navigate_to_noops_when_already_at_target(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import ui_state_actions

    def ui_match_state(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        if params.get("binding_id") == "feed_binding":
            return ActionResult(ok=True, code="ok", data={"state": {"state_id": "available"}})
        return ActionResult(ok=False, code="no_match", data={"state": {"state_id": "unknown"}})

    monkeypatch.setattr(ui_state_actions, "ui_match_state", ui_match_state)

    routes = {"feed": {"binding_id": "feed_binding", "display_name": "feed"}}

    handler = resolve_action("ui.navigate_to")
    result = handler(
        {"target": "feed", "routes": routes, "hops": []},
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is True
    assert result.data["noop"] is True
    assert result.data["current_route"] == "feed"


def test_navigate_to_recognizes_missing_state_page_as_current_route(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import ui_state_actions

    def ui_match_state(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        if params.get("binding_id") == "feed_binding":
            return ActionResult(ok=True, code="ok", data={"state": {"state_id": "missing"}})
        return ActionResult(ok=False, code="no_match", data={"state": {"state_id": "unknown"}})

    monkeypatch.setattr(ui_state_actions, "ui_match_state", ui_match_state)

    routes = {"feed": {"binding_id": "feed_binding", "display_name": "feed"}}

    handler = resolve_action("ui.navigate_to")
    result = handler(
        {"target": "feed", "routes": routes, "hops": []},
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is True
    assert result.data["noop"] is True
    assert result.data["current_route"] == "feed"


def test_navigate_to_runs_successful_bounded_route(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import ui_state_actions

    feed_calls = 0

    def ui_match_state(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        nonlocal feed_calls
        binding_id = params.get("binding_id")
        if binding_id == "inbox_binding":
            return ActionResult(ok=True, code="ok", data={"state": {"state_id": "available"}})
        if binding_id == "feed_binding":
            feed_calls += 1
            if feed_calls == 1:
                return ActionResult(ok=False, code="no_match", data={"state": {"state_id": "unknown"}})
            return ActionResult(ok=True, code="ok", data={"state": {"state_id": "available"}})
        return ActionResult(ok=False, code="no_match", data={"state": {"state_id": "unknown"}})

    monkeypatch.setattr(ui_state_actions, "ui_match_state", ui_match_state)

    def fake_resolve_action(_name: str):
        def _handler(_params: dict[str, object], _context: ExecutionContext) -> ActionResult:
            return ActionResult(ok=True, code="ok")
        return _handler

    monkeypatch.setattr("engine.action_registry.resolve_action", fake_resolve_action)

    routes = {
        "feed": {"binding_id": "feed_binding", "display_name": "feed"},
        "inbox": {"binding_id": "inbox_binding", "display_name": "inbox"},
    }
    hops = [
        {
            "hop_id": "inbox_to_feed",
            "from_route": "inbox",
            "to_route": "feed",
            "attempts": [{"action": "ui.key_press", "params": {"key": "home"}}],
        }
    ]

    handler = resolve_action("ui.navigate_to")
    result = handler(
        {"target": "feed", "routes": routes, "hops": hops},
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is True
    assert result.data["path"] == ["inbox_to_feed"]
    assert result.data["current_route"] == "feed"


def test_navigate_to_returns_target_unreachable_when_no_path(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import ui_state_actions

    def ui_match_state(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        if params.get("binding_id") == "feed_binding":
            return ActionResult(ok=True, code="ok", data={"state": {"state_id": "available"}})
        return ActionResult(ok=False, code="no_match", data={"state": {"state_id": "unknown"}})

    monkeypatch.setattr(ui_state_actions, "ui_match_state", ui_match_state)

    routes = {
        "feed": {"binding_id": "feed_binding", "display_name": "feed"},
        "inbox": {"binding_id": "inbox_binding", "display_name": "inbox"},
    }

    handler = resolve_action("ui.navigate_to")
    result = handler(
        {"target": "inbox", "routes": routes, "hops": []},
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is False
    assert result.code == "target_unreachable"


def test_navigate_to_returns_state_drift_detected(monkeypatch: pytest.MonkeyPatch):
    register_defaults()
    from engine.actions import navigation_actions, ui_state_actions

    def ui_match_state(params: dict[str, object], _context: ExecutionContext) -> ActionResult:
        if params.get("binding_id") == "inbox_binding":
            return ActionResult(ok=True, code="ok", data={"state": {"state_id": "available"}})
        return ActionResult(ok=False, code="no_match", data={"state": {"state_id": "unknown"}})

    monkeypatch.setattr(ui_state_actions, "ui_match_state", ui_match_state)
    monkeypatch.setattr(
        navigation_actions,
        "_execute_hop",
        lambda _routes, hop, _params, _context, *, active_route: {
            "code": "state_drift_detected",
            "message": f"navigation drifted during {hop.hop_id}",
            "attempts": [{"attempt_id": "open_action"}],
            "observed_route": "search",
        },
    )

    routes = {
        "feed": {"binding_id": "feed_binding", "display_name": "feed"},
        "inbox": {"binding_id": "inbox_binding", "display_name": "inbox"},
        "search": {"binding_id": "search_binding", "display_name": "search"},
    }
    hops = [
        {
            "hop_id": "inbox_to_feed",
            "from_route": "inbox",
            "to_route": "feed",
            "attempts": [{"action": "ui.key_press", "params": {"key": "home"}}],
        }
    ]

    handler = resolve_action("ui.navigate_to")
    result = handler(
        {"target": "feed", "routes": routes, "hops": hops},
        ExecutionContext(payload={"device_ip": "192.168.1.2"}),
    )

    assert result.ok is False
    assert result.code == "state_drift_detected"
