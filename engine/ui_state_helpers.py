from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from typing import cast

from engine.models.ui_state import (
    UIStateEvidence,
    UIStateIdentity,
    UIStateObservationResult,
    UIStateOperation,
    UIStatePlatform,
    UIStateTiming,
    UIStateTransition,
)


@dataclass(frozen=True)
class UIStatePollingOutcome:
    result: UIStateObservationResult
    attempts: int
    samples: int
    timed_out: bool


def build_timing(
    *,
    started_at: float,
    started_tick: float,
    finished_at: float,
    finished_tick: float,
    timeout_ms: int | None,
    interval_ms: int | None = None,
    attempt: int = 0,
    samples: int = 0,
    elapsed_ms: int | None = None,
) -> UIStateTiming:
    elapsed = elapsed_ms if elapsed_ms is not None else int(max(0.0, finished_tick - started_tick) * 1000)
    return UIStateTiming(
        started_at=started_at,
        finished_at=finished_at,
        elapsed_ms=max(0, elapsed),
        timeout_ms=timeout_ms,
        interval_ms=interval_ms,
        attempt=attempt,
        samples=samples,
    )


def copy_result(
    result: UIStateObservationResult,
    *,
    operation: UIStateOperation,
    timing: UIStateTiming,
    transition: UIStateTransition | None = None,
) -> UIStateObservationResult:
    return UIStateObservationResult(
        ok=result.ok,
        code=result.code,
        message=result.message,
        operation=operation,
        status=result.status,
        platform=result.platform,
        state=result.state,
        expected_state_ids=result.expected_state_ids,
        evidence=result.evidence,
        timing=timing,
        raw_details=result.raw_details,
        transition=transition if transition is not None else result.transition,
    )


def build_error_result(
    *,
    operation: UIStateOperation,
    code: str,
    message: str,
    platform: UIStatePlatform,
    expected_state_ids: Sequence[str],
    timing: UIStateTiming,
    state_id: str = "unknown",
    evidence: UIStateEvidence | None = None,
    raw_details: dict[str, object] | None = None,
    transition: UIStateTransition | None = None,
) -> UIStateObservationResult:
    return UIStateObservationResult(
        ok=False,
        code=code,
        message=message,
        operation=operation,
        status="unknown",
        platform=platform,
        state=UIStateIdentity(state_id=state_id),
        expected_state_ids=list(expected_state_ids),
        evidence=evidence or UIStateEvidence(summary=message),
        timing=timing,
        raw_details=dict(raw_details or {}),
        transition=transition,
    )


def build_transition(
    *,
    from_state: UIStateIdentity | dict[str, object] | None = None,
    to_state: UIStateIdentity | dict[str, object] | None = None,
    changed: bool,
) -> UIStateTransition:
    return UIStateTransition(
        from_state=cast(UIStateIdentity | dict[str, object], from_state or UIStateIdentity()),
        to_state=cast(UIStateIdentity | dict[str, object], to_state or UIStateIdentity()),
        changed=changed,
    )


def poll_until_result(
    *,
    observe: Callable[[], UIStateObservationResult],
    timeout_ms: int,
    interval_ms: int,
    monotonic_now: Callable[[], float],
    sleep: Callable[[float], None],
    retry_codes: Collection[str] = ("no_match",),
) -> UIStatePollingOutcome:
    deadline = monotonic_now() + max(0, timeout_ms) / 1000.0
    attempts = 0
    last_result: UIStateObservationResult | None = None

    while True:
        attempts += 1
        last_result = observe()
        if last_result.ok:
            return UIStatePollingOutcome(result=last_result, attempts=attempts, samples=attempts, timed_out=False)
        if last_result.code not in retry_codes:
            return UIStatePollingOutcome(result=last_result, attempts=attempts, samples=attempts, timed_out=False)
        if monotonic_now() >= deadline:
            return UIStatePollingOutcome(result=last_result, attempts=attempts, samples=attempts, timed_out=True)
        sleep(max(0.0, interval_ms) / 1000.0)
