# pyright: reportUnknownMemberType=false

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Callable, cast

from engine.actions import state_actions
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.ui_state import (
    X_LOGIN_STAGE_VALUES,
    UIStateEvidence,
    UIStateObservationResult,
    UIStateTiming,
    UIStateTransition,
    normalize_x_login_stage,
)
@dataclass(frozen=True)
class NativeStateBinding:
    binding_id: str
    display_name: str
    state_noun: str
    supported_state_ids: tuple[str, ...]
    normalize_state_id: Callable[[str], str]
    state_id_from_action_result: Callable[[ActionResult], str]
    match_action: Callable[[dict[str, object], ExecutionContext], ActionResult]
    wait_action: Callable[[dict[str, object], ExecutionContext], ActionResult] | None = None


def _normalize_supported_state(state_id: str, supported_state_ids: Sequence[str]) -> str:
    candidate = str(state_id or "unknown").strip() or "unknown"
    return candidate if candidate in supported_state_ids else "unknown"


def _extract_x_login_state_id(action_result: ActionResult) -> str:
    return normalize_x_login_stage(str(action_result.data.get("stage", "unknown") or "unknown"))


def _extract_presence_state_id(*, present_state_id: str, missing_codes: Sequence[str]) -> Callable[[ActionResult], str]:
    missing_code_set = {str(code).strip() for code in missing_codes if str(code).strip()}

    def _extract(action_result: ActionResult) -> str:
        if action_result.ok:
            return present_state_id
        if action_result.code in missing_code_set:
            return "missing"
        return "unknown"

    return _extract


def _is_presence_style_binding(binding: NativeStateBinding) -> bool:
    return "available" in binding.supported_state_ids and "missing" in binding.supported_state_ids


_X_LOGIN_BINDING = NativeStateBinding(
    binding_id="x_login",
    display_name="X login",
    state_noun="stage",
    supported_state_ids=X_LOGIN_STAGE_VALUES,
    normalize_state_id=normalize_x_login_stage,
    state_id_from_action_result=_extract_x_login_state_id,
    match_action=state_actions.detect_x_login_stage,
    wait_action=state_actions.wait_x_login_stage,
)

_DM_UNREAD_BINDING = NativeStateBinding(
    binding_id="dm_unread",
    display_name="DM unread conversation",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: _normalize_supported_state(state_id, ("available", "missing", "unknown")),
    state_id_from_action_result=_extract_presence_state_id(
        present_state_id="available",
        missing_codes=("unread_dm_missing",),
    ),
    match_action=state_actions.extract_unread_dm_targets,
)

_DM_LAST_MESSAGE_BINDING = NativeStateBinding(
    binding_id="dm_last_message",
    display_name="DM last message",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: _normalize_supported_state(state_id, ("available", "missing", "unknown")),
    state_id_from_action_result=_extract_presence_state_id(
        present_state_id="available",
        missing_codes=("dm_message_missing",),
    ),
    match_action=state_actions.extract_dm_last_message,
)

_DM_LAST_OUTBOUND_BINDING = NativeStateBinding(
    binding_id="dm_last_outbound_message",
    display_name="DM last outbound message",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: _normalize_supported_state(state_id, ("available", "missing", "unknown")),
    state_id_from_action_result=_extract_presence_state_id(
        present_state_id="available",
        missing_codes=("dm_outbound_message_missing",),
    ),
    match_action=state_actions.extract_dm_last_outbound_message,
)

_SEARCH_CANDIDATES_BINDING = NativeStateBinding(
    binding_id="search_candidates",
    display_name="search candidates",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: _normalize_supported_state(state_id, ("available", "missing", "unknown")),
    state_id_from_action_result=_extract_presence_state_id(
        present_state_id="available",
        missing_codes=("no_candidates",),
    ),
    match_action=state_actions.extract_search_candidates,
)

_BINDINGS: dict[str, NativeStateBinding] = {
    _X_LOGIN_BINDING.binding_id: _X_LOGIN_BINDING,
    _DM_UNREAD_BINDING.binding_id: _DM_UNREAD_BINDING,
    _DM_LAST_MESSAGE_BINDING.binding_id: _DM_LAST_MESSAGE_BINDING,
    _DM_LAST_OUTBOUND_BINDING.binding_id: _DM_LAST_OUTBOUND_BINDING,
    _SEARCH_CANDIDATES_BINDING.binding_id: _SEARCH_CANDIDATES_BINDING,
}


class NativeUIStateAdapter:
    def __init__(self, binding_id: str = "x_login", *, action_params: dict[str, object] | None = None) -> None:
        self._binding: NativeStateBinding
        self._action_params: dict[str, object]
        self._action_params = dict(action_params or {})
        try:
            self._binding = _BINDINGS[binding_id]
        except KeyError as exc:
            raise ValueError(f"unsupported native ui-state binding: {binding_id}") from exc

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
        action_result = self._binding.match_action(self._match_action_params(timeout_ms=timeout_ms), context)
        finished_at = time.monotonic()
        timing = self._timing(
            started_at=started_at,
            finished_at=finished_at,
            timeout_ms=timeout_ms,
            attempt=1 if action_result.code == "ok" else 0,
            samples=1 if action_result.code == "ok" else 0,
        )
        state_id = self._state_id_from_action_result(action_result)
        evidence = self._build_evidence(state_id, normalized_expected, matched=state_id in normalized_expected)
        raw_details = self._build_raw_details(
            state_id=state_id,
            expected_state_ids=normalized_expected,
            action_result=action_result,
        )

        if not action_result.ok and not self._is_observed_presence_state(state_id, normalized_expected):
            return self._error_result(
                operation="match_state",
                action_result=action_result,
                state_id=state_id,
                expected_state_ids=normalized_expected,
                timing=timing,
            )

        if state_id in normalized_expected:
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
        if self._binding.wait_action is None:
            return self._invalid_params_result(
                operation="wait_until",
                message=f"binding '{self._binding.binding_id}' does not support wait_until",
                expected_state_ids=normalized_expected,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
            )

        action_result = self._binding.wait_action(
            self._wait_action_params(
                target_stages=list(normalized_expected),
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
            ),
            context,
        )
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
                expected_state_ids=self._binding.supported_state_ids,
                timeout_ms=timeout_ms,
            )
            match_result_payload = cast(dict[str, object], match_result.model_dump(mode="python"))
            state_payload = cast(dict[str, object], match_result_payload.get("state", {}))
            current_state = self._binding.normalize_state_id(cast(str, state_payload.get("state_id", "unknown")))
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
                    extra={"from_state_ids": list(normalized_from), "to_state_ids": list(normalized_to)},
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
                    return UIStateObservationResult(
                        ok=True,
                        code="ok",
                        operation="observe_transition",
                        status="transition_observed",
                        platform="native",
                        state={"state_id": current_state},
                        expected_state_ids=list(normalized_to),
                        evidence=evidence,
                        timing=timing,
                        raw_details={
                            "binding_id": self._binding.binding_id,
                            "binding_name": self._binding.display_name,
                            "stage": current_state,
                            "attempt": attempt,
                            "elapsed_ms": timing.elapsed_ms,
                            "target_stages": list(normalized_to),
                            "from_state_ids": list(normalized_from),
                            "to_state_ids": list(normalized_to),
                        },
                        transition=UIStateTransition(
                            from_state={"state_id": previous_state},
                            to_state={"state_id": current_state},
                            changed=True,
                        ),
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
                "binding_id": self._binding.binding_id,
                "binding_name": self._binding.display_name,
                "stage": previous_state,
                "attempt": attempt,
                "elapsed_ms": timing.elapsed_ms,
                "target_stages": list(normalized_to),
                "from_state_ids": list(normalized_from),
                "to_state_ids": list(normalized_to),
            },
        )

    def _normalize_expected_state_ids(self, expected_state_ids: Sequence[str]) -> tuple[str, ...]:
        normalized = {self._binding.normalize_state_id(state_id) for state_id in expected_state_ids if str(state_id).strip()}
        return tuple(sorted(normalized))

    def _state_id_from_action_result(self, action_result: ActionResult) -> str:
        return self._binding.state_id_from_action_result(action_result)

    def _build_evidence(
        self,
        state_id: str,
        expected_state_ids: Sequence[str],
        *,
        matched: bool,
    ) -> UIStateEvidence:
        if matched:
            summary = f"matched native {self._binding.display_name} {self._binding.state_noun} '{state_id}'"
        else:
            summary = f"detected native {self._binding.display_name} {self._binding.state_noun} '{state_id}'"
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
            "binding_id": self._binding.binding_id,
            "binding_name": self._binding.display_name,
            "supported_state_ids": list(self._binding.supported_state_ids),
            "stage": state_id,
            "attempt": int(action_result.data.get("attempt", 1 if action_result.code == "ok" else 0) or 0),
            "elapsed_ms": int(action_result.data.get("elapsed_ms", 0) or 0),
            "target_stages": list(expected_state_ids),
        }
        if action_result.code != "ok":
            raw_details["error_code"] = action_result.code
        action_data = cast(dict[str, object], action_result.data)
        for key, value in action_data.items():
            raw_details[key] = value
        if self._binding.binding_id == "dm_unread" and isinstance(action_data.get("targets"), list):
            targets = cast(list[object], action_data["targets"])
            raw_details["target"] = targets[0] if targets else None
        if action_result.code != "ok":
            raw_details["legacy_code"] = action_result.code
        if extra:
            for key, value in extra.items():
                raw_details[key] = value
        return raw_details

    def _is_observed_presence_state(self, state_id: str, expected_state_ids: Sequence[str]) -> bool:
        return _is_presence_style_binding(self._binding) and state_id == "missing" and state_id in expected_state_ids

    def _error_result(
        self,
        *,
        operation: str,
        action_result: ActionResult,
        state_id: str,
        expected_state_ids: Sequence[str],
        timing: UIStateTiming,
        raw_details: dict[str, object] | None = None,
    ) -> UIStateObservationResult:
        return UIStateObservationResult(
            ok=False,
            code=action_result.code,
            message=action_result.message,
            operation=operation,
            status="unknown",
            platform="native",
            state={"state_id": state_id},
            expected_state_ids=list(expected_state_ids),
            evidence=UIStateEvidence(
                summary=action_result.message or action_result.code,
                text=state_id,
                matched=[],
                missing=list(expected_state_ids),
                confidence=0.0,
            ),
            timing=timing,
            raw_details=raw_details or self._build_raw_details(
                state_id=state_id,
                expected_state_ids=expected_state_ids,
                action_result=action_result,
            ),
        )

    def _invalid_params_result(
        self,
        *,
        operation: str,
        message: str,
        expected_state_ids: Sequence[str],
        timeout_ms: int | None,
        interval_ms: int | None = None,
    ) -> UIStateObservationResult:
        started_at = time.monotonic()
        finished_at = time.monotonic()
        return UIStateObservationResult(
            ok=False,
            code="invalid_params",
            message=message,
            operation=operation,
            status="unknown",
            platform="native",
            state={"state_id": "unknown"},
            expected_state_ids=list(expected_state_ids),
            evidence=UIStateEvidence(summary=message, matched=[], missing=list(expected_state_ids), confidence=0.0),
            timing=self._timing(
                started_at=started_at,
                finished_at=finished_at,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
            ),
            raw_details={
                "binding_id": self._binding.binding_id,
                "binding_name": self._binding.display_name,
                "supported_state_ids": list(self._binding.supported_state_ids),
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
        elapsed = elapsed_ms if elapsed_ms is not None else int(max(0.0, finished_at - started_at) * 1000)
        return UIStateTiming(
            started_at=started_at,
            finished_at=finished_at,
            elapsed_ms=max(0, elapsed),
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            attempt=attempt,
            samples=samples,
        )

    def _match_action_params(self, *, timeout_ms: int | None) -> dict[str, object]:
        params = dict(self._action_params)
        if timeout_ms is not None:
            _ = params.setdefault("timeout_ms", timeout_ms)
        return params

    def _wait_action_params(self, *, target_stages: list[str], timeout_ms: int, interval_ms: int) -> dict[str, object]:
        params = dict(self._action_params)
        params.update(
            {
                "target_stages": target_stages,
                "timeout_ms": timeout_ms,
                "interval_ms": interval_ms,
            }
        )
        return params
