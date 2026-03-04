import os
import time

from fastapi.testclient import TestClient

from new.api.server import app
from new.core.task_control import reset_task_controller_for_tests


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
