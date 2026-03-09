# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportIndexIssue=false

from pathlib import Path
from typing import cast

import pytest
import yaml

from engine.runner import Runner


def test_x_mobile_login_success_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "success"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "success"


def test_x_mobile_login_bad_credentials_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "bad_credentials"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "failed"
    assert "bad credentials" in result.get("message", "")


def test_x_mobile_login_2fa_failed_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "2fa_failed"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "failed"
    assert "2fa_failed" in result.get("message", "")


def test_x_mobile_login_captcha_status_contract():
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2", "status_hint": "captcha"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "failed"
    assert "captcha" in result.get("message", "")


def test_x_mobile_login_without_forced_hint_does_not_false_positive_when_rpc_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MYT_ENABLE_RPC", "0")
    result = Runner().run({"task": "x_mobile_login", "device_ip": "192.168.1.2"})
    assert result["task"] == "x_mobile_login"
    assert result["status"] == "failed"
    assert "device_connection_failed" in result.get("message", "")


def test_x_mobile_login_script_uses_composites_and_removes_duplicate_submits():
    script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_mobile_login" / "script.yaml"
    script = cast(dict[str, object], yaml.safe_load(script_path.read_text(encoding="utf-8")))
    steps = cast(list[dict[str, object]], script["steps"])
    labels = {step.get("label") for step in steps}

    for label in {
        "click_next_en",
        "click_next_zh",
        "click_login_zh",
        "click_login_en",
        "submit_2fa_zh",
        "key_enter_after_account",
        "key_enter_after_2fa",
    }:
        assert label not in labels

    composite_labels = {
        step["label"]: step["action"]
        for step in steps
        if step.get("label") in {"focus_account_input", "focus_password_input", "try_2fa_input_generated", "try_2fa_input_payload"}
    }
    assert composite_labels == {
        "focus_account_input": "ui.fill_form",
        "focus_password_input": "ui.fill_form",
        "try_2fa_input_generated": "ui.fill_form",
        "try_2fa_input_payload": "ui.fill_form",
    }
    goto_step = next(step for step in steps if step.get("label") == "goto_wait_after_2fa_generated")
    assert goto_step["kind"] == "goto"
    assert goto_step["target"] == "wait_after_2fa"


def test_x_mobile_login_script_uses_ui_state_service_for_native_stage_checks():
    script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_mobile_login" / "script.yaml"
    script = cast(dict[str, object], yaml.safe_load(script_path.read_text(encoding="utf-8")))
    steps = cast(list[dict[str, object]], script["steps"])
    labels = cast(dict[str, dict[str, object]], {step["label"]: step for step in steps if step.get("label")})

    def _params(label: str) -> dict[str, object]:
        return cast(dict[str, object], labels[label].get("params") or {})

    assert labels["detect_entry_stage"]["action"] == "ui.match_state"
    assert labels["wait_post_submit_stage"]["action"] == "ui.wait_until"
    assert labels["try_2fa_input_payload"]["action"] == "ui.fill_form"
    assert labels["detect_entry_stage"]["params"]["expected_state_ids"] == [
        "home",
        "captcha",
        "two_factor",
        "password",
        "account",
    ]
    assert "device_ip" not in cast(dict[str, object], script.get("vars") or {})
    assert "package" not in cast(dict[str, object], script.get("vars") or {})
    assert "device_ip" not in _params("detect_entry_stage")
    assert "device_ip" not in _params("wait_post_submit_stage")
    assert "device_ip" not in _params("try_2fa_input_payload")
    assert labels["check_entry_home"]["when"]["all"][0]["var"] == "entry_state.state.state_id"
    assert labels["check_post_submit_two_factor"]["when"]["all"][0]["var"] == "post_submit_state.state.state_id"
    assert labels["check_after_2fa_captcha"]["when"]["all"][0]["var"] == "after_2fa_state.state.state_id"


def test_x_mobile_login_script_relies_on_session_defaults_for_runtime_plumbing():
    script_path = Path(__file__).resolve().parents[1] / "plugins" / "x_mobile_login" / "script.yaml"
    script = cast(dict[str, object], yaml.safe_load(script_path.read_text(encoding="utf-8")))
    steps = cast(list[dict[str, object]], script["steps"])
    labels = cast(dict[str, dict[str, object]], {step["label"]: step for step in steps if step.get("label")})

    def _params(label: str) -> dict[str, object]:
        return cast(dict[str, object], labels[label].get("params") or {})

    for label in {
        "verify_rpa_connection",
        "enable_new_node_mode",
        "ensure_running",
        "open_app",
        "click_login_entry_direct",
        "click_login_entry_row",
        "focus_account_input",
        "focus_password_input",
        "try_2fa_input_generated",
        "try_2fa_input_payload",
    }:
        assert "device_ip" not in _params(label)

    assert "package" not in _params("ensure_running")
    assert "package" not in _params("open_app")
