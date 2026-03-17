from __future__ import annotations

import logging

from engine.models.runtime import ExecutionContext
from engine.models.workflow import Condition, ConditionExpr, ConditionType
from engine.ui_state_browser_service import BrowserUIStateService

logger = logging.getLogger(__name__)


def browser_condition_state_id(condition: Condition) -> str | None:
    if condition.type == ConditionType.exists and condition.selector:
        return f"exists:{condition.selector}"
    if condition.type == ConditionType.text_contains and condition.text:
        return f"html:{condition.text}"
    if condition.type == ConditionType.url_contains and condition.text:
        return f"url:{condition.text}"
    return None


def _eval_browser_condition_with_service(condition: Condition, context: ExecutionContext) -> bool:
    state_id = browser_condition_state_id(condition)
    if state_id is None or context.browser is None:
        return False
    try:
        return (
            BrowserUIStateService()
            .match_state(
                context,
                expected_state_ids=[state_id],
            )
            .ok
        )
    except Exception:
        logger.debug("failed to evaluate browser condition via ui state service", exc_info=True)
        return False


def _eval_single(condition: Condition, context: ExecutionContext) -> bool:
    """Evaluate a single Condition against the current execution context."""
    ct = condition.type

    if ct == ConditionType.result_ok:
        return context.last_result is not None and context.last_result.ok

    if ct == ConditionType.var_equals:
        if condition.var is None:
            return False
        # Handle nested var access like "creds.token"
        var_path = condition.var.split(".")
        actual = context.vars
        for p in var_path:
            actual = actual.get(p) if isinstance(actual, dict) else getattr(actual, p, None)
        return actual == condition.equals

    if ct == ConditionType.var_truthy:
        if condition.var is None:
            return False
        var_path = condition.var.split(".")
        actual = context.vars
        for p in var_path:
            actual = actual.get(p) if isinstance(actual, dict) else getattr(actual, p, None)
        return bool(actual)

    if ct == ConditionType.exists:
        return _eval_browser_condition_with_service(condition, context)

    if ct == ConditionType.text_contains:
        return _eval_browser_condition_with_service(condition, context)

    if ct == ConditionType.url_contains:
        return _eval_browser_condition_with_service(condition, context)

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
