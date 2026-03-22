# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingParameterType=false, reportDeprecated=false, reportImportCycles=false

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

from ai_services.llm_client import LLMClient
from engine.action_dispatcher import dispatch_action
from engine.action_registry import ActionRegistry, get_registry
from engine.models.runtime import ExecutionContext

from .agent_executor_planning import AgentExecutorPlanningMixin
from .agent_executor_support import (
    _action_fingerprint,
    _apply_fallback_state_hint,
    _build_history_digest,
    _build_reflection,
    _dynamic_step_extension_reason,
    _dynamic_step_extension_size,
    _fallback_xml_text,
    _int_in_range,
    _is_non_mutating_action,
    _json_dict,
    _needs_form_submit,
    _normalize_locate_point_params,
    _observation_certainty,
    _observation_requires_fallback,
    _observation_source,
    _observation_state_id,
    _planner_allowed_actions,
    _planner_inputs,
    _rewrite_text_entry_locate_params,
    _rewrite_two_factor_input_params,
    _should_wait_through_loading_overlay,
    _stabilize_fallback_state_hint,
    _stable_fingerprint,
    _string_list,
    _timestamp,
)
from .agent_executor_trace import AgentExecutorTraceMixin
from .agent_executor_types import AgentExecutorConfig, LLMClientLike

if TYPE_CHECKING:
    from core.model_trace_store import ModelTraceContext, ModelTraceStore
    from engine.planners import BasePlanner


_TRANSITION_WAIT_TIMEOUT_MS = 2500
_TRANSITION_WAIT_INTERVAL_MS = 300
_LOADING_WAIT_TIMEOUT_MS = 5000
_LOADING_WAIT_INTERVAL_MS = 400
_DYNAMIC_STEP_EXTENSION_MAX_ROUNDS = 1
_EMPTY_ACTION_DEFER_LIMIT = 3

_ = sys.modules.setdefault(f"{__name__}.time", time)


class AgentExecutorRuntime(AgentExecutorTraceMixin, AgentExecutorPlanningMixin):
    task_name: str = "agent_executor"

    def __init__(
        self,
        *,
        registry: ActionRegistry | None = None,
        llm_client_factory: Callable[[], LLMClientLike] | None = None,
        trace_store: ModelTraceStore | None = None,
        planner: BasePlanner | None = None,
    ) -> None:
        from core.model_trace_store import ModelTraceStore

        self._registry = registry or get_registry()
        self._llm_client_factory = llm_client_factory or LLMClient
        self._trace_store = trace_store or ModelTraceStore()
        if planner is None:
            from engine.planners import resolve_planner

            self._planner = resolve_planner(self)
        else:
            self._planner = planner

    def run(
        self,
        payload: dict[str, Any],
        *,
        should_cancel: Callable[[], bool] | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config_error = self.validate_payload(payload)
        if config_error is not None:
            return self._result(
                ok=False, status="failed_config_error", checkpoint="dispatch", **config_error
            )

        config = self._parse_config(payload, runtime=runtime)
        context = ExecutionContext(payload=dict(payload), runtime=dict(runtime or {}))
        context.should_cancel = should_cancel
        context.emit_event = (runtime or {}).get("emit_event")
        ui_match_state = self._registry.resolve("ui.match_state")
        ui_observe_transition = (
            self._registry.resolve("ui.observe_transition")
            if self._registry.has("ui.observe_transition")
            else None
        )
        ui_wait_until = (
            self._registry.resolve("ui.wait_until") if self._registry.has("ui.wait_until") else None
        )
        target_package = str(payload.get("package") or "").strip()

        if target_package:
            app_ensure_running = self._registry.resolve("app.ensure_running")
            ensure_running_result = app_ensure_running(
                {"package": target_package, "verify_timeout": 1.5}, context
            )
            if not ensure_running_result.ok:
                return self._result(
                    ok=False,
                    status="failed_runtime_error",
                    checkpoint="dispatch",
                    code=str(ensure_running_result.code or "app_ensure_running_failed"),
                    message=str(
                        ensure_running_result.message
                        or f"failed to bring {target_package} to foreground"
                    ),
                )

        stagnant_observation_count = 0
        previous_observation_fingerprint = ""
        last_action: dict[str, object] | None = None
        history: list[dict[str, object]] = []
        trace_context = self._trace_context(runtime)
        pending_trace_record: dict[str, object] | None = None
        repeated_action_count = 0
        previous_action_fingerprint = ""
        empty_action_defer_count = 0
        effective_max_steps = config.max_steps
        step_budget_extensions_used = 0
        extended_steps_total = 0
        last_observation: dict[str, object] = {
            "data": {},
            "ok": False,
            "modality": "structured_state",
            "observed_state_ids": [],
            "fallback_evidence": {},
            "observed_at": "",
            "step_index": 0,
        }

        step_index = 1
        while True:
            if step_index > effective_max_steps:
                extension_reason = ""
                if step_budget_extensions_used < _DYNAMIC_STEP_EXTENSION_MAX_ROUNDS:
                    extension_reason = _dynamic_step_extension_reason(
                        config=config,
                        history=history,
                        last_observation=last_observation,
                        last_action=last_action,
                        stagnant_observation_count=stagnant_observation_count,
                        repeated_action_count=repeated_action_count,
                    )
                if extension_reason:
                    extension_steps = _dynamic_step_extension_size(config.max_steps)
                    previous_max_steps = effective_max_steps
                    effective_max_steps += extension_steps
                    step_budget_extensions_used += 1
                    extended_steps_total += extension_steps
                    if context.emit_event:
                        context.emit_event(
                            "task.step_budget_extended",
                            {
                                "step": step_index - 1,
                                "previous_max_steps": previous_max_steps,
                                "effective_max_steps": effective_max_steps,
                                "extension_steps": extension_steps,
                                "reason": extension_reason,
                            },
                        )
                    continue
                break

            previous_state_id = _observation_state_id(last_observation.get("data"))
            if should_cancel is not None and should_cancel():
                self._flush_pending_trace(trace_context, pending_trace_record)
                self._append_trace(
                    trace_context,
                    self._terminal_trace_record(
                        status="cancelled",
                        sequence=step_index + (1 if pending_trace_record is not None else 0),
                        step_index=step_index - 1,
                        observation=_json_dict(last_observation.get("data")),
                        observation_ok=bool(last_observation.get("ok")),
                        observation_modality=str(
                            last_observation.get("modality") or "structured_state"
                        ),
                        observed_state_ids=_string_list(last_observation.get("observed_state_ids")),
                        fallback_reason=str(
                            last_observation.get("fallback_reason")
                            or self._fallback_reason(
                                observation_ok=bool(last_observation.get("ok")),
                                observation_payload=_json_dict(last_observation.get("data")),
                            )
                        ),
                        fallback_evidence=_json_dict(last_observation.get("fallback_evidence")),
                        code="task_cancelled",
                        message="task cancelled by user",
                        observed_at=str(last_observation.get("observed_at") or ""),
                    ),
                )
                return self._cancelled(step_index=step_index - 1, history=history)

            observation_result = self._observe_step(
                config=config,
                context=context,
                trace_context=trace_context,
                step_index=step_index,
                last_action=last_action,
                previous_state_id=previous_state_id,
                ui_match_state=ui_match_state,
                ui_observe_transition=ui_observe_transition,
                ui_wait_until=ui_wait_until,
            )
            observation_ok = bool(observation_result["observation_ok"])
            observation_state = observation_result["observation_state"]
            observed_at = str(observation_result["observed_at"])
            observation_modality = str(observation_result["modality"])
            observed_state_ids = _string_list(observation_result["observed_state_ids"])
            observation_requires_fallback = bool(observation_result["requires_fallback"])
            observation_certainty = str(observation_result["state_certainty"])
            observation_source = str(observation_result["state_source"])
            fallback_reason = str(observation_result["fallback_reason"])
            fallback_evidence = _json_dict(observation_result["fallback_evidence"])
            observation_fingerprint = str(observation_result["fingerprint"])
            last_observation = {
                "data": observation_state if isinstance(observation_state, dict) else {},
                "ok": observation_ok,
                "fallback_reason": fallback_reason,
                "modality": observation_modality,
                "observed_state_ids": observed_state_ids,
                "state_certainty": observation_certainty,
                "state_source": observation_source,
                "fallback_evidence": fallback_evidence,
                "observed_at": observed_at,
                "step_index": step_index,
            }

            if pending_trace_record is not None:
                pending_trace_record["post_action_transition"] = {
                    "transition_status": "observed",
                    "next_observation_modality": observation_modality,
                    "next_observed_state_ids": observed_state_ids,
                    "next_observation_ok": observation_ok,
                    "next_observation": observation_state,
                    "observed_at": observed_at,
                }
                self._append_trace(trace_context, pending_trace_record)
                pending_trace_record = None

            if (
                step_index > 1
                and observation_fingerprint == previous_observation_fingerprint
                and not _is_non_mutating_action(last_action)
            ):
                stagnant_observation_count += 1
            else:
                stagnant_observation_count = 0
            previous_observation_fingerprint = observation_fingerprint

            if stagnant_observation_count >= config.stagnant_limit:
                return self._failed_circuit_breaker_result(
                    trace_context=trace_context,
                    sequence=step_index,
                    step_index=step_index,
                    checkpoint="observe",
                    code="stagnant_structured_state",
                    message="structured state observation did not change across repeated actions",
                    step_count=step_index - 1,
                    history=history,
                    circuit_breaker={
                        "code": "stagnant_structured_state",
                        "step_index": step_index,
                        "stagnant_limit": config.stagnant_limit,
                        "stagnant_observation_count": stagnant_observation_count,
                        "observation": observation_state,
                    },
                    observation=observation_state if isinstance(observation_state, dict) else {},
                    observation_ok=observation_ok,
                    observation_modality=observation_modality,
                    observed_state_ids=observed_state_ids,
                    fallback_reason=fallback_reason,
                    fallback_evidence=fallback_evidence,
                    observed_at=observed_at,
                )

            planned_step = self._plan_step(
                config=config,
                context=context,
                step_index=step_index,
                last_action=last_action,
                history=history,
                repeated_action_count=repeated_action_count,
                previous_state_id=previous_state_id,
                observation_state=observation_state,
                observation_requires_fallback=observation_requires_fallback,
                fallback_reason=fallback_reason,
                fallback_evidence=fallback_evidence,
                should_cancel=should_cancel,
            )
            plan = _json_dict(planned_step["plan"])
            history_digest_raw = planned_step["history_digest"]
            history_digest = history_digest_raw if isinstance(history_digest_raw, list) else []
            reflection = _json_dict(planned_step["reflection"])

            if plan["ok"] is False:
                return self._planning_failure(
                    trace_context=trace_context,
                    step_index=step_index,
                    history=history,
                    observation_state=observation_state,
                    observation_ok=bool(last_observation.get("ok")),
                    observation_modality=observation_modality,
                    observed_state_ids=observed_state_ids,
                    fallback_reason=str(plan.get("fallback_reason") or ""),
                    fallback_evidence=fallback_evidence,
                    observed_at=observed_at,
                    plan=plan,
                    code=str(plan.get("code") or "planner_error"),
                    message=str(plan.get("message") or "planner failed"),
                )

            if bool(plan.get("done")):
                self._append_trace(
                    trace_context,
                    self._terminal_trace_record(
                        status="completed",
                        sequence=step_index,
                        step_index=step_index,
                        observation=observation_state
                        if isinstance(observation_state, dict)
                        else {},
                        observation_ok=bool(last_observation.get("ok")),
                        observation_modality=observation_modality,
                        observed_state_ids=observed_state_ids,
                        fallback_reason=str(plan.get("fallback_reason") or ""),
                        fallback_evidence=fallback_evidence,
                        code="done",
                        message=str(plan.get("message") or "gpt executor completed"),
                        observed_at=observed_at,
                        planner=plan,
                    ),
                )
                learned_package = self._resolve_learning_package(target_package, observation_state)
                if learned_package:
                    self._trigger_learning_hook(trace_context, learned_package)
                return self._result(
                    ok=True,
                    status="completed",
                    checkpoint="complete",
                    message=str(plan.get("message") or "gpt executor completed"),
                    step_count=step_index - 1,
                    history=history,
                    final_observation=observation_state,
                    extracted_data=plan.get("extracted_data"),
                    planner=plan,
                )

            action_name = str(planned_step["action_name"])
            action_params = _json_dict(planned_step["action_params"])

            empty_action_defer_outcome = self._handle_empty_action_defer_branch(
                config=config,
                trace_context=trace_context,
                step_index=step_index,
                history=history,
                empty_action_defer_count=empty_action_defer_count,
                observation_ok=observation_ok,
                observation_state=observation_state,
                observation_modality=observation_modality,
                observed_state_ids=observed_state_ids,
                observation_requires_fallback=observation_requires_fallback,
                fallback_reason=fallback_reason,
                fallback_evidence=fallback_evidence,
                observed_at=observed_at,
                plan=plan,
                emit_event=context.emit_event,
            )
            empty_action_defer_count = int(str(empty_action_defer_outcome["defer_count"]))
            if bool(empty_action_defer_outcome["continue_loop"]):
                step_index += 1
                continue
            branch_result = empty_action_defer_outcome.get("result")
            if isinstance(branch_result, dict):
                return branch_result

            empty_action_defer_count = 0
            if action_name not in config.allowed_actions:
                return self._planning_failure(
                    trace_context=trace_context,
                    step_index=step_index,
                    history=history,
                    observation_state=observation_state,
                    observation_ok=bool(last_observation.get("ok")),
                    observation_modality=observation_modality,
                    observed_state_ids=observed_state_ids,
                    fallback_reason=str(plan.get("fallback_reason") or ""),
                    fallback_evidence=fallback_evidence,
                    observed_at=observed_at,
                    plan=plan,
                    code="invalid_action_selection",
                    message=f"planner selected action outside allowed set: {action_name or '<empty>'}",
                )

            if context.emit_event:
                context.emit_event(
                    "task.planning",
                    {
                        "step": step_index,
                        "action": action_name,
                        "params": action_params,
                        "message": str(plan.get("message") or ""),
                    },
                )
            action_result = dispatch_action(action_name, action_params, context, registry=self._registry)
            action_result_payload = action_result.model_dump(mode="python")
            if context.emit_event:
                context.emit_event(
                    "task.action_result",
                    {
                        "step": step_index,
                        "label": action_name,
                        "ok": action_result.ok,
                        "message": action_result.message or "",
                    },
                )

            current_action_fp = _action_fingerprint(action_name, action_params)
            repeated_action_count = (
                repeated_action_count + 1
                if current_action_fp == previous_action_fingerprint
                else 1
            )
            previous_action_fingerprint = current_action_fp
            last_action = {
                "action": action_name,
                "params": action_params,
                "result": action_result_payload,
            }
            history.append(
                {
                    "step_index": step_index,
                    "observation": observation_state,
                    "action": action_name,
                    "params": action_params,
                    "result": action_result_payload,
                }
            )
            pending_trace_record = {
                "trace_version": 1,
                "sequence": step_index,
                "step_index": step_index,
                "record_type": "step",
                "task": self.task_name,
                "status": "action_executed",
                "observation": {
                    "ok": observation_ok,
                    "modality": observation_modality,
                    "observed_state_ids": observed_state_ids,
                    "expected_state_ids": list(config.expected_state_ids),
                    "data": observation_state,
                },
                "fallback_reason": str(plan.get("fallback_reason") or fallback_reason),
                "fallback_evidence": fallback_evidence,
                "planner": self._trace_planner(plan),
                "chosen_action": action_name,
                "action_params": action_params,
                "action_result": action_result_payload,
                "reflection": reflection if reflection else None,
                "history_digest_length": len(history_digest),
                "repeated_action_count": repeated_action_count,
                "timestamps": {
                    "observed_at": observed_at,
                    "planned_at": str(plan.get("planned_at") or ""),
                    "action_completed_at": _timestamp(),
                },
            }

            if should_cancel is not None and should_cancel():
                self._flush_pending_trace(trace_context, pending_trace_record)
                self._append_trace(
                    trace_context,
                    self._terminal_trace_record(
                        status="cancelled",
                        sequence=step_index + 1,
                        step_index=step_index,
                        observation=observation_state
                        if isinstance(observation_state, dict)
                        else {},
                        observation_ok=observation_ok,
                        observation_modality=observation_modality,
                        observed_state_ids=observed_state_ids,
                        fallback_reason=str(plan.get("fallback_reason") or fallback_reason),
                        fallback_evidence=fallback_evidence,
                        code="task_cancelled",
                        message="task cancelled by user",
                        observed_at=observed_at,
                        planner=plan,
                    ),
                )
                return self._cancelled(step_index=step_index, history=history)

            step_index += 1

        final_step_count = step_index - 1
        terminal_sequence = final_step_count + (1 if pending_trace_record is not None else 0)
        self._flush_pending_trace(trace_context, pending_trace_record)
        return self._failed_circuit_breaker_result(
            trace_context=trace_context,
            sequence=terminal_sequence,
            step_index=final_step_count,
            checkpoint="loop",
            code="step_budget_exhausted",
            message="gpt executor exhausted configured step budget",
            step_count=final_step_count,
            history=history,
            circuit_breaker={
                "code": "step_budget_exhausted",
                "max_steps": config.max_steps,
                "effective_max_steps": effective_max_steps,
                "step_budget_extensions_used": step_budget_extensions_used,
                "extended_steps_total": extended_steps_total,
            },
            observation=_json_dict(last_observation.get("data")),
            observation_ok=bool(last_observation.get("ok")),
            observation_modality=str(last_observation.get("modality") or "structured_state"),
            observed_state_ids=_string_list(last_observation.get("observed_state_ids")),
            fallback_reason=str(
                last_observation.get("fallback_reason")
                or self._fallback_reason(
                    observation_ok=bool(last_observation.get("ok")),
                    observation_payload=_json_dict(last_observation.get("data")),
                )
            ),
            fallback_evidence=_json_dict(last_observation.get("fallback_evidence")),
            observed_at=str(last_observation.get("observed_at") or ""),
        )

    def _observe_step(
        self,
        *,
        config: AgentExecutorConfig,
        context: ExecutionContext,
        trace_context: ModelTraceContext,
        step_index: int,
        last_action: dict[str, object] | None,
        previous_state_id: str,
        ui_match_state: Callable[[dict[str, object], ExecutionContext], Any],
        ui_observe_transition: Callable[[dict[str, object], ExecutionContext], Any] | None,
        ui_wait_until: Callable[[dict[str, object], ExecutionContext], Any] | None,
    ) -> dict[str, object]:
        observation_params = {
            **config.observation_params,
            "expected_state_ids": list(config.expected_state_ids),
        }
        observation_operation = "match_state"
        transition_target_state_ids = [
            state_id for state_id in config.expected_state_ids if state_id != previous_state_id
        ]

        if (
            last_action is not None
            and previous_state_id
            and previous_state_id != "unknown"
            and transition_target_state_ids
            and ui_observe_transition is not None
            and _json_dict(last_action).get("action") == "ui.key_press"
            and str(_json_dict(_json_dict(last_action).get("params")).get("key") or "")
            .strip()
            .lower()
            == "enter"
            and bool(_json_dict(_json_dict(last_action).get("result")).get("ok"))
        ):
            observation_operation = "observe_transition"
            observation = ui_observe_transition(
                {
                    **observation_params,
                    "from_state_ids": [previous_state_id],
                    "to_state_ids": transition_target_state_ids,
                    "timeout_ms": _TRANSITION_WAIT_TIMEOUT_MS,
                    "interval_ms": _TRANSITION_WAIT_INTERVAL_MS,
                },
                context,
            )
        elif (
            last_action is not None
            and _json_dict(last_action).get("action") == "ui.key_press"
            and str(_json_dict(_json_dict(last_action).get("params")).get("key") or "")
            .strip()
            .lower()
            == "enter"
            and bool(_json_dict(_json_dict(last_action).get("result")).get("ok"))
            and ui_wait_until is not None
        ):
            observation_operation = "wait_until"
            observation = ui_wait_until(
                {
                    **observation_params,
                    "expected_state_ids": transition_target_state_ids
                    or list(config.expected_state_ids),
                    "timeout_ms": _TRANSITION_WAIT_TIMEOUT_MS,
                    "interval_ms": _TRANSITION_WAIT_INTERVAL_MS,
                },
                context,
            )
        else:
            observation = ui_match_state(observation_params, context)

        def _capture_observation(
            observation_result: Any, operation: str
        ) -> tuple[str, str, bool, object, dict[str, object]]:
            observed_at = _timestamp()
            observation_payload = observation_result.model_dump(mode="python")
            observation_ok = bool(observation_payload.get("ok"))
            observation_state = observation_payload.get("data", {})
            fallback_evidence = self._collect_fallback_evidence(
                context,
                observation_state,
                trace_context=trace_context,
                step_index=step_index,
            )
            observation_state = _apply_fallback_state_hint(
                observation_state,
                fallback_evidence,
                last_action,
            )
            observation_state = _stabilize_fallback_state_hint(
                observation_state,
                previous_state_id=previous_state_id,
                last_action=last_action,
            )
            return operation, observed_at, observation_ok, observation_state, fallback_evidence

        (
            observation_operation,
            observed_at,
            observation_ok,
            observation_state,
            fallback_evidence,
        ) = _capture_observation(observation, observation_operation)

        if _should_wait_through_loading_overlay(
            last_action=last_action,
            fallback_evidence=fallback_evidence,
        ):
            loading_wait_params = {
                **observation_params,
                "expected_state_ids": list(config.expected_state_ids),
                "timeout_ms": _LOADING_WAIT_TIMEOUT_MS,
                "interval_ms": _LOADING_WAIT_INTERVAL_MS,
            }
            if ui_wait_until is not None:
                observation_operation = "wait_until_loading"
                observation = ui_wait_until(loading_wait_params, context)
            else:
                observation_operation = "match_state_loading"
                observation = ui_match_state(loading_wait_params, context)
            (
                observation_operation,
                observed_at,
                observation_ok,
                observation_state,
                fallback_evidence,
            ) = _capture_observation(observation, observation_operation)

        observation_modality = self._observation_modality(observation_state)
        observed_state_ids = self._observed_state_ids(observation_state)
        observation_requires_fallback = _observation_requires_fallback(
            observation_ok=observation_ok,
            observation_payload=observation_state,
        )
        observation_certainty = _observation_certainty(
            observation_state,
            observation_ok=observation_ok,
        )
        observation_source = _observation_source(
            observation_state,
            operation=observation_operation,
        )
        fallback_reason = self._fallback_reason(
            observation_ok=observation_ok,
            observation_payload=observation_state,
        )
        if not observation_requires_fallback:
            observation_fingerprint = _stable_fingerprint(observation_state)
        else:
            observation_fingerprint = _stable_fingerprint(_fallback_xml_text(fallback_evidence))
        if context.emit_event:
            context.emit_event(
                "task.observation",
                {
                    "step": step_index,
                    "modality": observation_modality,
                    "observed_state_ids": observed_state_ids,
                    "ok": observation_ok,
                    "state_certainty": observation_certainty,
                    "state_source": observation_source,
                },
            )
        return {
            "observation_ok": observation_ok,
            "observation_state": observation_state,
            "observed_at": observed_at,
            "modality": observation_modality,
            "observed_state_ids": observed_state_ids,
            "requires_fallback": observation_requires_fallback,
            "state_certainty": observation_certainty,
            "state_source": observation_source,
            "fallback_reason": fallback_reason,
            "fallback_evidence": fallback_evidence,
            "fingerprint": observation_fingerprint,
        }

    def _handle_empty_action_defer(
        self,
        *,
        config: AgentExecutorConfig,
        trace_context: ModelTraceContext,
        step_index: int,
        empty_action_defer_count: int,
        observation_ok: bool,
        observation_state: object,
        observation_modality: str,
        observed_state_ids: list[str],
        observation_requires_fallback: bool,
        fallback_reason: str,
        fallback_evidence: dict[str, object],
        observed_at: str,
        plan: dict[str, Any],
        emit_event: Callable[[str, dict[str, Any]], None] | None,
    ) -> dict[str, object]:
        if str(plan.get("action") or "").strip() or not observation_requires_fallback:
            return {
                "deferred": False,
                "defer_count": empty_action_defer_count,
                "continue_loop": False,
            }

        next_defer_count = empty_action_defer_count + 1
        defer_message = str(
            plan.get("message") or "planner returned empty action during fallback observation"
        )
        if emit_event:
            emit_event(
                "task.planning_deferred",
                {
                    "step": step_index,
                    "reason": "empty_action_during_fallback_observation",
                    "retry_count": next_defer_count,
                    "retry_limit": _EMPTY_ACTION_DEFER_LIMIT,
                    "message": defer_message,
                },
            )
        if next_defer_count <= _EMPTY_ACTION_DEFER_LIMIT:
            self._append_trace(
                trace_context,
                {
                    "trace_version": 1,
                    "sequence": step_index,
                    "step_index": step_index,
                    "record_type": "step",
                    "task": self.task_name,
                    "status": "planning_deferred",
                    "observation": {
                        "ok": observation_ok,
                        "modality": observation_modality,
                        "observed_state_ids": observed_state_ids,
                        "expected_state_ids": list(config.expected_state_ids),
                        "data": observation_state,
                    },
                    "fallback_reason": str(plan.get("fallback_reason") or fallback_reason),
                    "fallback_evidence": fallback_evidence,
                    "planner": self._trace_planner(plan),
                    "message": defer_message,
                    "defer_count": next_defer_count,
                    "defer_limit": _EMPTY_ACTION_DEFER_LIMIT,
                    "timestamps": {
                        "observed_at": observed_at,
                        "planned_at": str(plan.get("planned_at") or ""),
                        "recorded_at": _timestamp(),
                    },
                },
            )
        return {
            "deferred": True,
            "defer_count": next_defer_count,
            "continue_loop": next_defer_count <= _EMPTY_ACTION_DEFER_LIMIT,
        }

    def _handle_empty_action_defer_branch(
        self,
        *,
        config: AgentExecutorConfig,
        trace_context: ModelTraceContext,
        step_index: int,
        history: list[dict[str, object]],
        empty_action_defer_count: int,
        observation_ok: bool,
        observation_state: object,
        observation_modality: str,
        observed_state_ids: list[str],
        observation_requires_fallback: bool,
        fallback_reason: str,
        fallback_evidence: dict[str, object],
        observed_at: str,
        plan: dict[str, Any],
        emit_event: Callable[[str, dict[str, Any]], None] | None,
    ) -> dict[str, object]:
        defer_outcome = self._handle_empty_action_defer(
            config=config,
            trace_context=trace_context,
            step_index=step_index,
            empty_action_defer_count=empty_action_defer_count,
            observation_ok=observation_ok,
            observation_state=observation_state,
            observation_modality=observation_modality,
            observed_state_ids=observed_state_ids,
            observation_requires_fallback=observation_requires_fallback,
            fallback_reason=fallback_reason,
            fallback_evidence=fallback_evidence,
            observed_at=observed_at,
            plan=plan,
            emit_event=emit_event,
        )
        if not bool(defer_outcome["deferred"]):
            return {
                "defer_count": empty_action_defer_count,
                "continue_loop": False,
                "result": None,
            }
        if bool(defer_outcome["continue_loop"]):
            return {
                "defer_count": int(str(defer_outcome["defer_count"])),
                "continue_loop": True,
                "result": None,
            }
        return {
            "defer_count": int(str(defer_outcome["defer_count"])),
            "continue_loop": False,
            "result": self._planning_failure(
                trace_context=trace_context,
                step_index=step_index,
                history=history,
                observation_state=observation_state,
                observation_ok=observation_ok,
                observation_modality=observation_modality,
                observed_state_ids=observed_state_ids,
                fallback_reason=str(plan.get("fallback_reason") or ""),
                fallback_evidence=fallback_evidence,
                observed_at=observed_at,
                plan=plan,
                code="planner_empty_action_retry_exhausted",
                message="planner returned empty action during fallback observation too many times",
            ),
        }

    def _plan_step(
        self,
        *,
        config: AgentExecutorConfig,
        context: ExecutionContext,
        step_index: int,
        last_action: dict[str, object] | None,
        history: list[dict[str, object]],
        repeated_action_count: int,
        previous_state_id: str,
        observation_state: object,
        observation_requires_fallback: bool,
        fallback_reason: str,
        fallback_evidence: dict[str, object],
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        plan: dict[str, Any] = {"ok": False, "message": "uninitialized"}
        max_planner_retries = 3
        history_digest = _build_history_digest(history)
        reflection = _build_reflection(
            last_action,
            repeated_action_count=repeated_action_count,
        )
        planner_allowed_actions = _planner_allowed_actions(
            allowed_actions=config.allowed_actions,
            last_action=last_action,
            observation_payload=observation_state if isinstance(observation_state, dict) else None,
            previous_state_id=previous_state_id,
            observation_requires_fallback=observation_requires_fallback,
        )
        if _needs_form_submit(
            last_action,
            observation_state if isinstance(observation_state, dict) else None,
            previous_state_id=previous_state_id,
        ):
            plan = {
                "ok": True,
                "done": False,
                "action": "ui.key_press",
                "params": {"key": "enter"},
                "message": "submit focused login field",
                "planned_at": _timestamp(),
                "fallback_reason": fallback_reason,
                "request_id": "",
                "provider": "",
                "model": "",
                "planner_structured_state": None,
            }
        else:
            compensation_plan = None
            if (
                observation_requires_fallback
                and "ai.locate_point" in config.allowed_actions
                and "ui.click" in config.allowed_actions
            ):
                compensation_plan = self._maybe_build_submit_compensation_plan(
                    context=context,
                    last_action=last_action,
                    observation_state=observation_state
                    if isinstance(observation_state, dict)
                    else None,
                    previous_state_id=previous_state_id,
                    fallback_reason=fallback_reason,
                    step_index=step_index,
                )
            if compensation_plan is not None:
                plan = compensation_plan
            else:
                from engine.planners import PlannerInput

                planner_input = PlannerInput(
                    goal=config.goal,
                    step_index=step_index,
                    allowed_actions=planner_allowed_actions,
                    observation=observation_state if isinstance(observation_state, dict) else {},
                    last_action=last_action,
                    fallback_enabled=observation_requires_fallback,
                    fallback_reason=fallback_reason,
                    fallback_evidence=fallback_evidence,
                    fallback_modalities=config.fallback_modalities,
                    system_prompt=config.system_prompt,
                    llm_runtime=config.llm_runtime,
                    planner_inputs=config.planner_inputs,
                    history_digest=history_digest,
                    reflection=reflection,
                )
                for attempt in range(max_planner_retries):
                    planner_output = self._planner.plan(planner_input)
                    plan = planner_output.to_legacy_dict()
                    if plan.get("ok") is not False:
                        break
                    if plan.get("retryable") and attempt < max_planner_retries - 1:
                        backoff = 2 ** (attempt + 1)
                        if self._interruptible_sleep(backoff, should_cancel):
                            break
                        continue
                    break

        action_name = str(plan.get("action") or "").strip()
        action_params = _rewrite_two_factor_input_params(
            action_name,
            _json_dict(plan.get("params")),
            observation_state if isinstance(observation_state, dict) else None,
            config.planner_inputs,
        )
        action_params = _normalize_locate_point_params(action_name, action_params)
        action_params = _rewrite_text_entry_locate_params(
            action_name,
            action_params,
            observation_state if isinstance(observation_state, dict) else None,
            last_action=last_action,
            previous_state_id=previous_state_id,
            observation_requires_fallback=observation_requires_fallback,
        )
        return {
            "plan": plan,
            "history_digest": history_digest,
            "reflection": reflection,
            "action_name": action_name,
            "action_params": action_params,
        }

    def validate_payload(self, payload: Mapping[str, object]) -> dict[str, str] | None:
        try:
            _ = self._parse_config(payload)
        except ValueError as exc:
            return {"code": "invalid_params", "message": str(exc)}
        return None

    def _parse_config(
        self, payload: Mapping[str, object], *, runtime: Mapping[str, object] | None = None
    ) -> AgentExecutorConfig:
        goal = str(payload.get("goal") or "").strip()
        if not goal:
            raise ValueError("agent_executor requires non-empty goal")

        expected_state_ids = _string_list(
            payload.get("expected_state_ids") or payload.get("state_ids")
        )
        if not expected_state_ids:
            raise ValueError("agent_executor requires expected_state_ids")

        allowed_actions = _string_list(payload.get("allowed_actions"))
        if not allowed_actions:
            raise ValueError("agent_executor requires allowed_actions")
        unknown_actions = [action for action in allowed_actions if not self._registry.has(action)]
        if unknown_actions:
            rendered = ", ".join(sorted(unknown_actions))
            raise ValueError(
                f"agent_executor allowed_actions must reference registered actions: {rendered}"
            )
        if "ui.match_state" in allowed_actions:
            raise ValueError("agent_executor allowed_actions must not include ui.match_state")

        observation_params = _json_dict(payload.get("observation"))
        _ = observation_params.pop("expected_state_ids", None)
        _ = observation_params.pop("state_ids", None)

        runtime_llm = _json_dict(runtime.get("llm")) if isinstance(runtime, Mapping) else {}
        payload_llm = _json_dict(payload.get("llm"))
        llm_runtime = {**runtime_llm, **payload_llm} if runtime_llm or payload_llm else {}

        return AgentExecutorConfig(
            goal=goal,
            expected_state_ids=expected_state_ids,
            allowed_actions=allowed_actions,
            max_steps=_int_in_range(payload.get("max_steps"), default=8, minimum=1, maximum=100),
            stagnant_limit=_int_in_range(
                payload.get("stagnant_limit"), default=5, minimum=1, maximum=20
            ),
            system_prompt=str(payload.get("system_prompt") or "").strip(),
            llm_runtime=llm_runtime,
            planner_inputs=_planner_inputs(payload),
            fallback_modalities=_string_list(payload.get("fallback_modalities") or ["vlm"]),
            observation_params=observation_params,
        )

    def _cancelled(self, *, step_index: int, history: list[dict[str, object]]) -> dict[str, Any]:
        return self._result(
            ok=False,
            status="cancelled",
            checkpoint="cancel",
            code="task_cancelled",
            message="task cancelled by user",
            step_count=step_index,
            history=history,
        )

    def _failed_circuit_breaker_result(
        self,
        *,
        trace_context: ModelTraceContext,
        sequence: int,
        step_index: int,
        checkpoint: str,
        code: str,
        message: str,
        step_count: int,
        history: list[dict[str, object]],
        circuit_breaker: dict[str, object],
        observation: dict[str, object],
        observation_ok: bool,
        observation_modality: str,
        observed_state_ids: list[str],
        fallback_reason: str,
        fallback_evidence: dict[str, object],
        observed_at: str,
    ) -> dict[str, Any]:
        self._append_trace(
            trace_context,
            self._terminal_trace_record(
                status="failed_circuit_breaker",
                sequence=sequence,
                step_index=step_index,
                observation=observation,
                observation_ok=observation_ok,
                observation_modality=observation_modality,
                observed_state_ids=observed_state_ids,
                fallback_reason=fallback_reason,
                fallback_evidence=fallback_evidence,
                code=code,
                message=message,
                observed_at=observed_at,
            ),
        )
        return self._result(
            ok=False,
            status="failed_circuit_breaker",
            checkpoint=checkpoint,
            code=code,
            message=message,
            step_count=step_count,
            history=history,
            circuit_breaker=circuit_breaker,
        )

    def _planning_failure(
        self,
        *,
        trace_context: ModelTraceContext,
        step_index: int,
        history: list[dict[str, object]],
        observation_state: object,
        observation_ok: bool,
        observation_modality: str,
        observed_state_ids: list[str],
        fallback_reason: str,
        fallback_evidence: dict[str, object],
        observed_at: str,
        plan: dict[str, Any],
        code: str,
        message: str,
    ) -> dict[str, Any]:
        self._append_trace(
            trace_context,
            self._terminal_trace_record(
                status="failed_runtime_error",
                sequence=step_index,
                step_index=step_index,
                observation=observation_state if isinstance(observation_state, dict) else {},
                observation_ok=observation_ok,
                observation_modality=observation_modality,
                observed_state_ids=observed_state_ids,
                fallback_reason=fallback_reason,
                fallback_evidence=fallback_evidence,
                code=code,
                message=message,
                observed_at=observed_at,
                planner=plan,
            ),
        )
        return self._result(
            ok=False,
            status="failed_runtime_error",
            checkpoint="planning",
            code=code,
            message=message,
            step_count=step_index - 1,
            history=history,
            planner=plan,
        )

    def _result(self, *, ok: bool, status: str, checkpoint: str, **extra: object) -> dict[str, Any]:
        return {
            "ok": ok,
            "task": self.task_name,
            "status": status,
            "checkpoint": checkpoint,
            "timestamp": _timestamp(),
            **extra,
        }
