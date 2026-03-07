from __future__ import annotations

import logging
from typing import Any

from engine.models.runtime import ExecutionContext
from engine.models.workflow import Condition, ConditionExpr, ConditionType

logger = logging.getLogger(__name__)


def _eval_single(condition: Condition, context: ExecutionContext) -> bool:
    """Evaluate a single Condition against the current execution context."""
    ct = condition.type

    if ct == ConditionType.result_ok:
        return context.last_result is not None and context.last_result.ok

    if ct == ConditionType.var_equals:
        if condition.var is None:
            return False
        # Handle nested var access like "creds.token"
        var_path = condition.var.split('.')
        actual = context.vars
        for p in var_path:
            if isinstance(actual, dict):
                actual = actual.get(p)
            else:
                actual = getattr(actual, p, None)
        return actual == condition.equals

    if ct == ConditionType.var_truthy:
        if condition.var is None:
            return False
        var_path = condition.var.split('.')
        actual = context.vars
        for p in var_path:
            if isinstance(actual, dict):
                actual = actual.get(p)
            else:
                actual = getattr(actual, p, None)
        return bool(actual)

    # Browser-dependent checks — browser may not be open yet
    browser: Any = context.browser

    if ct == ConditionType.exists:
        if browser is None or condition.selector is None:
            return False
        try:
            return browser.exists(condition.selector)
        except Exception:
            return False

    if ct == ConditionType.text_contains:
        if browser is None or condition.text is None:
            return False
        try:
            html = browser.html()
            return condition.text.lower() in html.lower()
        except Exception:
            return False

    if ct == ConditionType.url_contains:
        if browser is None or condition.text is None:
            return False
        try:
            url = browser.current_url()
            return condition.text.lower() in url.lower()
        except Exception:
            return False

    # Unknown condition type — should never happen with Pydantic validation
    logger.warning("unknown condition type: %s", ct)
    return False


def evaluate(expr: ConditionExpr, context: ExecutionContext) -> bool:
    """Evaluate a ConditionExpr (any/all) against the execution context.

    Rules:
    - If `all` is set: every condition must be True
    - If `any` is set: at least one condition must be True
    - If both set: `all` takes precedence
    - If neither set: returns True (vacuous truth)
    """
    if expr.all is not None:
        return all(_eval_single(c, context) for c in expr.all)
    if expr.any is not None:
        return any(_eval_single(c, context) for c in expr.any)
    return True
