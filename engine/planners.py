# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportMissingParameterType=false

"""
Planner abstraction layer for AgentExecutorRuntime.

This module decouples the "decision strategy" (which model to call, what prompt
to assemble, how to parse the response) from the "execution loop" (observe →
plan → act → trace).  The executor only sees the ``BasePlanner`` protocol;
concrete strategies can be swapped at runtime without touching the core loop.

Current implementations
-----------------------
* ``StructuredPlanner`` – the production-grade, structured-state-first planner.
  Wraps the existing LLM + optional VLM fallback logic that was previously
  inlined inside ``AgentExecutorRuntime._plan_next_step``.

* ``OmniVisionPlanner`` – experimental planner optimised for next-gen
  multimodal models (GPT-5.4 / Gemini 3.1) that possess native pixel-level
  grounding.  Sends clean screenshots + compressed XML and lets the model
  choose between ``method: "xml"`` and ``method: "vision"`` routing.
  Gated behind ``MYT_EXPERIMENTAL_OMNIVISION=1``.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_services.llm_client import LLMRequest

logger = logging.getLogger(__name__)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _json_dict(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


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
    }


@dataclass(frozen=True, slots=True)
class _StructuredPlannerConfig:
    goal: str
    expected_state_ids: list[str]
    allowed_actions: list[str]
    max_steps: int
    stagnant_limit: int
    system_prompt: str
    llm_runtime: dict[str, object]
    planner_inputs: dict[str, object]
    fallback_modalities: list[str]
    observation_params: dict[str, object]


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannerInput:
    """Immutable snapshot of the current step context handed to a planner."""

    goal: str
    step_index: int
    allowed_actions: list[str]
    observation: dict[str, object]
    last_action: dict[str, object] | None
    fallback_enabled: bool
    fallback_reason: str
    fallback_evidence: dict[str, object]
    fallback_modalities: list[str]
    system_prompt: str
    llm_runtime: dict[str, object]
    planner_inputs: dict[str, object] = field(default_factory=dict)

    # --- Self-reflection fields ---
    history_digest: list[dict[str, object]] = field(default_factory=list)
    reflection: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class PlannerOutput:
    """Unified output contract that every planner must return.

    The executor loop consumes only these fields; planners are free to put
    provider-specific diagnostics into ``diagnostics``.
    """

    ok: bool
    done: bool = False
    action: str = ""
    params: dict[str, object] = field(default_factory=dict)
    message: str = ""
    extracted_data: dict[str, object] | None = None

    # --- metadata for tracing ---
    code: str = ""
    retryable: bool = False
    fallback_reason: str = ""
    planned_at: str = ""
    request_id: str = ""
    provider: str = ""
    model: str = ""
    planner_structured_state: object = None

    # Free-form bucket for request/response traces, vlm attempt logs, etc.
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_legacy_dict(self) -> dict[str, object]:
        """Convert back to the dict shape that the existing executor/trace
        code expects.  This keeps the migration non-breaking."""
        d: dict[str, object] = {
            "ok": self.ok,
            "done": self.done,
            "action": self.action,
            "params": dict(self.params),
            "message": self.message,
            "code": self.code,
            "retryable": self.retryable,
            "fallback_reason": self.fallback_reason,
            "planned_at": self.planned_at,
            "request_id": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "planner_structured_state": self.planner_structured_state,
        }
        if self.extracted_data is not None:
            d["extracted_data"] = self.extracted_data
        # Merge diagnostics (request / response traces) at top level for
        # backward compat with existing trace recording.
        d.update(self.diagnostics)
        return d


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class BasePlanner(Protocol):
    """Minimal contract that every planner must satisfy."""

    def plan(self, inp: PlannerInput) -> PlannerOutput:
        """Given the current step context, return the next action decision."""
        ...


# ---------------------------------------------------------------------------
# StructuredPlanner – production baseline
# ---------------------------------------------------------------------------


class StructuredPlanner:
    """Structured-state-first planner.

    This is a thin wrapper that delegates to the *existing* planning helpers on
    ``AgentExecutorRuntime``.  By keeping the actual implementation on the
    runtime class (for now), we avoid a massive code move in a single commit
    while still providing the protocol-level decoupling that enables
    alternative planners.

    In future commits, the planning logic can migrate fully into this class.
    """

    def __init__(self, runtime: Any) -> None:
        # ``runtime`` is a AgentExecutorRuntime instance.  We accept Any to
        # avoid a circular import.
        self._runtime = runtime

    def plan(self, inp: PlannerInput) -> PlannerOutput:
        # Reconstruct config that the existing helpers expect.
        config = _StructuredPlannerConfig(
            goal=inp.goal,
            expected_state_ids=[],  # not used inside _plan_next_step
            allowed_actions=inp.allowed_actions,
            max_steps=0,  # not used inside _plan_next_step
            stagnant_limit=0,  # not used inside _plan_next_step
            system_prompt=inp.system_prompt,
            llm_runtime=inp.llm_runtime,
            planner_inputs=inp.planner_inputs,
            fallback_modalities=inp.fallback_modalities,
            observation_params={},
        )

        llm_client = self._runtime._llm_client_factory()
        raw = self._runtime._plan_next_step(
            llm_client=llm_client,
            config=config,
            step_index=inp.step_index,
            observation=inp.observation,
            last_action=inp.last_action,
            fallback_enabled=inp.fallback_enabled,
            fallback_reason=inp.fallback_reason,
            fallback_evidence=inp.fallback_evidence,
            history_digest=inp.history_digest or None,
            reflection=inp.reflection or None,
        )

        return _legacy_dict_to_output(raw)


# ---------------------------------------------------------------------------
# OmniVisionPlanner – experimental, GPT-5.4 / Gemini 3.1 native grounding
# ---------------------------------------------------------------------------

_OMNIVISION_SYSTEM_PROMPT = """\
You are an expert mobile automation agent operating on an Android device.
You receive TWO sources of information for the current screen:
1. A **high-resolution screenshot** (attached as an image).
2. A **compressed XML node tree** describing the UI hierarchy.

Your task: decide the SINGLE next action to accomplish the goal.

## Routing Rules
- **Prefer XML selectors** whenever a target element has a stable `resource-id`
  or unique `text` attribute.  Output `"method": "xml"`.
- **Fallback to vision coordinates** ONLY when the target element is NOT
  present in the XML (e.g. canvas-rendered games, WebView, image-only UI).
  Output `"method": "vision"`.

## Output Contract (strict JSON)
Return EXACTLY ONE JSON object:
```json
{
  "done": false,
  "method": "xml",            // or "vision"
  "action": "ui.click",       // from allowed_actions
  "params": { ... },          // action parameters
  "message": "clicking login button via resource-id",
  "expected_next_state": "description of what the screen should look like after this action"
}
```
When the goal is achieved, return:
```json
{
  "done": true,
  "message": "goal achieved",
  "extracted_data": { ... }
}
```
"""


def _omnivision_enabled() -> bool:
    raw = os.getenv("MYT_EXPERIMENTAL_OMNIVISION", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class OmniVisionPlanner:
    """Experimental planner for next-gen multimodal models.

    Sends a clean screenshot alongside the XML tree and lets the model
    self-route between structured selectors and raw vision coordinates.

    **Gated** behind ``MYT_EXPERIMENTAL_OMNIVISION=1``.  When the env var
    is unset, the ``resolve_planner`` factory will never instantiate this.
    """

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def plan(self, inp: PlannerInput) -> PlannerOutput:
        planned_at = _timestamp()
        llm_client = self._runtime._llm_client_factory()

        # --- Build multimodal prompt payload ---
        prompt_payload: dict[str, object] = {
            "goal": inp.goal,
            "step_index": inp.step_index,
            "allowed_actions": inp.allowed_actions,
            "observation": inp.observation,
            "xml_evidence": inp.fallback_evidence.get("ui_xml", {}),
            "last_action": inp.last_action,
            "response_contract": {
                "done": "boolean",
                "method": "string (xml | vision)",
                "action": "string",
                "params": "object",
                "message": "string",
                "expected_next_state": "string",
                "extracted_data": "object (optional, populate when done=true)",
            },
        }
        if inp.history_digest:
            prompt_payload["history_digest"] = inp.history_digest
        if inp.reflection:
            prompt_payload["reflection"] = inp.reflection

        # --- Attach screenshot if available ---
        attachments: list[dict[str, object]] = []
        screen_capture = _json_dict(inp.fallback_evidence.get("screen_capture"))
        metadata = _json_dict(screen_capture.get("metadata"))
        save_path = str(metadata.get("save_path") or "").strip()
        if save_path:
            import base64
            from pathlib import Path

            img_path = Path(save_path)
            if img_path.exists():
                try:
                    img_bytes = img_path.read_bytes()
                    b64 = base64.b64encode(img_bytes).decode("ascii")
                    attachments.append({"image_url": f"data:image/png;base64,{b64}"})
                except Exception as exc:
                    logger.warning(
                        "OmniVisionPlanner: failed to read screenshot %s: %s", save_path, exc
                    )

        request = LLMRequest(
            prompt=json.dumps(prompt_payload, ensure_ascii=False),
            system_prompt=inp.system_prompt or _OMNIVISION_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
            planning={"mode": "omnivision"},
            fallback_modalities=inp.fallback_modalities,
            attachments=attachments,
        )
        response = llm_client.evaluate(request, runtime_config=inp.llm_runtime)

        request_trace = {
            "prompt": request.prompt,
            "system_prompt": request.system_prompt,
            "has_image_attachment": bool(attachments),
        }
        response_trace = _llm_response_trace(response)

        if not bool(response.ok):
            error = getattr(response, "error", None)
            code = str(getattr(error, "code", "llm_error") or "llm_error")
            message = str(getattr(error, "message", "llm planning failed") or "llm planning failed")
            retryable = bool(getattr(error, "retryable", False))
            return PlannerOutput(
                ok=False,
                code=code,
                message=message,
                retryable=retryable,
                planned_at=planned_at,
                fallback_reason="omnivision_llm_error",
                diagnostics={"request": request_trace, "response": response_trace},
            )

        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            return PlannerOutput(
                ok=False,
                code="invalid_planner_response",
                message="planner returned empty output",
                planned_at=planned_at,
                diagnostics={"request": request_trace, "response": response_trace},
            )

        try:
            plan = json.loads(output_text)
        except json.JSONDecodeError as exc:
            return PlannerOutput(
                ok=False,
                code="invalid_planner_response",
                message=f"planner returned invalid JSON: {exc.msg}",
                planned_at=planned_at,
                diagnostics={"request": request_trace, "response": response_trace},
            )

        if not isinstance(plan, dict):
            return PlannerOutput(
                ok=False,
                code="invalid_planner_response",
                message="planner must return a JSON object",
                planned_at=planned_at,
                diagnostics={"request": request_trace, "response": response_trace},
            )

        return PlannerOutput(
            ok=True,
            done=bool(plan.get("done")),
            action=str(plan.get("action") or "").strip(),
            params=dict(plan["params"]) if isinstance(plan.get("params"), dict) else {},
            message=str(plan.get("message") or ""),
            extracted_data=dict(plan["extracted_data"])
            if isinstance(plan.get("extracted_data"), dict)
            else None,
            planned_at=planned_at,
            request_id=str(getattr(response, "request_id", "") or ""),
            provider=str(getattr(response, "provider", "") or ""),
            model=str(getattr(response, "model", "") or ""),
            planner_structured_state=getattr(response, "structured_state", None),
            fallback_reason="omnivision"
            if not inp.fallback_enabled
            else "omnivision_with_fallback",
            diagnostics={
                "request": request_trace,
                "response": response_trace,
                "omnivision_method": str(plan.get("method") or ""),
                "expected_next_state": str(plan.get("expected_next_state") or ""),
            },
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def resolve_planner(runtime: Any) -> BasePlanner:
    """Select the active planner based on environment configuration.

    Returns ``OmniVisionPlanner`` when ``MYT_EXPERIMENTAL_OMNIVISION=1``,
    otherwise returns the production ``StructuredPlanner``.
    """
    if _omnivision_enabled():
        logger.info("resolve_planner: using OmniVisionPlanner (experimental)")
        return OmniVisionPlanner(runtime)
    return StructuredPlanner(runtime)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _legacy_dict_to_output(raw: dict[str, object]) -> PlannerOutput:
    """Convert the dict returned by the legacy ``_plan_next_step`` into a
    ``PlannerOutput`` dataclass."""
    # Separate known fields from diagnostics.
    known_keys = {
        "ok",
        "done",
        "action",
        "params",
        "message",
        "extracted_data",
        "code",
        "retryable",
        "fallback_reason",
        "planned_at",
        "request_id",
        "provider",
        "model",
        "planner_structured_state",
    }
    diagnostics = {k: v for k, v in raw.items() if k not in known_keys}
    params_raw = raw.get("params")
    extracted_raw = raw.get("extracted_data")

    return PlannerOutput(
        ok=bool(raw.get("ok")),
        done=bool(raw.get("done")),
        action=str(raw.get("action") or "").strip(),
        params=dict(params_raw) if isinstance(params_raw, dict) else {},
        message=str(raw.get("message") or ""),
        extracted_data=dict(extracted_raw) if isinstance(extracted_raw, dict) else None,
        code=str(raw.get("code") or ""),
        retryable=bool(raw.get("retryable")),
        fallback_reason=str(raw.get("fallback_reason") or ""),
        planned_at=str(raw.get("planned_at") or ""),
        request_id=str(raw.get("request_id") or ""),
        provider=str(raw.get("provider") or ""),
        model=str(raw.get("model") or ""),
        planner_structured_state=raw.get("planner_structured_state"),
        diagnostics=diagnostics,
    )
