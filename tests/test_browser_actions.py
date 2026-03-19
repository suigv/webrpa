from types import SimpleNamespace

from engine.actions import browser_actions
from engine.models.runtime import ExecutionContext


class _FailingBrowser:
    def __init__(self) -> None:
        self._page = SimpleNamespace(cookies=object())

    def input(self, selector: str, text: str) -> None:
        raise RuntimeError(f"missing selector: {selector} ({text})")


class _ExistsFailingBrowser:
    def __init__(self) -> None:
        self._page = SimpleNamespace()

    def exists(self, selector: str) -> bool:
        raise RuntimeError(f"lookup failed: {selector}")


def test_browser_input_surfaces_last_selector_error() -> None:
    context = ExecutionContext(payload={})
    context.browser = _FailingBrowser()

    result = browser_actions.browser_input(
        {"selectors": ["#first", "#second"], "text": "hello"},
        context,
    )

    assert result.ok is False
    assert result.code == "input_failed"
    assert "missing selector: #second (hello)" in result.message


def test_browser_exists_surfaces_last_selector_error() -> None:
    context = ExecutionContext(payload={})
    context.browser = _ExistsFailingBrowser()

    result = browser_actions.browser_exists({"selectors": ["#first", "#second"]}, context)

    assert result.ok is False
    assert result.code == "not_found"
    assert "lookup failed: #second" in result.message


def test_browser_add_cookies_rejects_unsupported_backend() -> None:
    context = ExecutionContext(payload={})
    context.browser = _FailingBrowser()

    result = browser_actions.browser_add_cookies(
        {"cookies": [{"name": "sid", "value": "abc"}]},
        context,
    )

    assert result.ok is False
    assert result.code == "cookie_backend_unsupported"
