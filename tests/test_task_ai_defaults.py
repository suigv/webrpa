from pathlib import Path

from core.task_control import TaskController
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskRecord, TaskStore
from engine.runner import Runner


def test_task_store_create_task_defaults_ai_type_to_default(tmp_path: Path) -> None:
    store = TaskStore(db_path=tmp_path / "tasks-default-ai.db")

    record = store.create_task(
        task_id="task-1",
        payload={"task": "demo"},
        devices=[1],
    )

    assert record.ai_type == "default"


def test_continue_workflow_draft_defaults_missing_ai_type_to_default(tmp_path: Path) -> None:
    controller = TaskController(
        store=TaskStore(db_path=tmp_path / "tasks-workflow-ai-default.db"),
        queue_backend=InMemoryTaskQueue(),
        runner=Runner(),
        event_store=TaskEventStore(db_path=tmp_path / "tasks-workflow-ai-default.db"),
    )
    observed: list[str] = []

    controller._workflow_drafts.continuation_snapshot = lambda draft_id: {
        "draft_id": draft_id,
        "display_name": "X 登录",
        "success_threshold": 3,
        "snapshot": {
            "payload": {"task": "agent_executor", "goal": "login"},
            "devices": [1],
            "targets": [{"device_id": 1, "cloud_id": 1}],
            "max_retries": 0,
            "retry_backoff_seconds": 2,
            "priority": 50,
        },
    }

    def _fake_submit_with_retry(**kwargs):
        observed.append(str(kwargs["ai_type"]))
        return TaskRecord(
            task_id="task-continued",
            payload=kwargs["payload"],
            devices=kwargs["devices"],
            targets=kwargs["targets"],
            ai_type=str(kwargs["ai_type"]),
            status="pending",
            created_at="2026-03-20T00:00:00+00:00",
            updated_at="2026-03-20T00:00:00+00:00",
        )

    controller.submit_with_retry = _fake_submit_with_retry

    records = controller.continue_workflow_draft("draft-1")

    assert len(records) == 1
    assert observed == ["default"]
    assert records[0].ai_type == "default"
