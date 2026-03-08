from engine.action_registry import register_defaults, resolve_action
from engine.actions import ui_actions
from engine.models.runtime import ActionResult, ExecutionContext


def test_click_selector_or_tap_uses_tap_fallback(monkeypatch):
    register_defaults()
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        ui_actions,
        "selector_click_one",
        lambda params, context: calls.append(("selector", params.copy())) or ActionResult(ok=False, code="not_found"),
    )
    from engine.actions import login_actions

    monkeypatch.setattr(
        login_actions,
        "_tap_fallback",
        lambda params, context: ActionResult(ok=True, code="ok", data={"x": params["fallback_x"], "y": params["fallback_y"]}),
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


def test_input_text_with_shell_fallback_uses_exec_command(monkeypatch):
    register_defaults()
    calls: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        ui_actions,
        "input_text",
        lambda params, context: calls.append(("input", params.copy())) or ActionResult(ok=False, code="send_text_failed"),
    )
    monkeypatch.setattr(
        ui_actions,
        "exec_command",
        lambda params, context: calls.append(("exec", params.copy())) or ActionResult(ok=True, code="ok", data={"output": "done"}),
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
