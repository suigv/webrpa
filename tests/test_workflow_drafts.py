# pyright: reportMissingImports=false
import json
import time
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from ai_services.llm_client import LLMResponse
from api.server import app
from core.task_control import (
    TaskController,
    override_task_controller_for_tests,
    reset_task_controller_for_tests,
)
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore
from engine.action_registry import ActionRegistry
from engine.agent_executor import AgentExecutorRuntime
from engine.models.runtime import ActionResult
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
                    "devices": [1],
                    "ai_type": "volc",
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
                        "expected_state_ids": ["account"],
                        "allowed_actions": ["ui.click"],
                        "max_steps": 4,
                    },
                    "targets": [{"device_id": 7, "cloud_id": 2}],
                    "ai_type": "volc",
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

            distill = client.post(f"/api/tasks/drafts/{draft_id}/distill", json={})
            assert distill.status_code == 200
            payload = distill.json()
            assert payload["ok"] is True
            assert Path(payload["manifest_path"]).exists()
            assert Path(payload["script_path"]).exists()
            assert str(payload["output_dir"]).startswith(str(plugins_root))
    finally:
        reset_task_controller_for_tests()
