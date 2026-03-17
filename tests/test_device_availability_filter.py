# pyright: reportPrivateUsage=false

import threading
from typing import cast

from _pytest.monkeypatch import MonkeyPatch

from core.cloud_probe_service import CloudProbeService
from core.config_loader import ConfigLoader
from core.device_manager import DeviceManager
from core.port_calc import calculate_ports


class _FakeProbeService:
    def __init__(self, model_map: dict[int, dict[str, object]]):
        self.model_map: dict[int, dict[str, object]] = model_map
        self.calls: list[tuple[str, bool]] = []

    def query_cloud_model_map(
        self, device_ip: str, refresh_if_missing: bool = False
    ) -> dict[int, dict[str, object]]:
        self.calls.append((device_ip, refresh_if_missing))
        return self.model_map


class _ProbeManager:
    def __init__(self) -> None:
        self.updates: list[tuple[int, int, bool, int | None, str]] = []
        self.refresh_called: bool = False

    def _update_probe_cache(
        self, device_id: int, cloud_id: int, ok: bool, latency_ms: int | None, reason: str
    ) -> None:
        self.updates.append((device_id, cloud_id, ok, latency_ms, reason))

    def _refresh_device_snapshots(self) -> None:
        self.refresh_called = True

    def update_cloud_probe(
        self, device_id: int, cloud_id: int, ok: bool, latency_ms: int | None, reason: str
    ) -> None:
        self._update_probe_cache(device_id, cloud_id, ok, latency_ms, reason)

    def refresh_device_snapshots(self) -> None:
        self._refresh_device_snapshots()


def _reset_manager_state(manager: DeviceManager) -> None:
    with manager._probe_lock:
        manager._probe_cache.clear()
    with manager._device_snapshot_lock:
        manager._device_snapshot_cache.clear()
        manager._device_snapshot_at.clear()
    with manager._devices_lock:
        manager._devices = {}


def test_device_snapshot_filters_available_clouds_and_uses_probe_service_model_map(
    monkeypatch: MonkeyPatch,
):
    backup = ConfigLoader._config
    manager = DeviceManager()
    try:
        _reset_manager_state(manager)
        monkeypatch.setattr("core.device_manager.get_cloud_machines_per_device", lambda: 2)
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11"},
            "total_devices": 1,
            "cloud_machines_per_device": 2,
            "sdk_port": 8000,
        }

        api_port, _rpa_port = calculate_ports(1, 1, 2)
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
        manager._update_probe_cache(1, 2, False, 70, "connect_failed")

        snapshot = manager.get_devices_snapshot(availability="available_only")
        assert len(snapshot) == 1
        device = snapshot[0]
        assert device["available_cloud_count"] == 1

        clouds = cast(list[dict[str, object]], device["cloud_machines"])
        assert len(clouds) == 1
        cloud = clouds[0]
        assert cloud["cloud_id"] == 1
        assert cloud["availability_state"] == "available"
        assert cloud["availability_reason"] == "ok"
        assert isinstance(cloud["last_checked_at"], str)
        assert cloud["machine_model_name"] == "Pixel 9"
        assert cloud["machine_model_id"] == "model-1"
        assert fake_probe.calls == [("10.0.0.11", False)]
    finally:
        ConfigLoader._config = backup


def test_cloud_probe_service_drives_probe_cache_updates(monkeypatch: MonkeyPatch):
    backup = ConfigLoader._config
    try:
        monkeypatch.setattr("core.cloud_probe_service.get_cloud_machines_per_device", lambda: 1)
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11"},
            "total_devices": 1,
            "cloud_machines_per_device": 1,
            "sdk_port": 8000,
        }

        service = CloudProbeService()
        manager = _ProbeManager()

        def _fake_probe_rpa_port(_ip: str, _port: int) -> tuple[bool, int, str]:
            return True, 5, "ok"

        monkeypatch.setattr(service, "_probe_rpa_port", _fake_probe_rpa_port)

        model_calls: list[tuple[str, bool]] = []
        model_lock = threading.Lock()

        def _record_model_call(
            device_ip: str, refresh_if_missing: bool = False
        ) -> dict[int, dict[str, object]]:
            with model_lock:
                model_calls.append((device_ip, refresh_if_missing))
            return {}

        monkeypatch.setattr(service, "query_cloud_model_map", _record_model_call)

        service._run_probe_sweep(manager)

        cloud_count = 1
        expected_updates = [(1, cloud_id, True, 5, "ok") for cloud_id in range(1, cloud_count + 1)]
        assert manager.updates == expected_updates
        assert manager.refresh_called is True
        assert model_calls == [("10.0.0.11", True)]
    finally:
        ConfigLoader._config = backup


def test_mark_cloud_released_does_not_overwrite_probe_unavailable_state(monkeypatch: MonkeyPatch):
    backup = ConfigLoader._config
    manager = DeviceManager()
    try:
        _reset_manager_state(manager)
        monkeypatch.setattr("core.device_manager.get_cloud_machines_per_device", lambda: 1)
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11"},
            "total_devices": 1,
            "cloud_machines_per_device": 1,
            "sdk_port": 8000,
        }
        monkeypatch.setattr(
            "core.cloud_probe_service.get_cloud_probe_service", lambda: _FakeProbeService({})
        )

        manager.update_cloud_probe(1, 1, False, 11, "connect_failed")
        manager.update_cloud_probe(1, 1, False, 12, "connect_failed")
        before = manager.get_cloud_probe_snapshot(1, 1)
        assert before["availability_state"] == "unavailable"

        manager.mark_cloud_released(1, 1)

        after = manager.get_cloud_probe_snapshot(1, 1)
        assert after["availability_state"] == "unavailable"
        assert after["availability_reason"] == "connect_failed"
    finally:
        ConfigLoader._config = backup
