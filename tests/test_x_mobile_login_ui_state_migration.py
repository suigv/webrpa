# pyright: reportMissingModuleSource=false, reportIndexIssue=false

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

import yaml

from engine.action_registry import get_registry, register_defaults
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.ui_state import UIStateObservationResult
from engine.runner import Runner


def _script_steps() -> list[dict[str, object]]:
    script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_mobile_login" / "script.yaml"
    script = cast(dict[str, object], yaml.safe_load(script_path.read_text(encoding="utf-8")))
    return cast(list[dict[str, object]], script["steps"])


def _register_noop_actions() -> None:
    registry = get_registry()

    def ok_action(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        return ActionResult(ok=True, code="ok")

    def load_selector(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = context
        key = str(params.get("key") or "selector")
        return ActionResult(
            ok=True,
            code="ok",
            data={"type": "text", "mode": "contains", "value": key},
        )

    register_defaults()
    registry.register("core.load_ui_selector", load_selector)
    for action_name in (
        "device.check_connect_state",
        "device.use_new_node_mode",
        "app.ensure_running",
        "app.open",
        "ui.selector_click_one",
        "ui.click_selector_or_tap",
        "ui.focus_and_input_with_shell_fallback",
        "mytos.keypress",
    ):
        registry.register(action_name, ok_action)


def _run_login_plugin(
    *,
    match_handler: Callable[[dict[str, object], ExecutionContext], ActionResult],
    wait_handler: Callable[[dict[str, object], ExecutionContext], ActionResult],
    two_factor_code: str = "",
) -> dict[str, object]:
    runner = Runner()
    _register_noop_actions()
    registry = get_registry()
    registry.register("ui.match_state", match_handler)
    registry.register("ui.wait_until", wait_handler)
    return runner.run(
        {
            "task": "x_mobile_login",
            "device_ip": "192.168.1.2",
            "acc": "demo_user",
            "pwd": "demo_pass",
            "two_factor_code": two_factor_code,
        }
    )


def test_x_mobile_login_script_uses_service_backed_native_state_actions() -> None:
    steps = _script_steps()
    by_label = cast(dict[str, dict[str, object]], {step["label"]: step for step in steps if "label" in step})

    assert by_label["detect_entry_stage"]["action"] == "ui.match_state"
    assert by_label["wait_post_submit_stage"]["action"] == "ui.wait_until"
    assert by_label["wait_after_2fa"]["action"] == "ui.wait_until"
    assert by_label["detect_entry_stage"]["params"]["binding_id"] == "x_login"
    assert by_label["wait_post_submit_stage"]["params"]["expected_state_ids"] == [
        "home",
        "two_factor",
        "captcha",
        "password",
        "account",
    ]
    assert by_label["check_entry_home"]["when"]["all"][0]["var"] == "entry_state.state.state_id"
    assert by_label["check_post_submit_home"]["when"]["all"][0]["var"] == "post_submit_state.state.state_id"
    assert by_label["check_after_2fa_home"]["when"]["all"][0]["var"] == "after_2fa_state.state.state_id"


def test_x_mobile_login_entry_home_success_preserved() -> None:
    def match_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        return UIStateObservationResult.matched(
            operation="match_state",
            state_id="home",
            platform="native",
            expected_state_ids=["home", "captcha", "two_factor", "password", "account"],
        ).to_action_result()

    def unused_wait_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        raise AssertionError("ui.wait_until should not run when entry stage is home")

    result = _run_login_plugin(match_handler=match_handler, wait_handler=unused_wait_handler)

    assert result["status"] == "success"
    assert result["message"] == "login completed"


def test_x_mobile_login_post_submit_home_success_preserved() -> None:
    def match_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        return UIStateObservationResult.matched(
            operation="match_state",
            state_id="account",
            platform="native",
            expected_state_ids=["home", "captcha", "two_factor", "password", "account"],
        ).to_action_result()

    def wait_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = context
        expected = list(cast(list[str], params.get("expected_state_ids") or []))
        if expected == ["home", "two_factor", "captcha", "password", "account"]:
            return UIStateObservationResult.matched(
                operation="wait_until",
                state_id="home",
                platform="native",
                expected_state_ids=expected,
            ).to_action_result()
        raise AssertionError(f"unexpected expected_state_ids: {expected}")

    result = _run_login_plugin(match_handler=match_handler, wait_handler=wait_handler)

    assert result["status"] == "success"
    assert result["message"] == "login completed"


def test_x_mobile_login_post_submit_captcha_preserved() -> None:
    def match_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        return UIStateObservationResult.matched(
            operation="match_state",
            state_id="account",
            platform="native",
            expected_state_ids=["home", "captcha", "two_factor", "password", "account"],
        ).to_action_result()

    def wait_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = context
        expected = list(cast(list[str], params.get("expected_state_ids") or []))
        if expected == ["home", "two_factor", "captcha", "password", "account"]:
            return UIStateObservationResult.matched(
                operation="wait_until",
                state_id="captcha",
                platform="native",
                expected_state_ids=expected,
            ).to_action_result()
        raise AssertionError(f"unexpected expected_state_ids: {expected}")

    result = _run_login_plugin(match_handler=match_handler, wait_handler=wait_handler)

    assert result["status"] == "failed"
    assert result["message"] == "captcha"


def test_x_mobile_login_two_factor_timeout_preserved() -> None:
    def match_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = (params, context)
        return UIStateObservationResult.matched(
            operation="match_state",
            state_id="account",
            platform="native",
            expected_state_ids=["home", "captcha", "two_factor", "password", "account"],
        ).to_action_result()

    def wait_handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        _ = context
        expected = list(cast(list[str], params.get("expected_state_ids") or []))
        if expected == ["home", "two_factor", "captcha", "password", "account"]:
            return UIStateObservationResult.matched(
                operation="wait_until",
                state_id="two_factor",
                platform="native",
                expected_state_ids=expected,
            ).to_action_result()
        if expected == ["home", "captcha"]:
            return UIStateObservationResult.timeout(
                operation="wait_until",
                state_id="unknown",
                platform="native",
                expected_state_ids=expected,
                message="timed out waiting for post-2fa state",
            ).to_action_result()
        raise AssertionError(f"unexpected expected_state_ids: {expected}")

    result = _run_login_plugin(
        match_handler=match_handler,
        wait_handler=wait_handler,
        two_factor_code="123456",
    )

    assert result["status"] == "failed"
    assert result["message"] == "2fa_failed"
