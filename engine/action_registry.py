from __future__ import annotations

from collections.abc import Callable

from .models.runtime import ActionResult, ExecutionContext

ActionCallable = Callable[[dict[str, object], ExecutionContext], ActionResult]


class ActionRegistry:
    """Maps action names (e.g. 'browser.open') to callable implementations."""

    def __init__(self) -> None:
        self._actions: dict[str, ActionCallable] = {}

    def register(self, name: str, handler: ActionCallable) -> None:
        self._actions[name] = handler

    def resolve(self, name: str) -> ActionCallable:
        if name not in self._actions:
            raise KeyError(f"unknown action: {name}")
        return self._actions[name]

    def has(self, name: str) -> bool:
        return name in self._actions

    @property
    def names(self) -> list[str]:
        return sorted(self._actions.keys())


# Global registry instance
_registry = ActionRegistry()
_defaults_registered = False


def _ensure_defaults_registered() -> None:
    global _defaults_registered
    if _defaults_registered:
        return
    register_defaults()
    _defaults_registered = True


def get_registry() -> ActionRegistry:
    _ensure_defaults_registered()
    return _registry


def register_action(name: str, handler: ActionCallable) -> None:
    _registry.register(name, handler)


def resolve_action(name: str) -> ActionCallable:
    return _registry.resolve(name)


def register_defaults() -> None:
    """Register all built-in actions. Call once at engine startup."""
    from engine.actions.browser_actions import (
        browser_check_html,
        browser_click,
        browser_close,
        browser_exists,
        browser_input,
        browser_open,
        browser_wait_url,
        browser_add_cookies,
    )
    from .actions.credential_actions import credentials_load, credentials_checkout
    from .actions.ui_actions import (
        app_dismiss_popups,
        app_ensure_running,
        app_grant_permissions,
        app_open,
        app_stop,
        check_connect_state,
        capture_compressed,
        capture_raw,
        click,
        create_selector,
        dump_node_xml_ex,
        dumpNodeXml,
        exec_command,
        get_sdk_version,
        get_display_rotate,
        input_text,
        key_press,
        long_click,
        set_work_mode,
        touch_down,
        touch_move,
        touch_up,
        selector_add_query,
        selector_click_one,
        selector_clear,
        selector_exec_all,
        selector_exec_one,
        selector_find_nodes,
        selector_free,
        selector_free_nodes,
        selector_get_node_by_index,
        selector_get_nodes_size,
        screenshot,
        start_video_stream,
        stop_video_stream,
        swipe,
        use_new_node_mode,
        node_click,
        node_get_bound,
        node_get_bound_center,
        node_get_class,
        node_get_child,
        node_get_child_count,
        node_get_desc,
        node_get_id,
        node_get_json,
        node_get_package,
        node_get_parent,
        node_get_text,
        node_long_click,
    )
    from .actions.login_actions import (
        click_selector_or_tap,
        focus_and_input_with_shell_fallback,
        input_text_with_shell_fallback,
    )
    from .actions.ui_state_actions import (
        browser_match_state,
        browser_observe_transition,
        browser_wait_until,
        ui_match_state,
        ui_observe_transition,
        ui_wait_until,
    )
    from .actions.sdk_actions import (
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
        mark_processed,
        pick_candidate,
        pick_weighted_keyword,
        plan_follow_rounds,
        save_blogger_candidates,
        save_blogger_candidate,
        load_ui_scheme,
        load_ui_selector,
        load_ui_value,
        load_shared_optional,
        load_shared_required,
        resolve_first_non_empty,
        save_shared,
    )
    from .actions.state_actions import (
        collect_blogger_candidates,
        detect_x_login_stage,
        extract_dm_last_message,
        extract_dm_last_outbound_message,
        extract_unread_dm_targets,
        extract_follow_targets,
        open_candidate,
        extract_search_candidates,
        extract_timeline_candidates,
        follow_visible_targets,
        open_first_unread_dm,
        wait_x_login_stage,
    )
    from .actions.ai_actions import llm_evaluate, vlm_evaluate

    _registry.register("browser.open", browser_open)
    _registry.register("browser.input", browser_input)
    _registry.register("browser.click", browser_click)
    _registry.register("browser.exists", browser_exists)
    _registry.register("browser.check_html", browser_check_html)
    _registry.register("browser.wait_url", browser_wait_url)
    _registry.register("browser.match_state", browser_match_state)
    _registry.register("browser.wait_until", browser_wait_until)
    _registry.register("browser.observe_transition", browser_observe_transition)
    _registry.register("browser.add_cookies", browser_add_cookies)
    _registry.register("browser.close", browser_close)
    _registry.register("credentials.load", credentials_load)
    _registry.register("credentials.checkout", credentials_checkout)
    _registry.register("core.save_shared", save_shared)
    _registry.register("core.load_shared_required", load_shared_required)
    _registry.register("core.load_shared_optional", load_shared_optional)
    _registry.register("core.append_shared_unique", append_shared_unique)
    _registry.register("core.increment_shared_counter", increment_shared_counter)
    _registry.register("core.resolve_first_non_empty", resolve_first_non_empty)
    _registry.register("core.load_ui_value", load_ui_value)
    _registry.register("core.load_ui_selector", load_ui_selector)
    _registry.register("core.load_ui_scheme", load_ui_scheme)
    _registry.register("core.check_daily_limit", check_daily_limit)
    _registry.register("core.increment_daily_counter", increment_daily_counter)
    _registry.register("core.pick_weighted_keyword", pick_weighted_keyword)
    _registry.register("core.pick_candidate", pick_candidate)
    _registry.register("core.plan_follow_rounds", plan_follow_rounds)
    _registry.register("core.is_text_blacklisted", is_text_blacklisted)
    _registry.register("core.choose_blogger_search_query", choose_blogger_search_query)
    _registry.register("core.derive_blogger_profile", derive_blogger_profile)
    _registry.register("core.save_blogger_candidates", save_blogger_candidates)
    _registry.register("core.save_blogger_candidate", save_blogger_candidate)
    _registry.register("core.get_blogger_candidate", get_blogger_candidate)
    _registry.register("core.mark_processed", mark_processed)
    _registry.register("core.check_processed", check_processed)
    _registry.register("core.generate_totp", generate_totp)
    _registry.register("core.generate_dm_reply", generate_dm_reply)
    _registry.register("core.generate_quote_text", generate_quote_text)
    _registry.register("core.detect_x_login_stage", detect_x_login_stage)
    _registry.register("core.wait_x_login_stage", wait_x_login_stage)
    _registry.register("core.extract_timeline_candidates", extract_timeline_candidates)
    _registry.register("core.extract_search_candidates", extract_search_candidates)
    _registry.register("core.collect_blogger_candidates", collect_blogger_candidates)
    _registry.register("core.open_candidate", open_candidate)
    _registry.register("core.extract_dm_last_message", extract_dm_last_message)
    _registry.register("core.extract_dm_last_outbound_message", extract_dm_last_outbound_message)
    _registry.register("core.extract_unread_dm_targets", extract_unread_dm_targets)
    _registry.register("core.open_first_unread_dm", open_first_unread_dm)
    _registry.register("core.extract_follow_targets", extract_follow_targets)
    _registry.register("core.follow_visible_targets", follow_visible_targets)
    _registry.register("ai.llm_evaluate", llm_evaluate)
    _registry.register("ai.vlm_evaluate", vlm_evaluate)
    _registry.register("ui.click", click)
    _registry.register("ui.match_state", ui_match_state)
    _registry.register("ui.touch_down", touch_down)
    _registry.register("ui.touch_up", touch_up)
    _registry.register("ui.touch_move", touch_move)
    _registry.register("ui.wait_until", ui_wait_until)
    _registry.register("ui.observe_transition", ui_observe_transition)
    _registry.register("ui.swipe", swipe)
    _registry.register("ui.long_click", long_click)
    _registry.register("ui.input_text", input_text)
    _registry.register("ui.input_text_with_shell_fallback", input_text_with_shell_fallback)
    _registry.register("ui.focus_and_input_with_shell_fallback", focus_and_input_with_shell_fallback)
    _registry.register("ui.key_press", key_press)
    _registry.register("ui.click_selector_or_tap", click_selector_or_tap)
    _registry.register("app.open", app_open)
    _registry.register("app.stop", app_stop)
    _registry.register("app.ensure_running", app_ensure_running)
    _registry.register("app.grant_permissions", app_grant_permissions)
    _registry.register("app.dismiss_popups", app_dismiss_popups)
    _registry.register("device.screenshot", screenshot)
    _registry.register("device.capture_raw", capture_raw)
    _registry.register("device.capture_compressed", capture_compressed)
    _registry.register("device.get_display_rotate", get_display_rotate)
    _registry.register("device.get_sdk_version", get_sdk_version)
    _registry.register("device.check_connect_state", check_connect_state)
    _registry.register("device.set_work_mode", set_work_mode)
    _registry.register("device.use_new_node_mode", use_new_node_mode)
    _registry.register("device.video_stream_start", start_video_stream)
    _registry.register("device.video_stream_stop", stop_video_stream)
    _registry.register("device.exec", exec_command)
    _registry.register("ui.create_selector", create_selector)
    _registry.register("ui.selector_add_query", selector_add_query)
    _registry.register("ui.selector_click_one", selector_click_one)
    _registry.register("ui.selector_exec_one", selector_exec_one)
    _registry.register("ui.selector_exec_all", selector_exec_all)
    _registry.register("ui.selector_find_nodes", selector_find_nodes)
    _registry.register("ui.selector_free", selector_free)
    _registry.register("ui.selector_free_nodes", selector_free_nodes)
    _registry.register("ui.selector_get_nodes_size", selector_get_nodes_size)
    _registry.register("ui.selector_get_node_by_index", selector_get_node_by_index)
    _registry.register("ui.selector_clear", selector_clear)
    _registry.register("ui.node_click", node_click)
    _registry.register("ui.node_long_click", node_long_click)
    _registry.register("ui.node_get_json", node_get_json)
    _registry.register("ui.node_get_text", node_get_text)
    _registry.register("ui.node_get_desc", node_get_desc)
    _registry.register("ui.node_get_package", node_get_package)
    _registry.register("ui.node_get_class", node_get_class)
    _registry.register("ui.node_get_id", node_get_id)
    _registry.register("ui.node_get_bound", node_get_bound)
    _registry.register("ui.node_get_bound_center", node_get_bound_center)
    _registry.register("ui.node_get_parent", node_get_parent)
    _registry.register("ui.node_get_child_count", node_get_child_count)
    _registry.register("ui.node_get_child", node_get_child)
    _registry.register("ui.dump_node_xml", dumpNodeXml)
    _registry.register("ui.dump_node_xml_ex", dump_node_xml_ex)
    for action_name, handler in get_sdk_action_bindings().items():
        _registry.register(action_name, handler)
