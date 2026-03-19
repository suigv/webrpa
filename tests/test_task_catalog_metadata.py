from fastapi.testclient import TestClient

from api.server import app


def test_task_catalog_returns_input_metadata_for_new_device_plugin():
    client = TestClient(app)
    response = client.get("/api/tasks/catalog")

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    plugin = next(item for item in tasks if item["task"] == "one_click_new_device")

    assert plugin["display_name"] == "一键新机"
    assert plugin["distillable"] is False
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
