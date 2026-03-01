from fastapi.testclient import TestClient

from new.api.server import app
import new.plugins.x_auto_login as x_auto_login


def test_x_login_runtime_integration_completed(monkeypatch):
    def fake_run(_context):
        return {
            "ok": True,
            "task": "x_auto_login",
            "status": "completed",
            "checkpoint": "verify_success",
            "message": "ok",
            "evidence_ref": "",
        }

    monkeypatch.setattr(x_auto_login, "run", fake_run)
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "x_auto_login", "credentials_ref": "/etc/myt/x_credentials.json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["checkpoint"] == "verify_success"


def test_x_login_runtime_integration_failure_branch(monkeypatch):
    def fake_run(_context):
        return {
            "ok": False,
            "task": "x_auto_login",
            "status": "failed_2fa_required",
            "checkpoint": "two_factor",
            "message": "two_factor_code is required",
            "evidence_ref": "",
        }

    monkeypatch.setattr(x_auto_login, "run", fake_run)
    client = TestClient(app)
    response = client.post("/api/runtime/execute", json={"task": "x_auto_login", "credentials_ref": "/etc/myt/x_credentials.json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed_2fa_required"
    assert payload["checkpoint"] == "two_factor"
