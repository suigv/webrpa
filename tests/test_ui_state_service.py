from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.ui_state import (
    X_LOGIN_STAGE_VALUES,
    UIStateEvidence,
    UIStateObservationResult,
    UIStateTiming,
    UIStateTransition,
    normalize_x_login_stage,
)
from engine.ui_state_service import UIStateService


def test_ui_state_service_shared_top_level_shape_and_action_result_bridge():
    result = UIStateObservationResult.matched(
        operation="match_state",
        state_id="home",
        platform="browser",
        expected_state_ids=["home", "account"],
        evidence=UIStateEvidence(summary="matched url", url="https://x.com/home", matched=["/home"]),
        timing=UIStateTiming(elapsed_ms=42, attempt=1, samples=1),
        raw_details={"url": "https://x.com/home", "selector": "body"},
    )

    payload = result.model_dump(mode="python")
    assert payload == {
        "ok": True,
        "code": "ok",
        "message": "",
        "operation": "match_state",
        "status": "matched",
        "platform": "browser",
        "state": {"state_id": "home", "display_name": None, "group": None, "aliases": []},
        "expected_state_ids": ["home", "account"],
        "evidence": {
            "summary": "matched url",
            "selector": None,
            "text": None,
            "url": "https://x.com/home",
            "confidence": None,
            "matched": ["/home"],
            "missing": [],
        },
        "timing": {
            "started_at": None,
            "finished_at": None,
            "elapsed_ms": 42,
            "timeout_ms": None,
            "interval_ms": None,
            "attempt": 1,
            "samples": 1,
        },
        "raw_details": {"url": "https://x.com/home", "selector": "body"},
        "transition": None,
    }

    action_result = result.to_action_result()
    assert isinstance(action_result, ActionResult)
    assert action_result.ok is True
    assert action_result.code == "ok"
    assert action_result.data["status"] == "matched"
    assert action_result.data["state"]["state_id"] == "home"


def test_ui_state_service_no_match_contract_defaults():
    result = UIStateObservationResult.no_match(
        operation="match_state",
        platform="native",
        expected_state_ids=["home"],
        raw_details={"last_stage": "captcha"},
    )

    assert result.ok is False
    assert result.code == "no_match"
    assert result.status == "no_match"
    assert result.state.state_id == "unknown"
    assert result.expected_state_ids == ["home"]
    assert result.timing.elapsed_ms == 0
    assert result.raw_details == {"last_stage": "captcha"}


def test_ui_state_service_timeout_contract_defaults():
    result = UIStateObservationResult.timeout(
        operation="wait_until",
        state_id="password",
        platform="native",
        expected_state_ids=["home"],
        timing=UIStateTiming(elapsed_ms=15000, timeout_ms=15000, attempt=5, samples=5),
    )

    assert result.ok is False
    assert result.code == "timeout"
    assert result.status == "timeout"
    assert result.state.state_id == "password"
    assert result.timing.timeout_ms == 15000
    assert result.timing.attempt == 5


def test_ui_state_service_unknown_stage_normalization_and_compatibility_values():
    assert X_LOGIN_STAGE_VALUES == ("home", "two_factor", "captcha", "password", "account", "unknown")

    for stage in X_LOGIN_STAGE_VALUES:
        assert normalize_x_login_stage(stage) == stage

    assert normalize_x_login_stage("email") == "unknown"
    assert normalize_x_login_stage("") == "unknown"


def test_ui_state_service_transition_shape_is_shared():
    result = UIStateObservationResult(
        ok=True,
        code="ok",
        operation="observe_transition",
        status="transition_observed",
        platform="browser",
        state={"state_id": "home"},
        transition=UIStateTransition(from_state={"state_id": "account"}, to_state={"state_id": "home"}, changed=True),
    )

    assert result.transition is not None
    assert result.transition.changed is True
    assert result.transition.from_state.state_id == "account"
    assert result.transition.to_state.state_id == "home"


def test_ui_state_service_protocol_method_names_are_stable():
    method_names = {name for name in UIStateService.__dict__ if not name.startswith("_")}
    assert {"match_state", "wait_until", "observe_transition"}.issubset(method_names)

    ctx = ExecutionContext(payload={})
    assert ctx.payload == {}
