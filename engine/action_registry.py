# pyright: reportImportCycles=false
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .models.runtime import ActionResult, ExecutionContext

ActionCallable = Callable[[dict[str, object], "ExecutionContext"], "ActionResult"]


class ActionMetadata(BaseModel):
    """Metadata describing an action's purpose and schema."""

    description: str = ""
    params_schema: dict[str, Any] | None = None
    returns_schema: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)


class ActionRegistry:
    """Maps action names (e.g. 'browser.open') to callable implementations."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionCallable] = {}
        self._metadata: dict[str, ActionMetadata] = {}

    def register(
        self, name: str, handler: ActionCallable, metadata: ActionMetadata | None = None
    ) -> None:
        self._actions[name] = handler
        if metadata:
            self._metadata[name] = metadata

    def resolve(self, name: str) -> ActionCallable:
        if name not in self._actions:
            raise KeyError(f"unknown action: {name}")
        return self._actions[name]

    def list_actions(self) -> list[str]:
        return list(self._actions.keys())

    def get_metadata(self, name: str) -> ActionMetadata | None:
        return self._metadata.get(name)

    def describe_all(self, tag: str | None = None) -> dict[str, ActionMetadata]:
        if not tag:
            return dict(self._metadata)
        return {name: meta for name, meta in self._metadata.items() if tag in meta.tags}

    def has(self, name: str) -> bool:
        return name in self._actions

    @property
    def names(self) -> list[str]:
        return sorted(self._actions.keys())


# Global registry instance
_registry = ActionRegistry()
_defaults_registered = False
_DEFAULT_SENTINEL_ACTION = "ui.focus_and_input_with_shell_fallback"


def _ensure_defaults_registered() -> None:
    global _defaults_registered
    if _defaults_registered and _registry.has(_DEFAULT_SENTINEL_ACTION):
        return
    register_defaults()
    _defaults_registered = True


def list_actions() -> list[str]:
    _ensure_defaults_registered()
    return sorted(_registry.list_actions())


def get_registry() -> ActionRegistry:
    _ensure_defaults_registered()
    return _registry


def reset_registry() -> None:
    global _registry, _defaults_registered
    _registry = ActionRegistry()
    _defaults_registered = False


def register_action(
    name: str, handler: ActionCallable, metadata: ActionMetadata | None = None
) -> None:
    _registry.register(name, handler, metadata=metadata)


def resolve_action(name: str) -> ActionCallable:
    _ensure_defaults_registered()
    return _registry.resolve(name)


def _register_browser_actions(registry: ActionRegistry) -> None:
    from engine.actions.browser_actions import (
        browser_add_cookies,
        browser_check_html,
        browser_click,
        browser_close,
        browser_exists,
        browser_input,
        browser_open,
        browser_wait_url,
    )

    from .actions.ui_state_actions import (
        browser_match_state,
        browser_observe_transition,
        browser_wait_until,
    )

    registry.register("browser.open", browser_open)
    registry.register("browser.input", browser_input)
    registry.register("browser.click", browser_click)
    registry.register("browser.exists", browser_exists)
    registry.register("browser.check_html", browser_check_html)
    registry.register("browser.wait_url", browser_wait_url)
    registry.register("browser.match_state", browser_match_state)
    registry.register("browser.wait_until", browser_wait_until)
    registry.register("browser.observe_transition", browser_observe_transition)
    registry.register("browser.add_cookies", browser_add_cookies)
    registry.register("browser.close", browser_close)


def _register_core_actions(registry: ActionRegistry) -> None:
    from .actions.app_config_actions import (
        EXPLORE_APP_CONFIG_METADATA,
        explore_app_config_action,
    )
    from .actions.ai_actions import (
        LLM_EVALUATE_METADATA,
        LOCATE_POINT_METADATA,
        VLM_EVALUATE_METADATA,
        llm_evaluate,
        locate_point,
        vlm_evaluate,
    )
    from .actions.credential_actions import credentials_checkout, credentials_load
    from .actions.profile_actions import (
        APPLY_ENV_BUNDLE_METADATA,
        GENERATE_CONTACT_METADATA,
        GENERATE_ENV_BUNDLE_METADATA,
        GENERATE_FINGERPRINT_METADATA,
        INVENTORY_PHONE_MODELS_METADATA,
        SELECT_CLOUD_CONTAINER_METADATA,
        SELECT_PHONE_MODEL_METADATA,
        WAIT_CLOUD_AVAILABLE_METADATA,
        generator_generate_contact,
        generator_generate_env_bundle,
        generator_generate_fingerprint,
        inventory_get_phone_models,
        inventory_refresh_phone_models,
        profile_apply_env_bundle,
        profile_wait_cloud_available,
        selector_resolve_cloud_container,
        selector_select_phone_model,
    )
    from .actions.sdk_actions import (
        LOAD_SHARED_REQUIRED_METADATA,
        SAVE_SHARED_METADATA,
        append_shared_unique,
        check_daily_limit,
        check_processed,
        choose_blogger_search_query,
        derive_blogger_profile,
        generate_dm_reply,
        generate_quote_text,
        generate_totp,
        get_blogger_candidate,
        get_sdk_action_bindings,
        increment_daily_counter,
        increment_shared_counter,
        is_text_blacklisted,
        load_shared_optional,
        load_shared_required,
        load_ui_scheme,
        load_ui_selector,
        load_ui_selectors,
        load_ui_value,
        mark_processed,
        pick_candidate,
        pick_weighted_keyword,
        plan_follow_rounds,
        resolve_first_non_empty,
        save_blogger_candidate,
        save_blogger_candidates,
        save_shared,
    )
    from .actions.state_actions import (
        collect_blogger_candidates,
        detect_login_stage,
        extract_dm_last_message,
        extract_dm_last_outbound_message,
        extract_follow_targets,
        extract_search_candidates,
        extract_timeline_candidates,
        extract_unread_dm_targets,
        follow_visible_targets,
        open_candidate,
        open_first_unread_dm,
        wait_login_stage,
    )

    registry.register(
        "core.explore_app_config",
        explore_app_config_action,
        metadata=EXPLORE_APP_CONFIG_METADATA,
    )
    registry.register("credentials.load", credentials_load)
    registry.register("credentials.checkout", credentials_checkout)
    registry.register("core.save_shared", save_shared, metadata=SAVE_SHARED_METADATA)
    registry.register(
        "core.load_shared_required", load_shared_required, metadata=LOAD_SHARED_REQUIRED_METADATA
    )
    registry.register("core.load_shared_optional", load_shared_optional)
    registry.register("core.append_shared_unique", append_shared_unique)
    registry.register("core.increment_shared_counter", increment_shared_counter)
    registry.register("core.resolve_first_non_empty", resolve_first_non_empty)
    registry.register("core.load_ui_value", load_ui_value)
    registry.register("core.load_ui_selector", load_ui_selector)
    registry.register("core.load_ui_selectors", load_ui_selectors)
    registry.register("core.load_ui_scheme", load_ui_scheme)
    registry.register("core.check_daily_limit", check_daily_limit)
    registry.register("core.increment_daily_counter", increment_daily_counter)
    registry.register("core.pick_weighted_keyword", pick_weighted_keyword)
    registry.register("core.pick_candidate", pick_candidate)
    registry.register("core.plan_follow_rounds", plan_follow_rounds)
    registry.register("core.is_text_blacklisted", is_text_blacklisted)
    registry.register("core.choose_blogger_search_query", choose_blogger_search_query)
    registry.register("core.derive_blogger_profile", derive_blogger_profile)
    registry.register("core.save_blogger_candidates", save_blogger_candidates)
    registry.register("core.save_blogger_candidate", save_blogger_candidate)
    registry.register("core.get_blogger_candidate", get_blogger_candidate)
    registry.register("core.mark_processed", mark_processed)
    registry.register("core.check_processed", check_processed)
    registry.register("core.generate_totp", generate_totp)
    registry.register("core.generate_dm_reply", generate_dm_reply)
    registry.register("core.generate_quote_text", generate_quote_text)
    registry.register(
        "inventory.get_phone_models",
        inventory_get_phone_models,
        metadata=INVENTORY_PHONE_MODELS_METADATA,
    )
    registry.register(
        "inventory.refresh_phone_models",
        inventory_refresh_phone_models,
        metadata=INVENTORY_PHONE_MODELS_METADATA,
    )
    registry.register(
        "selector.select_phone_model",
        selector_select_phone_model,
        metadata=SELECT_PHONE_MODEL_METADATA,
    )
    registry.register(
        "selector.resolve_cloud_container",
        selector_resolve_cloud_container,
        metadata=SELECT_CLOUD_CONTAINER_METADATA,
    )
    registry.register(
        "generator.generate_fingerprint",
        generator_generate_fingerprint,
        metadata=GENERATE_FINGERPRINT_METADATA,
    )
    registry.register(
        "generator.generate_contact",
        generator_generate_contact,
        metadata=GENERATE_CONTACT_METADATA,
    )
    registry.register(
        "generator.generate_env_bundle",
        generator_generate_env_bundle,
        metadata=GENERATE_ENV_BUNDLE_METADATA,
    )
    registry.register(
        "profile.apply_env_bundle",
        profile_apply_env_bundle,
        metadata=APPLY_ENV_BUNDLE_METADATA,
    )
    registry.register(
        "profile.wait_cloud_available",
        profile_wait_cloud_available,
        metadata=WAIT_CLOUD_AVAILABLE_METADATA,
    )
    registry.register("core.detect_login_stage", detect_login_stage)
    registry.register("core.wait_login_stage", wait_login_stage)
    registry.register("core.extract_timeline_candidates", extract_timeline_candidates)
    registry.register("core.extract_search_candidates", extract_search_candidates)
    registry.register("core.collect_blogger_candidates", collect_blogger_candidates)
    registry.register("core.open_candidate", open_candidate)
    registry.register("core.extract_dm_last_message", extract_dm_last_message)
    registry.register("core.extract_dm_last_outbound_message", extract_dm_last_outbound_message)
    registry.register("core.extract_unread_dm_targets", extract_unread_dm_targets)
    registry.register("core.open_first_unread_dm", open_first_unread_dm)
    registry.register("core.extract_follow_targets", extract_follow_targets)
    registry.register("core.follow_visible_targets", follow_visible_targets)
    registry.register("ai.llm_evaluate", llm_evaluate, metadata=LLM_EVALUATE_METADATA)
    registry.register("ai.vlm_evaluate", vlm_evaluate, metadata=VLM_EVALUATE_METADATA)
    registry.register("ai.locate_point", locate_point, metadata=LOCATE_POINT_METADATA)
    for action_name, handler in get_sdk_action_bindings().items():
        registry.register(action_name, handler)


def _register_ui_actions(registry: ActionRegistry) -> None:
    from .actions.login_actions import (
        click_selector_or_tap,
        fill_form,
        focus_and_input_with_shell_fallback,
        input_text_with_shell_fallback,
    )
    from .actions.navigation_actions import navigate_to
    from .actions.ui_actions import (
        APP_ENSURE_RUNNING_METADATA,
        APP_OPEN_METADATA,
        APP_STOP_METADATA,
        CAPTURE_COMPRESSED_METADATA,
        CLICK_METADATA,
        INPUT_TEXT_METADATA,
        KEY_PRESS_METADATA,
        LONG_CLICK_METADATA,
        SWIPE_METADATA,
        app_dismiss_popups,
        app_ensure_running,
        app_grant_permissions,
        app_open,
        app_stop,
        capture_compressed,
        capture_raw,
        check_connect_state,
        click,
        create_selector,
        dump_node_xml_ex,
        exec_command,
        get_display_rotate,
        get_sdk_version,
        input_text,
        key_press,
        long_click,
        node_click,
        node_get_bound,
        node_get_bound_center,
        node_get_child,
        node_get_child_count,
        node_get_class,
        node_get_desc,
        node_get_id,
        node_get_json,
        node_get_package,
        node_get_parent,
        node_get_text,
        node_long_click,
        screenshot,
        selector_add_query,
        selector_clear,
        selector_click_one,
        selector_click_with_fallback,
        selector_exec_all,
        selector_exec_one,
        selector_find_nodes,
        selector_free,
        selector_free_nodes,
        selector_get_node_by_index,
        selector_get_nodes_size,
        set_work_mode,
        start_video_stream,
        stop_video_stream,
        swipe,
        touch_down,
        touch_move,
        touch_up,
        use_new_node_mode,
    )
    from .actions.ui_state_actions import ui_match_state, ui_observe_transition, ui_wait_until

    registry.register("ui.click", click, metadata=CLICK_METADATA)
    registry.register("ui.touch_down", touch_down)
    registry.register("ui.touch_up", touch_up)
    registry.register("ui.touch_move", touch_move)
    registry.register("ui.swipe", swipe, metadata=SWIPE_METADATA)
    registry.register("ui.long_click", long_click, metadata=LONG_CLICK_METADATA)
    registry.register("ui.input_text", input_text, metadata=INPUT_TEXT_METADATA)
    registry.register("ui.key_press", key_press, metadata=KEY_PRESS_METADATA)
    registry.register("ui.create_selector", create_selector)
    registry.register("ui.selector_add_query", selector_add_query)
    registry.register("ui.selector_click_one", selector_click_one)
    registry.register("ui.selector_click_with_fallback", selector_click_with_fallback)
    registry.register("ui.selector_exec_one", selector_exec_one)
    registry.register("ui.selector_exec_all", selector_exec_all)
    registry.register("ui.selector_find_nodes", selector_find_nodes)
    registry.register("ui.selector_free", selector_free)
    registry.register("ui.selector_free_nodes", selector_free_nodes)
    registry.register("ui.selector_get_nodes_size", selector_get_nodes_size)
    registry.register("ui.selector_get_node_by_index", selector_get_node_by_index)
    registry.register("ui.selector_clear", selector_clear)
    registry.register("ui.node_click", node_click)
    registry.register("ui.node_long_click", node_long_click)
    registry.register("ui.node_get_json", node_get_json)
    registry.register("ui.node_get_text", node_get_text)
    registry.register("ui.node_get_desc", node_get_desc)
    registry.register("ui.node_get_package", node_get_package)
    registry.register("ui.node_get_class", node_get_class)
    registry.register("ui.node_get_id", node_get_id)
    registry.register("ui.node_get_bound", node_get_bound)
    registry.register("ui.node_get_bound_center", node_get_bound_center)
    registry.register("ui.node_get_parent", node_get_parent)
    registry.register("ui.node_get_child_count", node_get_child_count)
    registry.register("ui.node_get_child", node_get_child)
    registry.register("ui.dump_node_xml", dump_node_xml_ex)
    registry.register("ui.dump_node_xml_ex", dump_node_xml_ex)
    registry.register("ui.navigate_to", navigate_to)
    registry.register("ui.app_dismiss_popups", app_dismiss_popups)
    registry.register("ui.app_open", app_open)
    registry.register("ui.app_stop", app_stop)
    registry.register("ui.app_ensure_running", app_ensure_running)
    registry.register("ui.screenshot", screenshot)
    registry.register("ui.capture_compressed", capture_compressed)
    registry.register("ui.click_selector_or_tap", click_selector_or_tap)
    registry.register("ui.input_text_with_shell_fallback", input_text_with_shell_fallback)
    registry.register("ui.focus_and_input_with_shell_fallback", focus_and_input_with_shell_fallback)
    registry.register("ui.fill_form", fill_form)
    registry.register("ui.match_state", ui_match_state)
    registry.register("ui.wait_until", ui_wait_until)
    registry.register("ui.observe_transition", ui_observe_transition)
    registry.register("app.open", app_open, metadata=APP_OPEN_METADATA)
    registry.register("app.stop", app_stop, metadata=APP_STOP_METADATA)
    registry.register(
        "app.ensure_running", app_ensure_running, metadata=APP_ENSURE_RUNNING_METADATA
    )
    registry.register("app.grant_permissions", app_grant_permissions)
    registry.register("app.dismiss_popups", app_dismiss_popups)
    registry.register("device.screenshot", screenshot)
    registry.register("device.capture_raw", capture_raw)
    registry.register(
        "device.capture_compressed", capture_compressed, metadata=CAPTURE_COMPRESSED_METADATA
    )
    registry.register("device.get_display_rotate", get_display_rotate)
    registry.register("device.get_sdk_version", get_sdk_version)
    registry.register("device.check_connect_state", check_connect_state)
    registry.register("device.set_work_mode", set_work_mode)
    registry.register("device.use_new_node_mode", use_new_node_mode)
    registry.register("device.video_stream_start", start_video_stream)
    registry.register("device.video_stream_stop", stop_video_stream)
    registry.register("device.exec", exec_command)


def _register_android_actions(registry: ActionRegistry) -> None:
    from engine.actions.android_api_actions import (
        ADD_CONTACT_METADATA,
        BACKUP_APP_METADATA,
        GET_CLIPBOARD_METADATA,
        QUERY_PROXY_METADATA,
        RECEIVE_SMS_METADATA,
        RESTORE_APP_METADATA,
        SCREENSHOT_METADATA,
        SET_CLIPBOARD_METADATA,
        GRANT_APP_PERMISSIONS_METADATA,
        SET_FINGERPRINT_METADATA,
        SET_LANGUAGE_METADATA,
        SET_PROXY_METADATA,
        SET_SHAKE_METADATA,
        android_add_contact,
        android_autoclick,
        android_backup_app,
        android_batch_install_apps,
        android_camera_hot_start,
        android_download_file,
        android_export_app_info,
        android_get_call_records,
        android_get_clipboard,
        android_get_container_info,
        android_get_google_adid,
        android_get_google_id,
        android_get_root_allowed_apps,
        android_import_app_info,
        android_install_magisk,
        android_ip_geolocation,
        android_query_adb,
        android_query_proxy,
        android_receive_sms,
        android_refresh_location,
        android_restore_app,
        android_screenshot,
        android_set_background_keepalive,
        android_set_clipboard,
        android_set_fingerprint,
        android_set_google_id,
        android_set_key_block,
        android_set_language,
        android_set_proxy,
        android_set_proxy_filter,
        android_set_root_allowed_app,
        android_grant_app_permissions,
        android_set_shake,
        android_stop_proxy,
        android_switch_adb,
        android_upload_file,
        android_upload_google_cert,
    )

    registry.register(
        "android.get_clipboard", android_get_clipboard, metadata=GET_CLIPBOARD_METADATA
    )
    registry.register(
        "android.set_clipboard", android_set_clipboard, metadata=SET_CLIPBOARD_METADATA
    )
    registry.register("android.query_proxy", android_query_proxy, metadata=QUERY_PROXY_METADATA)
    registry.register("android.set_proxy", android_set_proxy, metadata=SET_PROXY_METADATA)
    registry.register("android.stop_proxy", android_stop_proxy)
    registry.register("android.set_proxy_filter", android_set_proxy_filter)
    registry.register("android.screenshot", android_screenshot, metadata=SCREENSHOT_METADATA)
    registry.register("android.snap_screenshot", android_screenshot, metadata=SCREENSHOT_METADATA)
    registry.register("android.download_file", android_download_file)
    registry.register("android.upload_file", android_upload_file)
    registry.register("android.set_language", android_set_language, metadata=SET_LANGUAGE_METADATA)
    registry.register(
        "android.set_fingerprint", android_set_fingerprint, metadata=SET_FINGERPRINT_METADATA
    )
    registry.register(
        "android.update_fingerprint", android_set_fingerprint, metadata=SET_FINGERPRINT_METADATA
    )
    registry.register(
        "android.grant_app_permissions",
        android_grant_app_permissions,
        metadata=GRANT_APP_PERMISSIONS_METADATA,
    )
    registry.register("android.set_shake", android_set_shake, metadata=SET_SHAKE_METADATA)
    registry.register("android.refresh_location", android_refresh_location)
    registry.register("android.get_google_adid", android_get_google_adid)
    registry.register("android.receive_sms", android_receive_sms, metadata=RECEIVE_SMS_METADATA)
    registry.register("android.add_contact", android_add_contact, metadata=ADD_CONTACT_METADATA)
    registry.register("android.get_container_info", android_get_container_info)
    registry.register("android.set_key_block", android_set_key_block)
    registry.register("android.set_background_keepalive", android_set_background_keepalive)
    registry.register("android.backup_app", android_backup_app, metadata=BACKUP_APP_METADATA)
    registry.register("android.restore_app", android_restore_app, metadata=RESTORE_APP_METADATA)
    registry.register("android.upload_google_cert", android_upload_google_cert)
    registry.register("android.batch_install_apps", android_batch_install_apps)
    registry.register("android.get_root_allowed_apps", android_get_root_allowed_apps)
    registry.register("android.set_root_allowed_app", android_set_root_allowed_app)
    registry.register("android.export_app_info", android_export_app_info)
    registry.register("android.import_app_info", android_import_app_info)
    registry.register("android.get_call_records", android_get_call_records)
    registry.register("android.ip_geolocation", android_ip_geolocation)
    registry.register("android.query_adb", android_query_adb)
    registry.register("android.switch_adb", android_switch_adb)
    registry.register("android.get_google_id", android_get_google_id)
    registry.register("android.set_google_id", android_set_google_id)
    registry.register("android.install_magisk", android_install_magisk)
    registry.register("android.camera_hot_start", android_camera_hot_start)
    registry.register("android.autoclick", android_autoclick)


def register_defaults() -> None:
    """Register all built-in actions. Call once at engine startup."""
    _register_browser_actions(_registry)
    _register_core_actions(_registry)
    _register_ui_actions(_registry)
    _register_android_actions(_registry)
