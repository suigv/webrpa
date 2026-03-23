from __future__ import annotations

# pyright: reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnusedCallResult=false
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

from core.app_config_writer import AppConfigWriter
from core.model_trace_store import ModelTraceContext, ModelTraceStore
from core.trace_learner import TraceLearner
from engine.actions.sdk_config_support import (
    app_config_path,
    app_from_package,
    load_app_config_document,
)
from engine.models.manifest import InputType, PluginInput, PluginManifest
from engine.models.workflow import ActionStep, WorkflowScript

_WORD_RE = re.compile(r"[^a-z0-9]+")
_FRAMEWORK_OWNED_INPUT_FIELDS = frozenset(
    {
        "adb_port",
        "api_port",
        "app",
        "app_id",
        "binding_id",
        "cloud_id",
        "cloud_index",
        "device_id",
        "device_ip",
        "package",
        "rpa_port",
        "run_id",
        "sdk_port",
        "serial",
        "state_profile_id",
        "target_label",
        "task_id",
        "_speed",
        "_wait_min_ms",
        "_wait_max_ms",
    }
)
_CREDENTIAL_LITERAL_FIELDS = {
    "account": "${vars.credential.account}",
    "password": "${vars.credential.password}",
    "pwd": "${vars.credential.password}",
    "username": "${vars.credential.account}",
    "username_or_email": "${vars.credential.account}",
    "twofa_secret": "${vars.credential.twofa_secret:-}",
    "twofa_code": "${vars.credential.twofa_code:-}",
    "two_factor_code": "${vars.credential.twofa_code:-}",
    "otp": "${vars.credential.twofa_code:-}",
    "otp_code": "${vars.credential.twofa_code:-}",
    "verification_code": "${vars.credential.twofa_code:-}",
}
_TEXT_INPUT_ACTIONS = frozenset(
    {
        "ui.input_text",
        "ui.input",
        "ui.type",
        "ui.type_text",
        "ui.focus_and_input_with_shell_fallback",
        "ui.input_text_with_shell_fallback",
    }
)
_ACCOUNT_HINT_TOKENS = ("account", "username", "email", "phone", "user", "login_id")
_PASSWORD_HINT_TOKENS = ("password", "passwd", "pwd")
_TWOFA_HINT_TOKENS = (
    "two_factor",
    "twofa",
    "2fa",
    "otp",
    "verification",
    "verify_code",
    "verification_code",
)


def _slug(value: str, *, default: str) -> str:
    lowered = value.strip().lower()
    cleaned = _WORD_RE.sub("_", lowered).strip("_")
    return cleaned or default


def _stable_key(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _is_framework_owned_input_path(path: tuple[str, ...]) -> bool:
    leaf = next((part for part in reversed(path) if not part.isdigit()), "")
    return leaf in _FRAMEWORK_OWNED_INPUT_FIELDS


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
    report: dict[str, object] = field(default_factory=dict)
    report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class DistillationIdentity:
    app_id: str = ""
    package: str = ""
    credentials_ref_kind: str = "missing"
    account: str = ""
    account_source: str = "unknown"


@dataclass(frozen=True, slots=True)
class CredentialBinding:
    app_id: str = ""


class GoldenRunDistillationError(RuntimeError):
    def __init__(
        self, *, code: str, message: str, details: dict[str, object] | None = None
    ) -> None:
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


class _DraftRefinerLLMClient(Protocol):
    def evaluate(self, request: object) -> object: ...


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
        snapshot_identity: dict[str, object] | DistillationIdentity | None = None,
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
            snapshot_identity=snapshot_identity,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "manifest.yaml"
        script_path = output_dir / "script.yaml"
        report_path = output_dir / "report.yaml"
        manifest_path.write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        script_path.write_text(
            yaml.safe_dump(script.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        self._merge_selectors_to_app_config(step_records, script)
        agent_hint_update = self._merge_agent_hint_candidates_to_app_config(step_records)
        report = self._build_distillation_report(
            context=context,
            records=records,
            distilled_records=step_records,
            terminal_record=terminal_record,
            agent_hint_update=agent_hint_update,
        )
        report_path.write_text(
            yaml.safe_dump(report, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return GoldenRunDraft(
            manifest=manifest,
            script=script,
            report=report,
            output_dir=output_dir,
            manifest_path=manifest_path,
            script_path=script_path,
            report_path=report_path,
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

        step_records = [
            self._normalize_step_record(record)
            for record in records
            if str(record.get("record_type") or "") == "step"
        ]
        if not step_records:
            raise GoldenRunDistillationError(
                code="bad_golden_run",
                message="golden run trace must contain at least one successful step",
                details={"reason": "missing_step_records"},
            )

        distillable_records: list[dict[str, object]] = []
        for index, record in enumerate(step_records, start=1):
            chosen_action = str(record.get("chosen_action") or "").strip()
            status = str(record.get("status") or "").strip().lower()
            source = str(record.get("source") or "ai").strip().lower() or "ai"
            human_guided = bool(record.get("human_guided"))
            if not chosen_action:
                if status and status != "action_executed":
                    continue
                if source == "human" or human_guided:
                    continue
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing chosen_action",
                    details={"reason": "missing_chosen_action", "step_index": index},
                )
            params = record.get("action_params")
            if not isinstance(params, dict):
                if source == "human" or human_guided:
                    continue
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing action_params",
                    details={"reason": "missing_action_params", "step_index": index},
                )
            observation = record.get("observation")
            if not isinstance(observation, dict):
                if source == "human" or human_guided:
                    continue
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing observation payload",
                    details={"reason": "missing_observation", "step_index": index},
                )
            data = observation.get("data")
            modality = str(observation.get("modality") or "").strip().lower()
            if not isinstance(data, dict) and modality not in {"vision", "vlm"}:
                if source == "human" or human_guided:
                    continue
                raise GoldenRunDistillationError(
                    code="bad_golden_run",
                    message="golden run step is missing structured observation data",
                    details={"reason": "missing_structured_observation", "step_index": index},
                )
            distillable_records.append(record)

        if not distillable_records:
            raise GoldenRunDistillationError(
                code="bad_golden_run",
                message="golden run trace must contain at least one distillable action step",
                details={"reason": "missing_distillable_steps"},
            )
        return distillable_records, terminal_record

    def _normalize_step_record(self, record: dict[str, object]) -> dict[str, object]:
        normalized = dict(record)
        action_name = str(
            normalized.get("chosen_action") or normalized.get("action_name") or ""
        ).strip()
        if action_name:
            normalized["chosen_action"] = action_name
        source = str(normalized.get("source") or "").strip().lower() or "ai"
        normalized["source"] = source
        normalized["human_guided"] = bool(normalized.get("human_guided") or source == "human")
        return normalized

    def _build_distillation_report(
        self,
        *,
        context: ModelTraceContext,
        records: list[dict[str, object]],
        distilled_records: list[dict[str, object]],
        terminal_record: dict[str, object],
        agent_hint_update: dict[str, object] | None = None,
    ) -> dict[str, object]:
        step_records = [
            self._normalize_step_record(record)
            for record in records
            if str(record.get("record_type") or "") == "step"
        ]
        source_counts: dict[str, int] = {}
        included_keys = {
            (
                int(record.get("sequence") or 0),
                int(record.get("step_index") or 0),
                str(record.get("chosen_action") or "").strip(),
            )
            for record in distilled_records
        }
        human_guided_steps: list[dict[str, object]] = []
        for record in step_records:
            source = str(record.get("source") or "ai").strip() or "ai"
            source_counts[source] = source_counts.get(source, 0) + 1
            if bool(record.get("human_guided")) or source == "human":
                action_name = str(
                    record.get("chosen_action") or record.get("action_name") or ""
                ).strip()
                human_guided_steps.append(
                    {
                        "sequence": int(record.get("sequence") or 0),
                        "step_index": int(record.get("step_index") or 0),
                        "action": action_name,
                        "status": str(record.get("status") or "").strip(),
                        "source": source,
                        "human_guided": True,
                        "included_in_script": (
                            (
                                int(record.get("sequence") or 0),
                                int(record.get("step_index") or 0),
                                action_name,
                            )
                            in included_keys
                        ),
                    }
                )

        return {
            "task_id": context.task_id,
            "run_id": context.run_id,
            "target_label": context.target_label,
            "attempt_number": context.attempt_number,
            "step_records_total": len(step_records),
            "distilled_step_count": len(distilled_records),
            "terminal_status": str(terminal_record.get("status") or ""),
            "terminal_code": str(terminal_record.get("code") or ""),
            "source_counts": source_counts,
            "human_guided_steps": human_guided_steps,
            "agent_hint_update": dict(agent_hint_update or {}),
        }

    def _build_draft(
        self,
        *,
        records: list[dict[str, object]],
        terminal_record: dict[str, object],
        plugin_name: str,
        display_name: str,
        category: str,
        snapshot_identity: dict[str, object] | DistillationIdentity | None = None,
    ) -> tuple[PluginManifest, WorkflowScript]:
        literal_counts = self._collect_literal_counts(records)
        payload_aliases: dict[str, str] = {}
        payload_inputs: dict[str, PluginInput] = {}
        produced_refs: dict[str, str] = {}
        steps: list[dict[str, object]] = []
        identity = self._normalize_snapshot_identity(snapshot_identity)
        credential_binding = self._resolve_credential_binding(records=records, identity=identity)

        if credential_binding is not None:
            self._register_credential_inputs(payload_inputs, credential_binding)
            steps.append(self._build_credential_load_step(credential_binding))

        for index, record in enumerate(records, start=1):
            action_name = str(record.get("chosen_action") or "").strip()
            step_label = f"{_slug(action_name.split('.')[-1], default='step')}_{index}"
            raw_params = record.get("action_params")
            action_params = raw_params if isinstance(raw_params, dict) else {}
            if credential_binding is not None:
                action_params = cast(
                    dict[str, object],
                    self._rewrite_credential_literals(
                        action_params,
                        path=(),
                        action_name=action_name,
                        action_params=action_params,
                        record=record,
                        identity=identity,
                    ),
                )
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
                    expected_state_ids = [
                        str(item).strip() for item in next_states if str(item).strip()
                    ]
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
                produced_refs[_stable_key(result_value)] = (
                    f"${{vars.{step_payload['save_as']}.{dotted_path}}}"
                )

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

    def _normalize_snapshot_identity(
        self, snapshot_identity: dict[str, object] | DistillationIdentity | None
    ) -> DistillationIdentity:
        if isinstance(snapshot_identity, DistillationIdentity):
            return snapshot_identity
        if not isinstance(snapshot_identity, dict):
            return DistillationIdentity()
        return DistillationIdentity(
            app_id=str(snapshot_identity.get("app_id") or "").strip().lower(),
            package=str(snapshot_identity.get("package") or "").strip(),
            credentials_ref_kind=(
                str(snapshot_identity.get("credentials_ref_kind") or "").strip().lower()
                or "missing"
            ),
            account=str(snapshot_identity.get("account") or "").strip(),
            account_source=(
                str(snapshot_identity.get("account_source") or "").strip().lower() or "unknown"
            ),
        )

    def _resolve_credential_binding(
        self, *, records: list[dict[str, object]], identity: DistillationIdentity
    ) -> CredentialBinding | None:
        if not any(
            self._record_uses_credential_binding(record, identity=identity) for record in records
        ):
            return None

        package = identity.package or self._extract_package_from_records(records)
        package_app_id = app_from_package(package) if package else ""
        app_id = identity.app_id
        if package_app_id and (not app_id or app_id == "default"):
            app_id = package_app_id

        return CredentialBinding(app_id=app_id)

    def _record_uses_credential_binding(
        self, record: dict[str, object], *, identity: DistillationIdentity
    ) -> bool:
        action_name = str(record.get("chosen_action") or "").strip()
        params = record.get("action_params")
        if not action_name or not isinstance(params, dict):
            return False
        rewritten = self._rewrite_credential_literals(
            params,
            path=(),
            action_name=action_name,
            action_params=params,
            record=record,
            identity=identity,
        )
        return rewritten != params

    def _register_credential_inputs(
        self, payload_inputs: dict[str, PluginInput], binding: CredentialBinding
    ) -> None:
        payload_inputs["credentials_ref"] = PluginInput(
            name="credentials_ref",
            type=InputType.string,
            required=False,
            default="",
            label="绑定账号",
            description="前端账号选择器会写入结构化凭据引用。",
            advanced=True,
            system=True,
            widget="hidden",
        )
        if binding.app_id:
            payload_inputs["app_id"] = PluginInput(
                name="app_id",
                type=InputType.string,
                required=False,
                default=binding.app_id,
                label="应用 ID",
                advanced=True,
                system=True,
                widget="hidden",
            )

    def _build_credential_load_step(self, binding: CredentialBinding) -> dict[str, object]:
        params: dict[str, object] = {
            "credentials_ref": "${payload.credentials_ref:-}",
        }
        if binding.app_id:
            params["app_id"] = f"${{payload.app_id:-{binding.app_id}}}"
        return {
            "label": "load_credentials",
            "kind": "action",
            "action": "credentials.load",
            "save_as": "credential",
            "params": params,
        }

    def _rewrite_credential_literals(
        self,
        value: object,
        *,
        path: tuple[str, ...],
        action_name: str,
        action_params: dict[str, object],
        record: dict[str, object],
        identity: DistillationIdentity,
    ) -> object:
        if isinstance(value, dict):
            return {
                str(key): self._rewrite_credential_literals(
                    item,
                    path=path + (str(key),),
                    action_name=action_name,
                    action_params=action_params,
                    record=record,
                    identity=identity,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._rewrite_credential_literals(
                    item,
                    path=path + (str(index),),
                    action_name=action_name,
                    action_params=action_params,
                    record=record,
                    identity=identity,
                )
                for index, item in enumerate(value)
            ]
        ref = self._credential_ref_for_literal(
            value,
            path=path,
            action_name=action_name,
            action_params=action_params,
            record=record,
            identity=identity,
        )
        return ref if ref is not None else value

    def _credential_ref_for_literal(
        self,
        value: object,
        *,
        path: tuple[str, ...],
        action_name: str,
        action_params: dict[str, object],
        record: dict[str, object],
        identity: DistillationIdentity,
    ) -> str | None:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw or raw.startswith("${vars.credential."):
            return None

        leaf = next((part for part in reversed(path) if not part.isdigit()), "")
        direct_ref = _CREDENTIAL_LITERAL_FIELDS.get(leaf)
        if direct_ref is not None:
            return direct_ref

        if leaf not in {"text", "value"} or action_name not in _TEXT_INPUT_ACTIONS:
            return None
        if identity.account and raw == identity.account:
            return "${vars.credential.account}"

        hint_text = self._build_credential_hint_text(record=record, action_params=action_params)
        if any(token in hint_text for token in _TWOFA_HINT_TOKENS):
            return "${vars.credential.twofa_code:-}"
        if any(token in hint_text for token in _PASSWORD_HINT_TOKENS):
            return "${vars.credential.password}"
        if any(token in hint_text for token in _ACCOUNT_HINT_TOKENS):
            return "${vars.credential.account}"
        return None

    def _build_credential_hint_text(
        self, *, record: dict[str, object], action_params: dict[str, object]
    ) -> str:
        parts: list[str] = []
        observation = record.get("observation")
        if isinstance(observation, dict):
            state_ids = observation.get("observed_state_ids")
            if isinstance(state_ids, list):
                parts.extend(str(item) for item in state_ids if str(item).strip())
            data = observation.get("data")
            if isinstance(data, dict):
                state = data.get("state")
                if isinstance(state, dict):
                    state_id = str(state.get("state_id") or "").strip()
                    if state_id:
                        parts.append(state_id)
        for key in (
            "field_id",
            "credential",
            "resource_id",
            "selector",
            "description",
            "query",
            "placeholder",
            "hint",
        ):
            value = action_params.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value)
        normalized = " ".join(parts).strip().lower()
        return normalized.replace("-", "_")

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
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            return value

        stable_key = _stable_key(value)
        produced_ref = produced_refs.get(stable_key)
        if produced_ref is not None:
            return produced_ref
        if _is_framework_owned_input_path(path):
            return value
        if not self._should_parameterize_literal(
            value=value, path=path, literal_counts=literal_counts
        ):
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

    _UI_LOCATOR_ACTIONS = frozenset(
        {
            "ui.click",
            "ui.long_click",
            "ui.input_text",
            "ui.node_click",
            "ui.node_long_click",
            "ui.focus_and_input_with_shell_fallback",
            "ui.input_text_with_shell_fallback",
            "ui.click_selector_or_tap",
        }
    )

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

    def _infer_state_id_from_features(
        self, resource_ids: list[str], texts: list[str]
    ) -> str | None:
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

    def _extract_states_from_records(
        self, records: list[dict[str, object]]
    ) -> list[dict[str, str]]:
        import xml.etree.ElementTree as ET

        state_map: dict[str, dict[str, str]] = {}
        for record in records:
            fe = record.get("fallback_evidence")
            if not isinstance(fe, dict):
                fe = {}
            ui_xml = fe.get("ui_xml")
            if not isinstance(ui_xml, dict):
                ui_xml = {}
            xml_content = str(ui_xml.get("content") or "").strip()
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
            fe = record.get("fallback_evidence")
            if not isinstance(fe, dict):
                fe = {}
            ui_xml = fe.get("ui_xml")
            if not isinstance(ui_xml, dict):
                ui_xml = {}
            xml_content = str(ui_xml.get("content") or "").strip()
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
        doc: dict[str, Any]
        try:
            doc = load_app_config_document(app)
        except Exception:
            doc = {"version": "v1", "package_name": package}

        changed = False

        # merge selectors
        if new_selectors:
            raw_selectors = doc.get("selectors")
            existing_sel: dict[str, object] = (
                raw_selectors if isinstance(raw_selectors, dict) else {}
            )
            for key, selector in new_selectors.items():
                if key not in existing_sel:
                    existing_sel[key] = selector
                    changed = True
            doc["selectors"] = existing_sel

        # merge states
        new_states = self._extract_states_from_records(records)
        if new_states:
            raw_states = doc.get("states")
            existing_states: list[dict[str, str]] = (
                raw_states if isinstance(raw_states, list) else []
            )
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

        if changed:
            config_path = app_config_path(app)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

        learned_stage_patterns = TraceLearner().learn_from_records(records)
        if learned_stage_patterns:
            AppConfigWriter(threshold=1).merge_stage_resource_ids(app, learned_stage_patterns)

    def _merge_agent_hint_candidates_to_app_config(
        self, records: list[dict[str, object]]
    ) -> dict[str, object]:
        package = self._extract_package_from_records(records)
        if not package:
            return {}
        app = app_from_package(package)
        if not app:
            return {}

        candidates: list[str] = []
        for record in records:
            planner = record.get("planner")
            if not isinstance(planner, dict):
                continue
            artifact = planner.get("planner_artifact")
            if not isinstance(artifact, dict):
                continue
            advanced_prompt = str(artifact.get("advanced_prompt") or "").strip()
            if advanced_prompt and advanced_prompt not in candidates:
                candidates.append(advanced_prompt)

        if not candidates:
            return {}

        try:
            doc = load_app_config_document(app)
        except Exception:
            doc = {"version": "v1", "package_name": package}

        existing_raw = doc.get("agent_hint_candidates")
        existing = (
            [item for item in existing_raw if isinstance(item, str) and item.strip()]
            if isinstance(existing_raw, list)
            else []
        )
        merged = existing[:]
        changed = False
        for candidate in candidates:
            if candidate not in merged:
                merged.append(candidate)
                changed = True
        promoted_agent_hint = str(doc.get("agent_hint") or "").strip()
        if not promoted_agent_hint and merged:
            promoted_agent_hint = merged[-1]
            doc["agent_hint"] = promoted_agent_hint
            changed = True
        if not changed:
            return {
                "app_id": app,
                "candidate_count": len(merged),
                "promoted_agent_hint": promoted_agent_hint or None,
            }
        doc["agent_hint_candidates"] = merged[-10:]
        config_path = app_config_path(app)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return {
            "app_id": app,
            "candidate_count": len(doc["agent_hint_candidates"]),
            "promoted_agent_hint": promoted_agent_hint or None,
            "config_path": str(config_path),
        }

    # ------------------------------------------------------------------
    # LLM Draft Refiner (旁路增强)
    # ------------------------------------------------------------------

    def refine_draft(
        self,
        draft: GoldenRunDraft,
        records: list[dict[str, object]],
        *,
        llm_client: object | None = None,
    ) -> GoldenRunDraft:
        """Optionally refine a draft using LLM-based parametrization.

        This is a **side-car** enhancement: if the LLM fails or returns
        garbage, the original draft is returned unchanged. The caller
        should never see an exception from this method.
        """
        refiner = LLMDraftRefiner(llm_client=llm_client)
        return refiner.refine(draft, records)


# ==========================================================================
# LLMDraftRefiner – 旁路增强蒸馏器
# ==========================================================================

_LLM_REFINER_SYSTEM_PROMPT = """\
You are a YAML workflow parametrization expert. You will be given:
1. A YAML workflow script generated from a successful automation trace.
2. The raw JSON trace records that produced this YAML.

Your task: identify **hardcoded business-specific values** in the YAML that
should be abstracted into reusable `${payload.xxx}` template variables, so the
workflow can be re-used with different inputs.

## What to parameterize
- Search terms, usernames, email addresses, message text, URLs
- Specific product names, order IDs, phone numbers
- Any value that would change between different runs of the same workflow

## What NOT to parameterize
- Action names (e.g. `ui.click`, `ui.input_text`)
- Selector keys (`text`, `resource_id`) that identify UI elements
- Timeout values, interval values, coordinates
- State IDs, step labels

## Output Contract (strict JSON)
Return a JSON object with a single key `"replacements"` containing an array.
Each replacement is:
```json
{
  "original_value": "the exact hardcoded string in the YAML",
  "variable_name": "descriptive_snake_case_name",
  "input_type": "string",
  "description": "brief description of what this parameter is"
}
```

If nothing should be parameterized, return `{"replacements": []}`.
"""


class LLMDraftRefiner:
    """Side-car LLM-based parametrization refiner.

    Takes a baseline ``GoldenRunDraft`` produced by the heuristic distiller
    and asks an LLM to identify additional hardcoded business values that
    should be abstracted into ``${payload.xxx}`` template variables.

    **Safety guarantee**: if the LLM is unreachable, returns bad JSON, or
    suggests replacements that break the YAML structure, the original draft
    is returned unchanged.
    """

    def __init__(self, *, llm_client: object | None = None) -> None:
        self._llm_client = llm_client

    def _get_client(self) -> object:
        if self._llm_client is not None:
            return self._llm_client
        from ai_services.llm_client import LLMClient

        return LLMClient()

    def refine(
        self,
        draft: GoldenRunDraft,
        records: list[dict[str, object]],
    ) -> GoldenRunDraft:
        """Attempt LLM-based refinement. Returns original draft on any failure."""
        import logging

        logger = logging.getLogger(__name__)

        try:
            return self._refine_impl(draft, records)
        except Exception as exc:
            logger.warning("LLMDraftRefiner: refinement failed, returning base draft: %s", exc)
            return draft

    def _refine_impl(
        self,
        draft: GoldenRunDraft,
        records: list[dict[str, object]],
    ) -> GoldenRunDraft:
        import json as _json

        # --- Build the prompt ---
        script_yaml = draft.script_path.read_text(encoding="utf-8")
        manifest_yaml = draft.manifest_path.read_text(encoding="utf-8")

        # Compress trace records for the LLM (only action + params + observation summary)
        compressed_trace: list[dict[str, object]] = []
        for record in records:
            if str(record.get("record_type") or "") != "step":
                continue
            compressed_trace.append(
                {
                    "step": record.get("step_index"),
                    "action": record.get("chosen_action"),
                    "params": record.get("action_params"),
                }
            )

        prompt_payload = {
            "script_yaml": script_yaml,
            "manifest_yaml": manifest_yaml,
            "trace_summary": compressed_trace,
        }

        from ai_services.llm_client import LLMRequest

        request = LLMRequest(
            prompt=_json.dumps(prompt_payload, ensure_ascii=False),
            system_prompt=_LLM_REFINER_SYSTEM_PROMPT,
            response_format={"type": "json_object"},
        )

        client = cast(_DraftRefinerLLMClient, self._get_client())
        response = client.evaluate(request)  # type: ignore[union-attr]

        if not bool(getattr(response, "ok", False)):
            import logging

            logging.getLogger(__name__).warning(
                "LLMDraftRefiner: LLM returned error, skipping refinement"
            )
            return draft

        output_text = str(getattr(response, "output_text", "") or "").strip()
        if not output_text:
            return draft

        result = _json.loads(output_text)
        if not isinstance(result, dict):
            return draft

        replacements = result.get("replacements")
        if not isinstance(replacements, list) or not replacements:
            return draft

        # --- Apply replacements ---
        return self._apply_replacements(draft, replacements)

    def _apply_replacements(
        self,
        draft: GoldenRunDraft,
        replacements: list[dict[str, object]],
    ) -> GoldenRunDraft:
        """Apply LLM-suggested replacements to the YAML files.

        Rewrites the YAML text and updates the manifest inputs.
        If any replacement would break the YAML, we bail out entirely.
        """
        import logging

        logger = logging.getLogger(__name__)

        script_text = draft.script_path.read_text(encoding="utf-8")
        manifest_text = draft.manifest_path.read_text(encoding="utf-8")

        # Collect existing input names from manifest
        existing_input_names = {inp.name for inp in draft.manifest.inputs}
        new_inputs: list[dict[str, object]] = []
        applied_count = 0

        for replacement in replacements:
            if not isinstance(replacement, dict):
                continue
            original = str(replacement.get("original_value") or "").strip()
            var_name = str(replacement.get("variable_name") or "").strip()
            input_type = str(replacement.get("input_type") or "string").strip()

            if not original or not var_name:
                continue

            # Safety: don't replace action names or structural keys
            if original in {
                "ui.click",
                "ui.input_text",
                "ui.swipe",
                "ui.long_click",
                "ui.key_press",
                "ui.wait_until",
                "ui.match_state",
                "action",
                "kind",
                "label",
                "stop",
                "success",
            }:
                continue

            # Safety: variable name must be valid identifier
            if not var_name.replace("_", "").isalnum():
                continue

            template_ref = f"${{payload.{var_name}}}"

            # Check if replacement would actually affect the script
            if original not in script_text:
                continue

            script_text = script_text.replace(original, template_ref)
            applied_count += 1

            if var_name not in existing_input_names:
                new_inputs.append(
                    {
                        "name": var_name,
                        "type": input_type
                        if input_type in {"string", "integer", "number", "boolean"}
                        else "string",
                        "required": True,
                    }
                )
                existing_input_names.add(var_name)

        if applied_count == 0:
            return draft

        # Validate the modified YAML is still parseable
        try:
            yaml.safe_load(script_text)
        except Exception as exc:
            logger.warning("LLMDraftRefiner: modified YAML is invalid, reverting: %s", exc)
            return draft

        # Update manifest with new inputs
        if new_inputs:
            manifest_data = yaml.safe_load(manifest_text)
            if isinstance(manifest_data, dict):
                existing_inputs = manifest_data.get("inputs", [])
                if isinstance(existing_inputs, list):
                    existing_inputs.extend(new_inputs)
                    manifest_data["inputs"] = existing_inputs
                manifest_text = yaml.safe_dump(manifest_data, sort_keys=False, allow_unicode=True)

        # Add vars mapping for new payload inputs
        script_data = yaml.safe_load(script_text)
        if isinstance(script_data, dict):
            existing_vars = script_data.get("vars", {})
            if isinstance(existing_vars, dict):
                for inp in new_inputs:
                    name = str(inp.get("name", ""))
                    if name and name not in existing_vars:
                        existing_vars[name] = f"${{payload.{name}}}"
                script_data["vars"] = existing_vars
            script_text = yaml.safe_dump(script_data, sort_keys=False, allow_unicode=True)

        # Write back
        draft.script_path.write_text(script_text, encoding="utf-8")
        draft.manifest_path.write_text(manifest_text, encoding="utf-8")

        # Rebuild models from updated YAML
        updated_manifest = PluginManifest.model_validate(yaml.safe_load(manifest_text))
        updated_script = WorkflowScript.model_validate(yaml.safe_load(script_text))

        logger.info("LLMDraftRefiner: applied %d replacements", applied_count)

        return GoldenRunDraft(
            manifest=updated_manifest,
            script=updated_script,
            output_dir=draft.output_dir,
            manifest_path=draft.manifest_path,
            script_path=draft.script_path,
        )
