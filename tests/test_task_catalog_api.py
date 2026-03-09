from fastapi.testclient import TestClient

from api.server import app
from core.task_control import get_task_controller, reset_task_controller_for_tests
from engine.plugin_loader import clear_shared_plugin_loader_cache


def _write_plugin(plugins_root, name: str) -> None:
    plugin_dir = plugins_root / name
    plugin_dir.mkdir()
    (plugin_dir / "manifest.yaml").write_text(
        f"api_version: v1\nkind: plugin\nname: {name}\nversion: '1.0'\ndisplay_name: {name}\n",
        encoding="utf-8",
    )
    (plugin_dir / "script.yaml").write_text(
        f"version: v1\nworkflow: {name}\nsteps:\n  - kind: stop\n    status: success\n    message: ok\n",
        encoding="utf-8",
    )


def test_task_catalog_endpoint_returns_migrated_tasks():
    client = TestClient(app)
    resp = client.get("/api/tasks/catalog")
    assert resp.status_code == 200
    data = resp.json()
    names = {item["task"] for item in data.get("tasks", [])}
    assert "device_reboot" in names
    assert "device_soft_reset" in names
    assert "x_mobile_login" in names
    reboot_item = next(item for item in data["tasks"] if item["task"] == "device_reboot")
    assert "example_payload" in reboot_item
    assert "device_ip" in reboot_item["example_payload"]


def test_task_catalog_refresh_updates_existing_controller_runner(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.plugin_loader._default_plugins_root", lambda: tmp_path)
    clear_shared_plugin_loader_cache()
    reset_task_controller_for_tests()

    try:
        controller = get_task_controller()
        initial = controller._runner.run({"task": "late_plugin"})
        assert initial["code"] == "unsupported_task"

        _write_plugin(tmp_path, "late_plugin")

        client = TestClient(app)
        resp = client.get("/api/tasks/catalog")
        assert resp.status_code == 200
        tasks = {item["task"] for item in resp.json()["tasks"]}
        assert "late_plugin" in tasks

        runtime = controller._runner.run({"task": "late_plugin"})
        assert runtime["ok"] is True
        assert runtime["status"] == "success"
    finally:
        reset_task_controller_for_tests()
        clear_shared_plugin_loader_cache()
