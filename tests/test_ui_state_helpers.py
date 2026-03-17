from __future__ import annotations

from engine.models.ui_state import UIStateObservationResult, UIStateTiming
from engine.ui_state_helpers import (
    build_error_result,
    build_timing,
    build_transition,
    copy_result,
    poll_until_result,
)


def test_ui_state_helpers_build_error_result_keeps_shared_shape() -> None:
    timing = UIStateTiming(elapsed_ms=12, attempt=0, samples=0)

    result = build_error_result(
        operation="wait_until",
        code="browser_unavailable",
        message="browser runtime missing",
        platform="browser",
        expected_state_ids=["exists:#login"],
        timing=timing,
        raw_details={"available": False},
    )

    assert result.ok is False
    assert result.code == "browser_unavailable"
    assert result.status == "unknown"
    assert result.state.state_id == "unknown"
    assert result.timing.attempt == 0
    assert result.timing.samples == 0
    assert result.raw_details == {"available": False}


def test_ui_state_helpers_copy_result_overrides_operation_and_transition() -> None:
    result = UIStateObservationResult.matched(
        operation="match_state",
        state_id="home",
        platform="native",
        expected_state_ids=["home"],
        timing=UIStateTiming(elapsed_ms=5, attempt=1, samples=1),
        raw_details={"stage": "home"},
    )
    timing = UIStateTiming(elapsed_ms=20, timeout_ms=1000, interval_ms=100, attempt=2, samples=2)

    copied = copy_result(
        result,
        operation="observe_transition",
        timing=timing,
        transition=build_transition(
            from_state={"state_id": "account"}, to_state=result.state, changed=True
        ),
    )

    assert copied.operation == "observe_transition"
    assert copied.timing.attempt == 2
    assert copied.raw_details == {"stage": "home"}
    assert copied.transition is not None
    assert copied.transition.from_state.state_id == "account"
    assert copied.transition.to_state.state_id == "home"


def test_ui_state_helpers_poll_until_result_retries_only_no_match() -> None:
    samples = iter(
        [
            UIStateObservationResult.no_match(operation="wait_until", state_id="login"),
            UIStateObservationResult.no_match(operation="wait_until", state_id="login"),
            UIStateObservationResult.matched(operation="wait_until", state_id="home"),
        ]
    )
    now = 0.0

    def monotonic_now() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        now += seconds

    outcome = poll_until_result(
        observe=lambda: next(samples),
        timeout_ms=5000,
        interval_ms=250,
        monotonic_now=monotonic_now,
        sleep=sleep,
    )

    assert outcome.result.ok is True
    assert outcome.attempts == 3
    assert outcome.samples == 3
    assert outcome.timed_out is False


def test_ui_state_helpers_build_timing_uses_supplied_ticks() -> None:
    timing = build_timing(
        started_at=10.0,
        started_tick=5.0,
        finished_at=12.5,
        finished_tick=5.75,
        timeout_ms=1000,
        interval_ms=100,
        attempt=2,
        samples=2,
    )

    assert timing.started_at == 10.0
    assert timing.finished_at == 12.5
    assert timing.elapsed_ms == 750
    assert timing.attempt == 2
    assert timing.samples == 2
