from __future__ import annotations

from fastapi.testclient import TestClient

from api.server import app
from core.app_config_candidate_service import AppConfigCandidateService, AppConfigCandidateStore
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
        assert data["intent"]["objective"] == "login"
        assert data["execution"]["runtime"] == "agent_executor"
        assert data["execution"]["readiness"] == "ready"
        assert any(item["task"] == "x_login" for item in data["recommended_workflows"])
        assert data["resolved_payload"]["_workflow_source"] == "ai_dialog"
        assert data["resolved_payload"]["_planner_objective"] == "login"
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
            == "执行方式：未绑定具体账号，运行时会从 x 账号池领取 1 个可用账号（当前 1 个就绪）。"
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
            == "执行方式：当前没有可用账号，先导入或选择 x 账号后再执行。"
        )
        assert data["account"]["requires_account"] is True
        assert data["account"]["can_execute"] is False
        assert data["execution"]["blocking_reasons"] == ["missing_account"]
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
        assert data["execution"]["mode"] == "exploration_bootstrap"
        assert data["account"]["can_execute"] is False
        assert data["resolved_payload"]["package"] == "com.twitter.cn"
    finally:
        reset_task_controller_for_tests()


def test_ai_dialog_planner_infers_branch_and_workflow_for_collection_goal(monkeypatch):
    reset_task_controller_for_tests()
    monkeypatch.setattr(
        "core.ai_dialog_service.list_accounts",
        lambda app_id=None: [
            {
                "account": "pool-1@example.com",
                "status": "ready",
                "app_id": app_id or "x",
                "default_branch": "part_time",
            }
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
                    "goal": "帮我做交友分支的采集博主任务",
                    "app_id": "x",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["intent"]["objective"] == "scrape_blogger"
        assert data["branch"]["branch_id"] == "volc"
        assert data["branch"]["source"] == "goal"
        assert data["resolved_payload"]["branch_id"] == "volc"
        assert data["execution"]["mode"] == "workflow_aligned"
        assert any(item["task"] == "x_scrape_blogger" for item in data["recommended_workflows"])
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


def test_ai_dialog_annotations_and_save_candidates_flow(tmp_path, monkeypatch):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks-ai-dialog-save.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    store = WorkflowDraftStore(db_path=db_path)
    store.create_draft(
        WorkflowDraftRecord(
            draft_id="draft_save",
            display_name="X 搜索",
            task_name="agent_executor",
            plugin_name_candidate="x_search",
            source="ai_dialog",
            latest_completed_task_id="task-save-1",
            last_success_snapshot={
                "payload": {
                    "goal": "搜索博主",
                    "branch_id": "volc",
                    "resource_namespace": "x.volc.pool",
                },
                "identity": {"app_id": "x", "account": "demo@example.com", "branch_id": "volc"},
            },
        )
    )

    try:
        merged_learning: dict[str, object] = {}

        def fake_merge_branch_learning(
            _self,
            app_id: str,
            *,
            branch_id: str,
            search_keywords=None,
            reply_texts=None,
            resource_namespace=None,
            payload_defaults=None,
        ):
            merged_learning.update(
                {
                    "app_id": app_id,
                    "branch_id": branch_id,
                    "search_keywords": list(search_keywords or []),
                    "reply_texts": list(reply_texts or []),
                    "resource_namespace": resource_namespace,
                    "payload_defaults": dict(payload_defaults or {}),
                }
            )
            return merged_learning

        monkeypatch.setattr(
            "core.ai_dialog_save_service.AppBranchProfileService.merge_branch_learning",
            fake_merge_branch_learning,
        )
        with TestClient(app) as client:
            created = client.post(
                "/api/ai_dialog/annotations",
                json={
                    "task_id": "task-save-1",
                    "input_type": "search_keyword",
                    "raw_value": "#mytxx",
                },
            )
            assert created.status_code == 200

            candidates = client.get("/api/ai_dialog/drafts/draft_save/save_candidates")
            assert candidates.status_code == 200
            payload = candidates.json()
            assert {item["kind"] for item in payload["candidates"]} == {
                "account_default_branch",
                "workflow_default_branch",
                "payload_default",
                "branch_keyword",
                "branch_resource_namespace",
            }

            selected_ids = [
                item["candidate_id"]
                for item in payload["candidates"]
                if item["kind"] != "account_default_branch"
            ]
            applied = client.post(
                "/api/ai_dialog/drafts/draft_save/save_choices",
                json={"candidate_ids": selected_ids},
            )
            assert applied.status_code == 200
            assert len(applied.json()["saved"]) == 4

            snapshot = client.get("/api/tasks/drafts/draft_save/snapshot")
            assert snapshot.status_code == 200
            replay_payload = snapshot.json()["snapshot"]["payload"]
            assert replay_payload["branch_id"] == "volc"
            assert replay_payload["keyword"] == "#mytxx"
            assert merged_learning == {
                "app_id": "x",
                "branch_id": "volc",
                "search_keywords": ["#mytxx"],
                "reply_texts": [],
                "resource_namespace": "x.volc.pool",
                "payload_defaults": {},
            }
    finally:
        reset_task_controller_for_tests()


def test_ai_dialog_app_branch_profiles_route_updates_app_config(monkeypatch):
    reset_task_controller_for_tests()
    app_doc = {
        "version": "v1",
        "app_id": "x",
        "display_name": "X",
        "default_branch": "default",
        "branches": {},
    }

    monkeypatch.setattr(
        "core.app_branch_service.AppConfigManager.ensure_app_config",
        lambda **kwargs: {"app_id": "x"},
    )
    monkeypatch.setattr("core.app_branch_service.get_app_config", lambda app_id: app_doc)

    def _write_branch_doc(app_id, document):
        _ = app_id
        snapshot = dict(document)
        app_doc.clear()
        app_doc.update(snapshot)
        return None

    monkeypatch.setattr(
        "core.app_branch_service.AppConfigManager.write_app_config",
        _write_branch_doc,
    )

    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/ai_dialog/apps/x/branch_profiles",
                json={
                    "default_branch": "volc",
                    "branches": [
                        {
                            "branch_id": "volc",
                            "label": "交友",
                            "search_keywords": ["#太もも"],
                            "reply_texts": ["你好呀"],
                            "resource_namespace": "x.volc.pool",
                            "reply_ai_type": "dating",
                            "payload_defaults": {"keyword": "#太もも"},
                        }
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["default_branch"] == "volc"
        volc_branch = next(item for item in data["branches"] if item["branch_id"] == "volc")
        assert volc_branch["reply_ai_type"] == "dating"
        assert app_doc["default_branch"] == "volc"
        assert app_doc["branches"]["volc"]["resource_namespace"] == "x.volc.pool"
        assert app_doc["nurture_keywords"]["volc"]["core"] == ["#太もも"]
        assert app_doc["quote_texts"]["volc"] == ["你好呀"]
    finally:
        reset_task_controller_for_tests()


def test_ai_dialog_config_candidate_review_promotes_into_app_config(tmp_path, monkeypatch):
    reset_task_controller_for_tests()
    app_doc = {
        "version": "v1",
        "app_id": "x",
        "display_name": "X",
        "selectors": {},
        "states": [],
        "stage_patterns": {},
    }
    monkeypatch.setattr(
        "core.app_config_candidate_service.AppConfigManager.ensure_app_config",
        lambda **kwargs: {"app_id": "x"},
    )
    monkeypatch.setattr(
        "core.app_config_candidate_service.AppConfigManager.app_config_path",
        lambda app_id: tmp_path / "x.yaml",
    )
    monkeypatch.setattr(
        "core.app_config_candidate_service.get_app_config",
        lambda app_id: app_doc,
    )

    def _write_candidate_doc(app_id, document):
        _ = app_id
        snapshot = dict(document)
        app_doc.clear()
        app_doc.update(snapshot)
        return None

    monkeypatch.setattr(
        "core.app_config_candidate_service.AppConfigManager.write_app_config",
        _write_candidate_doc,
    )
    candidate_service = AppConfigCandidateService(
        store=AppConfigCandidateStore(db_path=tmp_path / "app-config-candidates.db")
    )
    candidate = candidate_service.record_candidate(
        app_id="x",
        draft_id="draft-1",
        task_id="task-1",
        kind="selector",
        title="选择器 · home_tab",
        preview='{"type":"text","mode":"equal","value":"首页"}',
        value={
            "selector_key": "home_tab",
            "selector": {"type": "text", "mode": "equal", "value": "首页"},
        },
    )
    monkeypatch.setattr(
        "api.routes.ai_dialog.get_app_config_candidate_service",
        lambda: candidate_service,
    )

    try:
        with TestClient(app) as client:
            listed = client.get("/api/ai_dialog/apps/x/config_candidates?draft_id=draft-1")
            assert listed.status_code == 200
            assert len(listed.json()["candidates"]) == 1

            reviewed = client.post(
                "/api/ai_dialog/apps/x/config_candidates/review",
                json={
                    "candidate_ids": [candidate["candidate_id"]],
                    "action": "promote",
                },
            )

        assert reviewed.status_code == 200
        assert reviewed.json()["updated"] == 1
        assert app_doc["selectors"]["home_tab"] == {
            "type": "text",
            "mode": "equal",
            "value": "首页",
        }
        pending = candidate_service.list_candidates(app_id="x", draft_id="draft-1")
        assert pending["candidates"] == []
    finally:
        reset_task_controller_for_tests()
