import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def _wait_status(client: TestClient, task_id: str, wanted: str, timeout_s: float = 6.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        if resp.status_code == 200 and resp.json().get("status") == wanted:
            return True
        time.sleep(0.05)
    return False


def _stream_task_events(client: TestClient, task_id: str) -> str:
    text = ""
    with client.stream("GET", f"/api/tasks/{task_id}/events") as resp:
        assert resp.status_code == 200
        for chunk in resp.iter_text():
            text += chunk
            if ": close" in text:
                break
    return text


class OrderRunner:
    def __init__(self) -> None:
        self.order: list[str] = []
        self._lock = threading.Lock()

    def run(self, script_payload, should_cancel=None):
        with self._lock:
            self.order.append(str(script_payload.get("label", "unknown")))
        return {"ok": True, "status": "completed", "message": "ok"}


def test_run_at_delays_execution():
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        run_at = (datetime.now(timezone.utc) + timedelta(seconds=1.5)).isoformat()
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "priority": 50,
                "run_at": run_at,
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        early = client.get(f"/api/tasks/{task_id}")
        assert early.status_code == 200
        assert early.json()["status"] == "pending"

        time.sleep(0.6)
        still_waiting = client.get(f"/api/tasks/{task_id}")
        assert still_waiting.status_code == 200
        assert still_waiting.json()["status"] == "pending"

        assert _wait_status(client, task_id, "completed", timeout_s=5.0)


def test_priority_prefers_higher_first_when_same_run_at(tmp_path: Path, monkeypatch):
    reset_task_controller_for_tests()
    monkeypatch.setenv("MYT_MAX_CONCURRENT_TASKS", "1")
    db_path = tmp_path / "tasks_priority_test.db"
    if db_path.exists():
        db_path.unlink()
    runner = OrderRunner()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=runner,
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            run_at = (datetime.now(timezone.utc) + timedelta(seconds=1.2)).isoformat()
            low = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": [], "label": "low"},
                    "devices": [1],
                    "ai_type": "volc",
                    "priority": 1,
                    "run_at": run_at,
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            high = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": [], "label": "high"},
                    "devices": [1],
                    "ai_type": "volc",
                    "priority": 99,
                    "run_at": run_at,
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert low.status_code == 200
            assert high.status_code == 200
            low_id = low.json()["task_id"]
            high_id = high.json()["task_id"]

            assert _wait_status(client, low_id, "completed", timeout_s=6.0)
            assert _wait_status(client, high_id, "completed", timeout_s=6.0)
            assert runner.order[0] == "high"
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_events_sse_stream_contains_lifecycle_events():
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "priority": 50,
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        text = _stream_task_events(client, task_id)

        assert "event: task.created" in text
        assert "event: task.started" in text
        assert "event: task.dispatching" in text
        assert "event: task.dispatch_result" in text
        assert "event: task.completed" in text


def test_task_events_sse_stream_contains_retry_and_failed_terminal_events():
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "nonexistent_task"},
                "devices": [1],
                "ai_type": "volc",
                "priority": 50,
                "max_retries": 2,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        text = _stream_task_events(client, task_id)

        assert text.count("event: task.created") == 1
        assert text.count("event: task.started") == 3
        assert text.count("event: task.dispatching") == 3
        assert text.count("event: task.dispatch_result") == 3
        assert text.count("event: task.retry_scheduled") == 2
        assert text.count("event: task.failed") == 1


def test_pending_task_cancel_emits_cancel_requested_and_cancelled_without_starting():
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        run_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "priority": 50,
                "run_at": run_at,
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        cancel = client.post(f"/api/tasks/{task_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["cancelled"] is True
        assert cancel.json()["cancel_state"] == "cancelled"

        text = _stream_task_events(client, task_id)

        assert "event: task.created" in text
        assert "event: task.cancel_requested" in text
        assert "event: task.cancelled" in text
        assert "event: task.started" not in text
        assert "event: task.dispatching" not in text
