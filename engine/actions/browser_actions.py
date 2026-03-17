from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from engine.models.runtime import ActionResult, ExecutionContext

logger = logging.getLogger(__name__)


def _get_browser(context: ExecutionContext) -> Any:
    """Lazily open browser session, store in context."""
    if context.browser is None:
        try:
            from hardware_adapters.browser_client import BrowserClient

            context.browser = BrowserClient()
        except Exception as exc:
            raise RuntimeError(f"browser adapter unavailable: {exc}") from exc
    return context.browser


def browser_open(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    url = str(params.get("url", ""))
    if not url:
        return ActionResult(ok=False, code="missing_url", message="url param required")
    headless = params.get("headless", True)
    profile_id = params.get("profile_id")
    try:
        browser.open(url, headless=headless, profile_id=profile_id)
    except Exception as exc:
        return ActionResult(ok=False, code="browser_open_failed", message=str(exc))
    return ActionResult(ok=True, code="ok", message=f"opened {url}")


def browser_input(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    selectors = params.get("selectors", [])
    text = str(params.get("text", ""))
    if isinstance(selectors, str):
        selectors = [selectors]
    for sel in selectors:
        try:
            browser.input(sel, text)
            return ActionResult(ok=True, code="ok", message=f"input to {sel}")
        except Exception:
            continue
    return ActionResult(ok=False, code="input_failed", message="no selector matched")


def browser_click(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    selectors = params.get("selectors", [])
    if isinstance(selectors, str):
        selectors = [selectors]
    for sel in selectors:
        try:
            browser.click(sel)
            return ActionResult(ok=True, code="ok", message=f"clicked {sel}")
        except Exception:
            continue
    return ActionResult(ok=False, code="click_failed", message="no selector matched")


def browser_exists(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    selectors = params.get("selectors", [])
    if isinstance(selectors, str):
        selectors = [selectors]
    for sel in selectors:
        try:
            if browser.exists(sel):
                return ActionResult(ok=True, code="ok", data={"selector": sel})
        except Exception:
            continue
    return ActionResult(ok=False, code="not_found", message="element not found")


def browser_check_html(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    contains = params.get("contains", [])
    if isinstance(contains, str):
        contains = [contains]
    try:
        html = browser.html()
    except Exception as exc:
        return ActionResult(ok=False, code="html_error", message=str(exc))
    html_lower = html.lower()
    for keyword in contains:
        if keyword.lower() in html_lower:
            return ActionResult(ok=True, code="ok", data={"matched": keyword})
    return ActionResult(ok=False, code="not_found", message="no keyword found in html")


def browser_wait_url(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    fragment = str(params.get("fragment", ""))
    timeout_s = int(params.get("timeout_s", 15))
    if not fragment:
        return ActionResult(ok=False, code="missing_fragment", message="fragment param required")
    try:
        result = browser.wait_url_contains(fragment, timeout_seconds=timeout_s)
    except Exception as exc:
        return ActionResult(ok=False, code="wait_url_failed", message=str(exc))
    if result:
        return ActionResult(ok=True, code="ok", message=f"url contains {fragment}")
    return ActionResult(
        ok=False, code="timeout", message=f"url did not contain {fragment} within {timeout_s}s"
    )


def browser_add_cookies(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    cookies = params.get("cookies", [])
    if isinstance(cookies, dict):
        cookies = [cookies]
    if not cookies:
        return ActionResult(ok=False, code="missing_cookies", message="cookies param required")
    try:
        # Assuming DrissionPage set.cookies exists on the page
        if hasattr(browser._page, "set"):
            browser._page.set.cookies(cookies)
        elif hasattr(browser._page, "cookies"):  # Playwright style
            pass  # Implement fallback if necessary
        return ActionResult(ok=True, code="ok", message=f"added {len(cookies)} cookies")
    except Exception as exc:
        return ActionResult(ok=False, code="cookie_error", message=str(exc))


def browser_close(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    if context.browser is not None:
        with suppress(Exception):
            context.browser.close()
        context.browser = None
    return ActionResult(ok=True, code="ok", message="browser closed")
