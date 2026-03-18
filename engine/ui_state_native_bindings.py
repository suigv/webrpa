from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from engine.actions import state_actions
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.ui_state import LOGIN_STAGE_VALUES, normalize_login_stage


@dataclass(frozen=True, init=False)
class NativeStateProfile:
    state_profile_id: str
    display_name: str
    state_noun: str
    supported_state_ids: tuple[str, ...]
    normalize_state_id: Callable[[str], str]
    state_id_from_action_result: Callable[[ActionResult], str]
    match_action: Callable[[dict[str, object], ExecutionContext], ActionResult]
    wait_action: Callable[[dict[str, object], ExecutionContext], ActionResult] | None = None

    @property
    def binding_id(self) -> str:
        return self.state_profile_id

    def __init__(
        self,
        state_profile_id: str | None = None,
        *,
        binding_id: str | None = None,
        display_name: str,
        state_noun: str,
        supported_state_ids: tuple[str, ...],
        normalize_state_id: Callable[[str], str],
        state_id_from_action_result: Callable[[ActionResult], str],
        match_action: Callable[[dict[str, object], ExecutionContext], ActionResult],
        wait_action: Callable[[dict[str, object], ExecutionContext], ActionResult] | None = None,
    ) -> None:
        resolved_profile_id = str(state_profile_id or binding_id or "").strip()
        if not resolved_profile_id:
            raise ValueError("state_profile_id is required")
        object.__setattr__(self, "state_profile_id", resolved_profile_id)
        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "state_noun", state_noun)
        object.__setattr__(self, "supported_state_ids", supported_state_ids)
        object.__setattr__(self, "normalize_state_id", normalize_state_id)
        object.__setattr__(self, "state_id_from_action_result", state_id_from_action_result)
        object.__setattr__(self, "match_action", match_action)
        object.__setattr__(self, "wait_action", wait_action)


NativeStateBinding = NativeStateProfile


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


def is_presence_style_profile(profile: NativeStateProfile) -> bool:
    return "available" in profile.supported_state_ids and "missing" in profile.supported_state_ids


is_presence_style_binding = is_presence_style_profile


_LOGIN_STAGE_PROFILE = NativeStateProfile(
    state_profile_id="login_stage",
    display_name="login",
    state_noun="stage",
    supported_state_ids=LOGIN_STAGE_VALUES,
    normalize_state_id=normalize_login_stage,
    state_id_from_action_result=extract_login_state_id,
    match_action=state_actions.detect_login_stage,
    wait_action=state_actions.wait_login_stage,
)

_DM_UNREAD_PROFILE = NativeStateProfile(
    state_profile_id="dm_unread",
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

_DM_LAST_MESSAGE_PROFILE = NativeStateProfile(
    state_profile_id="dm_last_message",
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

_DM_LAST_OUTBOUND_PROFILE = NativeStateProfile(
    state_profile_id="dm_last_outbound_message",
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

_SEARCH_CANDIDATES_PROFILE = NativeStateProfile(
    state_profile_id="search_candidates",
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

_TIMELINE_CANDIDATES_PROFILE = NativeStateProfile(
    state_profile_id="timeline_candidates",
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

_FOLLOW_TARGETS_PROFILE = NativeStateProfile(
    state_profile_id="follow_targets",
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

_APP_STAGE_PROFILE = NativeStateProfile(
    state_profile_id="app_stage",
    display_name="app stage",
    state_noun="stage",
    supported_state_ids=("home", "login", "search", "notifications", "profile", "unknown"),
    normalize_state_id=lambda state_id: str(state_id or "unknown"),
    state_id_from_action_result=lambda r: str(r.data.get("stage", "unknown")),
    match_action=state_actions.detect_app_stage,
    wait_action=state_actions.wait_app_stage,
)

_STATE_PROFILES: dict[str, NativeStateProfile] = {
    _LOGIN_STAGE_PROFILE.state_profile_id: _LOGIN_STAGE_PROFILE,
    _DM_UNREAD_PROFILE.state_profile_id: _DM_UNREAD_PROFILE,
    _DM_LAST_MESSAGE_PROFILE.state_profile_id: _DM_LAST_MESSAGE_PROFILE,
    _DM_LAST_OUTBOUND_PROFILE.state_profile_id: _DM_LAST_OUTBOUND_PROFILE,
    _SEARCH_CANDIDATES_PROFILE.state_profile_id: _SEARCH_CANDIDATES_PROFILE,
    _TIMELINE_CANDIDATES_PROFILE.state_profile_id: _TIMELINE_CANDIDATES_PROFILE,
    _FOLLOW_TARGETS_PROFILE.state_profile_id: _FOLLOW_TARGETS_PROFILE,
    _APP_STAGE_PROFILE.state_profile_id: _APP_STAGE_PROFILE,
}


def resolve_native_state_profile(state_profile_id: str) -> NativeStateProfile:
    try:
        return _STATE_PROFILES[state_profile_id]
    except KeyError as exc:
        raise ValueError(f"unsupported native ui-state profile: {state_profile_id}") from exc


def list_native_state_profiles() -> tuple[str, ...]:
    return tuple(sorted(_STATE_PROFILES))


def resolve_native_state_binding(binding_id: str) -> NativeStateProfile:
    return resolve_native_state_profile(binding_id)


def list_native_state_bindings() -> tuple[str, ...]:
    return list_native_state_profiles()
