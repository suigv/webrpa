# pyright: reportMissingImports=false
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from api.server import app
from core.task_control import TaskController, override_task_controller_for_tests, reset_task_controller_for_tests
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore


def _wait_status(client: TestClient, task_id: str, timeout_s: float = 3.0) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        if status in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.05)
    return "timeout"


def test_task_control_plane_success_flow():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        status = _wait_status(client, task_id)
        assert status == "completed"

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "completed"
        assert payload["result"]["ok"] is True


def test_task_control_plane_failed_flow():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "nonexistent_task"},
                "devices": [1],
                "ai_type": "volc",
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        status = _wait_status(client, task_id)
        assert status == "failed"

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "failed"
        assert payload["retry_count"] == 0
        assert "unsupported task" in (payload.get("error") or "")


class _WrongPasswordRunner:
    def run(self, script_payload, should_cancel=None):
        return {"ok": False, "status": "failed", "message": "wrong password provided"}


class _RecordingAccountFeedback:
    def __init__(self):
        self.calls = []

    def handle_terminal_failure(self, payload, error):
        self.calls.append({"payload": payload, "error": error})


def test_task_controller_routes_terminal_failure_through_account_feedback_hook(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_account_feedback_hook_test.db"
    if db_path.exists():
        db_path.unlink()

    account_feedback = _RecordingAccountFeedback()
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_WrongPasswordRunner(),
        event_store=TaskEventStore(db_path=db_path),
        account_feedback=account_feedback,
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            create = client.post(
                "/api/tasks/",
                json={
                    "script": {
                        "task": "anonymous",
                        "steps": [],
                        "credentials_ref": json.dumps({"account": "alice@example.com"}),
                    },
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            assert create.status_code == 200
            task_id = create.json()["task_id"]

            assert _wait_status(client, task_id, timeout_s=3.0) == "failed"
            assert len(account_feedback.calls) == 1
            assert account_feedback.calls[0]["payload"]["credentials_ref"] == json.dumps({"account": "alice@example.com"})
            assert account_feedback.calls[0]["error"] == "wrong password provided"
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_task_control_plane_retries_then_fails():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "nonexistent_task"},
                "devices": [1],
                "ai_type": "volc",
                "max_retries": 2,
                "retry_backoff_seconds": 0,
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        status = _wait_status(client, task_id, timeout_s=5.0)
        assert status == "failed"

        detail = client.get(f"/api/tasks/{task_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == "failed"
        assert payload["retry_count"] == 2
        assert payload["max_retries"] == 2
        assert payload["retry_backoff_seconds"] == 0


def test_task_control_plane_create_returns_retry_metadata():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "max_retries": 3,
                "retry_backoff_seconds": 1,
            },
        )
        assert create.status_code == 200
        payload = create.json()
        assert payload["retry_count"] == 0
        assert payload["max_retries"] == 3
        assert payload["retry_backoff_seconds"] == 1


def test_task_control_plane_list_contains_created_task():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        create = client.post(
            "/api/tasks/",
            json={
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
            },
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        listing = client.get("/api/tasks/?limit=50")
        assert listing.status_code == 200
        ids = {item["task_id"] for item in listing.json()}
        assert task_id in ids


def test_duplicate_submit_with_same_idempotency_key_returns_same_task(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_duplicate_submit_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            request = {
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "idempotency_key": "dup-key-1",
                "run_at": "2999-01-01T00:00:00+00:00",
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            }
            first = client.post("/api/tasks/", json=request)
            second = client.post("/api/tasks/", json=request)

            assert first.status_code == 200
            assert second.status_code == 200
            assert first.json()["task_id"] == second.json()["task_id"]

            listing = client.get("/api/tasks/?limit=100")
            assert listing.status_code == 200
            ids = [item["task_id"] for item in listing.json()]
            assert ids.count(first.json()["task_id"]) == 1
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_dedupes_pending_task_across_controller_restart(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_restart_test.db"
    if db_path.exists():
        db_path.unlink()

    try:
        first_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        with TestClient(app) as client:
            request = {
                "script": {"task": "anonymous", "steps": []},
                "devices": [1],
                "ai_type": "volc",
                "idempotency_key": "restart-key-1",
                "run_at": "2999-01-01T00:00:00+00:00",
                "max_retries": 0,
                "retry_backoff_seconds": 0,
            }
            first = client.post("/api/tasks/", json=request)
            assert first.status_code == 200
            first_id = first.json()["task_id"]

            restarted_controller = TaskController(
                store=TaskStore(db_path=db_path),
                queue_backend=InMemoryTaskQueue(),
                event_store=TaskEventStore(db_path=db_path),
            )
            override_task_controller_for_tests(restarted_controller)

            second = client.post("/api/tasks/", json=request)
            assert second.status_code == 200
            assert second.json()["task_id"] == first_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_dedupes_running_task_across_controller_restart(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_running_restart_test.db"
    if db_path.exists():
        db_path.unlink()

    try:
        first_store = TaskStore(db_path=db_path)
        first_controller = TaskController(
            store=first_store,
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        created = first_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            ai_type="volc",
            max_retries=1,
            retry_backoff_seconds=1,
            priority=50,
            run_at=None,
            idempotency_key="restart-running-key-1",
        )
        assert first_store.mark_running(created.task_id) is True

        restarted_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(restarted_controller)

        duplicate = restarted_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            ai_type="volc",
            max_retries=1,
            retry_backoff_seconds=1,
            priority=50,
            run_at=None,
            idempotency_key="restart-running-key-1",
        )
        assert duplicate.task_id == created.task_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_dedupes_retry_scheduled_task_across_controller_restart(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_retry_window_restart_test.db"
    if db_path.exists():
        db_path.unlink()

    try:
        first_store = TaskStore(db_path=db_path)
        first_controller = TaskController(
            store=first_store,
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        created = first_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            ai_type="volc",
            max_retries=2,
            retry_backoff_seconds=60,
            priority=50,
            run_at=None,
            idempotency_key="restart-retry-key-1",
        )

        retry_record = first_store.schedule_retry(created.task_id, error="forced retry for idempotency test")
        assert retry_record is not None
        assert retry_record.status == "pending"
        assert retry_record.next_retry_at is not None

        restarted_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(restarted_controller)

        duplicate = restarted_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            ai_type="volc",
            max_retries=2,
            retry_backoff_seconds=60,
            priority=50,
            run_at=None,
            idempotency_key="restart-retry-key-1",
        )
        assert duplicate.task_id == created.task_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_stale_running_task_recovered_and_requeued_on_controller_start(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_stale_running_recovery_test.db"
    if db_path.exists():
        db_path.unlink()

    previous_stale = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS")
    os.environ["MYT_TASK_STALE_RUNNING_SECONDS"] = "0"

    try:
        first_store = TaskStore(db_path=db_path)
        first_controller = TaskController(
            store=first_store,
            queue_backend=InMemoryTaskQueue(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(first_controller)

        created = first_controller.submit_with_retry(
            payload={"task": "anonymous", "steps": []},
            devices=[1],
            ai_type="volc",
            max_retries=0,
            retry_backoff_seconds=0,
            priority=50,
            run_at=None,
            idempotency_key="stale-running-key-1",
        )
        assert first_store.mark_running(created.task_id) is True

        restarted_controller = TaskController(
            store=TaskStore(db_path=db_path),
            queue_backend=InMemoryTaskQueue(),
            runner=_ImmediateSuccessRunner(),
            event_store=TaskEventStore(db_path=db_path),
        )
        override_task_controller_for_tests(restarted_controller)
        restarted_controller.start()

        deadline = time.time() + 3.0
        final_status = "running"
        while time.time() < deadline:
            record = restarted_controller.get(created.task_id)
            assert record is not None
            final_status = record.status
            if final_status == "completed":
                break
            time.sleep(0.05)

        assert final_status == "completed"

        events = restarted_controller.list_events(created.task_id)
        assert any(ev.event_type == "task.recovered_stale_running" for ev in events)
    finally:
        reset_task_controller_for_tests()
        if previous_stale is None:
            os.environ.pop("MYT_TASK_STALE_RUNNING_SECONDS", None)
        else:
            os.environ["MYT_TASK_STALE_RUNNING_SECONDS"] = previous_stale
        if db_path.exists():
            db_path.unlink()


class _ImmediateSuccessRunner:
    def run(self, script_payload, should_cancel=None):
        return {"ok": True, "status": "completed", "message": "done"}


def test_same_idempotency_key_allows_new_task_after_terminal_state(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_idempotency_terminal_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        runner=_ImmediateSuccessRunner(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "idempotency_key": "dup-key-2",
                },
            )
            assert first.status_code == 200
            first_id = first.json()["task_id"]
            assert _wait_status(client, first_id, timeout_s=3.0) == "completed"

            second = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "idempotency_key": "dup-key-2",
                },
            )
            assert second.status_code == 200
            assert second.json()["task_id"] != first_id
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()


def test_idempotency_key_can_be_supplied_via_header():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        request = {
            "script": {"task": "anonymous", "steps": []},
            "devices": [1],
            "ai_type": "volc",
            "run_at": "2999-01-01T00:00:00+00:00",
            "max_retries": 0,
            "retry_backoff_seconds": 0,
        }
        first = client.post("/api/tasks/", json=request, headers={"X-Idempotency-Key": "header-key-1"})
        second = client.post("/api/tasks/", json=request, headers={"X-Idempotency-Key": "header-key-1"})

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["task_id"] == second.json()["task_id"]
        assert first.json()["idempotency_key"] == "header-key-1"


def test_conflicting_body_and_header_idempotency_key_rejected():
    os.environ["MYT_TASK_QUEUE_BACKEND"] = "memory"
    reset_task_controller_for_tests()
    with TestClient(app) as client:
        request = {
            "script": {"task": "anonymous", "steps": []},
            "devices": [1],
            "ai_type": "volc",
            "idempotency_key": "body-key",
        }
        response = client.post("/api/tasks/", json=request, headers={"X-Idempotency-Key": "header-key"})

        assert response.status_code == 400
        assert "idempotency key mismatch" in response.json().get("detail", "")


def test_task_metrics_aggregates_status_and_event_counts(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "tasks_metrics_test.db"
    if db_path.exists():
        db_path.unlink()

    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            success = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            failed = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "nonexistent_task"},
                    "devices": [1],
                    "ai_type": "volc",
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )
            cancelled = client.post(
                "/api/tasks/",
                json={
                    "script": {"task": "anonymous", "steps": []},
                    "devices": [1],
                    "ai_type": "volc",
                    "run_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    "max_retries": 0,
                    "retry_backoff_seconds": 0,
                },
            )

            assert success.status_code == 200
            assert failed.status_code == 200
            assert cancelled.status_code == 200

            assert _wait_status(client, success.json()["task_id"], timeout_s=5.0) == "completed"
            assert _wait_status(client, failed.json()["task_id"], timeout_s=5.0) == "failed"

            cancel_resp = client.post(f"/api/tasks/{cancelled.json()['task_id']}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["cancelled"] is True

            metrics = client.get("/api/tasks/metrics?window_seconds=86400")
            assert metrics.status_code == 200
            payload = metrics.json()

            assert payload["window_seconds"] == 86400
            assert payload["status_counts"].get("completed", 0) >= 1
            assert payload["status_counts"].get("failed", 0) >= 1
            assert payload["status_counts"].get("cancelled", 0) >= 1

            assert payload["event_type_counts"].get("task.created", 0) >= 3
            assert payload["terminal_outcomes"].get("completed", 0) >= 1
            assert payload["terminal_outcomes"].get("failed", 0) >= 1
            assert payload["terminal_outcomes"].get("cancelled", 0) >= 1
            assert payload["alerts"]["evaluated"] is False
            assert payload["alerts"]["triggered"] is False

            evaluated_metrics = client.get(
                "/api/tasks/metrics?window_seconds=86400&failure_rate_threshold=0.2&cancellation_rate_threshold=0.2&min_terminal_samples=1"
            )
            assert evaluated_metrics.status_code == 200
            evaluated_payload = evaluated_metrics.json()
            assert evaluated_payload["alerts"]["evaluated"] is True
            assert evaluated_payload["alerts"]["triggered"] is True
            assert "failure_rate" in evaluated_payload["rates"]
            assert "cancellation_rate" in evaluated_payload["rates"]
            assert "completion_rate" in evaluated_payload["rates"]
            assert len(evaluated_payload["alerts"].get("reasons", [])) >= 1

            prometheus_metrics = client.get(
                "/api/tasks/metrics/prometheus?window_seconds=86400&failure_rate_threshold=0.2&cancellation_rate_threshold=0.2&min_terminal_samples=1"
            )
            assert prometheus_metrics.status_code == 200
            body = prometheus_metrics.text
            assert "# TYPE new_task_status_count gauge" in body
            assert "new_task_status_count{status=\"completed\"}" in body
            assert "new_task_terminal_outcome_total{outcome=\"failed\"}" in body
            assert "new_task_failure_rate " in body
            assert "new_task_alert_triggered 1" in body
    finally:
        reset_task_controller_for_tests()
        if db_path.exists():
            db_path.unlink()
