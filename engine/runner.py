from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from engine.action_registry import get_registry
from engine.gpt_executor import GptExecutorRuntime
from engine.interpreter import Interpreter
from engine.models.manifest import InputType, PluginInput
from engine.models.workflow import ActionStep, WorkflowScript
from engine.parser import ScriptParser, parse_script
from engine.plugin_loader import get_shared_plugin_loader

logger = logging.getLogger(__name__)

ALLOWED_ACTION_PREFIXES = ("app.", "browser.", "core.", "credentials.", "device.", "mytos.", "sdk.", "ui.")


def strict_plugin_unknown_inputs_enabled() -> bool:
    raw = os.environ.get("MYT_STRICT_PLUGIN_UNKNOWN_INPUTS", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class Runner:
    def __init__(self, *, gpt_executor_runtime: GptExecutorRuntime | None = None) -> None:
        self._parser = ScriptParser()
        self._plugin_loader = get_shared_plugin_loader()
        self._interpreter = Interpreter()
        self._gpt_executor_runtime = gpt_executor_runtime or GptExecutorRuntime()

    def run(
        self,
        script_payload: Dict[str, Any],
        should_cancel: Callable[[], bool] | None = None,
        runtime: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        if task_name == self._gpt_executor_runtime.task_name:
            return self._gpt_executor_runtime.run(script_payload, should_cancel=should_cancel, runtime=runtime)

        # Try YAML plugin first
        plugin = self._plugin_loader.get(task_name)
        if plugin is not None:
            return self._run_yaml_plugin(task_name, script_payload, plugin, should_cancel, runtime, emit_event)

        # Unknown named task
        if task_name and task_name != "anonymous":
            return self._dispatch_error(
                task_name=task_name,
                code="unsupported_task",
                message=f"unsupported task: {task_name}",
            )

        # Anonymous script execution
        if plan.get("steps"):
            return self._run_anonymous_script(task_name, script_payload, plan, should_cancel, runtime, emit_event)

        # Empty anonymous stub
        return {
            "ok": True,
            "task": task_name,
            "step_count": 0,
            "status": "stub_executed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_anonymous_script(
        self,
        task_name: str,
        payload: Dict[str, Any],
        plan: Dict[str, Any],
        should_cancel: Callable[[], bool] | None = None,
        runtime: Dict[str, Any] | None = None,
        emit_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        try:
            # Construct a WorkflowScript model for validation and execution
            script = WorkflowScript(
                version="v1",
                workflow=task_name or "anonymous",
                steps=[ActionStep(**step) for step in plan.get("steps", [])]
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
            result.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
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
        payload: Dict[str, Any],
        plugin: Any,
        should_cancel: Callable[[], bool] | None = None,
        runtime: Dict[str, Any] | None = None,
        emit_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        try:
            script = parse_script(plugin.script_path)
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
            result.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
            return result
        except Exception as exc:
            logger.exception("plugin %s execution failed", task_name)
            return self._dispatch_error(
                task_name=task_name,
                code="plugin_dispatch_error",
                message=str(exc),
            )

    def _dispatch_error(self, task_name: str, code: str, message: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "task": task_name,
            "status": "failed_config_error",
            "checkpoint": "dispatch",
            "code": code,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _validate_plugin_payload(self, payload: Dict[str, Any], inputs: list[PluginInput]) -> Dict[str, str] | None:
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

    def _validate_script_actions(self, script: WorkflowScript) -> Dict[str, str] | None:
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
            return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(value, float)
        if expected_type == InputType.boolean:
            return isinstance(value, bool)
        return False
