from __future__ import annotations

from typing import Any, Callable, Dict

from .models.runtime import ActionResult, ExecutionContext

ActionCallable = Callable[[Dict[str, Any], ExecutionContext], ActionResult]


class ActionRegistry:
    """Maps action names (e.g. 'browser.open') to callable implementations."""

    def __init__(self) -> None:
        self._actions: Dict[str, ActionCallable] = {}

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


def get_registry() -> ActionRegistry:
    return _registry


def register_action(name: str, handler: ActionCallable) -> None:
    _registry.register(name, handler)


def resolve_action(name: str) -> ActionCallable:
    return _registry.resolve(name)


def register_defaults() -> None:
    """Register all built-in actions. Call once at engine startup."""
    from .actions.browser_actions import (
        browser_check_html,
        browser_click,
        browser_close,
        browser_exists,
        browser_input,
        browser_open,
        browser_wait_url,
    )
    from .actions.credential_actions import credentials_load
    from .actions.ui_actions import (
        app_open,
        app_stop,
        click,
        create_selector,
        dump_node_xml_ex,
        dumpNodeXml,
        exec_command,
        input_text,
        key_press,
        long_click,
        screenshot,
        swipe,
    )
    from .actions.sdk_actions import get_sdk_action_bindings

    _registry.register("browser.open", browser_open)
    _registry.register("browser.input", browser_input)
    _registry.register("browser.click", browser_click)
    _registry.register("browser.exists", browser_exists)
    _registry.register("browser.check_html", browser_check_html)
    _registry.register("browser.wait_url", browser_wait_url)
    _registry.register("browser.close", browser_close)
    _registry.register("credentials.load", credentials_load)
    _registry.register("ui.click", click)
    _registry.register("ui.swipe", swipe)
    _registry.register("ui.long_click", long_click)
    _registry.register("ui.input_text", input_text)
    _registry.register("ui.key_press", key_press)
    _registry.register("app.open", app_open)
    _registry.register("app.stop", app_stop)
    _registry.register("device.screenshot", screenshot)
    _registry.register("device.exec", exec_command)
    _registry.register("ui.create_selector", create_selector)
    _registry.register("ui.dump_node_xml", dumpNodeXml)
    _registry.register("ui.dump_node_xml_ex", dump_node_xml_ex)
    for action_name, handler in get_sdk_action_bindings().items():
        _registry.register(action_name, handler)
