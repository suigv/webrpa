from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.routes import task_routes
from api.server import app


def test_task_catalog_returns_input_metadata_for_new_device_plugin():
    client = TestClient(app)
    response = client.get("/api/tasks/catalog")

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    plugin = next(item for item in tasks if item["task"] == "one_click_new_device")

    assert plugin["display_name"] == "一键新机"
    assert plugin["description"]
    assert plugin["distillable"] is False
    assert plugin["visible_in_task_catalog"] is True
    inputs = plugin["inputs"]
    model_source = next(item for item in inputs if item["name"] == "model_source")
    assert model_source["widget"] == "select"
    assert model_source["label"] == "机型来源"
    assert [option["value"] for option in model_source["options"]] == ["online", "local"]

    take_screenshot = next(item for item in inputs if item["name"] == "take_screenshot")
    assert take_screenshot["type"] == "boolean"
    assert take_screenshot["advanced"] is True
    assert all(item["name"] != "app_id" for item in inputs)


def test_task_catalog_device_reboot_does_not_expose_app_id_input():
    client = TestClient(app)
    response = client.get("/api/tasks/catalog")

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    plugin = next(item for item in tasks if item["task"] == "device_reboot")

    assert all(input_item["name"] != "app_id" for input_item in plugin["inputs"])


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


def test_plugin_metrics_route_preserves_row_shape_while_enriching_metadata(
    monkeypatch: pytest.MonkeyPatch,
):
    class _Controller:
        def plugin_success_counts(self):
            return [{"task_name": "demo_plugin", "completed": "2", "label": "demo"}]

    monkeypatch.setattr(task_routes, "get_task_controller", lambda: _Controller())
    monkeypatch.setattr(task_routes, "_distill_threshold_for", lambda name: 3)
    monkeypatch.setattr(task_routes, "_plugin_distillable", lambda name: True)
    monkeypatch.setattr(task_routes, "_plugin_visible_in_task_catalog", lambda name: False)

    client = TestClient(app)
    response = client.get("/api/tasks/metrics/plugins")

    assert response.status_code == 200
    assert response.json() == [
        {
            "task_name": "demo_plugin",
            "completed": "2",
            "label": "demo",
            "distillable": True,
            "visible_in_task_catalog": False,
            "distill_threshold": 3,
            "distill_ready": False,
            "distill_remaining": 1,
        }
    ]


def test_distill_endpoint_keeps_threshold_payload_when_completed_count_is_string(
    monkeypatch: pytest.MonkeyPatch,
):
    class _Controller:
        def plugin_success_counts(self):
            return [{"task_name": "demo_plugin", "completed": "2"}]

    class _Loader:
        def get(self, name: str):
            if name != "demo_plugin":
                return None
            return SimpleNamespace(
                manifest=SimpleNamespace(distill_threshold=3, distillable=True)
            )

    monkeypatch.setattr(task_routes, "get_task_controller", lambda: _Controller())
    monkeypatch.setattr(task_routes, "_plugin_loader", lambda refresh=False: _Loader())

    client = TestClient(app)
    response = client.post("/api/tasks/distill/demo_plugin")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "code": "threshold_not_met",
        "message": "插件 demo_plugin 成功次数 2 未达到蒸馏门槛 3",
        "completed": 2,
        "threshold": 3,
    }
