from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.app_config import resolve_app_id, resolve_app_payload
from core.business_profile import inject_branch_payload
from engine.action_registry import get_registry
from engine.agent_executor import AgentExecutorRuntime
from engine.interpreter import Interpreter
from engine.models.manifest import InputType, PluginInput
from engine.models.workflow import ActionStep, WorkflowScript
from engine.parser import ScriptParser, parse_script
from engine.plugin_loader import get_shared_plugin_loader

logger = logging.getLogger(__name__)
_PIPELINE_TASK_NAME = "_pipeline"
_PIPELINE_WAIT_POLL_SECONDS = 0.2

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
        plugin = self._plugin_loader.get(task_name)
        if plugin is not None:
            return plugin
        self._plugin_loader = get_shared_plugin_loader(refresh=True)
        return self._plugin_loader.get(task_name)

    def _normalize_pipeline_steps(
        self,
        raw_steps: object,
        *,
        inherited_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if isinstance(raw_steps, str):
            try:
                raw_steps = json.loads(raw_steps)
            except Exception as exc:
                raise ValueError("pipeline steps must be valid JSON when provided as string") from exc
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("pipeline steps must be a non-empty list")
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(raw_steps, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"pipeline step #{index} must be an object")
            plugin_name = str(item.get("plugin") or item.get("task") or "").strip()
            if not plugin_name:
                raise ValueError(f"pipeline step #{index} is missing plugin")
            if plugin_name == _PIPELINE_TASK_NAME:
                raise ValueError("nested _pipeline steps are not supported")
            payload = item.get("payload")
            if payload is None:
                payload_dict: dict[str, Any] = {}
            elif isinstance(payload, dict):
                payload_dict = dict(payload)
            else:
                raise ValueError(f"pipeline step #{index} payload must be an object")
            if isinstance(inherited_payload, dict):
                for key, inherited_value in inherited_payload.items():
                    if inherited_value in (None, "", []):
                        continue
                    if key in payload_dict and payload_dict.get(key) not in (None, "", []):
                        raise ValueError(
                            f"pipeline step #{index} must not override inherited {key}"
                        )
                    payload_dict[key] = inherited_value
            label = str(item.get("label") or item.get("display_name") or plugin_name).strip()
            normalized.append(
                {
                    "plugin": plugin_name,
                    "label": label or plugin_name,
                    "payload": payload_dict,
                }
            )
        return normalized

    @staticmethod
    def _pipeline_cancelled_result(*, steps_completed: int, rounds_completed: int) -> dict[str, Any]:
        return {
            "ok": False,
            "task": _PIPELINE_TASK_NAME,
            "status": "cancelled",
            "code": "task_cancelled",
            "message": "pipeline cancelled by user",
            "data": {
                "steps_completed": steps_completed,
                "rounds_completed": rounds_completed,
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _run_pipeline_step(
        self,
        step: dict[str, Any],
        *,
        should_cancel: Callable[[], bool] | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        child_payload = {"task": str(step["plugin"]), **dict(step.get("payload") or {})}
        return self.run(child_payload, should_cancel=should_cancel, runtime=runtime)

    def _sleep_pipeline_interval(
        self,
        *,
        interval_ms: int,
        should_cancel: Callable[[], bool] | None,
    ) -> bool:
        remaining = max(0.0, interval_ms / 1000.0)
        while remaining > 0:
            if should_cancel is not None and should_cancel():
                return False
            chunk = min(remaining, _PIPELINE_WAIT_POLL_SECONDS)
            time.sleep(chunk)
            remaining -= chunk
        return True

    def _run_pipeline(
        self,
        payload: dict[str, Any],
        *,
        should_cancel: Callable[[], bool] | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            normalized_payload = inject_branch_payload(payload)
            inherited_payload = {
                key: normalized_payload.get(key)
                for key in ("branch_id", "accepted_role_tags", "resource_namespace")
            }
            steps = self._normalize_pipeline_steps(
                normalized_payload.get("steps"),
                inherited_payload=inherited_payload,
            )
            repeat = int(payload.get("repeat", 1) or 1)
            repeat_interval_ms = int(payload.get("repeat_interval_ms", 0) or 0)
        except ValueError as exc:
            return self._dispatch_error(
                task_name=_PIPELINE_TASK_NAME,
                code="pipeline_config_error",
                message=str(exc),
            )
        except Exception as exc:
            return self._dispatch_error(
                task_name=_PIPELINE_TASK_NAME,
                code="pipeline_config_error",
                message=f"invalid pipeline configuration: {exc}",
            )

        if repeat < 0:
            return self._dispatch_error(
                task_name=_PIPELINE_TASK_NAME,
                code="pipeline_config_error",
                message="pipeline repeat must be >= 0",
            )
        if repeat_interval_ms < 0:
            return self._dispatch_error(
                task_name=_PIPELINE_TASK_NAME,
                code="pipeline_config_error",
                message="pipeline repeat_interval_ms must be >= 0",
            )

        emit_event = runtime.get("emit_event") if runtime else None
        total_steps = len(steps)
        rounds_completed = 0
        steps_completed = 0
        round_index = 0
        collected_results: list[dict[str, Any]] = []

        while repeat == 0 or round_index < repeat:
            round_index += 1
            for step_index, step in enumerate(steps, start=1):
                if should_cancel is not None and should_cancel():
                    return self._pipeline_cancelled_result(
                        steps_completed=steps_completed,
                        rounds_completed=rounds_completed,
                    )

                child_result = self._run_pipeline_step(
                    step,
                    should_cancel=should_cancel,
                    runtime=runtime,
                )
                steps_completed += 1
                child_status = str(child_result.get("status") or "")
                collected_results.append(
                    {
                        "round": round_index,
                        "step": step_index,
                        "plugin": step["plugin"],
                        "label": step["label"],
                        "status": child_status,
                        "ok": bool(child_result.get("ok")),
                        "message": str(child_result.get("message") or ""),
                    }
                )
                if emit_event:
                    emit_event(
                        "pipeline.step_done",
                        {
                            "round": round_index,
                            "repeat": repeat,
                            "step": step_index,
                            "total_steps": total_steps,
                            "plugin": step["plugin"],
                            "label": step["label"],
                            "ok": bool(child_result.get("ok")),
                            "status": child_status,
                            "message": str(child_result.get("message") or ""),
                        },
                    )
                if not bool(child_result.get("ok")):
                    return {
                        **child_result,
                        "task": _PIPELINE_TASK_NAME,
                        "message": (
                            f"pipeline stopped at round {round_index} step {step_index} "
                            f"({step['label']}): {str(child_result.get('message') or '').strip()}"
                        ).strip(),
                        "data": {
                            **(
                                child_result.get("data")
                                if isinstance(child_result.get("data"), dict)
                                else {}
                            ),
                            "steps_completed": steps_completed,
                            "rounds_completed": rounds_completed,
                            "pipeline_results": collected_results,
                        },
                    }
            rounds_completed += 1
            if repeat != 0 and round_index >= repeat:
                break
            if repeat_interval_ms > 0 and not self._sleep_pipeline_interval(
                interval_ms=repeat_interval_ms,
                should_cancel=should_cancel,
            ):
                return self._pipeline_cancelled_result(
                    steps_completed=steps_completed,
                    rounds_completed=rounds_completed,
                )

        return {
            "ok": True,
            "task": _PIPELINE_TASK_NAME,
            "status": "completed",
            "message": "pipeline completed",
            "data": {
                "steps_completed": steps_completed,
                "rounds_completed": rounds_completed,
                "pipeline_results": collected_results,
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }

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

        if task_name == _PIPELINE_TASK_NAME:
            return self._run_pipeline(script_payload, should_cancel=should_cancel, runtime=runtime)

        if task_name == self._agent_executor_runtime.task_name:
            app_id = resolve_app_id(script_payload)
            enhanced_payload = resolve_app_payload(app_id, inject_branch_payload(script_payload))
            return self._agent_executor_runtime.run(
                enhanced_payload, should_cancel=should_cancel, runtime=runtime
            )

        # Try YAML plugin first
        plugin = self._resolve_plugin_entry(task_name)
        if plugin is not None:
            normalized_payload = self._normalize_plugin_input_aliases(
                script_payload,
                plugin.manifest.inputs,
            )
            payload_error = self._validate_plugin_payload(normalized_payload, plugin.manifest.inputs)
            if payload_error is not None:
                return self._dispatch_error(task_name=task_name, **payload_error)
            enhanced_payload = self._resolve_plugin_payload(normalized_payload, plugin.manifest.inputs)
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
            enhanced_payload = resolve_app_payload(app_id, inject_branch_payload(script_payload))
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
        normalized_payload = inject_branch_payload(payload)
        enhanced_payload = (
            resolve_app_payload(app_id, normalized_payload) if app_id else dict(normalized_payload)
        )
        if "app_id" not in declared_inputs:
            enhanced_payload.pop("app_id", None)
        return enhanced_payload

    def _normalize_plugin_input_aliases(
        self,
        payload: dict[str, Any],
        inputs: list[PluginInput],
    ) -> dict[str, Any]:
        normalized = inject_branch_payload(payload)
        declared_inputs = {plugin_input.name for plugin_input in inputs}
        if "branch_id" in declared_inputs:
            normalized.pop("ai_type", None)
        return normalized

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
