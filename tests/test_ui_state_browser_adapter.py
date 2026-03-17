# pyright: reportUnknownMemberType=false, reportAny=false

from __future__ import annotations

from typing import Protocol, cast

from engine.models.runtime import ExecutionContext
from engine.ui_state_browser_service import BrowserUIStateService


class FakeBrowser:
    def __init__(
        self,
        *,
        available: bool = True,
        error: str = "",
        error_code: str = "",
        existing: set[str] | None = None,
        html: str = "",
        url: str = "",
        wait_result: bool = False,
    ) -> None:
        self.available: bool = available
        self.error: str = error
        self.error_code: str = error_code
        self._existing: set[str] = existing or set()
        self._html: str = html
        self._url: str = url
        self._wait_result: bool = wait_result
        self.wait_calls: list[tuple[str, int]] = []

    def exists(self, selector: str) -> bool:
        return selector in self._existing

    def html(self) -> str:
        return self._html

    def current_url(self) -> str:
        return self._url

    def wait_url_contains(self, fragment: str, timeout_seconds: int) -> bool:
        self.wait_calls.append((fragment, timeout_seconds))
        return self._wait_result


class MonkeyPatchLike(Protocol):
    def setattr(self, target: str, value: object) -> None: ...


def test_browser_ui_state_adapter_matches_exists_and_keeps_lazy_context(
    monkeypatch: MonkeyPatchLike,
) -> None:
    created: list[FakeBrowser] = []

    def _fake_browser_client_class():
        class _Factory(FakeBrowser):
            def __init__(self):
                super().__init__(existing={"#login"}, url="https://example.com/login")
                created.append(self)

        return _Factory

    monkeypatch.setattr(
        "engine.ui_state_browser_service._load_browser_client_class", _fake_browser_client_class
    )
    service = BrowserUIStateService()
    context = ExecutionContext(payload={})

    result = service.match_state(context, expected_state_ids=["exists:#login"])

    assert result.ok is True
    assert result.status == "matched"
    assert result.state.state_id == "exists:#login"
    assert result.evidence.selector == "#login"
    assert result.evidence.url == "https://example.com/login"
    assert context.browser is created[0]


def test_browser_ui_state_adapter_matches_html() -> None:
    service = BrowserUIStateService()
    context = ExecutionContext(payload={})
    context.browser = FakeBrowser(html="<body>Welcome Home</body>", url="https://example.com/home")

    result = service.match_state(context, expected_state_ids=["html:welcome home"])

    assert result.ok is True
    assert result.state.state_id == "html:welcome home"
    assert result.evidence.text == "welcome home"
    assert result.evidence.url == "https://example.com/home"
    observations = cast(list[dict[str, object]], result.raw_details["observations"])
    assert observations[0]["kind"] == "html"


def test_browser_ui_state_adapter_matches_url_via_wait_primitive() -> None:
    service = BrowserUIStateService()
    browser = FakeBrowser(url="https://example.com/home", wait_result=True)
    context = ExecutionContext(payload={})
    context.browser = browser

    result = service.wait_until(
        context, expected_state_ids=["url:/home"], timeout_ms=2000, interval_ms=250
    )

    assert result.ok is True
    assert result.operation == "wait_until"
    assert result.state.state_id == "url:/home"
    assert result.evidence.url == "https://example.com/home"
    assert browser.wait_calls == [("/home", 2)]


def test_browser_ui_state_adapter_returns_no_match_without_mutating_context_vars() -> None:
    service = BrowserUIStateService()
    context = ExecutionContext(payload={})
    context.vars["sentinel"] = "keep"
    context.browser = FakeBrowser(
        existing={"#other"}, html="<body>Other</body>", url="https://example.com/login"
    )

    result = service.match_state(
        context, expected_state_ids=["exists:#missing", "html:welcome", "url:/home"]
    )

    assert result.ok is False
    assert result.code == "no_match"
    assert result.status == "no_match"
    assert result.evidence.missing == ["/home"]
    assert context.vars == {"sentinel": "keep"}
    assert context.last_result is None


def test_browser_ui_state_adapter_returns_timeout_for_unmet_url_wait() -> None:
    service = BrowserUIStateService()
    browser = FakeBrowser(url="https://example.com/login", wait_result=False)
    context = ExecutionContext(payload={})
    context.browser = browser

    result = service.wait_until(
        context, expected_state_ids=["url:/home"], timeout_ms=3000, interval_ms=200
    )

    assert result.ok is False
    assert result.code == "timeout"
    assert result.status == "timeout"
    assert result.evidence.url == "https://example.com/login"
    assert result.evidence.missing == ["/home"]
    assert browser.wait_calls == [("/home", 3)]


def test_browser_ui_state_adapter_returns_unavailable_error_without_caching_browser(
    monkeypatch: MonkeyPatchLike,
) -> None:
    def _fake_browser_client_class():
        class _Factory(FakeBrowser):
            def __init__(self):
                super().__init__(
                    available=False,
                    error="browser runtime missing",
                    error_code="browser_unavailable",
                )

        return _Factory

    monkeypatch.setattr(
        "engine.ui_state_browser_service._load_browser_client_class", _fake_browser_client_class
    )
    service = BrowserUIStateService()
    context = ExecutionContext(payload={})

    result = service.match_state(context, expected_state_ids=["exists:#login"])

    assert result.ok is False
    assert result.code == "browser_unavailable"
    assert result.status == "unknown"
    assert result.message == "browser runtime missing"
    assert result.timing.attempt == 0
    assert result.timing.samples == 0
    assert context.browser is None
