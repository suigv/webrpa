from __future__ import annotations

# pyright: reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedCallResult=false, reportUnannotatedClassAttribute=false, reportExplicitAny=false

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.model_trace_store import ModelTraceContext, ModelTraceStore
from engine.actions.sdk_config_support import app_config_path, app_from_package, load_app_config_document
from engine.models.manifest import InputType, PluginInput, PluginManifest
from engine.models.workflow import ActionStep, WorkflowScript


_WORD_RE = re.compile(r"[^a-z0-9]+")


def _slug(value: str, *, default: str) -> str:
    lowered = value.strip().lower()
    cleaned = _WORD_RE.sub("_", lowered).strip("_")
    return cleaned or default


def _stable_key(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _iter_scalar_paths(value: object, prefix: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_scalar_paths(item, prefix + (str(key),))
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_scalar_paths(item, prefix + (str(index),))
        return
    if value is None:
        return
    if isinstance(value, (str, int, float, bool)):
        yield prefix, value


@dataclass(frozen=True, slots=True)
class GoldenRunDraft:
    manifest: PluginManifest
    script: WorkflowScript
    output_dir: Path
    manifest_path: Path
    script_path: Path


class GoldenRunDistillationError(RuntimeError):
    def __init__(self, *, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": False,
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


class GoldenRunDistiller:
    def __init__(self, *, trace_store: ModelTraceStore | None = None) -> None:
        self._trace_store = trace_store or ModelTraceStore()

    def distill(
        self,
        *,
        context: ModelTraceContext,
        output_dir: Path,
        plugin_name: str | None = None,
        display_name: str | None = None,
        category: str = "AI Drafts",
    ) -> GoldenRunDraft:
        records = self._trace_store.read_records(context)
        step_records, terminal_record = self._validate_golden_run(context=context, records=records)
        resolved_name = plugin_name or _slug(context.task_id, default="distilled_workflow")
        manifest, script = self._build_draft(
            records=step_records,
            terminal_record=terminal_record,
            plugin_name=resolved_name,
            display_name=display_name or resolved_name.replace("_", " ").title(),
            category=category,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "manifest.yaml"
        script_path = output_dir / "script.yaml"
        manifest_path.write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        script_path.write_text(
            yaml.safe_dump(script.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        self._merge_selectors_to_app_config(step_records, script)
        return GoldenRunDraft(
            manifest=manifest,
            script=script,
            output_dir=output_dir,
            manifest_path=manifest_path,
            script_path=script_path,
        )

    def _validate_golden_run(
        self,
        *,
        context: ModelTraceContext,
        records: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        if not records:
            raise GoldenRunDistillationError(
                code="bad_golden_run",
                message="golden run trace is empty",
                details={
                    "reason": "empty_trace",
                    "task_id": context.task_id,
                    "run_id": context.run_id,
                    "target_label": context.target_label,
                    "attempt_number": context.attempt_number,
                },
            )

        terminal_record = records[-1]
        if str(terminal_record.get("record_type") or "") != "terminal":
            raise GoldenRunDistillationError(
                code="bad_golden_run",
                message="golden run trace must end with a terminal record",
                details={"reason": "missing_terminal_record"},
            )
        if str(terminal_record.get("status") or "") != "completed":
            raise GoldenRunDistillationError(
                code="bad_golden_run",
                message="golden run trace must end in completed status",
                details={
                    "reason": "terminal_status_not_completed",
                    "status": str(terminal_record.get("status") or ""),
                    "code": str(terminal_record.get("code") or ""),
                },
            )

        step_records = [record for record in records if str(record.get("record_type") or "") == "step"]
        if not step_records:
            raise GoldenRunDistillationError(
                code="bad_golden_run",
                message="golden run trace must contain at least one successful step",
                details={"reason": "missing_step_records"},
            )

        for index, record in enumerate(step_records, start=1):
            chosen_action = str(record.get("chosen_action") or "").strip()
            if not chosen_action:
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing chosen_action",
                    details={"reason": "missing_chosen_action", "step_index": index},
                )
            params = record.get("action_params")
            if not isinstance(params, dict):
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing action_params",
                    details={"reason": "missing_action_params", "step_index": index},
                )
            observation = record.get("observation")
            if not isinstance(observation, dict):
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing observation payload",
                    details={"reason": "missing_observation", "step_index": index},
                )
            data = observation.get("data")
            modality = str(observation.get("modality") or "").strip().lower()
            if not isinstance(data, dict) and modality not in {"vision", "vlm", "uitars", "ui-tars"}:
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing structured observation data",
                    details={"reason": "missing_structured_observation", "step_index": index},
                )
        return step_records, terminal_record

    def _build_draft(
        self,
        *,
        records: list[dict[str, object]],
        terminal_record: dict[str, object],
        plugin_name: str,
        display_name: str,
        category: str,
    ) -> tuple[PluginManifest, WorkflowScript]:
        literal_counts = self._collect_literal_counts(records)
        payload_aliases: dict[str, str] = {}
        payload_inputs: dict[str, PluginInput] = {}
        produced_refs: dict[str, str] = {}
        steps: list[dict[str, object]] = []

        for index, record in enumerate(records, start=1):
            action_name = str(record.get("chosen_action") or "").strip()
            step_label = f"{_slug(action_name.split('.')[-1], default='step')}_{index}"
            raw_params = record.get("action_params")
            action_params = raw_params if isinstance(raw_params, dict) else {}
            resolved_params = self._parameterize_value(
                action_params,
                path=(),
                literal_counts=literal_counts,
                payload_aliases=payload_aliases,
                payload_inputs=payload_inputs,
                produced_refs=produced_refs,
            )
            step_payload: dict[str, object] = {
                "label": step_label,
                "kind": "action",
                "action": action_name,
                "params": resolved_params,
            }

            action_result = record.get("action_result")
            action_result_data = {}
            if isinstance(action_result, dict):
                payload = action_result.get("data")
                if isinstance(payload, dict) and payload:
                    save_as = f"{step_label}_result"
                    step_payload["save_as"] = save_as
                    action_result_data = payload
            steps.append(step_payload)

            transition = record.get("post_action_transition")
            if isinstance(transition, dict):
                next_states = transition.get("next_observed_state_ids")
                if isinstance(next_states, list):
                    expected_state_ids = [str(item).strip() for item in next_states if str(item).strip()]
                    if expected_state_ids:
                        steps.append(
                            {
                                "label": f"wait_after_{step_label}",
                                "kind": "action",
                                "action": "ui.wait_until",
                                "params": {
                                    "expected_state_ids": expected_state_ids,
                                    "timeout_ms": 5000,
                                    "interval_ms": 500,
                                },
                            }
                        )

            for result_path, result_value in _iter_scalar_paths(action_result_data):
                dotted_path = ".".join(result_path)
                produced_refs[_stable_key(result_value)] = f"${{vars.{step_payload['save_as']}.{dotted_path}}}"

        steps.append(
            {
                "label": "distilled_success",
                "kind": "stop",
                "status": "success",
                "message": str(terminal_record.get("message") or "golden run completed"),
            }
        )

        vars_payload = {alias: f"${{payload.{alias}}}" for alias in payload_aliases.values()}
        script = WorkflowScript.model_validate(
            {
                "version": "v1",
                "workflow": plugin_name,
                "vars": vars_payload,
                "steps": steps,
            }
        )
        manifest = PluginManifest.model_validate(
            {
                "api_version": "v1",
                "kind": "plugin",
                "name": plugin_name,
                "version": "0.1.0",
                "display_name": display_name,
                "category": category,
                "entry_script": "script.yaml",
                "description": "Offline draft distilled from one successful golden run trace.",
                "inputs": [item.model_dump(mode="json") for item in payload_inputs.values()],
            }
        )
        return manifest, script

    def _collect_literal_counts(self, records: list[dict[str, object]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in records:
            params = record.get("action_params")
            if not isinstance(params, dict):
                continue
            for _path, scalar in _iter_scalar_paths(params):
                key = _stable_key(scalar)
                counts[key] = counts.get(key, 0) + 1
        return counts

    def _parameterize_value(
        self,
        value: object,
        *,
        path: tuple[str, ...],
        literal_counts: dict[str, int],
        payload_aliases: dict[str, str],
        payload_inputs: dict[str, PluginInput],
        produced_refs: dict[str, str],
    ) -> object:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                result[str(key)] = self._parameterize_value(
                    item,
                    path=path + (str(key),),
                    literal_counts=literal_counts,
                    payload_aliases=payload_aliases,
                    payload_inputs=payload_inputs,
                    produced_refs=produced_refs,
                )
            return result
        if isinstance(value, list):
            return [
                self._parameterize_value(
                    item,
                    path=path + (str(index),),
                    literal_counts=literal_counts,
                    payload_aliases=payload_aliases,
                    payload_inputs=payload_inputs,
                    produced_refs=produced_refs,
                )
                for index, item in enumerate(value)
            ]
        if not isinstance(value, (str, int, float, bool)) or value in ("", None):
            return value

        stable_key = _stable_key(value)
        produced_ref = produced_refs.get(stable_key)
        if produced_ref is not None:
            return produced_ref
        if not self._should_parameterize_literal(value=value, path=path, literal_counts=literal_counts):
            return value

        alias = payload_aliases.get(stable_key)
        if alias is None:
            alias = self._next_alias(path, existing_aliases=set(payload_aliases.values()))
            payload_aliases[stable_key] = alias
            payload_inputs[alias] = PluginInput(
                name=alias,
                type=self._infer_input_type(value),
                required=True,
            )
        return f"${{vars.{alias}}}"

    def _next_alias(self, path: tuple[str, ...], *, existing_aliases: set[str]) -> str:
        non_numeric_parts = [part for part in path if not part.isdigit()]
        base = _slug("_".join(non_numeric_parts[-2:]) or "input", default="input")
        candidate = base
        suffix = 2
        while candidate in existing_aliases:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def _should_parameterize_literal(
        self,
        *,
        value: str | int | float | bool,
        path: tuple[str, ...],
        literal_counts: dict[str, int],
    ) -> bool:
        stable_key = _stable_key(value)
        if literal_counts.get(stable_key, 0) > 1:
            return True
        leaf = next((part for part in reversed(path) if not part.isdigit()), "")
        return isinstance(value, str) and leaf in {
            "text",
            "url",
            "username",
            "email",
            "query",
            "prompt",
            "command",
            "package",
            "device_ip",
            "secret",
            "token",
        }

    def _infer_input_type(self, value: object) -> InputType:
        if isinstance(value, bool):
            return InputType.boolean
        if isinstance(value, int):
            return InputType.integer
        if isinstance(value, float):
            return InputType.number
        return InputType.string

    # ------------------------------------------------------------------
    # Selector extraction
    # ------------------------------------------------------------------

    _UI_LOCATOR_ACTIONS = frozenset({
        "ui.click", "ui.long_click", "ui.input_text",
        "ui.node_click", "ui.node_long_click",
        "ui.focus_and_input_with_shell_fallback",
        "ui.input_text_with_shell_fallback",
        "ui.click_selector_or_tap",
    })

    def _extract_package_from_records(self, records: list[dict[str, object]]) -> str:
        for record in records:
            observation = record.get("observation")
            if not isinstance(observation, dict):
                continue
            data = observation.get("data")
            if not isinstance(data, dict):
                continue
            pkg = str(data.get("package") or "").strip()
            if pkg:
                return pkg
        return ""

    def _merge_selectors_to_app_config(
        self,
        records: list[dict[str, object]],
        script: WorkflowScript,
    ) -> None:
        package = self._extract_package_from_records(records)
        if not package:
            return
        app = app_from_package(package)
        if not app:
            return

        # collect new selectors from script steps
        new_selectors: dict[str, dict[str, str]] = {}
        for step in script.steps:
            if not isinstance(step, ActionStep):
                continue
            if step.action not in self._UI_LOCATOR_ACTIONS:
                continue
            params = step.params
            # extract text-based selector
            text_val = params.get("text")
            if isinstance(text_val, str) and text_val and not text_val.startswith("${"):
                key = _slug(text_val, default="") or f"text_{len(new_selectors)}"
                if key not in new_selectors:
                    new_selectors[key] = {"type": "text", "mode": "equal", "value": text_val}
            # extract resource_id-based selector
            rid_val = params.get("resource_id")
            if isinstance(rid_val, str) and rid_val and not rid_val.startswith("${"):
                key = _slug(rid_val.split("/")[-1], default="") or f"rid_{len(new_selectors)}"
                if key not in new_selectors:
                    new_selectors[key] = {"type": "resource_id", "mode": "equal", "value": rid_val}

        if not new_selectors:
            return

        # load existing app config and merge
        try:
            doc = load_app_config_document(app)
        except Exception:
            doc = {"version": "v1", "package_name": package}

        existing: dict[str, object] = doc.get("selectors") if isinstance(doc.get("selectors"), dict) else {}  # type: ignore[assignment]
        merged = False
        for key, selector in new_selectors.items():
            if key not in existing:
                existing[key] = selector
                merged = True

        if not merged:
            return

        doc["selectors"] = existing
        config_path = app_config_path(app)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
