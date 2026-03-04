from __future__ import annotations

import logging
from typing import Any, Dict

from new.engine.models.runtime import ActionResult, ExecutionContext

logger = logging.getLogger(__name__)


def _get_browser(context: ExecutionContext) -> Any:
    """Lazily open browser session, store in context."""
    if context.browser is None:
        try:
            from new.hardware_adapters.browser_client import BrowserClient
            context.browser = BrowserClient()
        except Exception as exc:
            raise RuntimeError(f"browser adapter unavailable: {exc}") from exc
    return context.browser


def browser_open(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    browser = _get_browser(context)
    url = str(params.get("url", ""))
    if not url:
        return ActionResult(ok=False, code="missing_url", message="url param required")
    headless = params.get("headless", True)
    try:
        browser.open(url, headless=headless)
    except Exception as exc:
        return ActionResult(ok=False, code="browser_open_failed", message=str(exc))
    return ActionResult(ok=True, code="ok", message=f"opened {url}")


def browser_input(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
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


def browser_click(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
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


def browser_exists(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
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


def browser_check_html(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
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


def browser_wait_url(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
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
    return ActionResult(ok=False, code="timeout", message=f"url did not contain {fragment} within {timeout_s}s")


def browser_close(params: Dict[str, Any], context: ExecutionContext) -> ActionResult:
    if context.browser is not None:
        try:
            context.browser.close()
        except Exception:
            pass
        context.browser = None
    return ActionResult(ok=True, code="ok", message="browser closed")
