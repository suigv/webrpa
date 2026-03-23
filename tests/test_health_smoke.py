from api.routes import engine_routes
from api.server import browser_diagnostics, health


def test_health_endpoint():
    payload = health()
    assert payload["status"] == "ok"
    assert payload["runtime"] == "skeleton"
    assert "task_policy" in payload
    assert isinstance(payload["task_policy"]["strict_plugin_unknown_inputs"], bool)
    assert isinstance(payload["task_policy"]["stale_running_seconds"], int)


def test_health_endpoint_exposes_policy_from_env(monkeypatch):
    monkeypatch.setenv("MYT_STRICT_PLUGIN_UNKNOWN_INPUTS", "off")
    monkeypatch.setenv("MYT_TASK_STALE_RUNNING_SECONDS", "not-a-number")

    payload = health()

    assert payload["task_policy"]["strict_plugin_unknown_inputs"] is False
    assert payload["task_policy"]["stale_running_seconds"] == 300


def test_health_endpoint_clamps_negative_stale_threshold(monkeypatch):
    monkeypatch.setenv("MYT_TASK_STALE_RUNNING_SECONDS", "-10")

    payload = health()

    assert payload["task_policy"]["stale_running_seconds"] == 0


def test_browser_diagnostics_endpoint():
    payload = browser_diagnostics()
    assert "ready" in payload
    assert "error" in payload
    assert "error_code" in payload
    assert "drissionget_importable" in payload
    assert "drissionpage_importable" in payload
    assert "chromium_binary_found" in payload


def test_engine_schema_endpoint_returns_metadata_catalog():
    payload = engine_routes.get_action_schema()

    assert "ui.click" in payload
    assert "core.save_shared" in payload


def test_engine_skills_endpoint_returns_skill_tagged_actions_only():
    payload = engine_routes.get_skill_schema()

    assert "ui.click" in payload
    assert "core.save_shared" in payload
    assert all("skill" in list(item.tags or []) for item in payload.values())


def test_engine_schema_endpoint_supports_tag_filtering():
    payload = engine_routes.get_action_schema(tag="skill")

    assert "ui.click" in payload
    assert all("skill" in list(item.tags or []) for item in payload.values())
