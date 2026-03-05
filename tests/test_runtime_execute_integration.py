from fastapi.testclient import TestClient

from api.server import app


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
