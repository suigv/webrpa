from fastapi.testclient import TestClient

from api.server import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["runtime"] == "skeleton"
    assert "task_policy" in payload
    assert isinstance(payload["task_policy"]["strict_plugin_unknown_inputs"], bool)
    assert isinstance(payload["task_policy"]["stale_running_seconds"], int)


def test_health_endpoint_exposes_policy_from_env(monkeypatch):
    monkeypatch.setenv("MYT_STRICT_PLUGIN_UNKNOWN_INPUTS", "off")
    monkeypatch.setenv("MYT_TASK_STALE_RUNNING_SECONDS", "not-a-number")

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_policy"]["strict_plugin_unknown_inputs"] is False
    assert payload["task_policy"]["stale_running_seconds"] == 300


def test_health_endpoint_clamps_negative_stale_threshold(monkeypatch):
    monkeypatch.setenv("MYT_TASK_STALE_RUNNING_SECONDS", "-10")

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_policy"]["stale_running_seconds"] == 0


def test_browser_diagnostics_endpoint():
    client = TestClient(app)
    response = client.get("/api/diagnostics/browser")
    assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "error" in payload
    assert "error_code" in payload
    assert "drissionget_importable" in payload
    assert "drissionpage_importable" in payload
    assert "chromium_binary_found" in payload


def test_engine_schema_endpoint_returns_metadata_catalog():
    client = TestClient(app)
    response = client.get("/api/engine/schema")

    assert response.status_code == 200
    payload = response.json()
    assert "ui.click" in payload
    assert "core.save_shared" in payload


def test_engine_skills_endpoint_returns_skill_tagged_actions_only():
    client = TestClient(app)
    response = client.get("/api/engine/skills")

    assert response.status_code == 200
    payload = response.json()
    assert "ui.click" in payload
    assert "core.save_shared" in payload
    assert all("skill" in item.get("tags", []) for item in payload.values())


def test_engine_schema_endpoint_supports_tag_filtering():
    client = TestClient(app)
    response = client.get("/api/engine/schema", params={"tag": "skill"})

    assert response.status_code == 200
    payload = response.json()
    assert "ui.click" in payload
    assert all("skill" in item.get("tags", []) for item in payload.values())
