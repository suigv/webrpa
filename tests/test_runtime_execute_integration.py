from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from api.server import app
from core.task_control import TaskController, override_task_controller_for_tests, reset_task_controller_for_tests
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore


def _assert_direct_run_response_has_no_managed_task_lifecycle_fields(payload: dict[str, object]) -> None:
    forbidden_fields = {
        "task_id",
        "retry_count",
        "max_retries",
        "retry_backoff_seconds",
        "next_retry_at",
        "queued_at",
        "started_at",
        "completed_at",
        "cancelled_at",
        "events_url",
        "metrics_url",
        "cancel_url",
    }
    assert forbidden_fields.isdisjoint(payload)


def test_runtime_execute_anonymous_stub():
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "anonymous", "steps": []})
    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    assert payload["ok"] is True
    assert payload["status"] == "stub_executed"
    assert payload["task"] == "anonymous"
    _assert_direct_run_response_has_no_managed_task_lifecycle_fields(payload)


def test_runtime_execute_unsupported_task_returns_error():
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "nonexistent_task"})
    assert response.status_code == 200
    payload = cast(dict[str, object], response.json())
    assert payload["ok"] is False
    assert payload["status"] == "failed_config_error"
    assert payload["checkpoint"] == "dispatch"
    assert "unsupported task" in cast(str, payload["message"])


def test_runtime_execute_does_not_create_managed_task_record(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "runtime_execute_does_not_create_task.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            before = client.get("/api/tasks/?limit=50")
            assert before.status_code == 200

            response = client.post("/api/runtime/execute", json={"task": "anonymous", "steps": []})
            assert response.status_code == 200
            payload = cast(dict[str, object], response.json())
            assert payload["ok"] is True
            assert payload["status"] == "stub_executed"
            _assert_direct_run_response_has_no_managed_task_lifecycle_fields(payload)

            after = client.get("/api/tasks/?limit=50")
            assert after.status_code == 200
            assert after.json() == before.json()
    finally:
        reset_task_controller_for_tests()


def test_runtime_execute_does_not_create_managed_task_metrics_artifacts(tmp_path: Path):
    reset_task_controller_for_tests()
    db_path = tmp_path / "runtime_execute_does_not_create_metrics.db"
    controller = TaskController(
        store=TaskStore(db_path=db_path),
        queue_backend=InMemoryTaskQueue(),
        event_store=TaskEventStore(db_path=db_path),
    )
    override_task_controller_for_tests(controller)

    try:
        with TestClient(app) as client:
            before = client.get("/api/tasks/metrics?window_seconds=86400")
            assert before.status_code == 200
            before_payload = cast(dict[str, object], before.json())

            response = client.post("/api/runtime/execute", json={"task": "anonymous", "steps": []})
            assert response.status_code == 200
            direct_payload = cast(dict[str, object], response.json())
            assert direct_payload["ok"] is True

            after = client.get("/api/tasks/metrics?window_seconds=86400")
            assert after.status_code == 200
            after_payload = cast(dict[str, object], after.json())
            comparable_keys = (
                "window_seconds",
                "status_counts",
                "event_type_counts",
                "terminal_outcomes",
                "rates",
                "alerts",
            )
            assert {key: before_payload[key] for key in comparable_keys} == {
                key: after_payload[key] for key in comparable_keys
            }
    finally:
        reset_task_controller_for_tests()


def test_runtime_execute_openapi_marks_route_as_debug_only_direct_run():
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_payload = cast(dict[str, object], response.json())
    paths = cast(dict[str, object], openapi_payload["paths"])
    runtime_path = cast(dict[str, object], paths["/api/runtime/execute"])
    execute_route = cast(dict[str, object], runtime_path["post"])
    assert execute_route["summary"] == "Debug-only direct runtime execute"
    description = cast(str, execute_route["description"])
    assert "debug" in description.lower()
    assert "returns the raw runner result" in description.lower()
    assert "without creating managed task records" in description.lower()
    assert "synchronously" in description.lower()
    assert "retries" in description.lower()
    assert "cancellation flow" in description.lower()
    assert "sse task events" in description.lower()
    assert "task metrics artifacts" in description.lower()
    assert "exclusive to /api/tasks" in description.lower()
    assert "/api/tasks" in description
