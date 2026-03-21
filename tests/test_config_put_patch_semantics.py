import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api.routes.config as config_route
import core.config_loader as config_loader
from api.server import app


def _seed_config(config_path: Path) -> dict[str, object]:
    payload = {
        "schema_version": 2,
        "allocation_version": 1,
        "host_ip": "192.168.1.214",
        "device_ips": {"1": "192.168.1.214"},
        "total_devices": 1,
        "sdk_port": 8000,
        "default_ai": "volc",
        "stop_hour": 21,
    }
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


@pytest.fixture
def config_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_path = tmp_path / "devices.json"
    seeded = _seed_config(config_path)

    backup_file = config_loader.CONFIG_FILE
    backup_cache = config_loader.ConfigLoader._config
    config_loader.CONFIG_FILE = config_path
    config_loader.ConfigLoader._config = dict(seeded)
    monkeypatch.setattr(config_route.LanDeviceDiscovery, "scan_now", lambda self: None)

    try:
        yield config_path
    finally:
        config_loader.CONFIG_FILE = backup_file
        config_loader.ConfigLoader._config = backup_cache


def test_config_put_omitted_stop_hour_preserves_persisted_value(config_storage: Path) -> None:
    client = TestClient(app)

    response = client.put("/api/config/", json={"default_ai": "openai"})

    assert response.status_code == 200
    payload = response.json()
    persisted = json.loads(config_storage.read_text(encoding="utf-8"))
    assert payload["default_ai"] == "openai"
    assert payload["stop_hour"] == 21
    assert persisted["default_ai"] == "openai"
    assert persisted["stop_hour"] == 21


def test_config_put_explicit_stop_hour_updates_persisted_value(config_storage: Path) -> None:
    client = TestClient(app)

    response = client.put("/api/config/", json={"stop_hour": 9})

    assert response.status_code == 200
    payload = response.json()
    persisted = json.loads(config_storage.read_text(encoding="utf-8"))
    assert payload["stop_hour"] == 9
    assert persisted["stop_hour"] == 9


def test_config_put_rejects_null_stop_hour_without_mutating_persisted_value(
    config_storage: Path,
) -> None:
    client = TestClient(app)

    response = client.put("/api/config/", json={"stop_hour": None})

    assert response.status_code == 422
    assert "stop_hour" in str(response.json().get("detail", ""))
    persisted = json.loads(config_storage.read_text(encoding="utf-8"))
    assert persisted["stop_hour"] == 21
    assert persisted["default_ai"] == "volc"
