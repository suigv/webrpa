# pyright: reportMissingImports=false
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from api.server import app
from core.account_feedback import AccountFeedbackService
from core.task_control import (
    TaskController,
    override_task_controller_for_tests,
    reset_task_controller_for_tests,
)
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore


class CancellableFakeRunner:
    def run(self, script_payload, should_cancel=None, runtime=None):
        deadline = time.time() + 1.5
        while time.time() < deadline:
            if should_cancel is not None and should_cancel():
                return {
                    "ok": False,
                    "status": "cancelled",
                    "message": "task cancelled by user",
                }
            time.sleep(0.02)
        return {"ok": True, "status": "completed", "message": "done"}


class ExceptionAfterCancelRunner:
    def run(self, script_payload, should_cancel=None, runtime=None):
        deadline = time.time() + 1.5
        while time.time() < deadline:
            if should_cancel is not None and should_cancel():
                raise RuntimeError("interrupted by cancellation")
            time.sleep(0.02)
        return {"ok": True, "status": "completed", "message": "done"}



def _wait_until_status(client: TestClient, task_id: str, wanted: str, timeout_s: float = 4.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        if resp.status_code == 200 and resp.json().get("status") == wanted:
            return True
        time.sleep(0.05)
    return False


def test_running_task_can_be_cancelled_via_api(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_cancel_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=CancellableFakeRunner(),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            assert _wait_until_status(client, task_id, "running", timeout_s=2.0)

            cancel = client.post(f"/api/tasks/{task_id}/cancel")
            assert cancel.status_code == 200
            assert cancel.json()["cancelled"] is True
            assert cancel.json()["cancel_state"] in {"cancelling", "cancelled"}

            assert _wait_until_status(client, task_id, "cancelled", timeout_s=3.0)

            detail = client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200
            payload = detail.json()
            assert payload["status"] == "cancelled"
            assert "cancel" in (payload.get("error") or "").lower()
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_cancel_requested_with_runner_exception_marks_cancelled_not_failed(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_cancel_exception_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=ExceptionAfterCancelRunner(),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            assert _wait_until_status(client, task_id, "running", timeout_s=2.0)

            cancel = client.post(f"/api/tasks/{task_id}/cancel")
            assert cancel.status_code == 200
            assert cancel.json()["cancelled"] is True

            assert _wait_until_status(client, task_id, "cancelled", timeout_s=3.0)

            detail = client.get(f"/api/tasks/{task_id}")
            assert detail.status_code == 200
            payload = detail.json()
            assert payload["status"] == "cancelled"
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_account_feedback_service_does_not_mutate_on_cancellation_adjacent_path():
    writes = []
    service = AccountFeedbackService(
        read_account_lines=lambda data_type: [json.dumps({"account": "alice@example.com", "status": "active"})],
        write_account_lines=lambda data_type, lines: writes.append((data_type, lines)),
    )

    service.handle_terminal_failure({"credentials_ref": json.dumps({"account": "alice@example.com"})}, "task cancelled by user")

    assert writes == []
