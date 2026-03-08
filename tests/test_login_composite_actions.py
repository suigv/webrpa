from __future__ import annotations

import pytest

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
