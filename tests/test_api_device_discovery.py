# pyright: reportPrivateUsage=false

from contextlib import asynccontextmanager
from typing import cast

from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

import api.server as server
from api.routes import devices as devices_route
from api.server import app
from core.config_loader import ConfigLoader
from core.device_manager import DeviceManager
from core.port_calc import calculate_ports


class _FakeProbeService:
    def __init__(self, model_map: dict[int, dict[str, object]]):
        self.model_map: dict[int, dict[str, object]] = model_map
        self.calls: list[tuple[str, bool]] = []
        self.started: int = 0
        self.stopped: int = 0

    def query_cloud_model_map(
        self, device_ip: str, refresh_if_missing: bool = False
    ) -> dict[int, dict[str, object]]:
        self.calls.append((device_ip, refresh_if_missing))
        return self.model_map

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class _FakeDeviceManager:
    def __init__(self) -> None:
        self.validated: int = 0

    def validate_topology_or_raise(self) -> None:
        self.validated += 1


class _FakeEvents:
    def __init__(self) -> None:
        self.subscribers: list[object] = []

    def subscribe(self, callback: object) -> None:
        self.subscribers.append(callback)


class _FakeController:
    def __init__(self) -> None:
        self._events: _FakeEvents = _FakeEvents()
        self.started: int = 0
        self.stopped: int = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class _FakeDiscovery:
    def __init__(self) -> None:
        self.started: int = 0
        self.stopped: int = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def _reset_manager_state(manager: DeviceManager) -> None:
    with manager._probe_lock:
        manager._probe_cache.clear()
    with manager._device_snapshot_lock:
        manager._device_snapshot_cache.clear()
        manager._device_snapshot_at.clear()
    with manager._devices_lock:
        manager._devices = {}


def _scan_two_ips(force: bool = False) -> list[str]:
    return ["192.168.1.214", "192.168.1.216"] if force else []


def _scan_one_ip(force: bool = False) -> list[str]:
    return ["192.168.1.214"] if force else []


@asynccontextmanager
async def _noop_lifespan(_app: object):
    yield


def _disable_lifespan(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(app.router, "lifespan_context", _noop_lifespan)


def _patch_lifespan_services(
    monkeypatch: MonkeyPatch,
) -> tuple[_FakeController, _FakeDeviceManager, _FakeProbeService]:
    fake_controller = _FakeController()
    fake_manager = _FakeDeviceManager()
    fake_probe = _FakeProbeService({})

    monkeypatch.setattr(server, "get_task_controller", lambda: fake_controller)
    monkeypatch.setattr(server, "get_device_manager", lambda: fake_manager)
    monkeypatch.setattr(server, "get_cloud_probe_service", lambda: fake_probe)
    return fake_controller, fake_manager, fake_probe


def test_api_devices_discover_endpoint(monkeypatch: MonkeyPatch):
    _disable_lifespan(monkeypatch)
    monkeypatch.setattr(devices_route.discovery, "scan_now", _scan_two_ips)
    with TestClient(app) as client:
        response = client.post("/api/devices/discover")
        assert response.status_code == 200
        payload = cast(dict[str, object], response.json())
        assert payload["status"] == "started"
        assert "message" in payload


def test_api_devices_discover_updates_config_mapping(monkeypatch: MonkeyPatch):
    _disable_lifespan(monkeypatch)
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "192.168.1.214",
            "device_ips": {"1": "192.168.1.214", "2": "192.168.1.215"},
            "total_devices": 2,
            "sdk_port": 8000,
            "discovery_enabled": False,
            "discovery_subnet": "192.168.1.0/24",
        }
        monkeypatch.setattr(devices_route.discovery, "scan_now", _scan_one_ip)

        with TestClient(app) as client:
            response = client.post("/api/devices/discover")
            assert response.status_code == 200
            payload = cast(dict[str, object], response.json())
            assert payload["status"] == "started"

            cfg = cast(dict[str, object], client.get("/api/config/").json())
            assert cfg["total_devices"] == 1
            assert cfg["device_ips"] == {"1": "192.168.1.214"}
    finally:
        ConfigLoader._config = backup


def test_api_devices_list_preserves_payload_shape_for_available_only(monkeypatch: MonkeyPatch):
    _disable_lifespan(monkeypatch)
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11"},
            "total_devices": 1,
            "sdk_port": 8000,
            "cloud_machines_per_device": 1,
        }
        monkeypatch.setattr("core.device_manager.get_cloud_machines_per_device", lambda: 1)
        manager = DeviceManager()
        _reset_manager_state(manager)

        api_port, _rpa_port = calculate_ports(1, 1, 1)
        fake_probe = _FakeProbeService(
            {
                api_port: {
                    "machine_model_name": "Pixel 9",
                    "machine_model_id": "model-1",
                }
            }
        )
        monkeypatch.setattr("core.cloud_probe_service.get_cloud_probe_service", lambda: fake_probe)

        manager._update_probe_cache(1, 1, True, 11, "ok")

        with TestClient(app) as client:
            response = client.get("/api/devices/?availability=available_only")
            assert response.status_code == 200
            payload = cast(list[dict[str, object]], response.json())

        assert len(payload) == 1
        device = payload[0]
        assert set(device) == {
            "schema_version",
            "allocation_version",
            "device_id",
            "ip",
            "sdk_port",
            "sdk_port_role",
            "ai_type",
            "status",
            "cloud_slots_total",
            "available_cloud_count",
            "probe_stale",
            "probe_partial",
            "cloud_machines",
        }
        assert device["sdk_port_role"] == "device_control_api"
        assert device["available_cloud_count"] == 1
        assert "current_task" not in device
        assert "message" not in device

        clouds = cast(list[dict[str, object]], device["cloud_machines"])
        assert len(clouds) == 1
        cloud = clouds[0]
        assert set(cloud) == {
            "cloud_id",
            "api_port",
            "api_port_role",
            "rpa_port",
            "rpa_port_role",
            "status",
            "availability_state",
            "availability_reason",
            "last_checked_at",
            "latency_ms",
            "stale",
            "machine_model_name",
            "machine_model_id",
        }
        assert cloud["api_port_role"] == "cloud_api"
        assert cloud["rpa_port_role"] == "mytrpc_control"
        assert cloud["availability_reason"] == "ok"
        assert isinstance(cloud["last_checked_at"], str)
        assert cloud["machine_model_name"] == "Pixel 9"
        assert cloud["machine_model_id"] == "model-1"
        assert "streak_up" not in cloud
        assert "streak_down" not in cloud
        assert fake_probe.calls == [("10.0.0.11", False)]
    finally:
        ConfigLoader._config = backup


def test_api_devices_available_only_filters_out_devices_without_available_clouds(
    monkeypatch: MonkeyPatch,
):
    _disable_lifespan(monkeypatch)
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11"},
            "total_devices": 1,
            "sdk_port": 8000,
            "cloud_machines_per_device": 1,
        }
        manager = DeviceManager()
        _reset_manager_state(manager)

        with TestClient(app) as client:
            response = client.get("/api/devices/?availability=available_only")
            assert response.status_code == 200
            payload = cast(list[dict[str, object]], response.json())

        assert len(payload) == 1
        device = payload[0]
        assert device["available_cloud_count"] == 0
        assert device["cloud_machines"] == []
    finally:
        ConfigLoader._config = backup


def test_api_lifespan_wires_cloud_probe_service(monkeypatch: MonkeyPatch):
    fake_controller, fake_manager, fake_probe = _patch_lifespan_services(monkeypatch)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200

    assert fake_manager.validated == 1
    assert fake_controller.started == 1
    assert fake_controller.stopped == 1
    assert fake_probe.started == 1
    assert fake_probe.stopped == 1
    assert len(fake_controller._events.subscribers) == 1
