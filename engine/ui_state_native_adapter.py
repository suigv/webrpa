# pyright: reportUnknownMemberType=false

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import cast

from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.ui_state import (
    UIStateEvidence,
    UIStateIdentity,
    UIStateObservationResult,
    UIStateOperation,
    UIStateTiming,
)
from engine.ui_state_helpers import build_error_result, build_timing, build_transition
from engine.ui_state_native_bindings import (
    NativeStateProfile,
    build_native_state_identity_details,
    is_presence_style_profile,
    normalize_native_state_profile_id,
    resolve_native_state_profile,
)


def resolve_native_state_binding(binding_id: str) -> NativeStateProfile:
    return resolve_native_state_profile(normalize_native_state_profile_id(binding_id=binding_id))


class NativeUIStateAdapter:
    def __init__(
        self,
        state_profile_id: str | None = None,
        *,
        binding_id: str | None = None,
        action_params: dict[str, object] | None = None,
    ) -> None:
        self._state_profile: NativeStateProfile
        self._action_params: dict[str, object]
        self._action_params = dict(action_params or {})
        resolved_profile_id = normalize_native_state_profile_id(
            state_profile_id,
            binding_id=binding_id,
            default="login_stage",
        )
        self._state_profile = resolve_native_state_profile(resolved_profile_id)

    def match_state(
        self,
        context: ExecutionContext,
        *,
        expected_state_ids: Sequence[str],
        timeout_ms: int | None = None,
    ) -> UIStateObservationResult:
        normalized_expected = self._normalize_expected_state_ids(expected_state_ids)
        if not normalized_expected:
            return self._invalid_params_result(
                operation="match_state",
                message="expected_state_ids is required",
                expected_state_ids=(),
                timeout_ms=timeout_ms,
            )

        started_at = time.monotonic()
        action_result = self._state_profile.match_action(
            self._match_action_params(timeout_ms=timeout_ms), context
        )
        finished_at = time.monotonic()
        timing = self._timing(
            started_at=started_at,
            finished_at=finished_at,
            timeout_ms=timeout_ms,
            attempt=1 if action_result.code == "ok" else 0,
            samples=1 if action_result.code == "ok" else 0,
        )
        state_id = self._state_id_from_action_result(action_result)
        is_authoritative_match = state_id != "unknown" and state_id in normalized_expected
        evidence = self._build_evidence(
            state_id, normalized_expected, matched=is_authoritative_match
        )
        raw_details = self._build_raw_details(
            state_id=state_id,
            expected_state_ids=normalized_expected,
            action_result=action_result,
        )

        if not action_result.ok and not self._is_observed_presence_state(
            state_id, normalized_expected
        ):
            return self._error_result(
                operation="match_state",
                action_result=action_result,
                state_id=state_id,
                expected_state_ids=normalized_expected,
                timing=timing,
                raw_details=raw_details,
            )

        if is_authoritative_match:
            return UIStateObservationResult.matched(
                operation="match_state",
                state_id=state_id,
                platform="native",
                expected_state_ids=normalized_expected,
                message=action_result.message,
                evidence=evidence,
                timing=timing,
                raw_details=raw_details,
            )
        return UIStateObservationResult.no_match(
            operation="match_state",
            state_id=state_id,
            platform="native",
            expected_state_ids=normalized_expected,
            message=f"detected stage '{state_id}' did not match expected states",
            evidence=evidence,
            timing=timing,
            raw_details=raw_details,
        )

    def wait_until(
        self,
        context: ExecutionContext,
        *,
        expected_state_ids: Sequence[str],
        timeout_ms: int = 15000,
        interval_ms: int = 500,
    ) -> UIStateObservationResult:
        normalized_expected = self._normalize_expected_state_ids(expected_state_ids)
        if not normalized_expected:
            return self._invalid_params_result(
                operation="wait_until",
                message="expected_state_ids is required",
                expected_state_ids=(),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
            )

        started_at = time.monotonic()
        context.check_cancelled()
        if self._state_profile.wait_action is None:
            return self._invalid_params_result(
                operation="wait_until",
                message=(
                    f"state profile '{self._state_profile.state_profile_id}' "
                    "does not support wait_until"
                ),
                expected_state_ids=normalized_expected,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
            )

        context.check_cancelled()
        action_result = self._state_profile.wait_action(
            self._wait_action_params(
                target_stages=list(normalized_expected),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
            ),
            context,
        )
        context.check_cancelled()
        finished_at = time.monotonic()
        attempt = int(action_result.data.get("attempt", 0) or 0)
        samples = attempt
        timing = self._timing(
            started_at=started_at,
            finished_at=finished_at,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            attempt=attempt,
            samples=samples,
            elapsed_ms=int(action_result.data.get("elapsed_ms", 0) or 0),
        )
        state_id = self._state_id_from_action_result(action_result)
        evidence = self._build_evidence(state_id, normalized_expected, matched=action_result.ok)
        raw_details = self._build_raw_details(
            state_id=state_id,
            expected_state_ids=normalized_expected,
            action_result=action_result,
        )

        if action_result.ok:
            return UIStateObservationResult.matched(
                operation="wait_until",
                state_id=state_id,
                platform="native",
                expected_state_ids=normalized_expected,
                evidence=evidence,
                timing=timing,
                raw_details=raw_details,
            )
        if action_result.code == "stage_timeout":
            return UIStateObservationResult.timeout(
                operation="wait_until",
                state_id=state_id,
                platform="native",
                expected_state_ids=normalized_expected,
                message=action_result.message,
                evidence=evidence,
                timing=timing,
                raw_details=raw_details,
            )
        return self._error_result(
            operation="wait_until",
            action_result=action_result,
            state_id=state_id,
            expected_state_ids=normalized_expected,
            timing=timing,
        )

    def observe_transition(
        self,
        context: ExecutionContext,
        *,
        from_state_ids: Sequence[str] | None = None,
        to_state_ids: Sequence[str] | None = None,
        timeout_ms: int = 15000,
        interval_ms: int = 500,
    ) -> UIStateObservationResult:
        normalized_from = self._normalize_expected_state_ids(from_state_ids or ())
        normalized_to = self._normalize_expected_state_ids(to_state_ids or ())
        if not normalized_from and not normalized_to:
            return self._invalid_params_result(
                operation="observe_transition",
                message="from_state_ids or to_state_ids is required",
                expected_state_ids=(),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
            )

        started_at = time.monotonic()
        deadline = started_at + (max(timeout_ms, 0) / 1000.0)
        attempt = 0
        previous_state = "unknown"
        saw_previous = False

        while time.monotonic() <= deadline:
            attempt += 1
            match_result: UIStateObservationResult = self.match_state(
                context,
                expected_state_ids=self._state_profile.supported_state_ids,
                timeout_ms=timeout_ms,
            )
            match_result_payload = cast(dict[str, object], match_result.model_dump(mode="python"))
            state_payload = cast(dict[str, object], match_result_payload.get("state", {}))
            current_state = self._state_profile.normalize_state_id(
                cast(str, state_payload.get("state_id", "unknown"))
            )
            if not match_result.ok and match_result.code not in {"no_match"}:
                timing = self._timing(
                    started_at=started_at,
                    finished_at=time.monotonic(),
                    timeout_ms=timeout_ms,
                    interval_ms=interval_ms,
                    attempt=attempt,
                    samples=attempt,
                )
                raw_details = self._build_raw_details(
                    state_id=current_state,
                    expected_state_ids=normalized_to,
                    action_result=match_result.to_action_result(),
                    extra={
                        "from_state_ids": list(normalized_from),
                        "to_state_ids": list(normalized_to),
                    },
                )
                return self._error_result(
                    operation="observe_transition",
                    action_result=match_result.to_action_result(),
                    state_id=current_state,
                    expected_state_ids=normalized_to,
                    timing=timing,
                    raw_details=raw_details,
                )

            if saw_previous:
                from_matches = not normalized_from or previous_state in normalized_from
                to_matches = not normalized_to or current_state in normalized_to
                if previous_state != current_state and from_matches and to_matches:
                    finished_at = time.monotonic()
                    timing = self._timing(
                        started_at=started_at,
                        finished_at=finished_at,
                        timeout_ms=timeout_ms,
                        interval_ms=interval_ms,
                        attempt=attempt,
                        samples=attempt,
                    )
                    evidence = UIStateEvidence(
                        summary=f"observed native transition {previous_state} -> {current_state}",
                        text=current_state,
                        matched=[current_state] if current_state in normalized_to else [],
                        missing=[state for state in normalized_to if state != current_state],
                        confidence=1.0 if current_state != "unknown" else 0.0,
                    )
                    transition = build_transition(
                        from_state={"state_id": previous_state},
                        to_state={"state_id": current_state},
                        changed=True,
                    )
                    return UIStateObservationResult(
                        ok=True,
                        code="ok",
                        operation="observe_transition",
                        status="transition_observed",
                        platform="native",
                        state=UIStateIdentity(state_id=current_state),
                        expected_state_ids=list(normalized_to),
                        evidence=evidence,
                        timing=timing,
                        raw_details={
                            **self._profile_identity_details(),
                            "stage": current_state,
                            "attempt": attempt,
                            "elapsed_ms": timing.elapsed_ms,
                            "target_stages": list(normalized_to),
                            "from_state_ids": list(normalized_from),
                            "to_state_ids": list(normalized_to),
                        },
                        transition=transition,
                    )

            previous_state = current_state
            saw_previous = True
            time.sleep(max(0.05, interval_ms / 1000.0))

        finished_at = time.monotonic()
        timing = self._timing(
            started_at=started_at,
            finished_at=finished_at,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            attempt=attempt,
            samples=attempt,
        )
        return UIStateObservationResult.timeout(
            operation="observe_transition",
            state_id=previous_state,
            platform="native",
            expected_state_ids=normalized_to,
            message=f"transition timeout, last stage: {previous_state}",
            evidence=UIStateEvidence(
                summary=f"transition timeout after last native stage '{previous_state}'",
                text=previous_state,
                matched=[],
                missing=list(normalized_to),
                confidence=1.0 if previous_state != "unknown" else 0.0,
            ),
            timing=timing,
            raw_details={
                **self._profile_identity_details(),
                "stage": previous_state,
                "attempt": attempt,
                "elapsed_ms": timing.elapsed_ms,
                "target_stages": list(normalized_to),
                "from_state_ids": list(normalized_from),
                "to_state_ids": list(normalized_to),
            },
        )

    def _normalize_expected_state_ids(self, expected_state_ids: Sequence[str]) -> tuple[str, ...]:
        normalized = {
            self._state_profile.normalize_state_id(state_id)
            for state_id in expected_state_ids
            if str(state_id).strip()
        }
        return tuple(sorted(normalized))

    def _state_id_from_action_result(self, action_result: ActionResult) -> str:
        return self._state_profile.state_id_from_action_result(action_result)

    def _build_evidence(
        self,
        state_id: str,
        expected_state_ids: Sequence[str],
        *,
        matched: bool,
    ) -> UIStateEvidence:
        if matched:
            summary = (
                f"matched native {self._state_profile.display_name} "
                f"{self._state_profile.state_noun} '{state_id}'"
            )
        else:
            summary = (
                f"detected native {self._state_profile.display_name} "
                f"{self._state_profile.state_noun} '{state_id}'"
            )
        return UIStateEvidence(
            summary=summary,
            text=state_id,
            matched=[state_id] if matched else [],
            missing=[candidate for candidate in expected_state_ids if candidate != state_id],
            confidence=1.0 if state_id != "unknown" else 0.0,
        )

    def _build_raw_details(
        self,
        *,
        state_id: str,
        expected_state_ids: Sequence[str],
        action_result: ActionResult,
        extra: dict[str, object] | None = None,
    ) -> dict[str, object]:
        raw_details: dict[str, object] = {
            **self._profile_identity_details(),
            "supported_state_ids": list(self._state_profile.supported_state_ids),
            "stage": state_id,
            "attempt": int(
                action_result.data.get("attempt", 1 if action_result.code == "ok" else 0) or 0
            ),
            "elapsed_ms": int(action_result.data.get("elapsed_ms", 0) or 0),
            "target_stages": list(expected_state_ids),
        }
        if action_result.code != "ok":
            raw_details["error_code"] = action_result.code
        action_data = cast(dict[str, object], action_result.data)
        for key, value in action_data.items():
            raw_details[key] = value
        if isinstance(action_data.get("targets"), list):
            targets = cast(list[object], action_data["targets"])
            raw_details["target"] = targets[0] if targets else None
        if isinstance(action_data.get("candidates"), list):
            candidates = cast(list[object], action_data["candidates"])
            raw_details["candidate"] = candidates[0] if candidates else None
        if action_result.code != "ok":
            raw_details["legacy_code"] = action_result.code
        if extra:
            for key, value in extra.items():
                raw_details[key] = value
        return raw_details

    def _profile_identity_details(self) -> dict[str, str]:
        return build_native_state_identity_details(
            self._state_profile,
            include_legacy_aliases=True,
        )

    def _is_observed_presence_state(self, state_id: str, expected_state_ids: Sequence[str]) -> bool:
        return (
            is_presence_style_profile(self._state_profile)
            and state_id == "missing"
            and state_id in expected_state_ids
        )

    def _error_result(
        self,
        *,
        operation: UIStateOperation,
        action_result: ActionResult,
        state_id: str,
        expected_state_ids: Sequence[str],
        timing: UIStateTiming,
        raw_details: dict[str, object] | None = None,
    ) -> UIStateObservationResult:
        return build_error_result(
            operation=operation,
            code=action_result.code,
            message=action_result.message,
            platform="native",
            state_id=state_id,
            expected_state_ids=expected_state_ids,
            evidence=UIStateEvidence(
                summary=action_result.message or action_result.code,
                text=state_id,
                matched=[],
                missing=list(expected_state_ids),
                confidence=0.0,
            ),
            timing=timing,
            raw_details=raw_details
            or self._build_raw_details(
                state_id=state_id,
                expected_state_ids=expected_state_ids,
                action_result=action_result,
            ),
        )

    def _invalid_params_result(
        self,
        *,
        operation: UIStateOperation,
        message: str,
        expected_state_ids: Sequence[str],
        timeout_ms: int | None,
        interval_ms: int | None = None,
    ) -> UIStateObservationResult:
        started_at = time.monotonic()
        finished_at = time.monotonic()
        timing = self._timing(
            started_at=started_at,
            finished_at=finished_at,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
        )
        return build_error_result(
            operation=operation,
            code="invalid_params",
            message=message,
            platform="native",
            expected_state_ids=expected_state_ids,
            evidence=UIStateEvidence(
                summary=message, matched=[], missing=list(expected_state_ids), confidence=0.0
            ),
            timing=timing,
            raw_details={
                **self._profile_identity_details(),
                "supported_state_ids": list(self._state_profile.supported_state_ids),
                "stage": "unknown",
                "attempt": 0,
                "elapsed_ms": 0,
                "target_stages": list(expected_state_ids),
                "error_code": "invalid_params",
            },
        )

    def _timing(
        self,
        *,
        started_at: float,
        finished_at: float,
        timeout_ms: int | None,
        interval_ms: int | None = None,
        attempt: int = 0,
        samples: int = 0,
        elapsed_ms: int | None = None,
    ) -> UIStateTiming:
        return build_timing(
            started_at=started_at,
            started_tick=started_at,
            finished_at=finished_at,
            finished_tick=finished_at,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            attempt=attempt,
            samples=samples,
            elapsed_ms=elapsed_ms,
        )

    def _match_action_params(self, *, timeout_ms: int | None) -> dict[str, object]:
        params = dict(self._action_params)
        if timeout_ms is not None:
            _ = params.setdefault("timeout_ms", timeout_ms)
        return params

    def _wait_action_params(
        self, *, target_stages: list[str], timeout_ms: int, interval_ms: int
    ) -> dict[str, object]:
        params = dict(self._action_params)
        params.update(
            {
                "target_stages": target_stages,
                "timeout_ms": timeout_ms,
                "interval_ms": interval_ms,
            }
        )
        return params
