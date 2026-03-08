from pathlib import Path

from fastapi.testclient import TestClient

from api.server import app
from core.task_control import TaskController, override_task_controller_for_tests, reset_task_controller_for_tests
from core.task_events import TaskEventStore
from core.task_queue import InMemoryTaskQueue
from core.task_store import TaskStore


def test_runtime_execute_anonymous_stub():
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "anonymous", "steps": []})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "stub_executed"
    assert payload["task"] == "anonymous"


def test_runtime_execute_unsupported_task_returns_error():
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "nonexistent_task"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "failed_config_error"
    assert payload["checkpoint"] == "dispatch"
    assert "unsupported task" in payload["message"]


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
            payload = response.json()
            assert payload["ok"] is True
            assert payload["status"] == "stub_executed"
            assert "task_id" not in payload
            assert "retry_count" not in payload
            assert "max_retries" not in payload
            assert "next_retry_at" not in payload

            after = client.get("/api/tasks/?limit=50")
            assert after.status_code == 200
            assert after.json() == before.json()
    finally:
        reset_task_controller_for_tests()


def test_runtime_execute_openapi_marks_route_as_debug_only_direct_run():
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200

    execute_route = response.json()["paths"]["/api/runtime/execute"]["post"]
    assert execute_route["summary"] == "Debug-only direct runtime execute"
    description = execute_route["description"]
    assert "debug" in description.lower()
    assert "without creating managed task records" in description.lower()
    assert "/api/tasks" in description
