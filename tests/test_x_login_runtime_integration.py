from fastapi.testclient import TestClient

from api.server import app


def test_x_login_runtime_integration_missing_creds():
    """Posting x_auto_login without credentials_ref returns an error via YAML interpreter."""
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "x_auto_login"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["task"] == "x_auto_login"
    assert payload["status"] == "failed_config_error"
    assert payload["checkpoint"] == "dispatch"
    assert payload["code"] == "missing_required_param"


def test_x_login_runtime_integration_unknown_task():
    """Unknown task returns controlled error via runner dispatch."""
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "nonexistent_plugin"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["status"] == "failed_config_error"
    assert payload["checkpoint"] == "dispatch"
