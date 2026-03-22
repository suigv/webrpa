# pyright: reportMissingImports=false
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.server import app
from core.account_feedback import AccountFeedbackService
from core.device_manager import DeviceManager
from core.task_events import TaskEventStore
from core.task_finalizer import TaskAttemptFinalizer
from core.task_control import (
    TaskController,
    override_task_controller_for_tests,
    reset_task_controller_for_tests,
)
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore


def _reset_device_manager_state(manager: DeviceManager) -> None:
    with manager._probe_lock:
        manager._probe_cache.clear()
    with manager._probe_subscribers_lock:
        manager._probe_subscribers.clear()
        manager._next_probe_subscription_id = 0
    with manager._device_snapshot_lock:
        manager._device_snapshot_cache.clear()
        manager._device_snapshot_at.clear()
    with manager._devices_lock:
        manager._devices = {}


@pytest.fixture(autouse=True)
def _isolate_device_manager_state():
    manager = DeviceManager()
    _reset_device_manager_state(manager)
    try:
        yield
    finally:
        _reset_device_manager_state(manager)


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


def _wait_until_status(
    client: TestClient, task_id: str, wanted: str, timeout_s: float = 4.0
) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        if resp.status_code == 200 and resp.json().get("status") == wanted:
            return True
        time.sleep(0.05)
    return False


def _wait_for_run_id(controller: TaskController, task_id: str, timeout_s: float = 3.0) -> str | None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        record = controller.get(task_id)
        if record is not None and record.active_run_id:
            return str(record.active_run_id)
        time.sleep(0.05)
    return None


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


def test_running_task_can_be_paused_and_resumed_via_api(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_pause_resume_test.db"
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

            pause = client.post(f"/api/tasks/{task_id}/pause", json={"reason": "operator_pause"})
            assert pause.status_code == 200
            assert pause.json()["paused"] is True
            assert _wait_until_status(client, task_id, "paused", timeout_s=3.0)

            resume = client.post(f"/api/tasks/{task_id}/resume", json={"reason": "operator_resume"})
            assert resume.status_code == 200
            assert resume.json()["resumed"] is True
            assert _wait_until_status(client, task_id, "completed", timeout_s=4.0)
    finally:
        reset_task_controller_for_tests()


def test_running_task_takeover_requires_matching_run_id(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_takeover_test.db"
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

            active_run_id = _wait_for_run_id(controller, task_id)
            assert active_run_id

            bad = client.post(
                f"/api/tasks/{task_id}/takeover",
                json={"run_id": "wrong-run", "owner": "operator-a"},
            )
            assert bad.status_code == 409

            good = client.post(
                f"/api/tasks/{task_id}/takeover",
                json={"run_id": active_run_id, "owner": "operator-a"},
            )
            assert good.status_code == 200
            assert good.json()["takeover_state"] == "takeover_requested"
            assert _wait_until_status(client, task_id, "paused", timeout_s=3.0)
    finally:
        reset_task_controller_for_tests()


def test_paused_task_can_be_cancelled_via_api(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_pause_cancel_test.db"
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

            pause = client.post(f"/api/tasks/{task_id}/pause", json={"reason": "operator_pause"})
            assert pause.status_code == 200
            assert pause.json()["paused"] is True

            cancel = client.post(f"/api/tasks/{task_id}/cancel")
            assert cancel.status_code == 200
            assert cancel.json()["cancelled"] is True
            assert _wait_until_status(client, task_id, "cancelled", timeout_s=3.0)
    finally:
        reset_task_controller_for_tests()


def test_account_feedback_service_does_not_mutate_on_cancellation_adjacent_path():
    writes = []
    service = AccountFeedbackService(
        read_account_lines=lambda data_type: [
            json.dumps({"account": "alice@example.com", "status": "active"})
        ],
        write_account_lines=lambda data_type, lines: writes.append((data_type, lines)),
    )

    service.handle_terminal_failure(
        {"credentials_ref": json.dumps({"account": "alice@example.com"})}, "task cancelled by user"
    )

    assert writes == []


def test_finalizer_exception_after_cancel_uses_user_reason(tmp_path: Path):
    db_path = tmp_path / "task_finalizer_cancel_reason.db"
    store = TaskStore(db_path=db_path)
    events = TaskEventStore(db_path=db_path)
    finalizer = TaskAttemptFinalizer(store=store, event_store=events)

    with store.transaction(immediate=True) as conn:
        record = store.create_task(
            task_id="task-cancel-reason",
            payload={"task": "anonymous"},
            devices=[1],
            targets=[{"device_id": 1, "cloud_id": 1}],
            ai_type="default",
            max_retries=0,
            retry_backoff_seconds=0,
            priority=0,
            run_at=None,
            conn=conn,
        )
        store.mark_running(record.task_id, conn=conn)
        store.request_cancel(record.task_id, conn=conn)

    outcome = finalizer.finalize_exception_attempt(
        task_id="task-cancel-reason",
        task_name="anonymous",
        error="interrupted by cancellation",
    )

    assert outcome.should_enqueue_retry is False
    task_events = events.list_events("task-cancel-reason")
    assert [event.event_type for event in task_events] == [
        "task.dispatch_result",
        "task.cancelled",
    ]
    assert task_events[1].payload["reason"] == "user"
