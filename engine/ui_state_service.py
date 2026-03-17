from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from engine.models.runtime import ExecutionContext
from engine.models.ui_state import UIStateObservationResult


@runtime_checkable
class UIStateService(Protocol):
    """Read-only UI state observation contract.

    Implementations classify current UI state, wait for an expected state,
    or observe a state transition. This boundary does not own recovery,
    retries beyond a direct polling call, fallback plans, or background
    watchers.
    """

    def match_state(
        self,
        context: ExecutionContext,
        *,
        expected_state_ids: Sequence[str],
        timeout_ms: int | None = None,
    ) -> UIStateObservationResult: ...

    def wait_until(
        self,
        context: ExecutionContext,
        *,
        expected_state_ids: Sequence[str],
        timeout_ms: int = 15000,
        interval_ms: int = 500,
    ) -> UIStateObservationResult: ...

    def observe_transition(
        self,
        context: ExecutionContext,
        *,
        from_state_ids: Sequence[str] | None = None,
        to_state_ids: Sequence[str] | None = None,
        timeout_ms: int = 15000,
        interval_ms: int = 500,
    ) -> UIStateObservationResult: ...
