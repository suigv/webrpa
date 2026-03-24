from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.data_store import write_json_atomic
from engine.action_registry import ActionMetadata
from engine.models.runtime import ActionResult, ExecutionContext
from hardware_adapters.myt_client import MytSdkClient

from . import (
    sdk_business_support,
    sdk_config_support,
    sdk_profile_support,
    sdk_runtime_support,
    sdk_shared_store_support,
)
from ._context_value_support import resolve_context_value
from .sdk_action_catalog import ACTION_BUILDERS, build_mytos_android_bindings

SAVE_SHARED_METADATA = ActionMetadata(
    description="Save a value to the persistent shared store",
    params_schema={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Key to store the value under"},
            "value": {"type": "any", "description": "Value to store"},
        },
        "required": ["key", "value"],
    },
    tags=["skill"],
)

LOAD_SHARED_REQUIRED_METADATA = ActionMetadata(
    description="Load a required value from the shared store. Fails if not found.",
    params_schema={
        "type": "object",
        "properties": {"key": {"type": "string", "description": "Key to retrieve"}},
        "required": ["key"],
    },
    returns_schema={"type": "object", "properties": {"value": {"type": "any"}}},
    tags=["skill"],
)

_SHARED_STORE_LOCK = threading.Lock()


def _from_payload_or_params(
    params: dict[str, Any], context: ExecutionContext, key: str, default: Any = None
) -> Any:
    return resolve_context_value(
        params,
        context,
        key,
        default,
        source_order=("params", "payload", "target", "runtime"),
    )


def _sdk_client(params: dict[str, Any], context: ExecutionContext) -> MytSdkClient | None:
    device_ip = _from_payload_or_params(params, context, "device_ip")
    if not device_ip:
        return None
    sdk_port = int(_from_payload_or_params(params, context, "sdk_port", 8000))
    timeout_seconds = float(_from_payload_or_params(params, context, "timeout_seconds", 30.0))
    retries = int(_from_payload_or_params(params, context, "retries", 3))
    return MytSdkClient(
        device_ip=str(device_ip),
        sdk_port=sdk_port,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )


def _invoke(
    method_name: str,
    arg_builder: Callable[[dict[str, Any]], tuple[list[Any], dict[str, Any]]] | None = None,
) -> Callable[[dict[str, Any], ExecutionContext], ActionResult]:
    def _handler(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
        client = _sdk_client(params, context)
        if client is None:
            return ActionResult(ok=False, code="invalid_params", message="device_ip is required")
        method = getattr(client, method_name, None)
        if method is None:
            return ActionResult(
                ok=False, code="not_supported", message=f"method not found: {method_name}"
            )
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        if arg_builder is not None:
            args, kwargs = arg_builder(params)
        try:
            result = method(*args, **kwargs)
        except Exception as exc:
            return ActionResult(
                ok=False, code="sdk_call_failed", message=str(exc), data={"method": method_name}
            )
        if isinstance(result, dict):
            return ActionResult(
                ok=bool(result.get("ok", False)),
                code="ok" if result.get("ok", False) else "sdk_error",
                message=str(result.get("error", "")),
                data={"method": method_name, "result": result},
            )
        return ActionResult(ok=True, code="ok", data={"method": method_name, "result": result})

    return _handler


def _extract_cloud_status_payload(result: dict[str, Any]) -> tuple[str, Any]:
    return sdk_runtime_support.extract_cloud_status_payload(result)


def wait_cloud_status(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.wait_cloud_status_action(
        params,
        context,
        sdk_client=_sdk_client,
        time_module=time,
    )


def get_sdk_action_bindings() -> dict[
    str, Callable[[dict[str, Any], ExecutionContext], ActionResult]
]:
    bindings = {
        action_name: _invoke(method_name, arg_builder)
        for action_name, (method_name, arg_builder) in ACTION_BUILDERS.items()
        if not action_name.startswith("mytos.")
    }
    bindings["sdk.wait_cloud_status"] = wait_cloud_status
    bindings.update(build_mytos_android_bindings())
    return bindings


def _shared_path() -> Path:
    return sdk_shared_store_support.shared_path()


def _shared_lock_path(path: Path) -> Path:
    return sdk_shared_store_support.shared_lock_path(path)


def _exclusive_shared_lock(path: Path):
    return sdk_shared_store_support.exclusive_shared_lock(path)


def _read_store() -> dict[str, Any]:
    return sdk_shared_store_support.read_store()


def _write_store(payload: dict[str, Any]) -> None:
    sdk_shared_store_support.write_store(
        payload,
        write_json_atomic=write_json_atomic,
    )


def _update_store(updater: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    return sdk_shared_store_support.update_store(
        updater,
        write_json_atomic=write_json_atomic,
        thread_lock=_SHARED_STORE_LOCK,
    )


def _resolve_shared_key(params: dict[str, Any], context: ExecutionContext) -> str:
    return sdk_shared_store_support.resolve_shared_key(params, context)


def save_shared(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_shared_store_support.save_shared_action(
        params,
        context,
        resolve_shared_key=_resolve_shared_key,
        update_store=_update_store,
    )


def load_shared_required(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_shared_store_support.load_shared_required_action(
        params,
        context,
        resolve_shared_key=_resolve_shared_key,
        read_store=_read_store,
    )


def load_shared_optional(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_shared_store_support.load_shared_optional_action(
        params,
        context,
        resolve_shared_key=_resolve_shared_key,
        read_store=_read_store,
    )


def append_shared_unique(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_shared_store_support.append_shared_unique_action(
        params,
        context,
        resolve_shared_key=_resolve_shared_key,
        read_store=_read_store,
        update_store=_update_store,
    )


def increment_shared_counter(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_shared_store_support.increment_shared_counter_action(
        params,
        context,
        resolve_shared_key=_resolve_shared_key,
        update_store=_update_store,
    )


def resolve_first_non_empty(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.resolve_first_non_empty_action(params)


def plan_follow_rounds(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.plan_follow_rounds_action(params)


def generate_totp(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.generate_totp_action(params)


def _ui_config_paths() -> list[Path]:
    return sdk_config_support.ui_config_paths()


def _load_ui_config_document() -> dict[str, Any]:
    return sdk_config_support.load_ui_config_document()


def _load_app_config_document(app: str) -> dict[str, Any]:
    return sdk_config_support.load_app_config_document(app)


def _strategy_config_paths() -> list[Path]:
    return sdk_config_support.strategy_config_paths()


def _load_strategy_document() -> dict[str, Any]:
    return sdk_config_support.load_strategy_document()


def _interaction_text_config_paths() -> list[Path]:
    return sdk_config_support.interaction_text_config_paths()


def _load_interaction_text_document() -> dict[str, Any]:
    return sdk_config_support.load_interaction_text_document()


def _daily_counter_path() -> Path:
    return sdk_config_support.daily_counter_path()


def _read_daily_counters() -> dict[str, Any]:
    return sdk_config_support.read_daily_counters()


def _write_daily_counters(payload: dict[str, Any]) -> None:
    sdk_config_support.write_daily_counters(payload)


def _resolve_daily_counter_key(params: dict[str, Any], context: ExecutionContext) -> str:
    return sdk_runtime_support.resolve_daily_counter_key(
        params,
        context,
        resolve_shared_key=_resolve_shared_key,
    )


def check_daily_limit(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.check_daily_limit_action(
        params,
        context,
        read_daily_counters=_read_daily_counters,
        resolve_daily_counter_key=_resolve_daily_counter_key,
    )


def increment_daily_counter(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.increment_daily_counter_action(
        params,
        context,
        read_daily_counters=_read_daily_counters,
        write_daily_counters=_write_daily_counters,
        resolve_daily_counter_key=_resolve_daily_counter_key,
    )


def pick_weighted_keyword(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.pick_weighted_keyword_action(
        params,
        context,
        load_strategy_document=_load_strategy_document,
    )


def is_text_blacklisted(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.is_text_blacklisted_action(
        params,
        context,
        load_strategy_document=_load_strategy_document,
    )


def _select_interaction_template(section: str, ai_type: str) -> str:
    return sdk_config_support.select_interaction_template(section, ai_type)


def generate_dm_reply(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.generate_dm_reply_action(
        params,
        context,
        select_interaction_template=_select_interaction_template,
    )


def generate_quote_text(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.generate_quote_text_action(
        params,
        context,
        select_interaction_template=_select_interaction_template,
    )


def save_blogger_candidate(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.save_blogger_candidate_action(
        params,
        context,
        append_shared_unique=append_shared_unique,
    )


def get_blogger_candidate(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.get_blogger_candidate_action(
        params,
        context,
        load_shared_optional=load_shared_optional,
    )


def mark_processed(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.mark_processed_action(
        params,
        context,
        append_shared_unique=append_shared_unique,
    )


def check_processed(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.check_processed_action(
        params,
        context,
        load_shared_optional=load_shared_optional,
    )


def pick_candidate(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.pick_candidate_action(
        params,
        context,
        load_strategy_document=_load_strategy_document,
    )


def choose_blogger_search_query(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.choose_blogger_search_query_action(
        params,
        context,
        load_interaction_document=_load_interaction_text_document,
    )


def _derive_blogger_profile_data(
    candidate: dict[str, Any],
    fallback_username: str = "",
    fallback_display_name: str = "",
    fallback_profile: str = "",
) -> dict[str, Any] | None:
    return sdk_profile_support.derive_blogger_profile_data(
        candidate=candidate,
        fallback_username=fallback_username,
        fallback_display_name=fallback_display_name,
        fallback_profile=fallback_profile,
    )


def derive_blogger_profile(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.derive_blogger_profile_action(
        params,
        derive_blogger_profile_data=_derive_blogger_profile_data,
    )


def save_blogger_candidates(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_business_support.save_blogger_candidates_action(
        params,
        context,
        derive_blogger_profile_data=_derive_blogger_profile_data,
        save_blogger_candidate=save_blogger_candidate,
    )


def _resolve_ui_key(source: Any, key: str) -> Any:
    return sdk_config_support.resolve_ui_key(source, key)


def _resolve_localized_entry(entry: Any, locale: str) -> Any:
    return sdk_config_support.resolve_localized_entry(entry, locale)


def load_ui_value(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.load_ui_value_action(
        params,
        load_ui_config_document=_load_ui_config_document,
        load_app_config_document=_load_app_config_document,
        resolve_ui_key=_resolve_ui_key,
        context=context,
    )


def load_ui_selector(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.load_ui_selector_action(
        params,
        context,
        load_ui_config_document=_load_ui_config_document,
        load_app_config_document=_load_app_config_document,
        resolve_ui_key=_resolve_ui_key,
        resolve_localized_entry=_resolve_localized_entry,
    )


def load_ui_selectors(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    return sdk_runtime_support.load_ui_selectors_action(
        params,
        context,
        load_ui_config_document=_load_ui_config_document,
        load_app_config_document=_load_app_config_document,
        resolve_ui_key=_resolve_ui_key,
        resolve_localized_entry=_resolve_localized_entry,
    )


def load_ui_scheme(params: dict[str, Any], context: ExecutionContext) -> ActionResult:
    from engine.actions.ui_actions import _close_rpc, _get_rpc

    rpc, err = _get_rpc(params, context)
    if err is not None:
        rpc = None
    try:
        return sdk_runtime_support.load_ui_scheme_action(
            params,
            load_ui_config_document=_load_ui_config_document,
            load_app_config_document=_load_app_config_document,
            resolve_ui_key=_resolve_ui_key,
            context=context,
            rpc=rpc,
        )
    finally:
        if rpc is not None:
            _close_rpc(rpc)
