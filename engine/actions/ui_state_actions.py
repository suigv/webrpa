from __future__ import annotations

from collections.abc import Sequence

from engine.models.runtime import ActionResult, ExecutionContext
from engine.ui_state_browser_service import BrowserUIStateService
from engine.ui_state_native_adapter import NativeUIStateAdapter
from engine.ui_state_native_bindings import normalize_native_state_profile_id
from engine.ui_state_service import UIStateService


def ui_match_state(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    params = _with_injected_app_defaults(params, context)
    expected_state_ids = _coerce_state_ids(
        params.get("expected_state_ids") or params.get("state_ids")
    )
    service, error = _resolve_service(params, expected_state_ids=expected_state_ids)
    if error is not None:
        return error
    assert service is not None
    return service.match_state(
        context,
        expected_state_ids=expected_state_ids,
        timeout_ms=_optional_int(params.get("timeout_ms")),
    ).to_action_result()


def ui_wait_until(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    params = _with_injected_app_defaults(params, context)
    expected_state_ids = _coerce_state_ids(
        params.get("expected_state_ids") or params.get("state_ids") or params.get("target_stages")
    )
    service, error = _resolve_service(params, expected_state_ids=expected_state_ids)
    if error is not None:
        return error
    assert service is not None
    return service.wait_until(
        context,
        expected_state_ids=expected_state_ids,
        timeout_ms=_int_value(params.get("timeout_ms"), default=15000),
        interval_ms=_int_value(params.get("interval_ms"), default=500),
    ).to_action_result()


def ui_observe_transition(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    params = _with_injected_app_defaults(params, context)
    from_state_ids = _coerce_state_ids(params.get("from_state_ids") or params.get("from_states"))
    to_state_ids = _coerce_state_ids(
        params.get("to_state_ids")
        or params.get("state_ids")
        or params.get("expected_state_ids")
        or params.get("target_stages")
    )
    service, error = _resolve_service(
        params,
        expected_state_ids=(*from_state_ids, *to_state_ids),
    )
    if error is not None:
        return error
    assert service is not None
    return service.observe_transition(
        context,
        from_state_ids=from_state_ids or None,
        to_state_ids=to_state_ids or None,
        timeout_ms=_int_value(params.get("timeout_ms"), default=15000),
        interval_ms=_int_value(params.get("interval_ms"), default=500),
    ).to_action_result()


def browser_match_state(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    return ui_match_state(_with_platform(params, platform="browser"), context)


def browser_wait_until(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    return ui_wait_until(_with_platform(params, platform="browser"), context)


def browser_observe_transition(
    params: dict[str, object], context: ExecutionContext
) -> ActionResult:
    return ui_observe_transition(_with_platform(params, platform="browser"), context)


def _resolve_service(
    params: dict[str, object],
    *,
    expected_state_ids: Sequence[str],
) -> tuple[UIStateService | None, ActionResult | None]:
    platform = _resolve_platform(params, expected_state_ids=expected_state_ids)
    if platform == "browser":
        return BrowserUIStateService(), None
    if platform == "native":
        try:
            state_profile_id, normalized_params = _normalize_native_state_profile_params(params)
            return NativeUIStateAdapter(
                state_profile_id=state_profile_id,
                action_params=normalized_params,
            ), None
        except ValueError as exc:
            return None, ActionResult(ok=False, code="invalid_params", message=str(exc))
    return None, ActionResult(
        ok=False, code="invalid_params", message=f"unsupported platform: {platform}"
    )


def _resolve_platform(params: dict[str, object], *, expected_state_ids: Sequence[str]) -> str:
    explicit = str(params.get("platform") or "").strip().lower()
    if explicit:
        return explicit
    if any(_looks_like_browser_state_id(state_id) for state_id in expected_state_ids):
        return "browser"
    return "native"


def _coerce_state_ids(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    if isinstance(raw, Sequence):
        return tuple(str(part).strip() for part in raw if str(part).strip())
    return ()


def _with_injected_app_defaults(
    params: dict[str, object], context: ExecutionContext
) -> dict[str, object]:
    merged = dict(params)
    if merged.get("package") in (None, ""):
        package = context.get_session_default("package") or context.payload.get("package")
        if package not in (None, ""):
            merged["package"] = package

    if merged.get("stage_patterns") is None:
        stage_patterns = (
            context.get_session_default("stage_patterns")
            or context.get_session_default("_app_stage_patterns")
            or context.payload.get("stage_patterns")
            or context.payload.get("_app_stage_patterns")
        )
        if stage_patterns is not None:
            merged["stage_patterns"] = stage_patterns

    for key in ("_app_states", "_app_stage_patterns", "_app_selectors"):
        if key not in merged:
            value = context.get_session_default(key)
            if value is None:
                value = context.payload.get(key)
            if value is not None:
                merged[key] = value
    return merged


def _resolve_native_state_profile_id(params: dict[str, object]) -> str:
    default_profile_id = "app_stage" if _has_injected_app_stage_patterns(params) else "login_stage"
    return normalize_native_state_profile_id(
        str(params.get("state_profile_id") or "").strip() or None,
        binding_id=str(params.get("binding_id") or "").strip() or None,
        default=default_profile_id,
    )


def _normalize_native_state_profile_params(
    params: dict[str, object],
) -> tuple[str, dict[str, object]]:
    state_profile_id = _resolve_native_state_profile_id(params)
    normalized_params = dict(params)
    normalized_params["state_profile_id"] = state_profile_id
    _ = normalized_params.pop("binding_id", None)
    return state_profile_id, normalized_params


def _has_injected_app_stage_patterns(params: dict[str, object]) -> bool:
    if str(params.get("state_profile_id") or "").strip():
        return False
    if str(params.get("binding_id") or "").strip():
        return False
    raw_patterns = params.get("_app_stage_patterns")
    return isinstance(raw_patterns, dict) and bool(raw_patterns)


def _looks_like_browser_state_id(state_id: str) -> bool:
    return any(str(state_id).startswith(prefix) for prefix in ("exists:", "html:", "url:"))


def _optional_int(raw: object) -> int | None:
    if raw is None or raw == "":
        return None
    return _coerce_int(raw)


def _int_value(raw: object, *, default: int) -> int:
    if raw is None or raw == "":
        return default
    return _coerce_int(raw)


def _coerce_int(raw: object) -> int:
    if isinstance(raw, (bool, int, str)):
        return int(raw)
    raise ValueError(f"invalid integer value: {raw}")


def _with_platform(params: dict[str, object], *, platform: str) -> dict[str, object]:
    next_params = dict(params)
    if "platform" not in next_params:
        next_params["platform"] = platform
    return next_params
