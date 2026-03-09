# pyright: reportImplicitOverride=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional, Protocol, cast

from engine.models.runtime import ExecutionContext
from engine.models.ui_state import (
    UIStateEvidence,
    UIStateObservationResult,
    UIStateOperation,
    UIStatePlatform,
    UIStateTiming,
    UIStateTransition,
)
from engine.ui_state_helpers import (
    build_error_result,
    build_timing,
    build_transition,
    copy_result,
    poll_until_result,
)
from engine.ui_state_service import UIStateService


class BrowserObserver(Protocol):
    available: bool
    error: str
    error_code: str

    def exists(self, selector: str) -> bool: ...

    def html(self) -> str: ...

    def current_url(self) -> str: ...

    def wait_url_contains(self, fragment: str, timeout_seconds: int) -> bool: ...


def _load_browser_client_class() -> type[BrowserObserver]:
    from hardware_adapters.browser_client import BrowserClient

    return cast(type[BrowserObserver], BrowserClient)


@dataclass(frozen=True)
class _BrowserStateSpec:
    kind: str
    value: str


@dataclass(frozen=True)
class _BrowserStateMatch:
    state_id: str
    matched: bool
    evidence: UIStateEvidence
    raw_details: dict[str, object]


class BrowserUIStateService(UIStateService):
    platform: UIStatePlatform = "browser"

    def match_state(
        self,
        context: ExecutionContext,
        *,
        expected_state_ids: Sequence[str],
        timeout_ms: Optional[int] = None,
    ) -> UIStateObservationResult:
        started_at = time.time()
        started_tick = time.monotonic()
        expected_ids = list(expected_state_ids)
        browser, unavailable = self._get_browser(context, operation="match_state", expected_state_ids=expected_ids)
        if unavailable is not None:
            return unavailable

        assert browser is not None
        observations: list[dict[str, object]] = []
        last_match: Optional[_BrowserStateMatch] = None

        for state_id in expected_ids:
            try:
                current = self._observe_state(browser, state_id)
            except Exception as exc:
                return self._error_result(
                    operation="match_state",
                    code="browser_observation_error",
                    message=str(exc),
                    expected_state_ids=expected_ids,
                    started_at=started_at,
                    started_tick=started_tick,
                    timeout_ms=timeout_ms,
                    attempt=1,
                    samples=1,
                    raw_details={"state_id": state_id, "error": str(exc)},
                )
            observations.append(current.raw_details)
            last_match = current
            if current.matched:
                return UIStateObservationResult.matched(
                    operation="match_state",
                    state_id=state_id,
                    platform=self.platform,
                    expected_state_ids=expected_ids,
                    message=f"matched browser state {state_id}",
                    evidence=current.evidence,
                    timing=self._timing(
                        started_at=started_at,
                        started_tick=started_tick,
                        timeout_ms=timeout_ms,
                        attempt=1,
                        samples=1,
                    ),
                    raw_details={"observations": observations},
                )

        evidence = last_match.evidence if last_match is not None else UIStateEvidence(summary="no browser states configured")
        return UIStateObservationResult.no_match(
            operation="match_state",
            platform=self.platform,
            expected_state_ids=expected_ids,
            message="browser state did not match any expected observation",
            evidence=evidence,
            timing=self._timing(started_at=started_at, started_tick=started_tick, timeout_ms=timeout_ms, attempt=1, samples=1),
            raw_details={"observations": observations},
        )

    def wait_until(
        self,
        context: ExecutionContext,
        *,
        expected_state_ids: Sequence[str],
        timeout_ms: int = 15000,
        interval_ms: int = 500,
    ) -> UIStateObservationResult:
        started_at = time.time()
        started_tick = time.monotonic()
        expected_ids = list(expected_state_ids)
        browser, unavailable = self._get_browser(context, operation="wait_until", expected_state_ids=expected_ids)
        if unavailable is not None:
            return unavailable

        assert browser is not None
        url_spec = self._single_url_spec(expected_ids)

        if url_spec is not None:
            if browser.wait_url_contains(url_spec.value, timeout_seconds=max(1, int(timeout_ms / 1000))):
                current_url = self._safe_current_url(browser)
                return UIStateObservationResult.matched(
                    operation="wait_until",
                    state_id=f"url:{url_spec.value}",
                    platform=self.platform,
                    expected_state_ids=expected_ids,
                    message=f"browser url contains {url_spec.value}",
                    evidence=UIStateEvidence(
                        summary=f"current url contains {url_spec.value}",
                        text=url_spec.value,
                        url=current_url or None,
                        matched=[url_spec.value],
                    ),
                    timing=self._timing(
                        started_at=started_at,
                        started_tick=started_tick,
                        timeout_ms=timeout_ms,
                        interval_ms=interval_ms,
                        attempt=1,
                        samples=1,
                    ),
                    raw_details={"observations": [{"kind": "url", "target": url_spec.value, "current_url": current_url}]},
                )
            return UIStateObservationResult.timeout(
                operation="wait_until",
                platform=self.platform,
                expected_state_ids=expected_ids,
                message=f"browser url did not contain {url_spec.value} before timeout",
                evidence=UIStateEvidence(
                    summary=f"timed out waiting for url fragment {url_spec.value}",
                    text=url_spec.value,
                    url=self._safe_current_url(browser) or None,
                    missing=[url_spec.value],
                ),
                timing=self._timing(
                    started_at=started_at,
                    started_tick=started_tick,
                    timeout_ms=timeout_ms,
                    interval_ms=interval_ms,
                    attempt=1,
                    samples=1,
                ),
                raw_details={"observations": [{"kind": "url", "target": url_spec.value, "current_url": self._safe_current_url(browser)}]},
            )

        poll_outcome = poll_until_result(
            observe=lambda: self.match_state(context, expected_state_ids=expected_ids, timeout_ms=timeout_ms),
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            monotonic_now=time.monotonic,
            sleep=time.sleep,
        )
        timed_result = self._timing(
            started_at=started_at,
            started_tick=started_tick,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            attempt=poll_outcome.attempts,
            samples=poll_outcome.samples,
        )
        if not poll_outcome.timed_out:
            return self._copy_result(
                poll_outcome.result,
                operation="wait_until",
                timing=timed_result,
            )
        return UIStateObservationResult.timeout(
            operation="wait_until",
            platform=self.platform,
            expected_state_ids=expected_ids,
            message="timed out waiting for browser state",
            evidence=poll_outcome.result.evidence,
            timing=timed_result,
            raw_details=poll_outcome.result.raw_details,
        )

    def observe_transition(
        self,
        context: ExecutionContext,
        *,
        from_state_ids: Optional[Sequence[str]] = None,
        to_state_ids: Optional[Sequence[str]] = None,
        timeout_ms: int = 15000,
        interval_ms: int = 500,
    ) -> UIStateObservationResult:
        started_at = time.time()
        started_tick = time.monotonic()
        from_result: Optional[UIStateObservationResult] = None
        if from_state_ids:
            from_result = self.match_state(context, expected_state_ids=from_state_ids, timeout_ms=timeout_ms)
            if not from_result.ok:
                return self._copy_result(
                    from_result,
                    operation="observe_transition",
                    timing=self._timing(
                        started_at=started_at,
                        started_tick=started_tick,
                        timeout_ms=timeout_ms,
                        interval_ms=interval_ms,
                        attempt=1,
                        samples=1,
                    ),
                    transition=build_transition(changed=False),
                )

        if not to_state_ids:
            return self._error_result(
                operation="observe_transition",
                code="missing_target_states",
                message="observe_transition requires target browser states",
                expected_state_ids=[],
                started_at=started_at,
                started_tick=started_tick,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                attempt=0,
                samples=0,
                raw_details={},
            )

        to_result = self.wait_until(context, expected_state_ids=to_state_ids, timeout_ms=timeout_ms, interval_ms=interval_ms)
        transition = build_transition(
            from_state=(from_result.state if from_result is not None else None),
            to_state=to_result.state,
            changed=to_result.ok,
        )
        if not to_result.ok:
            return self._copy_result(to_result, operation="observe_transition", timing=to_result.timing, transition=transition)
        return UIStateObservationResult(
            ok=True,
            code="ok",
            message=to_result.message,
            operation="observe_transition",
            status="transition_observed",
            platform=self.platform,
            state=to_result.state,
            expected_state_ids=list(to_state_ids),
            evidence=to_result.evidence,
            timing=to_result.timing,
            raw_details=to_result.raw_details,
            transition=transition,
        )

    def _get_browser(
        self,
        context: ExecutionContext,
        *,
        operation: str,
        expected_state_ids: Sequence[str],
    ) -> tuple[BrowserObserver | None, UIStateObservationResult | None]:
        browser = cast(BrowserObserver | None, context.browser)
        if browser is not None:
            available = getattr(browser, "available", True)
            if not available:
                return None, self._error_result(
                    operation=operation,
                    code=getattr(browser, "error_code", "browser_unavailable") or "browser_unavailable",
                    message=getattr(browser, "error", "browser adapter unavailable") or "browser adapter unavailable",
                    expected_state_ids=expected_state_ids,
                    attempt=0,
                    samples=0,
                    raw_details={
                        "available": False,
                        "error_code": getattr(browser, "error_code", ""),
                        "error": getattr(browser, "error", ""),
                    },
                )
            return browser, None

        try:
            browser_client_cls = _load_browser_client_class()
            candidate = browser_client_cls()
        except Exception as exc:
            return None, self._error_result(
                operation=operation,
                code="browser_adapter_unavailable",
                message=str(exc),
                expected_state_ids=expected_state_ids,
                attempt=0,
                samples=0,
                raw_details={"available": False, "error": str(exc)},
            )

        if not getattr(candidate, "available", True):
            return None, self._error_result(
                operation=operation,
                code=getattr(candidate, "error_code", "browser_unavailable") or "browser_unavailable",
                message=getattr(candidate, "error", "browser adapter unavailable") or "browser adapter unavailable",
                expected_state_ids=expected_state_ids,
                attempt=0,
                samples=0,
                raw_details={
                    "available": False,
                    "error_code": getattr(candidate, "error_code", ""),
                    "error": getattr(candidate, "error", ""),
                },
            )

        context.browser = candidate
        return candidate, None

    def _observe_state(self, browser: BrowserObserver, state_id: str) -> _BrowserStateMatch:
        spec = self._parse_state_id(state_id)
        if spec is None:
            return _BrowserStateMatch(
                state_id=state_id,
                matched=False,
                evidence=UIStateEvidence(summary=f"unsupported browser state id {state_id}", missing=[state_id]),
                raw_details={"state_id": state_id, "supported": False},
            )

        if spec.kind == "exists":
            matched = bool(browser.exists(spec.value))
            return _BrowserStateMatch(
                state_id=state_id,
                matched=matched,
                evidence=UIStateEvidence(
                    summary=(f"selector {spec.value} exists" if matched else f"selector {spec.value} not found"),
                    selector=spec.value,
                    url=self._safe_current_url(browser) or None,
                    matched=[spec.value] if matched else [],
                    missing=[] if matched else [spec.value],
                ),
                raw_details={"kind": "exists", "target": spec.value, "matched": matched, "current_url": self._safe_current_url(browser)},
            )

        if spec.kind == "html":
            html = str(browser.html())
            matched = spec.value.lower() in html.lower()
            return _BrowserStateMatch(
                state_id=state_id,
                matched=matched,
                evidence=UIStateEvidence(
                    summary=(f"html contains {spec.value}" if matched else f"html missing {spec.value}"),
                    text=spec.value,
                    url=self._safe_current_url(browser) or None,
                    matched=[spec.value] if matched else [],
                    missing=[] if matched else [spec.value],
                ),
                raw_details={
                    "kind": "html",
                    "target": spec.value,
                    "matched": matched,
                    "current_url": self._safe_current_url(browser),
                    "html_length": len(html),
                },
            )

        current_url = self._safe_current_url(browser)
        matched = spec.value.lower() in current_url.lower()
        return _BrowserStateMatch(
            state_id=state_id,
            matched=matched,
            evidence=UIStateEvidence(
                summary=(f"url contains {spec.value}" if matched else f"url missing {spec.value}"),
                text=spec.value,
                url=current_url or None,
                matched=[spec.value] if matched else [],
                missing=[] if matched else [spec.value],
            ),
            raw_details={"kind": "url", "target": spec.value, "matched": matched, "current_url": current_url},
        )

    def _parse_state_id(self, state_id: str) -> Optional[_BrowserStateSpec]:
        kind, separator, value = str(state_id).partition(":")
        if separator != ":":
            return None
        kind = kind.strip().lower()
        value = value.strip()
        if kind not in {"exists", "html", "url"} or not value:
            return None
        return _BrowserStateSpec(kind=kind, value=value)

    def _single_url_spec(self, expected_state_ids: Sequence[str]) -> Optional[_BrowserStateSpec]:
        if len(expected_state_ids) != 1:
            return None
        spec = self._parse_state_id(expected_state_ids[0])
        if spec is None or spec.kind != "url":
            return None
        return spec

    def _safe_current_url(self, browser: BrowserObserver) -> str:
        try:
            return str(browser.current_url())
        except Exception:
            return ""

    def _copy_result(
        self,
        result: UIStateObservationResult,
        *,
        operation: UIStateOperation,
        timing: UIStateTiming,
        transition: Optional[UIStateTransition] = None,
    ) -> UIStateObservationResult:
        return copy_result(result, operation=operation, timing=timing, transition=transition)

    def _error_result(
        self,
        *,
        operation: UIStateOperation,
        code: str,
        message: str,
        expected_state_ids: Sequence[str],
        started_at: Optional[float] = None,
        started_tick: Optional[float] = None,
        timeout_ms: Optional[int] = None,
        interval_ms: Optional[int] = None,
        attempt: int = 0,
        samples: int = 0,
        raw_details: Optional[dict[str, object]] = None,
    ) -> UIStateObservationResult:
        if started_at is None:
            started_at = time.time()
        if started_tick is None:
            started_tick = time.monotonic()
        return build_error_result(
            operation=operation,
            code=code,
            message=message,
            platform=self.platform,
            expected_state_ids=expected_state_ids,
            timing=self._timing(
                started_at=started_at,
                started_tick=started_tick,
                timeout_ms=timeout_ms,
                interval_ms=interval_ms,
                attempt=attempt,
                samples=samples,
            ),
            raw_details=dict(raw_details or {}),
        )

    def _timing(
        self,
        *,
        started_at: float,
        started_tick: float,
        timeout_ms: Optional[int] = None,
        interval_ms: Optional[int] = None,
        attempt: int,
        samples: int,
    ) -> UIStateTiming:
        finished_at = time.time()
        finished_tick = time.monotonic()
        return build_timing(
            started_at=started_at,
            started_tick=started_tick,
            finished_at=finished_at,
            finished_tick=finished_tick,
            timeout_ms=timeout_ms,
            interval_ms=interval_ms,
            attempt=attempt,
            samples=samples,
        )
