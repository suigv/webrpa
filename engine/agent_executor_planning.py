from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_services.vlm_client import VLMClient
from engine.models.runtime import ExecutionContext

from . import planners as planner_module
from .agent_executor_support import (
    _json_dict,
    _submit_compensation_query,
    _timestamp,
    _vlm_allowed_action_types,
)

if TYPE_CHECKING:
    from .agent_executor_types import AgentExecutorConfig, LLMClientLike


logger = logging.getLogger(__name__)


class AgentExecutorPlanningMixin:
    def _maybe_build_submit_compensation_plan(
        self,
        *,
        context: ExecutionContext,
        last_action: Mapping[str, object] | None,
        observation_state: Mapping[str, object] | None,
        previous_state_id: str,
        fallback_reason: str,
        step_index: int,
    ) -> dict[str, Any] | None:
        query = _submit_compensation_query(
            last_action,
            observation_state,
            previous_state_id=previous_state_id,
        )
        if not query or not self._registry.has("ai.locate_point"):
            return None
        locate_action = self._registry.resolve("ai.locate_point")
        locate_result = locate_action({"query": query}, context)
        if not locate_result.ok:
            return None
        locate_data = _json_dict(locate_result.data)
        x = locate_data.get("x")
        y = locate_data.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None
        return {
            "ok": True,
            "done": False,
            "action": "ui.click",
            "params": {"x": int(x), "y": int(y)},
            "message": "submit compensation click after enter did not advance the current text-entry stage",
            "planned_at": _timestamp(),
            "fallback_reason": fallback_reason,
            "request_id": "",
            "provider": "",
            "model": "",
            "planner_structured_state": None,
            "compensation": {
                "kind": "submit_fallback_locate_click",
                "query": query,
                "step": step_index,
            },
        }

    def _interruptible_sleep(
        self, seconds: float, should_cancel: Callable[[], bool] | None
    ) -> bool:
        import time

        from engine import agent_executor as agent_executor_module

        if seconds <= 0:
            return False
        deadline = time.monotonic() + seconds
        step = 0.5
        while time.monotonic() < deadline:
            if should_cancel is not None and should_cancel():
                return True
            agent_executor_module.time.sleep(min(step, deadline - time.monotonic()))
        return False

    def _plan_next_step(
        self,
        *,
        llm_client: LLMClientLike,
        config: AgentExecutorConfig,
        step_index: int,
        observation: dict[str, object],
        last_action: dict[str, object] | None,
        fallback_enabled: bool,
        fallback_reason: str,
        fallback_evidence: dict[str, object],
        history_digest: list[dict[str, object]] | None = None,
        reflection: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return planner_module.plan_structured_step(
            runtime=self,
            llm_client=llm_client,
            config=config,
            step_index=step_index,
            observation=observation,
            last_action=last_action,
            fallback_enabled=fallback_enabled,
            fallback_reason=fallback_reason,
            fallback_evidence=fallback_evidence,
            history_digest=history_digest,
            reflection=reflection,
        ).to_legacy_dict()

    def _plan_next_step_vlm(
        self,
        *,
        config: AgentExecutorConfig,
        step_index: int,
        last_action: dict[str, object] | None,
        fallback_reason: str,
        fallback_evidence: dict[str, object],
    ) -> dict[str, object]:
        planned_at = _timestamp()
        image_ref, screen_meta = self._vlm_screen_capture_ref(fallback_evidence)
        if not image_ref:
            return {
                "ok": False,
                "code": "vlm_missing_screenshot",
                "message": "fallback evidence missing screen capture save_path",
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        if not Path(image_ref).exists():
            return {
                "ok": False,
                "code": "vlm_screenshot_missing",
                "message": f"screenshot not found at {image_ref}",
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        prompt = self._vlm_prompt(config=config, step_index=step_index, last_action=last_action)
        request_id = f"vlm-{planned_at}"
        request_trace = {
            "prompt": prompt,
            "system_prompt": "",
            "provider": "vlm",
            "model": "",
            "request_id": request_id,
            "image_ref": image_ref,
            "screen_meta": screen_meta,
            "fallback_reason": fallback_reason,
        }
        try:
            client = self._vlm_client(config)
            request_trace["system_prompt"] = client.system_prompt
            request_trace["model"] = client.model
            _pw = screen_meta.get("physical_width")
            _ph = screen_meta.get("physical_height")
            _sw = screen_meta.get("screen_width")
            _sh = screen_meta.get("screen_height")

            def _to_int_safe(v: Any) -> int | None:
                if isinstance(v, (int, float, str)) and str(v).strip().isdigit():
                    return int(v)
                return None

            screen_width = _to_int_safe(_pw) or _to_int_safe(_sw)
            screen_height = _to_int_safe(_ph) or _to_int_safe(_sh)
            action = client.predict(
                image_ref, prompt, screen_width=screen_width, screen_height=screen_height
            )
            response_trace = {
                "ok": True,
                "output_text": action.raw_text,
                "parsed_action": action.to_dict(),
                "image_ref": image_ref,
            }
        except Exception as exc:
            return {
                "ok": False,
                "code": "vlm_error",
                "message": str(exc),
                "request": request_trace,
                "response": {"ok": False, "error": str(exc), "image_ref": image_ref},
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        raw_action = str(action.raw_action or "").strip().lower()
        normalized_action = str(action.action or "").strip()
        if raw_action in {"finished", "finish", "done"} or normalized_action in {
            "task.finished",
            "task.complete",
        }:
            return {
                "ok": True,
                "done": True,
                "action": "",
                "params": {},
                "message": "vlm indicated task completion",
                "request_id": request_id,
                "provider": str(client.provider_name),
                "model": str(client.model),
                "request": request_trace,
                "response": response_trace,
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        if not normalized_action:
            return {
                "ok": False,
                "code": "vlm_empty_action",
                "message": "vlm returned empty action",
                "request": request_trace,
                "response": response_trace,
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        return {
            "ok": True,
            "done": False,
            "action": normalized_action,
            "params": dict(action.params),
            "message": "vlm predicted next action",
            "request_id": request_id,
            "provider": str(client.provider_name),
            "model": str(client.model),
            "request": request_trace,
            "response": response_trace,
            "planned_at": planned_at,
            "fallback_reason": fallback_reason,
        }

    @staticmethod
    def _wants_vlm(modalities: list[str]) -> bool:
        from core.system_settings_loader import get_vlm_enabled

        if not get_vlm_enabled():
            return False
        normalized = {item.strip().lower() for item in modalities if str(item).strip()}
        return bool(normalized.intersection({"vlm", "vision"}))

    @staticmethod
    def _vlm_screen_capture_ref(
        fallback_evidence: dict[str, object],
    ) -> tuple[str, dict[str, object]]:
        screen_capture = _json_dict(fallback_evidence.get("screen_capture"))
        metadata = _json_dict(screen_capture.get("metadata"))
        save_path = str(metadata.get("save_path") or "").strip()
        return save_path, metadata

    @staticmethod
    def _vlm_prompt(
        *,
        config: AgentExecutorConfig,
        step_index: int,
        last_action: dict[str, object] | None,
    ) -> str:
        lines = [f"Task: {config.goal}", f"Step: {step_index}"]
        if last_action:
            action_name = str(last_action.get("action") or "").strip()
            if action_name:
                lines.append(f"Last action: {action_name}")
        allowed = _vlm_allowed_action_types(config.allowed_actions)
        if allowed:
            lines.append(f"Allowed action types: {', '.join(sorted(allowed))}")
        lines.append("Respond with exactly one action in VLM format.")
        lines.append("If the task is complete, respond with: Action: finished()")
        return "\n".join(lines)

    @staticmethod
    def _vlm_client(config: AgentExecutorConfig) -> VLMClient:
        runtime_config = dict(config.llm_runtime)
        vlm_config = {}
        value = runtime_config.get("vlm")
        if isinstance(value, Mapping):
            vlm_config = _json_dict(value)

        def _read_str(keys: list[str]) -> str:
            for item in keys:
                raw = vlm_config.get(item) if item in vlm_config else runtime_config.get(item)
                if raw is not None:
                    text = str(raw).strip()
                    if text:
                        return text
            return ""

        def _read_float(keys: list[str]) -> float | None:
            for item in keys:
                raw = vlm_config.get(item) if item in vlm_config else runtime_config.get(item)
                if raw is None:
                    continue
                if isinstance(raw, (int, float)):
                    return float(raw)
                if isinstance(raw, str):
                    stripped = raw.strip()
                    if not stripped:
                        continue
                    try:
                        return float(stripped)
                    except ValueError:
                        continue
            return None

        base_url = _read_str(["base_url", "vlm_base_url"])
        model = _read_str(["model", "vlm_model"])
        api_key = _read_str(["api_key", "vlm_api_key"])
        system_prompt = _read_str(["system_prompt", "vlm_system_prompt"])
        timeout = _read_float(["timeout", "timeout_seconds", "vlm_timeout"])
        return VLMClient(
            base_url=base_url or None,
            model=model or None,
            api_key=api_key or None,
            system_prompt=system_prompt or None,
            timeout=timeout or 60.0,
        )
