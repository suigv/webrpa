from fastapi.testclient import TestClient

from new.api.server import app


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
