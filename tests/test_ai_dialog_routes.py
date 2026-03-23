from __future__ import annotations

from fastapi.testclient import TestClient

from api.server import app
from core.task_control import (
    TaskController,
    override_task_controller_for_tests,
    reset_task_controller_for_tests,
)
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore
from core.workflow_draft_store import WorkflowDraftRecord, WorkflowDraftStore


def test_ai_dialog_planner_returns_resolved_defaults(monkeypatch):
    reset_task_controller_for_tests()
    monkeypatch.setattr(
        "core.ai_dialog_service.AIDialogService._plan_with_llm",
        lambda self, **kwargs: {"display_name": "X 登录"} if kwargs else {},
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ai_dialog/planner",
                json={
                    "goal": "帮我登录 X",
                    "app_id": "x",
                    "selected_account": "demo@example.com",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "X 登录"
        assert data["source"] == "ai_dialog"
        assert data["resolved_app"]["app_id"] == "x"
        assert data["account"]["strategy"] == "selected"
        assert data["resolved_payload"]["_workflow_source"] == "ai_dialog"
        assert data["resolved_payload"]["expected_state_ids"] == ["home", "login"]
        assert "allowed_actions" in data["resolved_payload"]
    finally:
        reset_task_controller_for_tests()


def test_ai_dialog_history_filters_non_ai_dialog_drafts(tmp_path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks-ai-dialog-history.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    store = WorkflowDraftStore(db_path=db_path)
    store.create_draft(
        WorkflowDraftRecord(
            draft_id="draft_ai",
            display_name="X 登录",
            task_name="agent_executor",
            plugin_name_candidate="x_login",
            source="ai_dialog",
            latest_completed_task_id="task-ai",
            last_success_snapshot={
                "identity": {"app_id": "x", "account": "demo@example.com"},
            },
        )
    )
    store.create_draft(
        WorkflowDraftRecord(
            draft_id="draft_generic",
            display_name="Generic",
            task_name="agent_executor",
            plugin_name_candidate="generic_flow",
            source="generic",
        )
    )

    try:
        with TestClient(app) as client:
            response = client.get("/api/ai_dialog/history")

        assert response.status_code == 200
        data = response.json()
        assert [item["draft_id"] for item in data] == ["draft_ai"]
        assert data[0]["app_id"] == "x"
        assert data[0]["account"] == "demo@example.com"
        assert data[0]["can_replay"] is True
        assert data[0]["can_edit"] is True
    finally:
        reset_task_controller_for_tests()
