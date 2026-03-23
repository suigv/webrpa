import sqlite3
from pathlib import Path

from core.task_control import TaskController
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskRecord, TaskStore
from engine.runner import Runner
from models.task import TaskRequest


def test_task_store_create_task_keeps_payload_shape_without_store_level_ai_type(
    tmp_path: Path,
) -> None:
    store = TaskStore(db_path=tmp_path / "tasks-default-ai.db")

    record = store.create_task(
        task_id="task-1",
        payload={"task": "demo"},
        devices=[1],
    )

    assert record.payload == {"task": "demo"}


def test_task_request_preserves_payload_ai_type() -> None:
    request = TaskRequest.model_validate(
        {
            "task": "agent_executor",
            "targets": [{"device_id": 1}],
            "payload": {"goal": "login", "ai_type": "volc"},
        }
    )

    assert request.payload["ai_type"] == "volc"


def test_continue_workflow_draft_uses_payload_ai_type_from_snapshot(tmp_path: Path) -> None:
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
            "payload": {"task": "agent_executor", "goal": "login", "ai_type": "volc"},
            "targets": [{"device_id": 1, "cloud_id": 1}],
            "max_retries": 0,
            "retry_backoff_seconds": 2,
            "priority": 50,
        },
    }

    def _fake_submit_with_retry(**kwargs):
        observed.append(str(kwargs["payload"].get("ai_type")))
        targets = kwargs.get("targets") or []
        return TaskRecord(
            task_id="task-continued",
            payload=kwargs["payload"],
            devices=[int(item["device_id"]) for item in targets],
            targets=targets,
            status="pending",
            created_at="2026-03-20T00:00:00+00:00",
            updated_at="2026-03-20T00:00:00+00:00",
        )

    controller.submit_with_retry = _fake_submit_with_retry

    records = controller.continue_workflow_draft("draft-1")

    assert len(records) == 1
    assert observed == ["volc"]
    assert records[0].payload["ai_type"] == "volc"


def test_task_store_migrates_legacy_ai_type_schema_on_startup(tmp_path: Path) -> None:
    db_path = tmp_path / "tasks-legacy-ai.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                devices_json TEXT NOT NULL,
                ai_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, payload_json, devices_json, ai_type, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "task-1",
                '{"task":"agent_executor","goal":"login"}',
                "[1]",
                "volc",
                "pending",
                "2026-03-23T00:00:00+00:00",
                "2026-03-23T00:00:00+00:00",
            ),
        )
        conn.commit()

    store = TaskStore(db_path=db_path)
    record = store.get_task("task-1")

    assert record is not None
    assert record.payload["goal"] == "login"

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    assert "ai_type" not in columns
    assert "pause_requested" in columns
