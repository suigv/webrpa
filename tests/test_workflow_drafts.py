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
from core.app_config_candidate_service import AppConfigCandidateService, AppConfigCandidateStore
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
from core.workflow_draft_store import (
    WorkflowDraftRecord,
    WorkflowDraftStore,
    WorkflowRunAssetRecord,
)
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
    distilled_root = tmp_path / "distilled_plugins"
    distilled_root.mkdir(parents=True, exist_ok=True)

    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "distilled_plugins_dir", lambda: distilled_root)

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
            assert str(payload["output_dir"]).startswith(str(distilled_root))

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

    with pytest.raises(ValueError, match="no replayable snapshot to continue"):
        service.continuation_snapshot("draft-test")


def test_workflow_draft_completed_empty_dm_run_is_retained_but_not_counted(tmp_path: Path):
    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service)

    task_record = SimpleNamespace(
        task_id="task-empty-dm",
        status="completed",
        payload={
            "task": "agent_executor",
            "_workflow_draft_id": "draft-test",
            "goal": "检查私信并自动回复新消息",
            "app_id": "x",
            "branch_id": "volc",
        },
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
    )

    payload = service.record_terminal(
        task_record=task_record,
        result={
            "targets": [
                {
                    "result": {
                        "message": "已进入私信/聊天页面，当前收件箱为空，未发现新消息，因此无需调用AI接口回复。",
                        "history": [
                            {
                                "action": "ui.click",
                                "observation": {"state": {"state_id": "dm_inbox"}},
                            }
                        ],
                    }
                }
            ]
        },
    )

    summary = service.summary("draft-test")
    assert summary is not None
    assert summary["success_count"] == 0
    assert summary["latest_completed_task_id"] == "task-empty-dm"
    assert summary["can_continue"] is True
    assert summary["last_success_snapshot_available"] is False
    assert summary["last_replayable_snapshot_available"] is True
    assert summary["latest_run_asset"]["distill_reason"] == "empty_inbox"
    assert "未计入蒸馏样本" in str(payload["message"])

    assets = service._store.list_run_assets(draft_id="draft-test")
    assert len(assets) == 1
    assert assets[0].distill_decision == "rejected"
    assert assets[0].value_level == "replayable"

    replay = service.continuation_snapshot("draft-test")
    assert replay["snapshot"]["payload"]["goal"] == "检查私信并自动回复新消息"


def test_workflow_draft_failed_useful_trace_is_still_editable(tmp_path: Path):
    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service)

    task_record = SimpleNamespace(
        task_id="task-follow-failed",
        status="failed",
        payload={
            "task": "agent_executor",
            "_workflow_draft_id": "draft-test",
            "goal": "进入通知页面如果有新的关注就回关没有则返回主页",
            "app_id": "x",
        },
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
        error="gpt executor exhausted configured step budget",
    )

    service.record_terminal(
        task_record=task_record,
        result={
            "message": "gpt executor exhausted configured step budget",
            "targets": [
                {
                    "result": {
                        "message": "gpt executor exhausted configured step budget",
                        "history": [
                            {
                                "action": "ui.click",
                                "result": {"ok": True},
                                "observation": {"state": {"state_id": "notifications"}},
                            },
                            {
                                "action": "ui.click",
                                "result": {"ok": True},
                                "observation": {"state": {"state_id": "home"}},
                            },
                        ],
                    }
                }
            ],
        },
    )

    summary = service.summary("draft-test")
    assert summary is not None
    assert summary["failure_count"] == 1
    assert summary["status"] == "needs_attention"
    assert summary["latest_terminal_task_id"] == "task-follow-failed"
    assert summary["last_replayable_snapshot_available"] is True
    assert summary["can_continue"] is True
    assert summary["latest_run_asset"]["completion_status"] == "failed"
    assert summary["latest_run_asset"]["value_level"] == "useful_trace"
    assert summary["latest_run_asset"]["value_profile"]["qualification"] == "useful_trace"
    assert summary["exit"]["action"] == "apply_suggestion"
    assert summary["distill_assessment"]["can_distill_now"] is False

    replay = service.continuation_snapshot("draft-test")
    assert replay["snapshot"]["payload"]["goal"] == "进入通知页面如果有新的关注就回关没有则返回主页"


def test_workflow_draft_completed_login_run_counts_for_distill(tmp_path: Path):
    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service)

    task_record = SimpleNamespace(
        task_id="task-login-success",
        status="completed",
        payload={
            "task": "agent_executor",
            "_workflow_draft_id": "draft-test",
            "goal": "用绑定账号登录 X 并进入首页",
            "app_id": "x",
        },
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
    )

    service.record_terminal(
        task_record=task_record,
        result={
            "message": "登录成功",
            "history": [
                {
                    "action": "ui.click",
                    "observation": {"state": {"state_id": "home"}},
                }
            ],
        },
    )

    summary = service.summary("draft-test")
    assert summary is not None
    assert summary["success_count"] == 1
    assert summary["last_success_snapshot_available"] is True
    assert summary["latest_run_asset"]["distill_decision"] == "accepted"
    assert summary["latest_run_asset"]["distill_reason"] == "fulfilled_main_path"
    assert summary["latest_run_asset"]["value_profile"]["qualification"] == "distillable"
    assert summary["exit"]["action"] == "continue_validation"


def test_workflow_draft_summary_snapshot_and_distill_expose_declarative_binding(
    tmp_path: Path, monkeypatch
):
    distilled_root = tmp_path / "distilled_plugins"
    distilled_root.mkdir(parents=True, exist_ok=True)

    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "distilled_plugins_dir", lambda: distilled_root)

    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service)

    task_record = SimpleNamespace(
        task_id="task-login-declarative",
        status="completed",
        payload={
            "task": "agent_executor",
            "_workflow_draft_id": "draft-test",
            "goal": "用绑定账号登录 X 并进入首页",
            "app_id": "x",
            "_planner_declarative_summary": "X 登录（login）：完成登录；阶段：准备登录流程 -> 判断登录状态 -> 收尾完成",
            "_planner_declarative_scripts": [
                {
                    "name": "x_login_decl",
                    "title": "X 登录",
                    "goal": "完成登录并进入首页",
                    "role": "login",
                    "stages": [
                        {
                            "name": "prepare_auth_flow",
                            "title": "准备登录流程",
                            "kind": "setup",
                            "goal": "进入可尝试登录的准备态",
                        },
                        {
                            "name": "check_auth_state",
                            "title": "判断登录状态",
                            "kind": "decision",
                            "goal": "明确当前登录分支",
                        },
                        {
                            "name": "finalize_auth_flow",
                            "title": "收尾完成",
                            "kind": "finalize",
                            "goal": "确认已经进入首页",
                        },
                    ],
                }
            ],
        },
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
    )

    terminal_stage = {
        "script_name": "x_login_decl",
        "script_title": "X 登录",
        "script_role": "login",
        "stage_name": "finalize_auth_flow",
        "stage_title": "收尾完成",
        "stage_kind": "finalize",
        "stage_goal": "确认已经进入首页",
        "stage_index": 2,
        "stage_count": 3,
        "step_index": 2,
        "observed_state_ids": ["home"],
    }

    service.record_terminal(
        task_record=task_record,
        result={
            "message": "登录成功",
            "current_declarative_stage": terminal_stage,
            "history": [
                {
                    "action": "ui.click",
                    "observation": {"state": {"state_id": "home"}},
                }
            ],
        },
    )

    summary = service.summary("draft-test")
    assert summary is not None
    assert summary["declarative_binding"] == {
        "summary": "X 登录（login）：完成登录；阶段：准备登录流程 -> 判断登录状态 -> 收尾完成",
        "script_count": 1,
        "script_name": "x_login_decl",
        "script_title": "X 登录",
        "current_stage": terminal_stage,
    }
    latest_run_asset = cast(dict[str, object], summary["latest_run_asset"])
    assert cast(dict[str, object], latest_run_asset["declarative_binding"])["current_stage"] == (
        terminal_stage
    )

    snapshot_bundle = service.continuation_snapshot("draft-test")
    snapshot = cast(dict[str, object], snapshot_bundle["snapshot"])
    assert cast(dict[str, object], snapshot["declarative_binding"])["current_stage"] == (
        terminal_stage
    )

    class _FakeDistiller:
        def distill(self, **kwargs):
            output_dir = Path(cast(str, kwargs["output_dir"]))
            output_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = output_dir / "manifest.yaml"
            script_path = output_dir / "script.yaml"
            report_path = output_dir / "report.json"
            manifest_path.write_text("name: fake\n", encoding="utf-8")
            script_path.write_text("steps: []\n", encoding="utf-8")
            report_path.write_text("{}\n", encoding="utf-8")
            return SimpleNamespace(
                manifest_path=manifest_path,
                script_path=script_path,
                report_path=report_path,
            )

    monkeypatch.setattr(workflow_drafts_module, "GoldenRunDistiller", _FakeDistiller)
    monkeypatch.setattr(
        service,
        "_resolve_distill_trace_context",
        lambda record: ModelTraceContext(
            task_id="task-login-declarative",
            run_id="run-1",
            target_label="Unit #7-2",
            attempt_number=1,
        ),
    )

    distilled = service.distill_draft("draft-test", force=True)
    assert distilled["ok"] is True
    assert distilled["declarative_binding"] == summary["declarative_binding"]


def test_workflow_draft_memory_summary_exposes_reuse_priority(tmp_path: Path):
    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service, draft_id="draft-memory")
    service._store.upsert_run_asset(
        WorkflowRunAssetRecord(
            asset_id="run-memory-1",
            draft_id="draft-memory",
            task_id="task-memory-1",
            app_id="x",
            branch_id="volc",
            objective="reply_dm",
            completion_status="completed",
            business_outcome="empty",
            distill_decision="rejected",
            distill_reason="empty_inbox",
            value_level="replayable",
            retained_value=["draft_memory"],
            learned_assets={"observed_state_ids": ["dm_inbox"], "entry_actions": ["ui.click"]},
            terminal_message="未发现新消息",
        )
    )

    memory = service.summarize_recent_run_assets(app_id="x", objective="reply_dm", branch_id="volc")

    assert memory["available"] is True
    assert memory["reuse_priority"] == "continue_trace"
    assert memory["recommended_action"] == "continue_from_memory"
    assert memory["qualification"] == "replayable"
    assert memory["distill_assessment"]["can_distill_now"] is False


def test_workflow_draft_records_output_profile_for_ai_channel_and_human_runs(tmp_path: Path):
    service = _build_workflow_draft_service(tmp_path)
    _create_draft(service, draft_id="draft-output-profile")

    ai_task = SimpleNamespace(
        task_id="task-ai",
        status="completed",
        takeover_owner=None,
        payload={"task": "agent_executor", "_workflow_draft_id": "draft-output-profile", "goal": "登录 X"},
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
    )
    service.record_terminal(
        task_record=ai_task,
        result={
            "message": "AI solved challenge",
            "history": [
                {"action": "ai.solve_captcha", "observation": {"state": {"state_id": "captcha"}}}
            ],
        },
    )

    channel_task = SimpleNamespace(
        task_id="task-channel",
        status="completed",
        takeover_owner=None,
        payload={"task": "agent_executor", "_workflow_draft_id": "draft-output-profile", "goal": "登录 X"},
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
    )
    service.record_terminal(
        task_record=channel_task,
        result={
            "message": "Email code received",
            "history": [
                {
                    "action": "channel.read_email_code",
                    "observation": {"state": {"state_id": "verification"}},
                }
            ],
        },
    )

    human_task = SimpleNamespace(
        task_id="task-human",
        status="completed",
        takeover_owner="operator-1",
        payload={"task": "agent_executor", "_workflow_draft_id": "draft-output-profile", "goal": "登录 X"},
        devices=[7],
        targets=[{"device_id": 7, "cloud_id": 2}],
        max_retries=0,
        retry_backoff_seconds=2,
        priority=50,
    )
    payload = service.record_terminal(
        task_record=human_task,
        result={
            "message": "Need operator completion",
            "history": [
                {"action": "ui.input_text", "observation": {"state": {"state_id": "two_factor"}}}
            ],
        },
    )

    assert payload is not None
    summary = service.summary("draft-output-profile")
    assert summary is not None
    latest_run_asset = cast(dict[str, object], summary["latest_run_asset"])
    output_profile = cast(dict[str, object], latest_run_asset["learned_assets"])["output_profile"]
    assert output_profile["output_type"] == "human_assisted"
    assert output_profile["used_human_takeover"] is True

    assets = service._store.list_run_assets(limit=10, draft_id="draft-output-profile")
    output_types = [
        cast(dict[str, object], asset.learned_assets["output_profile"])["output_type"]
        for asset in assets
    ]
    assert output_types[:3] == ["human_assisted", "yaml_with_channel", "yaml_with_ai"]


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
    assert manifest.distill_mode.output_type == "pure_yaml"
    assert manifest.distill_mode.requires_ai_runtime is False
    assert manifest.distill_mode.requires_channel_runtime is False
    assert first_step.params["device_ip"] == "192.168.1.214"
    assert first_step.params["package"] == "com.twitter.android"
    assert first_step.params["app_id"] == "x"
    assert first_step.params["state_profile_id"] == "app_stage"


def test_golden_run_distillation_marks_ai_and_channel_output_modes():
    distiller = GoldenRunDistiller()

    ai_manifest, _script = distiller._build_draft(
        records=[
            {
                "chosen_action": "ai.solve_captcha",
                "action_params": {"captcha_type": "image"},
                "observation": {"modality": "vision", "data": {}},
            }
        ],
        terminal_record={"message": "done"},
        plugin_name="ai_distilled_test",
        display_name="AI Distilled Test",
        category="AI Drafts",
    )
    assert ai_manifest.distill_mode.output_type == "yaml_with_ai"
    assert ai_manifest.distill_mode.requires_ai_runtime is True
    assert ai_manifest.distill_mode.requires_channel_runtime is False

    channel_manifest, _script = distiller._build_draft(
        records=[
            {
                "chosen_action": "channel.read_email_code",
                "action_params": {"account_ref": "${payload.credentials_ref}"},
                "observation": {"modality": "native", "data": {"state": "verification"}},
            }
        ],
        terminal_record={"message": "done"},
        plugin_name="channel_distilled_test",
        display_name="Channel Distilled Test",
        category="AI Drafts",
    )
    assert channel_manifest.distill_mode.output_type == "yaml_with_channel"
    assert channel_manifest.distill_mode.requires_ai_runtime is False
    assert channel_manifest.distill_mode.requires_channel_runtime is True


def test_workflow_draft_distill_preserves_account_picker_for_login_flow(
    tmp_path: Path, monkeypatch
):
    traces_root = tmp_path / "traces"
    distilled_root = tmp_path / "distilled_plugins"
    distilled_root.mkdir(parents=True, exist_ok=True)

    import core.model_trace_store as model_trace_store_module
    import core.workflow_drafts as workflow_drafts_module

    monkeypatch.setattr(workflow_drafts_module, "distilled_plugins_dir", lambda: distilled_root)
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


def test_golden_run_distillation_collects_stage_patterns_as_review_candidates(
    tmp_path: Path, monkeypatch
):
    candidate_service = AppConfigCandidateService(
        store=AppConfigCandidateStore(db_path=tmp_path / "app-config-candidates.db")
    )
    monkeypatch.setattr(
        "core.golden_run_distillation.app_from_package", lambda package: "x" if package else ""
    )
    monkeypatch.setattr(
        "core.golden_run_distillation.get_app_config_candidate_service",
        lambda: candidate_service,
    )

    distiller = GoldenRunDistiller()
    result = distiller._merge_selectors_to_app_config(
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
        context=ModelTraceContext(
            task_id="task-distill-1",
            run_id="run-1",
            target_label="Unit #1-1",
            attempt_number=1,
        ),
        snapshot_identity={"app_id": "x"},
        draft_id="draft-1",
    )

    assert result == {"app_id": "x", "recorded": 1}
    bundle = candidate_service.list_candidates(app_id="x", draft_id="draft-1")
    assert len(bundle["candidates"]) == 1
    candidate = bundle["candidates"][0]
    assert candidate["kind"] == "stage_pattern"
    assert candidate["value"]["state_id"] == "home"
    assert candidate["value"]["resource_ids"] == [
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


def test_golden_run_distillation_records_agent_hint_candidate_for_review(
    tmp_path: Path, monkeypatch
):
    candidate_service = AppConfigCandidateService(
        store=AppConfigCandidateStore(db_path=tmp_path / "app-config-candidates.db")
    )
    monkeypatch.setattr(
        "core.golden_run_distillation.app_from_package", lambda package: "x" if package else ""
    )
    monkeypatch.setattr(
        "core.golden_run_distillation.get_app_config_candidate_service",
        lambda: candidate_service,
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
        ],
        context=ModelTraceContext(
            task_id="task-hint-1",
            run_id="run-1",
            target_label="Unit #1-1",
            attempt_number=1,
        ),
        snapshot_identity={"app_id": "x"},
        draft_id="draft-hint-1",
    )

    assert result == {
        "app_id": "x",
        "candidate_count": 1,
        "promoted_agent_hint": None,
    }
    bundle = candidate_service.list_candidates(app_id="x", draft_id="draft-hint-1")
    assert len(bundle["candidates"]) == 1
    assert bundle["candidates"][0]["kind"] == "agent_hint"
    assert bundle["candidates"][0]["value"]["text"] == "首页优先检查是否有升级弹窗，有则先关闭。"


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


@pytest.mark.parametrize(
    "plugin_dir",
    [
        "x_clone_profile",
        "x_follow_followers",
        "x_home_interaction",
        "x_login",
        "x_nurture",
        "x_quote_intercept",
        "x_reply_dm",
        "x_scrape_blogger",
    ],
)
def test_x_plugins_do_not_force_business_branch_defaults(plugin_dir: str):
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = repo_root / "plugins" / plugin_dir / "manifest.yaml"
    script_path = repo_root / "plugins" / plugin_dir / "script.yaml"

    manifest = cast(dict[str, object], yaml.safe_load(manifest_path.read_text(encoding="utf-8")))
    script = cast(dict[str, object], yaml.safe_load(script_path.read_text(encoding="utf-8")))

    inputs = cast(list[dict[str, object]], manifest.get("inputs", []))
    branch_input = next(
        (item for item in inputs if str(item.get("name") or "") == "branch_id"),
        None,
    )
    assert branch_input is not None
    assert branch_input.get("default") == ""

    if plugin_dir != "x_login":
        options = cast(list[dict[str, object]], branch_input.get("options") or [])
        assert any(str(item.get("value") or "") == "" for item in options)

    steps = cast(list[dict[str, object]], script.get("steps", []))
    for step in steps:
        params = cast(dict[str, object], step.get("params") or {})
        if "branch_id" in params:
            assert params["branch_id"] == "${payload.branch_id:-}"

    if plugin_dir == "x_scrape_blogger":
        keyword_input = next(item for item in inputs if str(item.get("name") or "") == "keyword")
        assert keyword_input.get("required") is False
