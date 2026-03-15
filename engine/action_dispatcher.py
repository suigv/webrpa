from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from engine.action_registry import ActionRegistry, get_registry
from engine.models.runtime import ActionResult, ExecutionContext


def dispatch_action(
    action_name: str,
    params: Mapping[str, Any] | None,
    context: ExecutionContext,
    *,
    registry: ActionRegistry | None = None,
) -> ActionResult:
    """Resolve and execute an action via the shared ActionRegistry.

    This centralizes action dispatch so runtimes (Interpreter, AgentExecutor, etc.)
    do not call registry.resolve(...)(...) directly.
    """
    reg = registry or get_registry()
    handler = reg.resolve(action_name)
    normalized = dict(params) if params is not None else {}
    return handler(normalized, context)

