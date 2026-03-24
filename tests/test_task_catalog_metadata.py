from types import SimpleNamespace

import pytest
import yaml
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


def test_task_catalog_exposes_builtin_pipeline_entry():
    client = TestClient(app)
    response = client.get("/api/tasks/catalog")

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    pipeline = next(item for item in tasks if item["task"] == "_pipeline")

    assert pipeline["display_name"] == "Pipeline 编排"
    assert pipeline["distillable"] is False
    assert pipeline["visible_in_task_catalog"] is True
    assert pipeline["required"] == ["steps"]
    inputs = {item["name"]: item for item in pipeline["inputs"]}
    assert inputs["steps"]["widget"] == "hidden"
    assert inputs["repeat"]["default"] == 1
    assert inputs["repeat_interval_ms"]["advanced"] is True


def test_task_catalog_exposes_app_config_explorer_plugin():
    client = TestClient(app)
    response = client.get("/api/tasks/catalog")

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    plugin = next(item for item in tasks if item["task"] == "app_config_explorer")

    assert plugin["display_name"] == "App 探索建档"
    assert plugin["distillable"] is False
    assert plugin["visible_in_task_catalog"] is True
    inputs = {item["name"]: item for item in plugin["inputs"]}
    assert "package_name" in plugin["required"]
    assert inputs["package_name"]["label"] == "包名"
    assert inputs["max_steps"]["default"] == 12
    assert inputs["advanced_prompt"]["advanced"] is True


def test_task_catalog_device_reboot_does_not_expose_app_id_input():
    client = TestClient(app)
    response = client.get("/api/tasks/catalog")

    assert response.status_code == 200
    tasks = response.json()["tasks"]
    plugin = next(item for item in tasks if item["task"] == "device_reboot")

    assert all(input_item["name"] != "app_id" for input_item in plugin["inputs"])


def test_current_distill_endpoint_rejects_non_distillable_plugin():
    client = TestClient(app)
    response = client.post("/api/tasks/plugins/one_click_new_device/distill")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["code"] == "distillation_not_supported"


def test_distill_threshold_payload_only_blocks_below_threshold():
    blocked = task_routes._distill_threshold_payload(
        plugin_name="demo_plugin",
        completed=1,
        threshold=3,
        force=False,
    )
    assert blocked is not None
    assert blocked["code"] == "threshold_not_met"

    allowed = task_routes._distill_threshold_payload(
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
            return SimpleNamespace(manifest=SimpleNamespace(distill_threshold=3, distillable=True))

    monkeypatch.setattr(task_routes, "get_task_controller", lambda: _Controller())
    monkeypatch.setattr(task_routes, "_plugin_loader", lambda refresh=False: _Loader())

    client = TestClient(app)
    response = client.post("/api/tasks/plugins/demo_plugin/distill")

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "code": "threshold_not_met",
        "message": "插件 demo_plugin 成功次数 2 未达到蒸馏门槛 3",
        "completed": 2,
        "threshold": 3,
    }


def test_distill_endpoint_clears_plugin_loader_cache_only_on_success(
    monkeypatch: pytest.MonkeyPatch,
):
    class _Controller:
        def plugin_success_counts(self):
            return [{"task_name": "demo_plugin", "completed": 3}]

    class _Loader:
        def get(self, name: str):
            if name != "demo_plugin":
                return None
            return SimpleNamespace(manifest=SimpleNamespace(distill_threshold=3, distillable=True))

    cleared: list[bool] = []

    monkeypatch.setattr(task_routes, "get_task_controller", lambda: _Controller())
    monkeypatch.setattr(task_routes, "_plugin_loader", lambda refresh=False: _Loader())
    monkeypatch.setattr(
        "engine.plugin_loader.clear_shared_plugin_loader_cache", lambda: cleared.append(True)
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )

    client = TestClient(app)
    response = client.post("/api/tasks/plugins/demo_plugin/distill")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert cleared == [True]


def test_task_catalog_apps_exposes_aliases_and_package_names(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    (apps_dir / "x.yaml").write_text(
        yaml.safe_dump(
            {
                "app_id": "x",
                "display_name": "X",
                "aliases": ["twitter"],
                "package_name": "com.twitter.android",
                "package_names": ["com.twitter.android", "com.twitter.android.beta"],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("core.app_config.config_dir", lambda: tmp_path)

    client = TestClient(app)
    response = client.get("/api/tasks/catalog/apps")

    assert response.status_code == 200
    apps = response.json()["apps"]
    x_app = next(item for item in apps if item["id"] == "x")
    assert x_app["display_name"] == "X"
    assert x_app["aliases"] == ["twitter"]
    assert x_app["package_name"] == "com.twitter.android"
    assert x_app["package_names"] == ["com.twitter.android", "com.twitter.android.beta"]
