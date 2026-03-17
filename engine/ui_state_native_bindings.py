from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from engine.actions import state_actions
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.ui_state import LOGIN_STAGE_VALUES, normalize_login_stage


@dataclass(frozen=True)
class NativeStateBinding:
    binding_id: str
    display_name: str
    state_noun: str
    supported_state_ids: tuple[str, ...]
    normalize_state_id: Callable[[str], str]
    state_id_from_action_result: Callable[[ActionResult], str]
    match_action: Callable[[dict[str, object], ExecutionContext], ActionResult]
    wait_action: Callable[[dict[str, object], ExecutionContext], ActionResult] | None = None


def normalize_supported_state(state_id: str, supported_state_ids: Sequence[str]) -> str:
    candidate = str(state_id or "unknown").strip() or "unknown"
    return candidate if candidate in supported_state_ids else "unknown"


def extract_login_state_id(action_result: ActionResult) -> str:
    return normalize_login_stage(str(action_result.data.get("stage", "unknown") or "unknown"))


def extract_presence_state_id(
    *,
    present_state_id: str,
    missing_codes: Sequence[str],
) -> Callable[[ActionResult], str]:
    missing_code_set = {str(code).strip() for code in missing_codes if str(code).strip()}

    def _extract(action_result: ActionResult) -> str:
        if action_result.ok:
            return present_state_id
        if action_result.code in missing_code_set:
            return "missing"
        return "unknown"

    return _extract


def is_presence_style_binding(binding: NativeStateBinding) -> bool:
    return "available" in binding.supported_state_ids and "missing" in binding.supported_state_ids


_LOGIN_STAGE_BINDING = NativeStateBinding(
    binding_id="login_stage",
    display_name="login",
    state_noun="stage",
    supported_state_ids=LOGIN_STAGE_VALUES,
    normalize_state_id=normalize_login_stage,
    state_id_from_action_result=extract_login_state_id,
    match_action=state_actions.detect_login_stage,
    wait_action=state_actions.wait_login_stage,
)

_DM_UNREAD_BINDING = NativeStateBinding(
    binding_id="dm_unread",
    display_name="DM unread conversation",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: normalize_supported_state(
        state_id, ("available", "missing", "unknown")
    ),
    state_id_from_action_result=extract_presence_state_id(
        present_state_id="available",
        missing_codes=("unread_dm_missing",),
    ),
    match_action=state_actions.extract_unread_dm_targets,
)

_DM_LAST_MESSAGE_BINDING = NativeStateBinding(
    binding_id="dm_last_message",
    display_name="DM last message",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: normalize_supported_state(
        state_id, ("available", "missing", "unknown")
    ),
    state_id_from_action_result=extract_presence_state_id(
        present_state_id="available",
        missing_codes=("dm_message_missing",),
    ),
    match_action=state_actions.extract_dm_last_message,
)

_DM_LAST_OUTBOUND_BINDING = NativeStateBinding(
    binding_id="dm_last_outbound_message",
    display_name="DM last outbound message",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: normalize_supported_state(
        state_id, ("available", "missing", "unknown")
    ),
    state_id_from_action_result=extract_presence_state_id(
        present_state_id="available",
        missing_codes=("dm_outbound_message_missing",),
    ),
    match_action=state_actions.extract_dm_last_outbound_message,
)

_SEARCH_CANDIDATES_BINDING = NativeStateBinding(
    binding_id="search_candidates",
    display_name="search candidates",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: normalize_supported_state(
        state_id, ("available", "missing", "unknown")
    ),
    state_id_from_action_result=extract_presence_state_id(
        present_state_id="available",
        missing_codes=("no_candidates",),
    ),
    match_action=state_actions.extract_search_candidates,
)

_TIMELINE_CANDIDATES_BINDING = NativeStateBinding(
    binding_id="timeline_candidates",
    display_name="timeline candidates",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: normalize_supported_state(
        state_id, ("available", "missing", "unknown")
    ),
    state_id_from_action_result=extract_presence_state_id(
        present_state_id="available",
        missing_codes=("no_candidates",),
    ),
    match_action=state_actions.extract_timeline_candidates,
)

_FOLLOW_TARGETS_BINDING = NativeStateBinding(
    binding_id="follow_targets",
    display_name="follow targets",
    state_noun="state",
    supported_state_ids=("available", "missing", "unknown"),
    normalize_state_id=lambda state_id: normalize_supported_state(
        state_id, ("available", "missing", "unknown")
    ),
    state_id_from_action_result=extract_presence_state_id(
        present_state_id="available",
        missing_codes=("follow_targets_missing",),
    ),
    match_action=state_actions.extract_follow_targets,
)

_APP_STAGE_BINDING = NativeStateBinding(
    binding_id="app_stage",
    display_name="app stage",
    state_noun="stage",
    supported_state_ids=("home", "login", "search", "notifications", "profile", "unknown"),
    normalize_state_id=lambda state_id: str(state_id or "unknown"),
    state_id_from_action_result=lambda r: str(r.data.get("stage", "unknown")),
    match_action=state_actions.detect_app_stage,
    wait_action=state_actions.wait_app_stage,
)

_BINDINGS: dict[str, NativeStateBinding] = {
    _LOGIN_STAGE_BINDING.binding_id: _LOGIN_STAGE_BINDING,
    _DM_UNREAD_BINDING.binding_id: _DM_UNREAD_BINDING,
    _DM_LAST_MESSAGE_BINDING.binding_id: _DM_LAST_MESSAGE_BINDING,
    _DM_LAST_OUTBOUND_BINDING.binding_id: _DM_LAST_OUTBOUND_BINDING,
    _SEARCH_CANDIDATES_BINDING.binding_id: _SEARCH_CANDIDATES_BINDING,
    _TIMELINE_CANDIDATES_BINDING.binding_id: _TIMELINE_CANDIDATES_BINDING,
    _FOLLOW_TARGETS_BINDING.binding_id: _FOLLOW_TARGETS_BINDING,
    _APP_STAGE_BINDING.binding_id: _APP_STAGE_BINDING,
}


def resolve_native_state_binding(binding_id: str) -> NativeStateBinding:
    try:
        return _BINDINGS[binding_id]
    except KeyError as exc:
        raise ValueError(f"unsupported native ui-state binding: {binding_id}") from exc


def list_native_state_bindings() -> tuple[str, ...]:
    return tuple(sorted(_BINDINGS))
