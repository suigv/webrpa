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
        assert data["account"]["execution_hint"] == "执行方式：使用已选账号 demo@example.com。"
        assert data["account"]["requires_account"] is True
        assert data["account"]["can_execute"] is True
        assert data["resolved_payload"]["_workflow_source"] == "ai_dialog"
        assert data["resolved_payload"]["expected_state_ids"] == ["home", "login"]
        assert "allowed_actions" in data["resolved_payload"]
    finally:
        reset_task_controller_for_tests()


def test_ai_dialog_planner_marks_pool_checkout_for_login_goal(monkeypatch):
    reset_task_controller_for_tests()
    monkeypatch.setattr(
        "core.ai_dialog_service.list_accounts",
        lambda app_id=None: [
            {"account": "pool-1@example.com", "status": "ready", "app_id": app_id or "x"}
        ],
    )
    monkeypatch.setattr(
        "core.ai_dialog_service.AIDialogService._plan_with_llm",
        lambda self, **kwargs: {},
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ai_dialog/planner",
                json={
                    "goal": "帮我登录 X",
                    "app_id": "x",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["account"]["strategy"] == "pool"
        assert (
            data["account"]["execution_hint"]
            == "执行方式：本次未指定具体账号，运行时会从 x 账号池领取 1 个可用账号。"
        )
        assert data["account"]["ready_count"] == 1
        assert data["account"]["requires_account"] is True
        assert data["account"]["can_execute"] is True
    finally:
        reset_task_controller_for_tests()


def test_ai_dialog_planner_marks_login_without_account_as_not_executable(monkeypatch):
    reset_task_controller_for_tests()
    monkeypatch.setattr("core.ai_dialog_service.list_accounts", lambda app_id=None: [])
    monkeypatch.setattr(
        "core.ai_dialog_service.AIDialogService._plan_with_llm",
        lambda self, **kwargs: {},
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ai_dialog/planner",
                json={
                    "goal": "帮我登录 X",
                    "app_id": "x",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["account"]["strategy"] == "none"
        assert (
            data["account"]["execution_hint"]
            == "执行方式：当前没有可用账号，登录类任务下发后大概率无法完成。"
        )
        assert data["account"]["requires_account"] is True
        assert data["account"]["can_execute"] is False
        assert "account" in data["follow_up"]["missing"]
    finally:
        reset_task_controller_for_tests()


def test_ai_dialog_planner_accepts_custom_app_identity(monkeypatch):
    reset_task_controller_for_tests()
    monkeypatch.setattr("core.ai_dialog_service.list_accounts", lambda app_id=None: [])
    monkeypatch.setattr(
        "core.ai_dialog_service.AIDialogService._plan_with_llm",
        lambda self, **kwargs: {},
    )

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ai_dialog/planner",
                json={
                    "goal": "打开首页并检查是否可浏览",
                    "app_id": "twitter_cn",
                    "app_display_name": "Twitter 中文",
                    "package_name": "com.twitter.cn",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["resolved_app"]["app_id"] == "twitter_cn"
        assert data["resolved_app"]["name"] == "Twitter 中文"
        assert data["resolved_app"]["package"] == "com.twitter.cn"
        assert data["resolved_app"]["has_app_config"] is False
        assert data["resolved_payload"]["package"] == "com.twitter.cn"
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
