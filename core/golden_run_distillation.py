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

    def _infer_state_id_from_features(self, resource_ids: list[str], texts: list[str]) -> str | None:
        """从 resource_id 推断通用 state_id，不包含 app 特定关键字。"""
        for rid in resource_ids:
            part = rid.split(":id/")[-1].strip().lower()
            part = re.sub(r"[^a-z0-9]+", "_", part).strip("_")
            if part and len(part) > 2:
                return part
        if texts:
            part = re.sub(r"[^a-z0-9]+", "_", texts[0].lower()).strip("_")
            if part and len(part) > 2:
                return part
        return None

    def _extract_states_from_records(self, records: list[dict[str, object]]) -> list[dict[str, str]]:
        import xml.etree.ElementTree as ET
        from collections import Counter
        state_map: dict[str, dict[str, str]] = {}
        for record in records:
            fe = record.get("fallback_evidence") or {}
            xml_content = str((fe.get("ui_xml") or {}).get("content") or "").strip()
            if not xml_content:
                continue
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError:
                continue
            rids: list[str] = []
            texts: list[str] = []
            for node in root.iter():
                rid = node.get("resource-id", "")
                if rid and ":id/" in rid:
                    rids.append(rid)
                text = node.get("text", "").strip()
                if text and len(text) < 60:
                    texts.append(text)
            state_id = self._infer_state_id_from_features(rids, texts)
            if state_id and state_id not in state_map:
                top_rids = [r.split(":id/")[-1] for r in rids[:3]]
                top_texts = texts[:3]
                desc_parts = []
                if top_rids:
                    desc_parts.append(" / ".join(top_rids))
                if top_texts:
                    desc_parts.append(" / ".join(top_texts))
                state_map[state_id] = {
                    "id": state_id,
                    "description": "、".join(desc_parts) if desc_parts else state_id,
                }
        return list(state_map.values())

    def _compute_xml_filter(self, records: list[dict[str, object]]) -> dict[str, int] | None:
        import xml.etree.ElementTree as ET
        text_lens: list[int] = []
        desc_lens: list[int] = []
        for record in records:
            fe = record.get("fallback_evidence") or {}
            xml_content = str((fe.get("ui_xml") or {}).get("content") or "").strip()
            if not xml_content:
                continue
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError:
                continue
            for node in root.iter():
                text = node.get("text", "").strip()
                if text:
                    text_lens.append(len(text))
                desc = node.get("content-desc", "").strip()
                if desc:
                    desc_lens.append(len(desc))
        if not text_lens or not desc_lens:
            return None
        text_lens.sort()
        desc_lens.sort()
        p90_text = text_lens[int(len(text_lens) * 0.9)]
        p90_desc = desc_lens[int(len(desc_lens) * 0.9)]
        # clamp to reasonable range [20, 200]
        return {
            "max_text_len": max(20, min(200, p90_text)),
            "max_desc_len": max(20, min(200, p90_desc)),
        }

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
            text_val = params.get("text")
            if isinstance(text_val, str) and text_val and not text_val.startswith("${"):
                key = _slug(text_val, default="") or f"text_{len(new_selectors)}"
                if key not in new_selectors:
                    new_selectors[key] = {"type": "text", "mode": "equal", "value": text_val}
            rid_val = params.get("resource_id")
            if isinstance(rid_val, str) and rid_val and not rid_val.startswith("${"):
                key = _slug(rid_val.split("/")[-1], default="") or f"rid_{len(new_selectors)}"
                if key not in new_selectors:
                    new_selectors[key] = {"type": "resource_id", "mode": "equal", "value": rid_val}

        # load existing app config
        try:
            doc = load_app_config_document(app)
        except Exception:
            doc = {"version": "v1", "package_name": package}

        changed = False

        # merge selectors
        if new_selectors:
            existing_sel: dict[str, object] = doc.get("selectors") if isinstance(doc.get("selectors"), dict) else {}  # type: ignore[assignment]
            for key, selector in new_selectors.items():
                if key not in existing_sel:
                    existing_sel[key] = selector
                    changed = True
            doc["selectors"] = existing_sel

        # merge states
        new_states = self._extract_states_from_records(records)
        if new_states:
            existing_states: list[dict[str, str]] = doc.get("states") if isinstance(doc.get("states"), list) else []  # type: ignore[assignment]
            existing_ids = {str(s.get("id") or "") for s in existing_states}
            for state in new_states:
                if state["id"] not in existing_ids:
                    existing_states.append(state)
                    changed = True
            doc["states"] = existing_states

        # update xml_filter if not already set
        if not doc.get("xml_filter"):
            xml_filter = self._compute_xml_filter(records)
            if xml_filter:
                doc["xml_filter"] = xml_filter
                changed = True

        if not changed:
            return

        config_path = app_config_path(app)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
