# pyright: reportMissingImports=false
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_services.llm_client import LLMResponse
from api.server import app
from core.golden_run_distillation import GoldenRunDistiller
from core.model_trace_store import ModelTraceContext, ModelTraceStore
from core.task_control import (
    TaskController,
    override_task_controller_for_tests,
    reset_task_controller_for_tests,
)
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore
from core.workflow_draft_store import WorkflowDraftRecord, WorkflowDraftStore
from core.workflow_drafts import WorkflowDraftService
from engine.action_registry import ActionRegistry, register_defaults, resolve_action
from engine.agent_executor import AgentExecutorRuntime
from engine.models.runtime import ActionResult, ExecutionContext
from engine.models.workflow import ActionStep, WorkflowScript
from engine.runner import Runner


def _wait_status(client: TestClient, task_id: str, timeout_s: float = 10.0) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        response = client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        status = str(response.json()["status"])
        if status in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.05)
    return "timeout"


class _SequencedLLMClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)

    def evaluate(self, request, *, runtime_config=None):
        _ = (request, runtime_config)
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(
            ok=True,
            request_id="req-default",
            provider="openai",
            model="gpt-5.4",
            output_text=json.dumps({"done": True, "message": "default complete"}),
        )


def _build_agent_executor_runner(*, successful_runs: int) -> Runner:
    registry = ActionRegistry()

    def _ui_match_state(params, context):
        _ = (params, context)
        return ActionResult(
            ok=True,
            code="ok",
            data={
                "operation": "match_state",
                "status": "matched",
                "state": {"state_id": "account"},
                "expected_state_ids": ["account"],
            },
        )

    def _ui_click(params, context):
        _ = context
        return ActionResult(ok=True, code="ok", data={"clicked": params})

    registry.register("ui.match_state", _ui_match_state)
    registry.register("ui.click", _ui_click)

    responses: list[LLMResponse] = []
    for index in range(successful_runs):
        responses.extend(
            [
                LLMResponse(
                    ok=True,
                    request_id=f"req-{index}-1",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps(
                        {
                            "done": False,
                            "action": "ui.click",
                            "params": {"selector": "#continue"},
                        }
                    ),
                ),
                LLMResponse(
                    ok=True,
                    request_id=f"req-{index}-2",
                    provider="openai",
                    model="gpt-5.4",
                    output_text=json.dumps({"done": True, "message": "executor completed"}),
                ),
            ]
        )
    llm_client = _SequencedLLMClient(responses=responses)
    return Runner(
        agent_executor_runtime=AgentExecutorRuntime(
            registry=registry,
            llm_client_factory=lambda: llm_client,
        )
    )


def _build_workflow_draft_service(tmp_path: Path) -> WorkflowDraftService:
    store = WorkflowDraftStore(db_path=tmp_path / "workflow-drafts.db")
    return WorkflowDraftService(store=store)


def _create_draft(
    service: WorkflowDraftService, *, draft_id: str = "draft-test"
) -> WorkflowDraftRecord:
    record = WorkflowDraftRecord(
        draft_id=draft_id,
        display_name="X 登录",
        task_name="agent_executor",
        plugin_name_candidate="x_login_test",
        success_threshold=3,
    )
    service._store.create_draft(record)
    created = service._store.get_draft(draft_id)
    assert created is not None
    return created


def _write_trace_file(
    traces_root: Path,
    *,
    task_id: str,
    run_id: str,
    target_label: str,
    attempt_number: int = 1,
    mtime: int | None = None,
) -> Path:
    path = traces_root / task_id / run_id / f"{target_label}.attempt-{attempt_number}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"record_type":"terminal","status":"completed"}\n', encoding="utf-8")
    if mtime is not None:
        path.touch()
        import os

        os.utime(path, (mtime, mtime))
    return path


def test_workflow_draft_failure_advice_is_exposed(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks-workflow-drafts-failure.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=Runner(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "task": "missing-task",
                    "display_name": "X 登录",
                    "payload": {"goal": "帮我登录 X"},
                    "targets": [{"device_id": 1, "cloud_id": 1}],
                },
            )
            assert create.status_code == 200
            task_id = str(create.json()["task_id"])

            assert _wait_status(client, task_id) == "failed"

            detail = client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200
            workflow = cast(dict[str, object], detail.json()["workflow_draft"])
            assert workflow["display_name"] == "X 登录"
            assert workflow["status"] == "needs_attention"
            assert workflow["next_action"] == "apply_suggestion"
            advice = cast(dict[str, object], workflow["latest_failure_advice"])
            assert advice["summary"]
            assert cast(list[str], advice["suggestions"])
            assert advice["suggested_prompt"]

            drafts = client.get("/api/tasks/drafts")
            assert drafts.status_code == 200
            assert any(item["draft_id"] == workflow["draft_id"] for item in drafts.json())
    finally:
        reset_task_controller_for_tests()


def test_workflow_draft_continue_and_distill_flow(tmp_path: Path, monkeypatch):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks-workflow-drafts-success.db"
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)

    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "plugins_dir", lambda: plugins_root)

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_build_agent_executor_runner(successful_runs=3),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "task": "agent_executor",
                    "display_name": "X 登录",
                    "payload": {
                        "goal": "用绑定账号登录 X 并进入首页",
                        "credentials_ref": '{"account":"demo","password":"secret"}',
                        "expected_state_ids": ["account"],
                        "allowed_actions": ["ui.click"],
                        "max_steps": 4,
                    },
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                },
            )
            assert create.status_code == 200
            created = create.json()
            task_id = str(created["task_id"])

            assert _wait_status(client, task_id, timeout_s=30.0) == "completed"

            detail = client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200
            workflow = cast(dict[str, object], detail.json()["workflow_draft"])
            assert workflow["display_name"] == "X 登录"
            assert workflow["success_count"] == 1
            assert workflow["remaining_successes"] == 2
            assert workflow["next_action"] == "continue_validation"
            draft_id = str(workflow["draft_id"])

            continue_resp = client.post(
                f"/api/tasks/drafts/{draft_id}/continue",
                json={"count": 2},
            )
            assert continue_resp.status_code == 200
            followups = continue_resp.json()
            assert len(followups) == 2
            assert all(item["workflow_draft"]["draft_id"] == draft_id for item in followups)

            for item in followups:
                assert _wait_status(client, str(item["task_id"]), timeout_s=30.0) == "completed"

            draft_detail = client.get(f"/api/tasks/drafts/{draft_id}")
            assert draft_detail.status_code == 200
            summary = draft_detail.json()
            assert summary["success_count"] == 3
            assert summary["can_distill"] is True
            assert summary["next_action"] == "distill"
            snapshot = controller._workflow_drafts.continuation_snapshot(draft_id)
            trace_context = cast(dict[str, object], snapshot["snapshot"]["trace_context"])
            assert trace_context["task_id"] == summary["latest_completed_task_id"]

            snapshot_http = client.get(f"/api/tasks/drafts/{draft_id}/snapshot")
            assert snapshot_http.status_code == 200
            snapshot_bundle = snapshot_http.json()
            assert snapshot_bundle["draft_id"] == draft_id
            identity = cast(dict[str, object], snapshot_bundle["snapshot"]["identity"])
            assert identity["app_id"] == "default"
            assert identity["credentials_ref_kind"] == "inline_json"
            assert identity["account"] == "demo"

            distill = client.post(f"/api/tasks/drafts/{draft_id}/distill", json={})
            assert distill.status_code == 200
            payload = distill.json()
            assert payload["ok"] is True
            assert Path(payload["manifest_path"]).exists()
            assert Path(payload["script_path"]).exists()
            assert Path(payload["report_path"]).exists()
            assert str(payload["output_dir"]).startswith(str(plugins_root))

            distilled_detail = client.get(f"/api/tasks/drafts/{draft_id}")
            assert distilled_detail.status_code == 200
            distilled_summary = distilled_detail.json()
            assert distilled_summary["status"] == "distilled"
            assert distilled_summary["can_distill"] is False
            assert distilled_summary["next_action"] == "review_distilled"
    finally:
        reset_task_controller_for_tests()


def test_workflow_draft_rejects_identity_mismatch(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks-workflow-drafts-mismatch.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=Runner(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "task": "agent_executor",
                    "display_name": "X 登录",
                    "payload": {"goal": "用绑定账号登录 X"},
                    "targets": [{"device_id": 1, "cloud_id": 1}],
                },
            )
            assert create.status_code == 200
            draft_id = str(create.json()["workflow_draft"]["draft_id"])

            mismatch_name = client.post(
                "/api/tasks/",
                json={
                    "task": "agent_executor",
                    "display_name": "Y 登录",
                    "draft_id": draft_id,
                    "payload": {"goal": "用绑定账号登录 Y"},
                    "targets": [{"device_id": 1, "cloud_id": 1}],
                },
            )
            assert mismatch_name.status_code == 400
            assert "display_name mismatch" in mismatch_name.json()["detail"]

            mismatch_task = client.post(
                "/api/tasks/",
                json={
                    "task": "missing-task",
                    "display_name": "X 登录",
                    "draft_id": draft_id,
                    "payload": {"goal": "执行别的任务"},
                    "targets": [{"device_id": 1, "cloud_id": 1}],
                },
            )
            assert mismatch_task.status_code == 400
            assert "task mismatch" in mismatch_task.json()["detail"]
    finally:
        reset_task_controller_for_tests()


def test_workflow_draft_cancel_and_cleanup_keep_state_consistent(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks-workflow-drafts-cleanup.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=Runner(),
        event_store=TaskEventStore(db_path=db_path),
    )

    try:
        created = controller.submit_with_retry(
            payload={"task": "agent_executor", "goal": "用绑定账号登录 X"},
            targets=[{"device_id": 1, "cloud_id": 1}],
            max_retries=0,
            retry_backoff_seconds=0,
            priority=50,
            run_at=None,
            display_name="X 登录",
        )
        workflow = cast(dict[str, object], controller.workflow_draft_summary_for_task(created))
        draft_id = str(workflow["draft_id"])

        assert controller.cancel_state(created.task_id) == "cancelled"

        cancelled_summary = cast(dict[str, object], controller.workflow_draft_summary(draft_id))
        assert cancelled_summary["cancelled_count"] == 1
        assert cancelled_summary["latest_terminal_task_id"] == created.task_id

        assert controller.cleanup_failed_tasks() == 1

        cleaned_summary = cast(dict[str, object], controller.workflow_draft_summary(draft_id))
        assert cleaned_summary["latest_terminal_task_id"] is None
        assert cleaned_summary["status"] == "collecting"

        controller.clear_all()
        assert controller.workflow_draft_summary(draft_id) is None
    finally:
        reset_task_controller_for_tests()


def test_workflow_draft_continuation_requires_success_snapshot(tmp_path: Path):
    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service)

    with pytest.raises(ValueError, match="no successful snapshot to replay"):
        service.continuation_snapshot("draft-test")


def test_workflow_draft_records_ambiguous_latest_success_without_trace_context(
    tmp_path: Path, monkeypatch
):
    traces_root = tmp_path / "traces"

    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "traces_dir", lambda: traces_root)

    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service)
    _write_trace_file(traces_root, task_id="task-1", run_id="run-b", target_label="target-b")
    _write_trace_file(traces_root, task_id="task-1", run_id="run-a", target_label="target-a")

    task_record = SimpleNamespace(
        task_id="task-1",
        status="completed",
        payload={"task": "agent_executor", "_workflow_draft_id": "draft-test", "goal": "登录 X"},
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
    )

    service.record_terminal(task_record=task_record, result={"ok": True})

    snapshot = service.continuation_snapshot("draft-test")["snapshot"]
    assert snapshot["trace_context"] is None
    assert snapshot["trace_context_count"] == 2
    assert snapshot["trace_context_ambiguous"] is True

    with pytest.raises(ValueError, match="multiple golden run traces found"):
        service.distill_draft("draft-test", force=True)


def test_workflow_draft_distill_falls_back_to_latest_unambiguous_success_when_snapshot_trace_missing(
    tmp_path: Path, monkeypatch
):
    traces_root = tmp_path / "traces"

    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "traces_dir", lambda: traces_root)

    service = _build_workflow_draft_service(tmp_path)
    record = _create_draft(service)
    record.success_count = 3
    record.latest_completed_task_id = "task-latest"
    record.successful_task_ids = ["task-oldest", "task-older", "task-latest"]
    record.last_success_snapshot = {
        "trace_context": {
            "task_id": "task-latest",
            "run_id": "missing-run",
            "target_label": "missing-target",
            "attempt_number": 1,
        },
        "trace_context_count": 1,
        "trace_context_ambiguous": False,
    }
    service._store.update_draft(record)

    _write_trace_file(traces_root, task_id="task-oldest", run_id="run-1", target_label="target-a")
    _write_trace_file(traces_root, task_id="task-older", run_id="run-2", target_label="target-b")

    resolved = service._resolve_distill_trace_context(
        cast(WorkflowDraftRecord, service._store.get_draft("draft-test"))
    )

    assert resolved is not None
    assert resolved.task_id == "task-older"
    assert resolved.run_id == "run-2"
    assert resolved.target_label == "target-b"


def test_list_trace_contexts_orders_equal_mtime_entries_deterministically(
    tmp_path: Path, monkeypatch
):
    traces_root = tmp_path / "traces"

    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "traces_dir", lambda: traces_root)

    _write_trace_file(
        traces_root,
        task_id="task-1",
        run_id="run-a",
        target_label="target-a",
        attempt_number=1,
        mtime=100,
    )
    _write_trace_file(
        traces_root,
        task_id="task-1",
        run_id="run-a",
        target_label="target-a",
        attempt_number=2,
        mtime=100,
    )
    _write_trace_file(
        traces_root,
        task_id="task-1",
        run_id="run-b",
        target_label="target-b",
        attempt_number=1,
        mtime=100,
    )

    contexts = workflow_drafts_module._list_trace_contexts("task-1")

    assert [(item.run_id, item.target_label, item.attempt_number) for item in contexts] == [
        ("run-b", "target-b", 1),
        ("run-a", "target-a", 2),
        ("run-a", "target-a", 1),
    ]


def test_golden_run_distillation_keeps_framework_owned_fields_out_of_manifest_inputs():
    manifest, script = GoldenRunDistiller()._build_draft(
        records=[
            {
                "chosen_action": "ui.input_text",
                "action_params": {
                    "device_ip": "192.168.1.214",
                    "cloud_index": 2,
                    "package": "com.twitter.android",
                    "app_id": "x",
                    "state_profile_id": "app_stage",
                    "text": "hello@example.com",
                },
                "observation": {
                    "modality": "native",
                    "data": {"package": "com.twitter.android"},
                },
            }
        ],
        terminal_record={"message": "done"},
        plugin_name="x_distilled_test",
        display_name="X Distilled Test",
        category="AI Drafts",
    )

    input_names = {item.name for item in manifest.inputs}
    first_step = cast(ActionStep, script.steps[0])

    assert input_names == {"text"}
    assert first_step.params["device_ip"] == "192.168.1.214"
    assert first_step.params["package"] == "com.twitter.android"
    assert first_step.params["app_id"] == "x"
    assert first_step.params["state_profile_id"] == "app_stage"


def test_workflow_draft_distill_preserves_account_picker_for_login_flow(
    tmp_path: Path, monkeypatch
):
    traces_root = tmp_path / "traces"
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)

    import core.model_trace_store as model_trace_store_module
    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "plugins_dir", lambda: plugins_root)
    monkeypatch.setattr(workflow_drafts_module, "traces_dir", lambda: traces_root)
    monkeypatch.setattr(model_trace_store_module, "traces_dir", lambda: traces_root)
    monkeypatch.setattr("core.golden_run_distillation.app_from_package", lambda package: "")

    service = _build_workflow_draft_service(tmp_path)
    record = _create_draft(service)
    record.success_count = 3
    record.latest_completed_task_id = "task-login"
    record.successful_task_ids = ["task-login"]
    record.last_success_snapshot = {
        "identity": {
            "app_id": "x",
            "package": "com.twitter.android",
            "credentials_ref_kind": "missing",
            "account": "demo@example.com",
            "account_source": "inline_payload",
        },
        "trace_context": {
            "task_id": "task-login",
            "run_id": "run-1",
            "target_label": "Unit #1-1",
            "attempt_number": 1,
        },
        "trace_context_count": 1,
        "trace_context_ambiguous": False,
    }
    service._store.update_draft(record)

    trace_store = ModelTraceStore(root_dir=traces_root)
    context = ModelTraceContext(
        task_id="task-login",
        run_id="run-1",
        target_label="Unit #1-1",
        attempt_number=1,
    )
    trace_store.append_record(
        context,
        {
            "sequence": 1,
            "step_index": 1,
            "record_type": "step",
            "status": "action_executed",
            "chosen_action": "ui.input_text",
            "action_params": {"text": "demo@example.com"},
            "action_result": {"ok": True, "data": {"typed": True}},
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["account"],
                "data": {
                    "package": "com.twitter.android",
                    "state": {"state_id": "account"},
                },
            },
        },
    )
    trace_store.append_record(
        context,
        {
            "sequence": 2,
            "step_index": 2,
            "record_type": "step",
            "status": "action_executed",
            "chosen_action": "ui.input_text",
            "action_params": {"text": "super-secret"},
            "action_result": {"ok": True, "data": {"typed": True}},
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["password"],
                "data": {
                    "package": "com.twitter.android",
                    "state": {"state_id": "password"},
                },
            },
        },
    )
    trace_store.append_record(
        context,
        {
            "sequence": 3,
            "step_index": 3,
            "record_type": "step",
            "status": "action_executed",
            "chosen_action": "ui.input_text",
            "action_params": {"text": "123456"},
            "action_result": {"ok": True, "data": {"typed": True}},
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["two_factor"],
                "data": {
                    "package": "com.twitter.android",
                    "state": {"state_id": "two_factor"},
                },
            },
        },
    )
    trace_store.append_record(
        context,
        {
            "sequence": 4,
            "step_index": 4,
            "record_type": "terminal",
            "status": "completed",
            "message": "done",
        },
    )

    result = service.distill_draft("draft-test", force=True)

    manifest = yaml.safe_load(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    script = yaml.safe_load(Path(result["script_path"]).read_text(encoding="utf-8"))

    assert {item["name"] for item in manifest["inputs"]} == {"credentials_ref", "app_id"}
    assert next(item for item in manifest["inputs"] if item["name"] == "app_id")["default"] == "x"

    steps = script["steps"]
    assert steps[0]["action"] == "credentials.load"
    assert steps[0]["params"]["credentials_ref"] == "${payload.credentials_ref:-}"
    assert steps[0]["params"]["app_id"] == "${payload.app_id:-x}"
    assert steps[1]["params"]["text"] == "${vars.credential.account}"
    assert steps[2]["params"]["text"] == "${vars.credential.password}"
    assert steps[3]["params"]["text"] == "${vars.credential.twofa_code:-}"


def test_golden_run_distillation_merges_stage_patterns_into_app_config(tmp_path: Path, monkeypatch):
    app_config = tmp_path / "x.yaml"
    app_config.write_text(
        yaml.safe_dump(
            {
                "version": "v1",
                "package_name": "com.twitter.android",
                "stage_patterns": {},
                "states": [],
                "selectors": {},
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "core.golden_run_distillation.app_from_package", lambda package: "x" if package else ""
    )
    monkeypatch.setattr("core.golden_run_distillation.app_config_path", lambda app_id: app_config)
    monkeypatch.setattr(
        "core.golden_run_distillation.load_app_config_document",
        lambda app_id: yaml.safe_load(app_config.read_text(encoding="utf-8")),
    )
    monkeypatch.setattr(
        "core.app_config.AppConfigManager.load_app_config",
        lambda app_id: yaml.safe_load(app_config.read_text(encoding="utf-8")),
    )
    monkeypatch.setattr(
        "core.app_config.AppConfigManager.write_app_config",
        lambda app_id, document: (
            app_config.write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            or app_config
        ),
    )
    monkeypatch.setattr(
        "core.app_config_writer._learned_ids_path",
        lambda: tmp_path / "learned_ids.json",
    )

    distiller = GoldenRunDistiller()
    distiller._merge_selectors_to_app_config(
        records=[
            {
                "record_type": "step",
                "observation": {
                    "data": {
                        "package": "com.twitter.android",
                        "state": {"state_id": "home"},
                    }
                },
                "action_params": {},
                "action_result": {"data": {"resource_id": "com.twitter.android:id/tabs"}},
            },
            {
                "record_type": "step",
                "observation": {
                    "data": {
                        "package": "com.twitter.android",
                        "state": {"state_id": "home"},
                    }
                },
                "action_params": {"resource_id": "com.twitter.android:id/composer_write"},
                "action_result": {"data": {}},
            },
        ],
        script=WorkflowScript(version="v1", workflow="x_distilled_test", steps=[]),
    )

    document = yaml.safe_load(app_config.read_text(encoding="utf-8"))
    assert document["stage_patterns"]["home"]["resource_ids"] == [
        "com.twitter.android:id/tabs",
        "com.twitter.android:id/composer_write",
    ]


def test_golden_run_distillation_reports_human_guided_steps_without_blocking_distill(
    tmp_path: Path, monkeypatch
):
    trace_store = ModelTraceStore(root_dir=tmp_path / "traces")
    context = ModelTraceContext(
        task_id="task-1",
        run_id="run-1",
        target_label="Unit #1-1",
        attempt_number=1,
    )
    trace_store.append_record(
        context,
        {
            "sequence": 1,
            "step_index": 1,
            "record_type": "step",
            "status": "action_executed",
            "chosen_action": "ui.click",
            "action_params": {"text": "登录"},
            "action_result": {"ok": True, "data": {"clicked": True}},
            "observation": {
                "ok": True,
                "modality": "structured_state",
                "observed_state_ids": ["login"],
                "data": {"package": "com.twitter.android", "state": {"state_id": "login"}},
            },
        },
    )
    trace_store.append_record(
        context,
        {
            "sequence": 2,
            "step_index": 2,
            "record_type": "step",
            "status": "action_executed",
            "source": "human",
            "human_guided": True,
            "action_name": "ui.click",
            "action_params": {"nx": 500, "ny": 500},
            "action_result": {"ok": True, "data": {"nx": 500, "ny": 500}},
        },
    )
    trace_store.append_record(
        context,
        {
            "sequence": 3,
            "step_index": 2,
            "record_type": "terminal",
            "status": "completed",
            "message": "done",
        },
    )
    monkeypatch.setattr("core.golden_run_distillation.app_from_package", lambda package: "")

    draft = GoldenRunDistiller(trace_store=trace_store).distill(
        context=context,
        output_dir=tmp_path / "draft",
        plugin_name="x_distilled_test",
        display_name="X Distilled Test",
    )

    report = yaml.safe_load(draft.report_path.read_text(encoding="utf-8"))
    assert report["source_counts"] == {"ai": 1, "human": 1}
    assert report["distilled_step_count"] == 1
    assert report["human_guided_steps"] == [
        {
            "sequence": 2,
            "step_index": 2,
            "action": "ui.click",
            "status": "action_executed",
            "source": "human",
            "human_guided": True,
            "included_in_script": False,
        }
    ]
    first_step = cast(ActionStep, draft.script.steps[0])
    assert first_step.action == "ui.click"


def test_golden_run_distillation_promotes_agent_hint_candidate_when_missing(
    tmp_path: Path, monkeypatch
):
    app_config = tmp_path / "x.yaml"
    app_config.write_text(
        yaml.safe_dump(
            {
                "version": "v1",
                "package_name": "com.twitter.android",
                "selectors": {},
                "states": [],
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "core.golden_run_distillation.app_from_package", lambda package: "x" if package else ""
    )
    monkeypatch.setattr("core.golden_run_distillation.app_config_path", lambda app_id: app_config)
    monkeypatch.setattr(
        "core.golden_run_distillation.load_app_config_document",
        lambda app_id: yaml.safe_load(app_config.read_text(encoding="utf-8")),
    )

    result = GoldenRunDistiller()._merge_agent_hint_candidates_to_app_config(
        [
            {
                "observation": {
                    "data": {
                        "package": "com.twitter.android",
                    }
                },
                "planner": {
                    "planner_artifact": {
                        "advanced_prompt": "首页优先检查是否有升级弹窗，有则先关闭。",
                    }
                },
            }
        ]
    )

    document = yaml.safe_load(app_config.read_text(encoding="utf-8"))
    assert document["agent_hint_candidates"] == ["首页优先检查是否有升级弹窗，有则先关闭。"]
    assert document["agent_hint"] == "首页优先检查是否有升级弹窗，有则先关闭。"
    assert result["promoted_agent_hint"] == "首页优先检查是否有升级弹窗，有则先关闭。"


def test_ui_wait_until_infers_app_stage_from_injected_patterns(monkeypatch):
    import engine.actions.ui_state_actions as ui_state_actions

    register_defaults()
    captured: dict[str, object] = {}

    class FakeAdapter:
        def __init__(self, state_profile_id: str, *, action_params=None, binding_id=None):
            captured["state_profile_id"] = state_profile_id
            captured["binding_id"] = binding_id
            captured["action_params"] = dict(action_params or {})

        def wait_until(
            self, context: ExecutionContext, *, expected_state_ids, timeout_ms, interval_ms
        ):
            _ = (context, expected_state_ids, timeout_ms, interval_ms)

            class _Result:
                def to_action_result(self):
                    return ActionResult(ok=True, code="ok", data={"state": {"state_id": "home"}})

            return _Result()

    monkeypatch.setattr(ui_state_actions, "NativeUIStateAdapter", FakeAdapter)

    ctx = ExecutionContext(
        payload={"device_ip": "192.168.1.214"},
        session={
            "defaults": {
                "package": "com.twitter.android",
                "_app_stage_patterns": {"home": {"text_markers": ["For you"]}},
            }
        },
    )
    result = resolve_action("ui.wait_until")(
        {"platform": "native", "expected_state_ids": ["home"]},
        ctx,
    )

    assert result.ok is True
    assert captured["state_profile_id"] == "app_stage"
    action_params = cast(dict[str, object], captured["action_params"])
    assert action_params["package"] == "com.twitter.android"
    assert action_params["stage_patterns"] == {"home": {"text_markers": ["For you"]}}


@pytest.mark.parametrize(
    ("plugin_dir", "redundant_actions"),
    [
        (
            "x_home_interaction",
            {
                "app.open": {"package"},
                "app.stop": {"package"},
                "core.extract_timeline_candidates": {"app_id"},
                "ui.wait_until": {"app_id", "app", "package", "state_profile_id"},
            },
        ),
        (
            "x_login",
            {
                "app.ensure_running": {"app_id"},
                "app.grant_permissions": {"app_id"},
                "core.detect_login_stage": {"app_id"},
                "core.wait_login_stage": {"app_id"},
            },
        ),
        (
            "x_follow_followers",
            {
                "app.ensure_running": {"app_id"},
                "core.follow_visible_targets": {"app_id"},
                "core.load_ui_scheme": {"app_id"},
            },
        ),
        (
            "x_nurture",
            {
                "app.ensure_running": {"app_id"},
                "core.extract_timeline_candidates": {"app_id"},
                "core.load_ui_scheme": {"app_id"},
            },
        ),
        (
            "x_quote_intercept",
            {
                "app.ensure_running": {"app_id"},
                "core.extract_search_candidates": {"app_id"},
                "core.load_ui_scheme": {"app_id"},
                "ui.click_selector_or_tap": {"app_id"},
                "ui.input_text_with_shell_fallback": {"app_id"},
            },
        ),
        (
            "x_clone_profile",
            {
                "app.ensure_running": {"app_id"},
                "core.load_ui_scheme": {"app_id"},
                "ui.click_selector_or_tap": {"app_id"},
                "ui.input_text_with_shell_fallback": {"app_id"},
            },
        ),
        (
            "x_scrape_blogger",
            {
                "app.ensure_running": {"app_id"},
                "core.collect_blogger_candidates": {"app_id"},
                "core.load_ui_scheme": {"app_id"},
            },
        ),
        (
            "x_reply_dm",
            {
                "app.ensure_running": {"app_id"},
                "core.load_ui_scheme": {"app_id"},
                "ui.input_text_with_shell_fallback": {"app_id"},
            },
        ),
    ],
)
def test_x_plugins_keep_manifest_app_id_but_drop_redundant_step_wiring(
    plugin_dir: str,
    redundant_actions: dict[str, set[str]],
):
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / "plugins" / plugin_dir / "manifest.yaml"
    script_path = repo_root / "plugins" / plugin_dir / "script.yaml"

    manifest = cast(dict[str, object], yaml.safe_load(manifest_path.read_text(encoding="utf-8")))
    script = cast(dict[str, object], yaml.safe_load(script_path.read_text(encoding="utf-8")))

    inputs = cast(list[dict[str, object]], manifest.get("inputs", []))
    assert any(str(item.get("name") or "") == "app_id" for item in inputs)

    steps = cast(list[dict[str, object]], script.get("steps", []))
    for step in steps:
        action = str(step.get("action") or "")
        disallowed_keys = redundant_actions.get(action)
        if not disallowed_keys:
            continue
        params = cast(dict[str, object], step.get("params") or {})
        assert disallowed_keys.isdisjoint(params.keys()), f"{plugin_dir}:{action}:{params}"
