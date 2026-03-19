from __future__ import annotations

from typing import Any

from engine.models.runtime import ExecutionContext

SourceName = str


def runtime_target(context: ExecutionContext) -> dict[str, Any]:
    runtime = context.runtime if isinstance(context.runtime, dict) else {}
    target = runtime.get("target")
    return target if isinstance(target, dict) else {}


def session_defaults(context: ExecutionContext) -> dict[str, Any]:
    defaults = getattr(context, "session_defaults", None)
    return defaults if isinstance(defaults, dict) else {}


def resolve_context_value(
    params: dict[str, Any],
    context: ExecutionContext,
    key: str,
    default: Any = None,
    *,
    source_order: tuple[SourceName, ...] = ("params", "payload", "target", "runtime"),
) -> Any:
    payload = context.payload if isinstance(context.payload, dict) else {}
    runtime = context.runtime if isinstance(context.runtime, dict) else {}
    sources: dict[SourceName, dict[str, Any]] = {
        "params": params,
        "payload": payload,
        "target": runtime_target(context),
        "runtime": runtime,
        "session_defaults": session_defaults(context),
    }
    for source_name in source_order:
        source = sources.get(source_name)
        if isinstance(source, dict) and key in source:
            return source[key]
    return default
