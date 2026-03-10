from __future__ import annotations

# pyright: reportUnusedCallResult=false, reportAny=false

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, cast

import pytest
import yaml

from core.golden_run_distillation import GoldenRunDistillationError, GoldenRunDistiller
from core.model_trace_store import ModelTraceContext, ModelTraceStore
from engine.action_registry import ActionRegistry
from engine.models.manifest import InputType, PluginManifest
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.workflow import WorkflowScript
from engine.plugin_loader import PluginLoader
from engine.parser import parse_manifest, parse_script
from engine.runner import Runner
from tools.check_plugin_manifest_inputs import collect_manifest_input_gaps

ActionHandler = Callable[[dict[str, object], ExecutionContext], ActionResult]


@dataclass
class DraftUsabilityGateResult:
    manifest: PluginManifest
    script: WorkflowScript
    gaps: list[str]
    loader: PluginLoader
    runner_result: dict[str, object] | None
    captured: list[dict[str, object]]


def _context() -> ModelTraceContext:
    return ModelTraceContext(
        task_id="task-123",
        run_id="task-123-run-1",
        target_label="device-7-cloud-2",
        attempt_number=1,
    )


def _append_success_trace(store: ModelTraceStore, context: ModelTraceContext) -> None:
    store.append_record(
        context,
        {
            "trace_version": 1,
            "sequence": 1,
            "step_index": 1,
            "record_type": "step",
            "status": "action_executed",
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["login_prompt"],
                "data": {"state": {"state_id": "login_prompt"}},
            },
            "chosen_action": "core.load_selector",
            "action_params": {"query": "login_button"},
            "action_result": {"ok": True, "code": "ok", "message": "", "data": {"selector": "#login-button"}},
            "post_action_transition": {
                "transition_status": "observed",
                "next_observed_state_ids": ["ready_to_submit"],
                "next_observation_ok": True,
                "next_observation": {"state": {"state_id": "ready_to_submit"}},
                "observed_at": "2026-03-10T00:00:01Z",
            },
        },
    )
    store.append_record(
        context,
        {
            "trace_version": 1,
            "sequence": 2,
            "step_index": 2,
            "record_type": "step",
            "status": "action_executed",
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["ready_to_submit"],
                "data": {"state": {"state_id": "ready_to_submit"}},
            },
            "chosen_action": "ui.click",
            "action_params": {"selector": "#login-button", "text": "alice@example.com"},
            "action_result": {"ok": True, "code": "ok", "message": "", "data": {}},
            "post_action_transition": {
                "transition_status": "observed",
                "next_observed_state_ids": ["confirm_email"],
                "next_observation_ok": True,
                "next_observation": {"state": {"state_id": "confirm_email"}},
                "observed_at": "2026-03-10T00:00:02Z",
            },
        },
    )
    store.append_record(
        context,
        {
            "trace_version": 1,
            "sequence": 3,
            "step_index": 3,
            "record_type": "step",
            "status": "action_executed",
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["confirm_email"],
                "data": {"state": {"state_id": "confirm_email"}},
            },
            "chosen_action": "ui.fill_form",
            "action_params": {"text": "alice@example.com", "confirm_text": "alice@example.com"},
            "action_result": {"ok": True, "code": "ok", "message": "", "data": {}},
            "post_action_transition": {
                "transition_status": "observed",
                "next_observed_state_ids": ["logged_in"],
                "next_observation_ok": True,
                "next_observation": {"state": {"state_id": "logged_in"}},
                "observed_at": "2026-03-10T00:00:03Z",
            },
        },
    )
    store.append_record(
        context,
        {
            "trace_version": 1,
            "sequence": 4,
            "step_index": 4,
            "record_type": "terminal",
            "status": "completed",
            "code": "done",
            "message": "golden run completed",
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["logged_in"],
                "data": {"state": {"state_id": "logged_in"}},
            },
        },
    )


def _distill_success_draft(tmp_path: Path):
    traces_root = tmp_path / "config" / "data" / "traces"
    store = ModelTraceStore(root_dir=traces_root)
    context = _context()
    _append_success_trace(store, context)

    return GoldenRunDistiller(trace_store=store).distill(
        context=context,
        output_dir=tmp_path / "drafts" / "distilled_login_root" / "distilled_login",
        plugin_name="distilled_login",
        display_name="Distilled Login",
    )


def _sample_payload_for_manifest(manifest: PluginManifest) -> dict[str, object]:
    payload: dict[str, object] = {"task": manifest.name}
    for plugin_input in manifest.inputs:
        if plugin_input.default is not None:
            payload[plugin_input.name] = cast(object, plugin_input.default)
        elif plugin_input.type == InputType.boolean:
            payload[plugin_input.name] = True
        elif plugin_input.type == InputType.integer:
            payload[plugin_input.name] = 1
        elif plugin_input.type == InputType.number:
            payload[plugin_input.name] = 1.5
        else:
            payload[plugin_input.name] = f"{plugin_input.name}-value"
    return payload


def _build_distilled_replay_smoke_registry(captured: list[dict[str, object]]) -> ActionRegistry:
    registry = ActionRegistry()

    def fake_load_selector(params: dict[str, object], context: ExecutionContext) -> ActionResult:
        captured.append({"action": "core.load_selector", "params": dict(params), "payload": dict(context.payload)})
        return ActionResult(ok=True, code="ok", data={"selector": f"#{params.get('query', 'missing')}"})

    def fake_ui_action(action_name: str) -> ActionHandler:
        def _handler(params: dict[str, object], context: ExecutionContext) -> ActionResult:
            captured.append({"action": action_name, "params": dict(params), "payload": dict(context.payload)})
            return ActionResult(ok=True, code="ok", data={})

        return _handler

    registry.register("core.load_selector", fake_load_selector)
    registry.register("ui.click", fake_ui_action("ui.click"))
    registry.register("ui.fill_form", fake_ui_action("ui.fill_form"))
    registry.register("ui.wait_until", fake_ui_action("ui.wait_until"))
    return registry


def _run_generated_draft_usability_gate(
    draft_root: Path,
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> DraftUsabilityGateResult:
    plugin_dir = draft_root / "distilled_login"
    manifest = parse_manifest(plugin_dir / "manifest.yaml")
    script = parse_script(plugin_dir / "script.yaml")
    gaps = collect_manifest_input_gaps(draft_root)
    loader = PluginLoader(plugins_root=draft_root)
    loader.scan()

    result = DraftUsabilityGateResult(
        manifest=manifest,
        script=script,
        gaps=gaps,
        loader=loader,
        runner_result=None,
        captured=[],
    )
    if gaps or not loader.has(manifest.name):
        return result
    if monkeypatch is None:
        return result

    captured: list[dict[str, object]] = []
    registry = _build_distilled_replay_smoke_registry(captured)
    monkeypatch.setattr("engine.runner.get_registry", lambda: registry)
    monkeypatch.setattr("engine.interpreter.get_registry", lambda: registry)
    monkeypatch.setattr("engine.runner.get_shared_plugin_loader", lambda: loader)
    result.runner_result = Runner().run(_sample_payload_for_manifest(manifest))
    result.captured = captured
    return result


def test_generated_draft_emits_parseable_draft_artifacts(tmp_path: Path):
    draft = _distill_success_draft(tmp_path)

    assert draft.output_dir == tmp_path / "drafts" / "distilled_login_root" / "distilled_login"
    assert draft.manifest_path.exists()
    assert draft.script_path.exists()
    assert "plugins" not in str(draft.output_dir)

    manifest = parse_manifest(draft.manifest_path)
    script = parse_script(draft.script_path)
    assert manifest.name == "distilled_login"
    assert script.workflow == "distilled_login"
    assert script.steps[-1].kind == "stop"
    assert any(getattr(step, "action", "") == "ui.wait_until" for step in script.steps)


def test_generated_draft_replay_smoke_passes_usability_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    draft = _distill_success_draft(tmp_path)

    gate = _run_generated_draft_usability_gate(draft.output_dir.parent, monkeypatch=monkeypatch)

    assert gate.gaps == []
    assert gate.loader.has("distilled_login") is True
    assert gate.runner_result is not None
    runner_result = gate.runner_result
    assert runner_result == {
        "ok": True,
        "workflow": "distilled_login",
        "status": "success",
        "message": "golden run completed",
        "task": "distilled_login",
        "timestamp": runner_result["timestamp"],
    }
    assert [entry["action"] for entry in gate.captured] == [
        "core.load_selector",
        "ui.wait_until",
        "ui.click",
        "ui.wait_until",
        "ui.fill_form",
        "ui.wait_until",
    ]


def test_invalid_generated_draft_fails_usability_gate_on_manifest_input_gap(tmp_path: Path):
    draft = _distill_success_draft(tmp_path)
    script_payload = cast(dict[str, object], yaml.safe_load(draft.script_path.read_text(encoding="utf-8")))
    assert isinstance(script_payload, dict)
    steps = cast(list[dict[str, object]], script_payload.get("steps"))
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    params = cast(dict[str, object], first_step.get("params"))
    assert isinstance(params, dict)
    params["missing_ref"] = "${payload.missing_ref}"
    draft.script_path.write_text(yaml.safe_dump(script_payload, sort_keys=False, allow_unicode=True), encoding="utf-8")

    gate = _run_generated_draft_usability_gate(draft.output_dir.parent)

    assert gate.manifest.name == "distilled_login"
    assert gate.script.workflow == "distilled_login"
    assert gate.runner_result is None
    assert gate.gaps == [
        "distilled_login: missing manifest inputs for payload refs: missing_ref"
    ]


def test_parameterization_reuses_payload_and_vars_refs(tmp_path: Path):
    draft = _distill_success_draft(tmp_path)

    manifest = parse_manifest(draft.manifest_path)
    script_text = draft.script_path.read_text(encoding="utf-8")
    assert {item.name for item in manifest.inputs} >= {"text", "query"}
    assert "${payload.text}" in script_text
    assert "${vars.text}" in script_text
    assert "${vars.load_selector_1_result.selector}" in script_text


def test_rejects_bad_golden_run(tmp_path: Path):
    traces_root = tmp_path / "config" / "data" / "traces"
    store = ModelTraceStore(root_dir=traces_root)
    context = _context()
    store.append_record(
        context,
        {
            "trace_version": 1,
            "sequence": 1,
            "step_index": 1,
            "record_type": "terminal",
            "status": "failed_runtime_error",
            "code": "planner_error",
            "message": "planner failed",
            "observation": {
                "ok": False,
                "modality": "structured_state",
                "observed_state_ids": ["login_prompt"],
                "data": {"state": {"state_id": "login_prompt"}},
            },
        },
    )

    with pytest.raises(GoldenRunDistillationError) as exc_info:
        GoldenRunDistiller(trace_store=store).distill(
            context=context,
            output_dir=tmp_path / "drafts" / "bad_run",
            plugin_name="bad_run",
        )

    assert exc_info.value.code == "bad_golden_run"
    assert exc_info.value.to_dict()["details"] == {
        "reason": "terminal_status_not_completed",
        "status": "failed_runtime_error",
        "code": "planner_error",
    }
