from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.app_config import resolve_app_id, resolve_app_payload
from engine.action_registry import get_registry
from engine.agent_executor import AgentExecutorRuntime
from engine.interpreter import Interpreter
from engine.models.manifest import InputType, PluginInput
from engine.models.workflow import ActionStep, WorkflowScript
from engine.parser import ScriptParser, parse_script
from engine.plugin_loader import get_shared_plugin_loader

logger = logging.getLogger(__name__)

ALLOWED_ACTION_PREFIXES = (
    "app.",
    "browser.",
    "core.",
    "credentials.",
    "device.",
    "generator.",
    "inventory.",
    "mytos.",
    "profile.",
    "selector.",
    "sdk.",
    "ui.",
)


def strict_plugin_unknown_inputs_enabled() -> bool:
    raw = os.environ.get("MYT_STRICT_PLUGIN_UNKNOWN_INPUTS", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class Runner:
    def __init__(self, *, agent_executor_runtime: AgentExecutorRuntime | None = None) -> None:
        self._parser = ScriptParser()
        self._plugin_loader = get_shared_plugin_loader()
        self._interpreter = Interpreter()
        self._agent_executor_runtime = agent_executor_runtime or AgentExecutorRuntime()

    def _resolve_plugin_entry(self, task_name: str):
        self._plugin_loader = get_shared_plugin_loader()
        return self._plugin_loader.get(task_name)

    def run(
        self,
        script_payload: dict[str, Any],
        should_cancel: Callable[[], bool] | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plan = self._parser.parse(script_payload)
        task_name = str(plan.get("task") or "")
        emit_event = runtime.get("emit_event") if runtime else None

        if should_cancel is not None and should_cancel():
            return {
                "ok": False,
                "task": task_name,
                "status": "cancelled",
                "code": "task_cancelled",
                "message": "task cancelled by user",
                "timestamp": datetime.now(UTC).isoformat(),
            }

        if task_name == self._agent_executor_runtime.task_name:
            app_id = resolve_app_id(script_payload)
            enhanced_payload = resolve_app_payload(app_id, script_payload)
            return self._agent_executor_runtime.run(
                enhanced_payload, should_cancel=should_cancel, runtime=runtime
            )

        # Try YAML plugin first
        plugin = self._resolve_plugin_entry(task_name)
        if plugin is not None:
            payload_error = self._validate_plugin_payload(script_payload, plugin.manifest.inputs)
            if payload_error is not None:
                return self._dispatch_error(task_name=task_name, **payload_error)
            enhanced_payload = self._resolve_plugin_payload(script_payload, plugin.manifest.inputs)
            return self._run_yaml_plugin(
                task_name,
                enhanced_payload,
                plugin,
                should_cancel,
                runtime,
                emit_event,
                validate_payload=False,
            )

        # Unknown named task
        if task_name and task_name != "anonymous":
            return self._dispatch_error(
                task_name=task_name,
                code="unsupported_task",
                message=f"unsupported task: {task_name}",
            )

        # Anonymous script execution
        if plan.get("steps"):
            app_id = resolve_app_id(script_payload)
            enhanced_payload = resolve_app_payload(app_id, script_payload)
            return self._run_anonymous_script(
                task_name, enhanced_payload, plan, should_cancel, runtime, emit_event
            )

        # Empty anonymous stub
        return {
            "ok": True,
            "task": task_name,
            "step_count": 0,
            "status": "stub_executed",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _run_anonymous_script(
        self,
        task_name: str,
        payload: dict[str, Any],
        plan: dict[str, Any],
        should_cancel: Callable[[], bool] | None = None,
        runtime: dict[str, Any] | None = None,
        emit_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        try:
            # Construct a WorkflowScript model for validation and execution
            script = WorkflowScript(
                version="v1",
                workflow=task_name or "anonymous",
                steps=[ActionStep(**step) for step in plan.get("steps", [])],
            )

            # Validate actions
            action_error = self._validate_script_actions(script)
            if action_error is not None:
                return self._dispatch_error(task_name=task_name, **action_error)

            # Execute via interpreter
            result = self._interpreter.execute(
                script,
                payload,
                should_cancel=should_cancel,
                runtime=runtime,
                emit_event=emit_event,
            )
            result.setdefault("task", task_name)
            result.setdefault("timestamp", datetime.now(UTC).isoformat())
            return result
        except Exception as exc:
            logger.exception("anonymous script execution failed")
            return self._dispatch_error(
                task_name=task_name,
                code="script_execution_error",
                message=str(exc),
            )

    def _run_yaml_plugin(
        self,
        task_name: str,
        payload: dict[str, Any],
        plugin: Any,
        should_cancel: Callable[[], bool] | None = None,
        runtime: dict[str, Any] | None = None,
        emit_event: Callable[[str, dict[str, Any]], None] | None = None,
        *,
        validate_payload: bool = True,
    ) -> dict[str, Any]:
        try:
            script = parse_script(plugin.script_path)
            if validate_payload:
                payload_error = self._validate_plugin_payload(payload, plugin.manifest.inputs)
                if payload_error is not None:
                    return self._dispatch_error(task_name=task_name, **payload_error)

            action_error = self._validate_script_actions(script)
            if action_error is not None:
                return self._dispatch_error(task_name=task_name, **action_error)

            result = self._interpreter.execute(
                script,
                payload,
                plugin_inputs=plugin.manifest.inputs,
                should_cancel=should_cancel,
                runtime=runtime,
                emit_event=emit_event,
            )
            result.setdefault("task", task_name)
            result.setdefault("timestamp", datetime.now(UTC).isoformat())
            return result
        except Exception as exc:
            logger.exception("plugin %s execution failed", task_name)
            return self._dispatch_error(
                task_name=task_name,
                code="plugin_dispatch_error",
                message=str(exc),
            )

    def _resolve_plugin_payload(
        self,
        payload: dict[str, Any],
        inputs: list[PluginInput],
    ) -> dict[str, Any]:
        declared_inputs = {plugin_input.name for plugin_input in inputs}
        app_id = self._resolve_plugin_app_id(payload, inputs)
        enhanced_payload = resolve_app_payload(app_id, payload) if app_id else dict(payload)
        if "app_id" not in declared_inputs:
            enhanced_payload.pop("app_id", None)
        return enhanced_payload

    @staticmethod
    def _resolve_plugin_app_id(payload: dict[str, Any], inputs: list[PluginInput]) -> str:
        # Explicit app_id or app in payload takes priority
        for key in ("app_id", "app"):
            raw = str(payload.get(key) or "").strip().lower()
            if raw and raw != "default":
                return raw
        # package -> app lookup
        package = str(payload.get("package") or "").strip()
        if package:
            from core.app_config import AppConfigManager
            mapped = AppConfigManager.find_app_by_package(package)
            if mapped:
                return mapped
        # Fall back to manifest input default
        for plugin_input in inputs:
            if plugin_input.name != "app_id":
                continue
            raw = str(plugin_input.default or "").strip().lower()
            if raw:
                return raw
        return ""

    def _dispatch_error(self, task_name: str, code: str, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "task": task_name,
            "status": "failed_config_error",
            "checkpoint": "dispatch",
            "code": code,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _validate_plugin_payload(
        self, payload: dict[str, Any], inputs: list[PluginInput]
    ) -> dict[str, str] | None:
        if self._strict_unknown_inputs_enabled():
            declared_inputs = {plugin_input.name for plugin_input in inputs}
            unknown_inputs = sorted(
                key
                for key in payload
                if key not in declared_inputs and key != "task" and not str(key).startswith("_")
            )
            if unknown_inputs:
                rendered = ", ".join(unknown_inputs)
                return {
                    "code": "invalid_params",
                    "message": f"unknown input parameter(s): {rendered}",
                }

        for plugin_input in inputs:
            value = payload.get(plugin_input.name)
            has_value = plugin_input.name in payload and value is not None
            if plugin_input.required and not has_value and plugin_input.default is None:
                return {
                    "code": "missing_required_param",
                    "message": f"missing required input: {plugin_input.name}",
                }
            if not has_value:
                continue
            if not self._matches_input_type(plugin_input.type, value):
                expected = plugin_input.type.value
                actual = type(value).__name__
                return {
                    "code": "invalid_params",
                    "message": f"invalid input type for {plugin_input.name}: expected {expected}, got {actual}",
                }
        return None

    @staticmethod
    def _strict_unknown_inputs_enabled() -> bool:
        return strict_plugin_unknown_inputs_enabled()

    def _validate_script_actions(self, script: WorkflowScript) -> dict[str, str] | None:
        allowed_actions = set(get_registry().names)
        for step in script.steps:
            if not isinstance(step, ActionStep):
                continue
            action = step.action.strip()
            if action not in allowed_actions:
                return {
                    "code": "unknown_action",
                    "message": f"unknown action in plugin script: {action}",
                }
            if not action.startswith(ALLOWED_ACTION_PREFIXES):
                return {
                    "code": "action_not_allowed",
                    "message": f"action is outside allowed namespaces: {action}",
                }
        return None

    def _matches_input_type(self, expected_type: InputType, value: Any) -> bool:
        if expected_type == InputType.string:
            return isinstance(value, str)
        if expected_type == InputType.integer:
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == InputType.number:
            return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(
                value, float
            )
        if expected_type == InputType.boolean:
            return isinstance(value, bool)
        return False
