from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.models.runtime import ActionResult

UIStateOperation = Literal["match_state", "wait_until", "observe_transition"]
UIStatePlatform = Literal["native", "browser", "unknown"]
UIStateMatchStatus = Literal["matched", "no_match", "timeout", "transition_observed", "unknown"]

LOGIN_STAGE_VALUES: tuple[str, ...] = (
    "home",
    "two_factor",
    "captcha",
    "password",
    "account",
    "login_entry",
    "unknown",
)


class UIStateIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_id: str = "unknown"
    display_name: str | None = None
    group: str | None = None
    aliases: list[str] = Field(default_factory=list)


class UIStateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    selector: str | None = None
    text: str | None = None
    url: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class UIStateTiming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    started_at: float | None = None
    finished_at: float | None = None
    elapsed_ms: int = 0
    timeout_ms: int | None = None
    interval_ms: int | None = None
    attempt: int = 0
    samples: int = 0


class UIStateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_state: UIStateIdentity = Field(default_factory=UIStateIdentity)
    to_state: UIStateIdentity = Field(default_factory=UIStateIdentity)
    changed: bool = False


class UIStateObservationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    code: str = "ok"
    message: str = ""
    operation: UIStateOperation
    status: UIStateMatchStatus
    platform: UIStatePlatform = "unknown"
    state: UIStateIdentity = Field(default_factory=UIStateIdentity)
    expected_state_ids: list[str] = Field(default_factory=list)
    evidence: UIStateEvidence = Field(default_factory=UIStateEvidence)
    timing: UIStateTiming = Field(default_factory=UIStateTiming)
    raw_details: dict[str, object] = Field(default_factory=dict)
    transition: UIStateTransition | None = None

    def to_action_result(self) -> ActionResult:
        return ActionResult(
            ok=self.ok, code=self.code, message=self.message, data=self.model_dump(mode="python")
        )

    @classmethod
    def matched(
        cls,
        *,
        operation: UIStateOperation,
        state_id: str,
        platform: UIStatePlatform = "unknown",
        expected_state_ids: Sequence[str] | None = None,
        message: str = "",
        evidence: UIStateEvidence | None = None,
        timing: UIStateTiming | None = None,
        raw_details: dict[str, object] | None = None,
    ) -> UIStateObservationResult:
        return cls(
            ok=True,
            code="ok",
            message=message,
            operation=operation,
            status="matched",
            platform=platform,
            state=UIStateIdentity(state_id=state_id),
            expected_state_ids=list(expected_state_ids or []),
            evidence=evidence or UIStateEvidence(),
            timing=timing or UIStateTiming(),
            raw_details=dict(raw_details or {}),
        )

    @classmethod
    def no_match(
        cls,
        *,
        operation: UIStateOperation,
        state_id: str = "unknown",
        platform: UIStatePlatform = "unknown",
        expected_state_ids: Sequence[str] | None = None,
        message: str = "state did not match",
        evidence: UIStateEvidence | None = None,
        timing: UIStateTiming | None = None,
        raw_details: dict[str, object] | None = None,
    ) -> UIStateObservationResult:
        return cls(
            ok=False,
            code="no_match",
            message=message,
            operation=operation,
            status="no_match",
            platform=platform,
            state=UIStateIdentity(state_id=state_id),
            expected_state_ids=list(expected_state_ids or []),
            evidence=evidence or UIStateEvidence(),
            timing=timing or UIStateTiming(),
            raw_details=dict(raw_details or {}),
        )

    @classmethod
    def timeout(
        cls,
        *,
        operation: UIStateOperation,
        state_id: str = "unknown",
        platform: UIStatePlatform = "unknown",
        expected_state_ids: Sequence[str] | None = None,
        message: str = "timed out waiting for state",
        evidence: UIStateEvidence | None = None,
        timing: UIStateTiming | None = None,
        raw_details: dict[str, object] | None = None,
    ) -> UIStateObservationResult:
        return cls(
            ok=False,
            code="timeout",
            message=message,
            operation=operation,
            status="timeout",
            platform=platform,
            state=UIStateIdentity(state_id=state_id),
            expected_state_ids=list(expected_state_ids or []),
            evidence=evidence or UIStateEvidence(),
            timing=timing or UIStateTiming(),
            raw_details=dict(raw_details or {}),
        )


def normalize_login_stage(stage: str) -> str:
    candidate = str(stage or "unknown").strip() or "unknown"
    return candidate if candidate in LOGIN_STAGE_VALUES else "unknown"
