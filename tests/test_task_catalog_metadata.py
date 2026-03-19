from fastapi.testclient import TestClient

from api.routes import task_routes
from api.server import app


def test_task_catalog_returns_input_metadata_for_new_device_plugin():
    client = TestClient(app)
    response = client.get("/api/tasks/catalog")

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    assert all(item["task"] != "one_click_new_device" for item in tasks)

    hidden_response = client.get("/api/tasks/catalog?include_hidden=true")
    assert hidden_response.status_code == 200
    hidden_tasks = hidden_response.json()["tasks"]
    plugin = next(item for item in hidden_tasks if item["task"] == "one_click_new_device")

    assert plugin["display_name"] == "一键新机"
    assert plugin["description"]
    assert plugin["distillable"] is False
    assert plugin["visible_in_task_catalog"] is False
    inputs = plugin["inputs"]
    model_source = next(item for item in inputs if item["name"] == "model_source")
    assert model_source["widget"] == "select"
    assert model_source["label"] == "机型来源"
    assert [option["value"] for option in model_source["options"]] == ["online", "local"]

    take_screenshot = next(item for item in inputs if item["name"] == "take_screenshot")
    assert take_screenshot["type"] == "boolean"
    assert take_screenshot["advanced"] is True


def test_distill_endpoint_rejects_non_distillable_plugin():
    client = TestClient(app)
    response = client.post("/api/tasks/distill/one_click_new_device")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "distillation_not_supported"


def test_current_distill_endpoint_rejects_non_distillable_plugin():
    client = TestClient(app)
    response = client.post("/api/tasks/plugins/one_click_new_device/distill")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "distillation_not_supported"


def test_legacy_distill_threshold_payload_only_blocks_below_threshold():
    blocked = task_routes._legacy_distill_threshold_payload(
        plugin_name="demo_plugin",
        completed=1,
        threshold=3,
        force=False,
    )
    assert blocked is not None
    assert blocked["code"] == "threshold_not_met"

    allowed = task_routes._legacy_distill_threshold_payload(
        plugin_name="demo_plugin",
        completed=3,
        threshold=3,
        force=False,
    )
    assert allowed is None
