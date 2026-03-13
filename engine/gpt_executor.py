# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingParameterType=false, reportDeprecated=false

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)

from ai_services.llm_client import LLMClient, LLMRequest
from ai_services.vlm_client import VLMClient
from core.model_trace_store import ModelTraceContext, ModelTraceStore
from core.paths import traces_dir
from engine.action_registry import ActionRegistry, get_registry
from engine.models.runtime import ExecutionContext


class LLMClientLike(Protocol):
    def evaluate(self, request: LLMRequest, *, runtime_config: dict[str, object] | None = None) -> Any: ...


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dict(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _json_safe(value: object, *, string_limit: int = 4000) -> object:
    if isinstance(value, (bytes, bytearray)):
        return {"byte_length": len(value)}
    if isinstance(value, str):
        return value if len(value) <= string_limit else f"{value[:string_limit]}…"
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, string_limit=string_limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item, string_limit=string_limit) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item, string_limit=string_limit) for item in value]
    return value


_SAFE_PART_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_XML_PACKAGE_RE = re.compile(r'package="([^"]+)"')

_KNOWN_APP_SCHEMES: dict[str, dict[str, str]] = {
    "com.twitter.android": {
        "user_profile": "twitter://user?screen_name={username}",
        "search": "twitter://search?query={query}",
        "home": "twitter://timeline",
        "notifications": "twitter://notifications",
        "messages": "twitter://messages",
    },
    "com.instagram.android": {
        "user_profile": "instagram://user?username={username}",
        "home": "instagram://feed",
    },
    "com.facebook.katana": {
        "home": "fb://feed",
        "user_profile": "fb://profile/{user_id}",
    },
    "com.tiktok.android": {
        "user_profile": "snssdk1128://user/profile/{user_id}",
        "home": "snssdk1128://feed",
    },
}


def _safe_path_part(value: object, *, default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    sanitized = _SAFE_PART_RE.sub("-", raw).strip("-._")
    return sanitized or default


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            item_str = str(item).strip()
            if item_str:
                result.append(item_str)
        return result
    return []


def _env_enabled(name: str) -> bool:
    raw = os.getenv(name, "")
    if not raw:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_in_range(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        raise ValueError("must be an integer")
    parsed = int(str(value))
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"must be between {minimum} and {maximum}")
    return parsed


def _stable_fingerprint(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _vlm_allowed_action_types(allowed_actions: list[str]) -> set[str]:
    mapping = {
        "ui.click": "click",
        "ui.input_text": "type",
        "ui.swipe": "scroll",
        "ui.long_click": "long_press",
        "ui.key_press": "key",
    }
    allowed: set[str] = set()
    for action in allowed_actions:
        mapped = mapping.get(action)
        if mapped:
            allowed.add(mapped)
    allowed.add("finished")
    return allowed


@dataclass(frozen=True)
class GptExecutorConfig:
    goal: str
    expected_state_ids: list[str]
    allowed_actions: list[str]
    max_steps: int
    stagnant_limit: int
    system_prompt: str
    llm_runtime: dict[str, object]
    fallback_modalities: list[str]
    observation_params: dict[str, object]


class GptExecutorRuntime:
    task_name: str = "gpt_executor"

    def __init__(
        self,
        *,
        registry: ActionRegistry | None = None,
        llm_client_factory: Callable[[], LLMClientLike] | None = None,
        trace_store: ModelTraceStore | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._llm_client_factory = llm_client_factory or LLMClient
        self._trace_store = trace_store or ModelTraceStore()
        self._binding_cache: dict[str, dict[str, object]] = self._load_binding_cache()

    def run(
        self,
        payload: dict[str, Any],
        *,
        should_cancel: Callable[[], bool] | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config_error = self.validate_payload(payload)
        if config_error is not None:
            return self._result(ok=False, status="failed_config_error", checkpoint="dispatch", **config_error)

        config = self._parse_config(payload, runtime=runtime)
        context = ExecutionContext(payload=dict(payload), runtime=dict(runtime or {}))
        context.should_cancel = should_cancel
        context.emit_event = (runtime or {}).get("emit_event")
        llm_client = self._llm_client_factory()
        ui_match_state = self._registry.resolve("ui.match_state")

        stagnant_observation_count = 0
        previous_observation_fingerprint = ""
        last_action: dict[str, object] | None = None
        history: list[dict[str, object]] = []
        trace_context = self._trace_context(runtime)
        pending_trace_record: dict[str, object] | None = None
        last_observation: dict[str, object] = {
            "data": {},
            "ok": False,
            "modality": "structured_state",
            "observed_state_ids": [],
            "fallback_evidence": {},
            "observed_at": "",
            "step_index": 0,
        }

        for step_index in range(1, config.max_steps + 1):
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
                        observation_modality=str(last_observation.get("modality") or "structured_state"),
                        observed_state_ids=_string_list(last_observation.get("observed_state_ids")),
                        fallback_reason=str(self._fallback_reason(observation_ok=bool(last_observation.get("ok")))),
                        fallback_evidence=_json_dict(last_observation.get("fallback_evidence")),
                        code="task_cancelled",
                        message="task cancelled by user",
                        observed_at=str(last_observation.get("observed_at") or ""),
                    ),
                )
                return self._cancelled(step_index=step_index - 1, history=history)

            observation = ui_match_state(
                {**config.observation_params, "expected_state_ids": list(config.expected_state_ids)},
                context,
            )
            observed_at = _timestamp()
            observation_payload = observation.model_dump(mode="python")
            observation_state = observation_payload.get("data", {})
            observation_modality = self._observation_modality(observation_state)
            observed_state_ids = self._observed_state_ids(observation_state)
            fallback_evidence = self._collect_fallback_evidence(
                context,
                observation_state,
                trace_context=trace_context,
                step_index=step_index,
            )
            if observation.ok:
                observation_fingerprint = _stable_fingerprint(observation_state)
            else:
                xml_content = _json_dict(fallback_evidence.get("ui_xml")).get("content", "")
                observation_fingerprint = _stable_fingerprint(xml_content)
            if context.emit_event:
                context.emit_event("task.observation", {
                    "step": step_index,
                    "modality": observation_modality,
                    "observed_state_ids": observed_state_ids,
                    "ok": bool(observation.ok),
                })
            last_observation = {
                "data": observation_state if isinstance(observation_state, dict) else {},
                "ok": bool(observation.ok),
                "modality": observation_modality,
                "observed_state_ids": observed_state_ids,
                "fallback_evidence": fallback_evidence,
                "observed_at": observed_at,
                "step_index": step_index,
            }

            if pending_trace_record is not None:
                pending_trace_record["post_action_transition"] = {
                    "transition_status": "observed",
                    "next_observation_modality": observation_modality,
                    "next_observed_state_ids": observed_state_ids,
                    "next_observation_ok": bool(observation.ok),
                    "next_observation": observation_state,
                    "observed_at": observed_at,
                }
                self._append_trace(trace_context, pending_trace_record)
                pending_trace_record = None

            if step_index > 1 and observation_fingerprint == previous_observation_fingerprint:
                stagnant_observation_count += 1
            else:
                stagnant_observation_count = 0
            previous_observation_fingerprint = observation_fingerprint

            if stagnant_observation_count >= config.stagnant_limit:
                self._append_trace(
                    trace_context,
                    self._terminal_trace_record(
                        status="failed_circuit_breaker",
                        sequence=step_index,
                        step_index=step_index,
                        observation=observation_state if isinstance(observation_state, dict) else {},
                        observation_ok=bool(observation.ok),
                        observation_modality=observation_modality,
                        observed_state_ids=observed_state_ids,
                        fallback_reason=self._fallback_reason(observation_ok=bool(observation.ok)),
                        fallback_evidence=fallback_evidence,
                        code="stagnant_structured_state",
                        message="structured state observation did not change across repeated actions",
                        observed_at=observed_at,
                    ),
                )
                return self._result(
                    ok=False,
                    status="failed_circuit_breaker",
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
                )

            plan: dict[str, Any] = {"ok": False, "message": "uninitialized"}
            max_planner_retries = 3
            for attempt in range(max_planner_retries):
                plan = self._plan_next_step(
                    llm_client=llm_client,
                    config=config,
                    step_index=step_index,
                    observation=observation_state if isinstance(observation_state, dict) else {},
                    last_action=last_action,
                    fallback_enabled=not observation.ok,
                    fallback_evidence=fallback_evidence,
                )
                if plan.get("ok") is not False:
                    break
                
                # 指数退避重试
                if plan.get("retryable") and attempt < max_planner_retries - 1:
                    backoff = 2 ** (attempt + 1)
                    logger.warning(f"Planner failed (retryable), backing off {backoff}s: {plan.get('message')}")
                    time.sleep(backoff)
                    continue
                break

            if plan["ok"] is False:
                self._append_trace(
                    trace_context,
                    self._terminal_trace_record(
                        status="failed_runtime_error",
                        sequence=step_index,
                        step_index=step_index,
                        observation=observation_state if isinstance(observation_state, dict) else {},
                        observation_ok=bool(last_observation.get("ok")),
                        observation_modality=observation_modality,
                        observed_state_ids=observed_state_ids,
                        fallback_reason=str(plan.get("fallback_reason") or ""),
                        fallback_evidence=fallback_evidence,
                        code=str(plan.get("code") or "planner_error"),
                        message=str(plan.get("message") or "planner failed"),
                        observed_at=observed_at,
                        planner=plan,
                    ),
                )
                return self._result(
                    ok=False,
                    status="failed_runtime_error",
                    checkpoint="planning",
                    code=str(plan.get("code") or "planner_error"),
                    message=str(plan.get("message") or "planner failed"),
                    step_count=step_index - 1,
                    history=history,
                    planner=plan,
                )

            if bool(plan.get("done")):
                self._append_trace(
                    trace_context,
                    self._terminal_trace_record(
                        status="completed",
                        sequence=step_index,
                        step_index=step_index,
                        observation=observation_state if isinstance(observation_state, dict) else {},
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
                return self._result(
                    ok=True,
                    status="completed",
                    checkpoint="complete",
                    message=str(plan.get("message") or "gpt executor completed"),
                    step_count=step_index - 1,
                    history=history,
                    final_observation=observation_state,
                    planner=plan,
                )

            action_name = str(plan.get("action") or "").strip()
            action_params = _json_dict(plan.get("params"))

            if action_name not in config.allowed_actions:
                self._append_trace(
                    trace_context,
                    self._terminal_trace_record(
                        status="failed_runtime_error",
                        sequence=step_index,
                        step_index=step_index,
                        observation=observation_state if isinstance(observation_state, dict) else {},
                        observation_ok=bool(last_observation.get("ok")),
                        observation_modality=observation_modality,
                        observed_state_ids=observed_state_ids,
                        fallback_reason=str(plan.get("fallback_reason") or ""),
                        fallback_evidence=fallback_evidence,
                        code="invalid_action_selection",
                        message=f"planner selected action outside allowed set: {action_name or '<empty>'}",
                        observed_at=observed_at,
                        planner=plan,
                    ),
                )
                return self._result(
                    ok=False,
                    status="failed_runtime_error",
                    checkpoint="planning",
                    code="invalid_action_selection",
                    message=f"planner selected action outside allowed set: {action_name or '<empty>'}",
                    step_count=step_index - 1,
                    history=history,
                    planner=plan,
                )

            if context.emit_event:
                context.emit_event("task.planning", {
                    "step": step_index,
                    "action": action_name,
                    "params": action_params,
                    "message": str(plan.get("message") or ""),
                })
            action_result = self._registry.resolve(action_name)(action_params, context)
            action_result_payload = action_result.model_dump(mode="python")
            if context.emit_event:
                context.emit_event("task.action_result", {
                    "step": step_index,
                    "label": action_name,
                    "ok": action_result.ok,
                    "message": action_result.message or "",
                })
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
                    "ok": bool(observation.ok),
                    "modality": observation_modality,
                    "observed_state_ids": observed_state_ids,
                    "expected_state_ids": list(config.expected_state_ids),
                    "data": observation_state,
                },
                "fallback_reason": str(plan.get("fallback_reason") or self._fallback_reason(observation_ok=bool(observation.ok))),
                "fallback_evidence": fallback_evidence,
                "planner": self._trace_planner(plan),
                "chosen_action": action_name,
                "action_params": action_params,
                "action_result": action_result_payload,
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
                        observation=observation_state if isinstance(observation_state, dict) else {},
                        observation_ok=bool(observation.ok),
                        observation_modality=observation_modality,
                        observed_state_ids=observed_state_ids,
                        fallback_reason=str(plan.get("fallback_reason") or self._fallback_reason(observation_ok=bool(observation.ok))),
                        fallback_evidence=fallback_evidence,
                        code="task_cancelled",
                        message="task cancelled by user",
                        observed_at=observed_at,
                        planner=plan,
                    ),
                )
                return self._cancelled(step_index=step_index, history=history)

        terminal_sequence = config.max_steps + (1 if pending_trace_record is not None else 0)
        self._flush_pending_trace(trace_context, pending_trace_record)
        self._append_trace(
            trace_context,
            self._terminal_trace_record(
                status="failed_circuit_breaker",
                sequence=terminal_sequence,
                step_index=config.max_steps,
                observation=_json_dict(last_observation.get("data")),
                observation_ok=bool(last_observation.get("ok")),
                observation_modality=str(last_observation.get("modality") or "structured_state"),
                observed_state_ids=_string_list(last_observation.get("observed_state_ids")),
                fallback_reason=str(self._fallback_reason(observation_ok=bool(last_observation.get("ok")))),
                fallback_evidence=_json_dict(last_observation.get("fallback_evidence")),
                code="step_budget_exhausted",
                message="gpt executor exhausted configured step budget",
                observed_at=str(last_observation.get("observed_at") or ""),
            ),
        )
        return self._result(
            ok=False,
            status="failed_circuit_breaker",
            checkpoint="loop",
            code="step_budget_exhausted",
            message="gpt executor exhausted configured step budget",
            step_count=config.max_steps,
            history=history,
            circuit_breaker={
                "code": "step_budget_exhausted",
                "max_steps": config.max_steps,
            },
        )

    @staticmethod
    def _normalize_xml_filter(raw: object) -> dict[str, int] | None:
        if not isinstance(raw, Mapping) or not raw:
            return None
        try:
            return {
                "max_text_len": int(raw.get("max_text_len", 60)),
                "max_desc_len": int(raw.get("max_desc_len", 100)),
            }
        except Exception:
            return None

    def _load_binding_cache(self) -> dict[str, dict[str, object]]:
        try:
            from core.paths import config_dir
            apps_dir = config_dir() / "apps"
            if not apps_dir.exists():
                return {}
            cache: dict[str, dict[str, object]] = {}
            for app_path in sorted(apps_dir.glob("*.yaml")):
                try:
                    import yaml as _yaml
                    data = _yaml.safe_load(app_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.warning("Failed to read app config file %s: %s", app_path, exc)
                    continue
                if not isinstance(data, dict):
                    continue
                app_package = str(data.get("package_name") or "").strip()
                if not app_package:
                    continue
                entry = {
                    "xml_filter": self._normalize_xml_filter(data.get("xml_filter")),
                    "states": data.get("states") if isinstance(data.get("states"), list) else [],
                }
                if app_package in cache:
                    logger.warning("Duplicate package_name in app configs: %s", app_package)
                cache[app_package] = entry
            return cache
        except Exception as exc:
            logger.warning("Failed to build binding cache: %s", exc)
            return {}

    def _binding_xml_filter(self, app_package: str) -> dict[str, int] | None:
        if not app_package:
            return None
        entry = self._binding_cache.get(app_package)
        if not entry:
            self._bootstrap_app_config(app_package)
            return None
        xml_filter = entry.get("xml_filter")
        if isinstance(xml_filter, Mapping):
            return {str(k): int(v) for k, v in xml_filter.items() if str(k) in {"max_text_len", "max_desc_len"}}
        return None

    def _bootstrap_app_config(self, app_package: str) -> None:
        """首次遇到未知 package 时，自动创建 config/apps/<app>.yaml 骨架文件。"""
        try:
            from engine.actions.sdk_config_support import app_config_path, app_from_package
            import yaml as _yaml
            app_name = app_from_package(app_package)
            if not app_name:
                return
            path = app_config_path(app_name)
            if path.exists():
                # 已存在但未被 cache 加载（如启动后新建），补充加入 cache
                data = _yaml.safe_load(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._binding_cache[app_package] = {
                        "xml_filter": self._normalize_xml_filter(data.get("xml_filter")),
                        "states": data.get("states") if isinstance(data.get("states"), list) else [],
                    }
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            schemes = _KNOWN_APP_SCHEMES.get(app_package, {})
            skeleton = {"version": "v1", "package_name": app_package, "schemes": schemes, "selectors": {}}
            path.write_text(_yaml.safe_dump(skeleton, sort_keys=False, allow_unicode=True), encoding="utf-8")
            self._binding_cache[app_package] = {"xml_filter": None, "states": []}
            logger.info("bootstrapped app config for package %s at %s", app_package, path)
        except Exception as exc:
            logger.warning("Failed to bootstrap app config for %s: %s", app_package, exc)

    @staticmethod
    def _extract_xml_package(xml: str) -> str:
        if not xml:
            return ""
        match = _XML_PACKAGE_RE.search(xml)
        return match.group(1).strip() if match else ""

    def validate_payload(self, payload: Mapping[str, object]) -> dict[str, str] | None:
        try:
            _ = self._parse_config(payload)
        except ValueError as exc:
            return {"code": "invalid_params", "message": str(exc)}
        return None

    def _parse_config(self, payload: Mapping[str, object], *, runtime: Mapping[str, object] | None = None) -> GptExecutorConfig:
        goal = str(payload.get("goal") or "").strip()
        if not goal:
            raise ValueError("gpt_executor requires non-empty goal")

        expected_state_ids = _string_list(payload.get("expected_state_ids") or payload.get("state_ids"))
        if not expected_state_ids:
            raise ValueError("gpt_executor requires expected_state_ids")

        allowed_actions = _string_list(payload.get("allowed_actions"))
        if not allowed_actions:
            raise ValueError("gpt_executor requires allowed_actions")
        unknown_actions = [action for action in allowed_actions if not self._registry.has(action)]
        if unknown_actions:
            rendered = ", ".join(sorted(unknown_actions))
            raise ValueError(f"gpt_executor allowed_actions must reference registered actions: {rendered}")
        if "ui.match_state" in allowed_actions:
            raise ValueError("gpt_executor allowed_actions must not include ui.match_state")

        observation_params = _json_dict(payload.get("observation"))
        _ = observation_params.pop("expected_state_ids", None)
        _ = observation_params.pop("state_ids", None)

        runtime_llm = _json_dict(runtime.get("llm")) if isinstance(runtime, Mapping) else {}
        payload_llm = _json_dict(payload.get("llm"))
        llm_runtime = {**runtime_llm, **payload_llm} if runtime_llm or payload_llm else {}

        return GptExecutorConfig(
            goal=goal,
            expected_state_ids=expected_state_ids,
            allowed_actions=allowed_actions,
            max_steps=_int_in_range(payload.get("max_steps"), default=8, minimum=1, maximum=100),
            stagnant_limit=_int_in_range(payload.get("stagnant_limit"), default=2, minimum=1, maximum=20),
            system_prompt=str(payload.get("system_prompt") or "").strip(),
            llm_runtime=llm_runtime,
            fallback_modalities=_string_list(payload.get("fallback_modalities")),
            observation_params=observation_params,
        )

    def _plan_next_step(
        self,
        *,
        llm_client: LLMClientLike,
        config: GptExecutorConfig,
        step_index: int,
        observation: dict[str, object],
        last_action: dict[str, object] | None,
        fallback_enabled: bool,
        fallback_evidence: dict[str, object],
    ) -> dict[str, object]:
        fallback_reason = self._fallback_reason(observation_ok=not fallback_enabled)
        vlm_attempt: dict[str, object] | None = None
        if fallback_enabled and self._wants_vlm(config.fallback_modalities):
            vlm_plan = self._plan_next_step_vlm(
                config=config,
                step_index=step_index,
                last_action=last_action,
                fallback_reason=fallback_reason,
                fallback_evidence=fallback_evidence,
            )
            if bool(vlm_plan.get("ok")):
                if bool(vlm_plan.get("done")):
                    return vlm_plan
                action_name = str(vlm_plan.get("action") or "").strip()
                if action_name and action_name in config.allowed_actions:
                    return vlm_plan
                vlm_attempt = {
                    "ok": False,
                    "code": "vlm_action_not_allowed" if action_name else "vlm_action_missing",
                    "message": (
                        "vlm selected action outside allowed set"
                        if action_name
                        else "vlm returned empty action"
                    ),
                    "action": action_name,
                    "request": _json_dict(vlm_plan.get("request")),
                    "response": _json_dict(vlm_plan.get("response")),
                }
            else:
                vlm_attempt = {
                    "ok": False,
                    "code": str(vlm_plan.get("code") or "vlm_error"),
                    "message": str(vlm_plan.get("message") or "vlm planning failed"),
                    "request": _json_dict(vlm_plan.get("request")),
                    "response": _json_dict(vlm_plan.get("response")),
                }

        prompt_payload: dict[str, object] = {
            "goal": config.goal,
            "step_index": step_index,
            "allowed_actions": config.allowed_actions,
            "observation": observation,
            "fallback_evidence": fallback_evidence if fallback_enabled else {},
            "last_action": last_action,
            "response_contract": {
                "done": "boolean",
                "action": "string",
                "params": "object",
                "message": "string",
            },
        }
        if vlm_attempt is not None:
            prompt_payload["vlm_attempt"] = vlm_attempt

        request = LLMRequest(
            prompt=json.dumps(
                prompt_payload,
                ensure_ascii=False,
            ),
            system_prompt=(
                config.system_prompt
                or "Return JSON only. Prefer structured-state-first planning. Mark done=true only when the task goal is complete."
            ),
            response_format={"type": "json_object"},
            planning={"mode": "structured_state_first"},
            fallback_modalities=config.fallback_modalities if fallback_enabled else [],
        )
        planned_at = _timestamp()
        response = llm_client.evaluate(request, runtime_config=config.llm_runtime)
        response_trace = self._llm_response_trace(response)
        if not bool(response.ok):
            error = getattr(response, "error", None)
            code = str(getattr(error, "code", "llm_error") or "llm_error")
            message = str(getattr(error, "message", "llm planning failed") or "llm planning failed")
            retryable = bool(getattr(error, "retryable", False))
            return {
                "ok": False,
                "code": code,
                "message": message,
                "retryable": retryable,
                "request": self._llm_request_trace(request, runtime_config=config.llm_runtime),
                "response": response_trace,
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }

        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            return {
                "ok": False,
                "code": "invalid_planner_response",
                "message": "planner returned empty output",
                "request": self._llm_request_trace(request, runtime_config=config.llm_runtime),
                "response": response_trace,
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        try:
            plan = json.loads(output_text)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "code": "invalid_planner_response",
                "message": f"planner returned invalid JSON: {exc.msg}",
                "request": self._llm_request_trace(request, runtime_config=config.llm_runtime),
                "response": response_trace,
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        if not isinstance(plan, dict):
            return {
                "ok": False,
                "code": "invalid_planner_response",
                "message": "planner must return a JSON object",
                "request": self._llm_request_trace(request, runtime_config=config.llm_runtime),
                "response": response_trace,
                "planned_at": planned_at,
                "fallback_reason": fallback_reason,
            }
        return {str(key): value for key, value in plan.items()} | {
            "ok": True,
            "planner_structured_state": getattr(response, "structured_state", None),
            "request_id": str(getattr(response, "request_id", "") or ""),
            "provider": str(getattr(response, "provider", "") or ""),
            "model": str(getattr(response, "model", "") or ""),
            "request": self._llm_request_trace(request, runtime_config=config.llm_runtime),
            "response": response_trace,
            "planned_at": planned_at,
            "fallback_reason": fallback_reason,
        }

    def _plan_next_step_vlm(
        self,
        *,
        config: GptExecutorConfig,
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
            "provider": "uitars",
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
            _sw = screen_meta.get("screen_width")
            _sh = screen_meta.get("screen_height")
            _screen_w = int(_sw) if isinstance(_sw, (int, float, str)) and str(_sw).strip().isdigit() else None
            _screen_h = int(_sh) if isinstance(_sh, (int, float, str)) and str(_sh).strip().isdigit() else None
            action = client.predict(image_ref, prompt, screen_width=_screen_w, screen_height=_screen_h)
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
        if raw_action in {"finished", "finish", "done"} or normalized_action in {"task.finished", "task.complete"}:
            return {
                "ok": True,
                "done": True,
                "action": "",
                "params": {},
                "message": "vlm indicated task completion",
                "request_id": request_id,
                "provider": "uitars",
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
            "provider": "uitars",
            "model": str(client.model),
            "request": request_trace,
            "response": response_trace,
            "planned_at": planned_at,
            "fallback_reason": fallback_reason,
        }

    @staticmethod
    def _wants_vlm(modalities: list[str]) -> bool:
        if not _env_enabled("MYT_ENABLE_VLM"):
            return False
        normalized = {item.strip().lower() for item in modalities if str(item).strip()}
        return bool(normalized.intersection({"vlm", "vision", "uitars", "ui-tars"}))

    @staticmethod
    def _vlm_screen_capture_ref(fallback_evidence: dict[str, object]) -> tuple[str, dict[str, object]]:
        screen_capture = _json_dict(fallback_evidence.get("screen_capture"))
        metadata = _json_dict(screen_capture.get("metadata"))
        save_path = str(metadata.get("save_path") or "").strip()
        return save_path, metadata

    @staticmethod
    def _vlm_prompt(
        *,
        config: GptExecutorConfig,
        step_index: int,
        last_action: dict[str, object] | None,
    ) -> str:
        lines = [
            f"Task: {config.goal}",
            f"Step: {step_index}",
        ]
        if last_action:
            action_name = str(last_action.get("action") or "").strip()
            if action_name:
                lines.append(f"Last action: {action_name}")
        allowed = _vlm_allowed_action_types(config.allowed_actions)
        if allowed:
            lines.append(f"Allowed action types: {', '.join(sorted(allowed))}")
        lines.append("Respond with exactly one action in UI-TARS format.")
        lines.append("If the task is complete, respond with: Action: finished()")
        return "\n".join(lines)

    @staticmethod
    def _vlm_client(config: GptExecutorConfig) -> VLMClient:
        runtime_config = dict(config.llm_runtime)
        vlm_config = {}
        for key in ("vlm", "uitars"):
            value = runtime_config.get(key)
            if isinstance(value, Mapping):
                vlm_config = _json_dict(value)
                break

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

        base_url = _read_str(["base_url", "vlm_base_url", "uitars_base_url"])
        model = _read_str(["model", "vlm_model", "uitars_model"])
        api_key = _read_str(["api_key", "vlm_api_key", "uitars_api_key"])
        system_prompt = _read_str(["system_prompt", "vlm_system_prompt", "uitars_system_prompt"])
        timeout = _read_float(["timeout", "timeout_seconds", "vlm_timeout"])

        return VLMClient(
            base_url=base_url or None,
            model=model or None,
            api_key=api_key or None,
            system_prompt=system_prompt or None,
            timeout=timeout or 60.0,
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

    def _result(self, *, ok: bool, status: str, checkpoint: str, **extra: object) -> dict[str, Any]:
        return {
            "ok": ok,
            "task": self.task_name,
            "status": status,
            "checkpoint": checkpoint,
            "timestamp": _timestamp(),
            **extra,
        }

    def _trace_context(self, runtime: dict[str, Any] | None) -> ModelTraceContext:
        runtime_dict = dict(runtime or {})
        target = runtime_dict.get("target")
        target_dict = target if isinstance(target, Mapping) else {}
        device_id = str(target_dict.get("device_id") or "unknown")
        cloud_id = str(target_dict.get("cloud_id") or "unknown")
        task_id = str(runtime_dict.get("task_id") or self.task_name)
        run_id = str(runtime_dict.get("run_id") or f"{task_id}-run-1")
        attempt_number = int(runtime_dict.get("attempt_number") or 1)
        target_label = str(runtime_dict.get("cloud_target") or f"device-{device_id}-cloud-{cloud_id}")
        return ModelTraceContext(
            task_id=task_id,
            run_id=run_id,
            target_label=target_label,
            attempt_number=attempt_number,
        )

    def _append_trace(self, context: ModelTraceContext, record: dict[str, object]) -> None:
        _ = self._trace_store.append_record(context, record)

    def _flush_pending_trace(self, context: ModelTraceContext, record: dict[str, object] | None) -> None:
        if record is None:
            return
        if "post_action_transition" not in record:
            record["post_action_transition"] = {
                "transition_status": "no_followup_observation",
                "next_observation_modality": "",
                "next_observed_state_ids": [],
                "next_observation_ok": None,
                "next_observation": {},
                "observed_at": "",
            }
        self._append_trace(context, record)

    @staticmethod
    def _observation_modality(observation_payload: object) -> str:
        observation = _json_dict(observation_payload)
        platform = str(observation.get("platform") or "").strip().lower()
        if platform != "browser":
            return "structured_state"
        raw_details = _json_dict(observation.get("raw_details"))
        observations = raw_details.get("observations")
        browser_kinds: list[str] = []
        if isinstance(observations, list):
            for item in observations:
                item_dict = _json_dict(item)
                kind = str(item_dict.get("kind") or "").strip().lower()
                if kind and kind not in browser_kinds:
                    browser_kinds.append(kind)
        if len(browser_kinds) == 1:
            return f"browser_{browser_kinds[0]}"
        if browser_kinds:
            return "browser_observation"
        return "browser_observation"

    @staticmethod
    def _observed_state_ids(observation: object) -> list[str]:
        if not isinstance(observation, Mapping):
            return []
        observed: list[str] = []
        state = observation.get("state")
        if isinstance(state, Mapping):
            state_id = str(state.get("state_id") or "").strip()
            if state_id:
                observed.append(state_id)
        for key in ("matched_state_ids", "observed_state_ids", "expected_state_ids"):
            raw = observation.get(key)
            if isinstance(raw, list):
                for item in raw:
                    item_str = str(item).strip()
                    if item_str and item_str not in observed:
                        observed.append(item_str)
        return observed

    @staticmethod
    def _fallback_reason(*, observation_ok: bool) -> str:
        return "observation_not_ok" if not observation_ok else ""

    def _collect_fallback_evidence(
        self,
        context: ExecutionContext,
        observation_payload: object,
        *,
        trace_context: ModelTraceContext | None = None,
        step_index: int | None = None,
    ) -> dict[str, object]:
        observation = _json_dict(observation_payload)
        platform = str(observation.get("platform") or "").strip().lower()
        evidence: dict[str, object] = {}
        if platform == "browser":
            browser_html = self._collect_browser_html(context)
            if browser_html:
                evidence["browser_html"] = browser_html
            return evidence

        native_xml = self._collect_native_xml(context, trace_context=trace_context, step_index=step_index)
        if native_xml:
            evidence["ui_xml"] = native_xml
        screenshot = self._collect_native_capture(
            context,
            trace_context=trace_context,
            step_index=step_index,
        )
        if screenshot:
            # 从 XML 证据注入屏幕分辨率到截图 metadata
            if native_xml:
                sw = native_xml.get("screen_width")
                sh = native_xml.get("screen_height")
                if sw and sh:
                    metadata = _json_dict(screenshot.get("metadata"))
                    metadata["screen_width"] = sw
                    metadata["screen_height"] = sh
                    screenshot["metadata"] = metadata
            evidence["screen_capture"] = screenshot
        return evidence

    def _collect_browser_html(self, context: ExecutionContext) -> dict[str, object]:
        browser = getattr(context, "browser", None)
        if browser is None or not hasattr(browser, "html"):
            return {}
        try:
            html = str(browser.html())
            current_url = ""
            if hasattr(browser, "current_url"):
                current_url = str(browser.current_url())
            return {
                "source": "browser.html",
                "current_url": current_url,
                "html_length": len(html),
                "content": _json_safe(html),
                "truncated": len(html) > 4000,
            }
        except Exception as exc:
            return {"source": "browser.html", "ok": False, "message": str(exc)}

    def _collect_native_xml(
        self,
        context: ExecutionContext,
        *,
        trace_context: ModelTraceContext | None = None,
        step_index: int | None = None,
    ) -> dict[str, object]:
        preferred = self._call_optional_action("ui.dump_node_xml_ex", {"work_mode": False, "timeout_ms": 1500}, context)
        if bool(preferred.get("ok")):
            return self._xml_evidence_from_result("ui.dump_node_xml_ex", preferred, trace_context=trace_context, step_index=step_index)

        fallback = self._call_optional_action("ui.dump_node_xml", {"dump_all": False}, context)
        if bool(fallback.get("ok")):
            return self._xml_evidence_from_result("ui.dump_node_xml", fallback, trace_context=trace_context, step_index=step_index)

        failure = _json_dict(preferred or fallback)
        if not failure:
            return {}
        return {
            "source": str(failure.get("action") or "ui.dump_node_xml_ex"),
            "ok": False,
            "code": str(failure.get("code") or "fallback_unavailable"),
            "message": str(failure.get("message") or ""),
        }

    def _collect_native_capture(
        self,
        context: ExecutionContext,
        *,
        trace_context: ModelTraceContext | None = None,
        step_index: int | None = None,
    ) -> dict[str, object]:
        save_path = ""
        if trace_context is not None:
            task_part = _safe_path_part(trace_context.task_id, default="task")
            run_part = _safe_path_part(trace_context.run_id, default="run")
            target_part = _safe_path_part(trace_context.target_label, default="target")
            step_part = f"step-{int(step_index) if step_index is not None else 0}"
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            screens_dir = traces_dir() / task_part / run_part / "screens" / target_part
            screens_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(screens_dir / f"{step_part}-{timestamp}.png")

        preferred_params: dict[str, object] = {}
        if save_path:
            preferred_params["save_path"] = save_path
        preferred = self._call_optional_action("device.capture_compressed", preferred_params, context)
        if bool(preferred.get("ok")):
            data = _json_dict(_json_safe(preferred.get("data")))
            if save_path:
                data["save_path"] = save_path
            return {
                "source": "device.capture_compressed",
                "metadata": data,
            }

        fallback_params: dict[str, object] = {}
        if save_path:
            fallback_params["save_path"] = save_path
        fallback = self._call_optional_action("device.screenshot", fallback_params, context)
        if bool(fallback.get("ok")):
            data = _json_dict(_json_safe(fallback.get("data")))
            if save_path:
                data["save_path"] = save_path
            return {
                "source": "device.screenshot",
                "metadata": data,
            }

        failure = _json_dict(preferred or fallback)
        if not failure:
            return {}
        return {
            "source": str(failure.get("action") or "device.capture_compressed"),
            "ok": False,
            "code": str(failure.get("code") or "fallback_unavailable"),
            "message": str(failure.get("message") or ""),
        }

    def _xml_evidence_from_result(
        self,
        action_name: str,
        result: Mapping[str, object],
        *,
        trace_context: ModelTraceContext | None = None,
        step_index: int | None = None,
    ) -> dict[str, object]:
        payload = _json_dict(result.get("data"))
        xml = str(payload.get("xml") or "")
        save_path = ""
        if xml and trace_context is not None:
            task_part = _safe_path_part(trace_context.task_id, default="task")
            run_part = _safe_path_part(trace_context.run_id, default="run")
            target_part = _safe_path_part(trace_context.target_label, default="target")
            step_part = f"step-{int(step_index) if step_index is not None else 0}"
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            xml_dir = traces_dir() / task_part / run_part / "xml" / target_part
            xml_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(xml_dir / f"{step_part}-{timestamp}.xml")
            try:
                Path(save_path).write_text(xml, encoding="utf-8")
            except Exception:
                save_path = ""
        # 从 XML 根节点 bounds 解析屏幕分辨率
        screen_width: int | None = None
        screen_height: int | None = None
        if xml:
            try:
                import re as _re
                m = _re.search(r'bounds="\[0,0\]\[(\d+),(\d+)\]"', xml)
                if m:
                    screen_width = int(m.group(1))
                    screen_height = int(m.group(2))
            except Exception:
                pass
        evidence: dict[str, object] = {
            "source": action_name,
            "xml_length": len(xml),
        }
        if screen_width and screen_height:
            evidence["screen_width"] = screen_width
            evidence["screen_height"] = screen_height
        if save_path:
            evidence["save_path"] = save_path
        else:
            # fallback: 预处理后存入 JSONL
            from engine.actions._state_detection_support import preprocess_xml as _preprocess_xml
            app_package = self._extract_xml_package(xml)
            flt = self._binding_xml_filter(app_package) or {}
            processed = _preprocess_xml(xml, **flt)
            evidence["content"] = processed
            evidence["truncated"] = False
        return evidence

    def _call_optional_action(
        self,
        action_name: str,
        params: dict[str, object],
        context: ExecutionContext,
    ) -> dict[str, object]:
        if not self._registry.has(action_name):
            return {}
        try:
            result = self._registry.resolve(action_name)(params, context)
        except Exception as exc:
            return {"action": action_name, "ok": False, "code": "fallback_capture_failed", "message": str(exc)}
        payload = result.model_dump(mode="python")
        return {"action": action_name, **_json_dict(_json_safe(payload))}

    def _trace_planner(self, plan: Mapping[str, object]) -> dict[str, object]:
        return {
            "done": bool(plan.get("done")),
            "message": str(plan.get("message") or ""),
            "request": _json_dict(plan.get("request")),
            "response": _json_dict(plan.get("response")),
            "model_metadata": {
                "request_id": str(plan.get("request_id") or ""),
                "provider": str(plan.get("provider") or ""),
                "model": str(plan.get("model") or ""),
                "planner_structured_state": plan.get("planner_structured_state"),
            },
        }

    def _terminal_trace_record(
        self,
        *,
        status: str,
        sequence: int,
        step_index: int,
        observation: dict[str, object],
        observation_ok: bool,
        observation_modality: str,
        observed_state_ids: list[str],
        fallback_reason: str,
        fallback_evidence: dict[str, object],
        code: str,
        message: str,
        observed_at: str,
        planner: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        record: dict[str, object] = {
            "trace_version": 1,
            "sequence": sequence,
            "step_index": step_index,
            "record_type": "terminal",
            "task": self.task_name,
            "status": status,
            "code": code,
            "message": message,
            "observation": {
                "ok": observation_ok,
                "modality": observation_modality,
                "observed_state_ids": observed_state_ids,
                "data": observation,
            },
            "fallback_reason": fallback_reason,
            "fallback_evidence": fallback_evidence,
            "timestamps": {"observed_at": observed_at, "recorded_at": _timestamp()},
        }
        if planner is not None:
            record["planner"] = self._trace_planner(planner)
        return record

    @staticmethod
    def _llm_request_trace(request: LLMRequest, *, runtime_config: dict[str, object]) -> dict[str, object]:
        sanitized_runtime = _redact_runtime_config(runtime_config)
        return {
            "prompt": request.prompt,
            "system_prompt": request.system_prompt,
            "provider": request.provider,
            "model": request.model,
            "request_id": request.request_id,
            "metadata": dict(request.metadata),
            "options": dict(request.options),
            "response_format": dict(request.response_format),
            "planning": dict(request.planning),
            "modality": request.modality,
            "fallback_modalities": list(request.fallback_modalities),
            "runtime_config": sanitized_runtime,
        }

    @staticmethod
    def _llm_response_trace(response: object) -> dict[str, object]:
        return {
            "ok": bool(getattr(response, "ok", False)),
            "request_id": str(getattr(response, "request_id", "") or ""),
            "provider": str(getattr(response, "provider", "") or ""),
            "model": str(getattr(response, "model", "") or ""),
            "latency_ms": getattr(response, "latency_ms", None),
            "output_text": str(getattr(response, "output_text", "") or ""),
            "structured_state": getattr(response, "structured_state", None),
            "modality": str(getattr(response, "modality", "") or ""),
            "fallback_modalities": list(getattr(response, "fallback_modalities", []) or []),
            "usage": dict(getattr(response, "usage", {}) or {}),
            "finish_reason": str(getattr(response, "finish_reason", "") or ""),
            "model_metadata": dict(getattr(response, "model_metadata", {}) or {}),
            "error": getattr(getattr(response, "error", None), "to_dict", lambda: None)(),
            "raw": dict(getattr(response, "raw", {}) or {}),
        }


def _redact_runtime_config(runtime_config: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in runtime_config.items():
        if isinstance(value, dict):
            redacted[key] = _redact_runtime_config(value)
            continue
        key_lower = str(key).lower()
        if "api_key" in key_lower or "apikey" in key_lower or "authorization" in key_lower or "token" in key_lower:
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted
