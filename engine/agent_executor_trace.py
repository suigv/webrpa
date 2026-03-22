from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_services.llm_client import LLMRequest
from core.app_config import AppConfigManager
from core.app_config_writer import AppConfigWriter
from core.model_trace_store import ModelTraceContext
from core.paths import traces_dir
from core.trace_learner import TraceLearner
from engine.action_dispatcher import dispatch_action
from engine.models.runtime import ExecutionContext

from .agent_executor_support import (
    _json_dict,
    _json_safe,
    _observation_confidence,
    _observation_state_id,
    _safe_path_part,
    _timestamp,
)

logger = logging.getLogger(__name__)
_XML_PACKAGE_RE = re.compile(r'package="([^"]+)"')


def _redact_runtime_config(runtime_config: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in runtime_config.items():
        if isinstance(value, dict):
            redacted[key] = _redact_runtime_config(value)
            continue
        key_lower = str(key).lower()
        if (
            "api_key" in key_lower
            or "apikey" in key_lower
            or "authorization" in key_lower
            or "token" in key_lower
        ):
            redacted[key] = "***"
        else:
            redacted[key] = value
    return redacted


class AgentExecutorTraceMixin:
    @staticmethod
    def _normalize_xml_filter(raw: object) -> dict[str, int] | None:
        if not isinstance(raw, Mapping) or not raw:
            return None
        max_text_len = raw.get("max_text_len", 60)
        max_desc_len = raw.get("max_desc_len", 100)
        if not isinstance(max_text_len, (int, float, str)):
            return None
        if not isinstance(max_desc_len, (int, float, str)):
            return None
        try:
            return {
                "max_text_len": int(max_text_len),
                "max_desc_len": int(max_desc_len),
            }
        except Exception:
            return None

    def _binding_xml_filter(self, app_package: str) -> dict[str, int] | None:
        if not app_package:
            return None
        app_name = AppConfigManager.find_app_by_package(app_package)
        if not app_name:
            AppConfigManager.bootstrap_app_config(app_package)
            return None
        data = AppConfigManager.load_app_config(app_name)
        xml_filter = data.get("xml_filter")
        if isinstance(xml_filter, list):
            return self._normalize_xml_filter(xml_filter)
        if isinstance(xml_filter, Mapping):
            normalized: dict[str, int] = {}
            for key, value in xml_filter.items():
                key_str = str(key)
                if key_str not in {"max_text_len", "max_desc_len"}:
                    continue
                if not isinstance(value, (int, float, str)):
                    continue
                normalized[key_str] = int(value)
            return normalized or None
        return None

    @staticmethod
    def _extract_xml_package(xml: str) -> str:
        if not xml:
            return ""
        match = _XML_PACKAGE_RE.search(xml)
        return match.group(1).strip() if match else ""

    def _trace_context(self, runtime: dict[str, Any] | None) -> ModelTraceContext:
        runtime_dict = dict(runtime or {})
        target = runtime_dict.get("target")
        target_dict = target if isinstance(target, Mapping) else {}
        device_id = str(target_dict.get("device_id") or "unknown")
        cloud_id = str(target_dict.get("cloud_id") or "unknown")
        task_id = str(runtime_dict.get("task_id") or self.task_name)
        run_id = str(runtime_dict.get("run_id") or f"{task_id}-run-1")
        attempt_number = int(runtime_dict.get("attempt_number") or 1)
        target_label = str(
            runtime_dict.get("cloud_target") or f"device-{device_id}-cloud-{cloud_id}"
        )
        return ModelTraceContext(
            task_id=task_id,
            run_id=run_id,
            target_label=target_label,
            attempt_number=attempt_number,
        )

    def _append_trace(self, context: ModelTraceContext, record: dict[str, object]) -> None:
        _ = self._trace_store.append_record(context, record)

    @staticmethod
    def _resolve_learning_package(target_package: str, observation: object) -> str:
        if str(target_package or "").strip():
            return str(target_package).strip()
        observation_dict = _json_dict(observation)
        return str(observation_dict.get("package") or "").strip()

    def _trigger_learning_hook(self, trace_context: ModelTraceContext, package_name: str) -> None:
        package = str(package_name or "").strip()
        if not package:
            return
        try:
            app_id = AppConfigManager.find_app_by_package(package)
            if not app_id:
                AppConfigManager.bootstrap_app_config(package)
                app_id = AppConfigManager.find_app_by_package(package)
            if not app_id:
                return
            learned = TraceLearner(trace_store=self._trace_store).learn_from_context(trace_context)
            if not learned:
                return
            AppConfigWriter().merge_stage_resource_ids(app_id, learned)
        except Exception as exc:
            logger.warning("Learning hook failed for %s: %s", package, exc)

    def _flush_pending_trace(
        self, context: ModelTraceContext, record: dict[str, object] | None
    ) -> None:
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
        for key in ("matched_state_ids", "observed_state_ids"):
            raw = observation.get(key)
            if isinstance(raw, list):
                for item in raw:
                    item_str = str(item).strip()
                    if item_str and item_str not in observed:
                        observed.append(item_str)
        return observed

    @staticmethod
    def _fallback_reason(*, observation_ok: bool, observation_payload: object) -> str:
        if not observation_ok:
            return "observation_not_ok"
        state_id = _observation_state_id(observation_payload)
        if state_id == "unknown":
            return "unknown_state"
        confidence = _observation_confidence(observation_payload)
        if confidence is not None and confidence <= 0.0:
            return "low_confidence_observation"
        return ""

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
        native_xml = self._collect_native_xml(
            context, trace_context=trace_context, step_index=step_index
        )
        if native_xml:
            evidence["ui_xml"] = native_xml
        screenshot = self._collect_native_capture(
            context,
            trace_context=trace_context,
            step_index=step_index,
        )
        if screenshot:
            if native_xml:
                metadata = _json_dict(screenshot.get("metadata"))
                sw = native_xml.get("screen_width")
                sh = native_xml.get("screen_height")
                if sw and not metadata.get("screen_width"):
                    metadata["screen_width"] = sw
                if sh and not metadata.get("screen_height"):
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
        preferred = self._call_optional_action(
            "ui.dump_node_xml_ex", {"work_mode": False, "timeout_ms": 1500}, context
        )
        if bool(preferred.get("ok")):
            return self._xml_evidence_from_result(
                "ui.dump_node_xml_ex", preferred, trace_context=trace_context, step_index=step_index
            )
        fallback = self._call_optional_action("ui.dump_node_xml", {"dump_all": False}, context)
        if bool(fallback.get("ok")):
            return self._xml_evidence_from_result(
                "ui.dump_node_xml", fallback, trace_context=trace_context, step_index=step_index
            )
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
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            screens_dir = traces_dir() / task_part / run_part / "screens" / target_part
            screens_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(screens_dir / f"{step_part}-{timestamp}.png")
        preferred_params: dict[str, object] = {}
        if save_path:
            preferred_params["save_path"] = save_path
        preferred = self._call_optional_action(
            "device.capture_compressed", preferred_params, context
        )
        if bool(preferred.get("ok")):
            data = _json_dict(_json_safe(preferred.get("data")))
            if save_path:
                data["save_path"] = save_path
            return {"source": "device.capture_compressed", "metadata": data}
        fallback_params: dict[str, object] = {}
        if save_path:
            fallback_params["save_path"] = save_path
        fallback = self._call_optional_action("device.screenshot", fallback_params, context)
        if bool(fallback.get("ok")):
            data = _json_dict(_json_safe(fallback.get("data")))
            if save_path:
                data["save_path"] = save_path
            return {"source": "device.screenshot", "metadata": data}
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
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            xml_dir = traces_dir() / task_part / run_part / "xml" / target_part
            xml_dir.mkdir(parents=True, exist_ok=True)
            save_path = str(xml_dir / f"{step_part}-{timestamp}.xml")
            try:
                Path(save_path).write_text(xml, encoding="utf-8")
            except Exception:
                save_path = ""
        screen_width: int | None = None
        screen_height: int | None = None
        if xml:
            try:
                match = re.search(r'bounds="\[0,0\]\[(\d+),(\d+)\]"', xml)
                if match:
                    screen_width = int(match.group(1))
                    screen_height = int(match.group(2))
            except Exception:
                pass
        evidence: dict[str, object] = {"source": action_name, "xml_length": len(xml)}
        if screen_width and screen_height:
            evidence["screen_width"] = screen_width
            evidence["screen_height"] = screen_height
        if save_path:
            evidence["save_path"] = save_path
        else:
            from engine.actions._state_detection_support import preprocess_xml

            app_package = self._extract_xml_package(xml)
            xml_filter = self._binding_xml_filter(app_package) or {}
            evidence["content"] = preprocess_xml(xml, **xml_filter)
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
            result = dispatch_action(action_name, params, context, registry=self._registry)
        except Exception as exc:
            return {
                "action": action_name,
                "ok": False,
                "code": "fallback_capture_failed",
                "message": str(exc),
            }
        payload = result.model_dump(mode="python")
        return {"action": action_name, **_json_dict(_json_safe(payload))}

    def _trace_planner(self, plan: Mapping[str, object]) -> dict[str, object]:
        return {
            "done": bool(plan.get("done")),
            "message": str(plan.get("message") or ""),
            "request": _json_dict(plan.get("request")),
            "response": _json_dict(plan.get("response")),
            "planner_artifact": _json_dict(plan.get("planner_artifact")),
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
    def _llm_request_trace(
        request: LLMRequest, *, runtime_config: dict[str, object]
    ) -> dict[str, object]:
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
            "runtime_config": _redact_runtime_config(runtime_config),
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
