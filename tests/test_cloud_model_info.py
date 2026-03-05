import time
from typing import Any, cast

from new.core.config_loader import ConfigLoader
from new.core.device_manager import DeviceManager
from new.hardware_adapters.myt_client import BaseHTTPClient


def test_device_manager_loads_cloud_model_from_sdk_android_list(monkeypatch):
    backup = ConfigLoader._config
    manager = DeviceManager()
    manager.stop_cloud_probe_worker()
    calls: list[tuple[str, int, str]] = []

    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 3,
            "sdk_port": 8000,
        }
        now = time.time()
        with manager._probe_lock:
            manager._probe_cache.clear()
            for cloud_id in range(1, 13):
                manager._probe_cache[(1, cloud_id)] = {
                    "state": "available" if cloud_id == 1 else "unavailable",
                    "success_streak": 2 if cloud_id == 1 else 0,
                    "failure_streak": 0 if cloud_id == 1 else 3,
                    "state_changed_at": now,
                    "last_checked_at": now,
                    "latency_ms": 30,
                    "reason": "ok" if cloud_id == 1 else "connect_failed",
                }
        with manager._cloud_model_lock:
            manager._cloud_model_cache.clear()

        def fake_get(self, path, query=None):
            del query
            calls.append((self.host, self.port, path))
            if path == "/android":
                return {
                    "ok": True,
                    "data": {
                        "list": [
                            {
                                "id": "cloud-id-1",
                                "modelPath": "Pixel 7",
                                "portBindings": {
                                    "9082/tcp": [{"HostPort": "30001"}],
                                },
                            }
                        ]
                    },
                }
            return {"ok": False, "error": "unsupported"}

        monkeypatch.setattr(BaseHTTPClient, "get", fake_get)

        info = manager.get_device_info(1, availability="available_only")
        clouds = cast(list[dict[str, Any]], info["cloud_machines"])

        assert len(clouds) == 1
        assert clouds[0]["cloud_id"] == 1
        assert clouds[0]["machine_model_name"] == "Pixel 7"
        assert clouds[0]["machine_model_id"] == "cloud-id-1"
        assert calls == [("127.0.0.1", 8000, "/android")]

        _ = manager.get_device_info(1, availability="available_only")
        assert calls == [("127.0.0.1", 8000, "/android")]
    finally:
        ConfigLoader._config = backup


def test_device_manager_skips_invalid_host_port_from_android_response(monkeypatch):
    backup = ConfigLoader._config
    manager = DeviceManager()
    manager.stop_cloud_probe_worker()

    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 1,
            "sdk_port": 8000,
        }
        with manager._cloud_model_lock:
            manager._cloud_model_cache.clear()

        def fake_get(self, path, query=None):
            del self, query
            if path == "/android":
                return {
                    "ok": True,
                    "data": {
                        "list": [
                            {
                                "id": "broken",
                                "modelPath": "Invalid Model",
                                "portBindings": {
                                    "9082/tcp": [{"HostPort": "not-a-number"}],
                                },
                            }
                        ]
                    },
                }
            return {"ok": False, "error": "unsupported"}

        monkeypatch.setattr(BaseHTTPClient, "get", fake_get)

        info = manager.get_device_info(1)
        clouds = cast(list[dict[str, Any]], info["cloud_machines"])

        assert len(clouds) >= 1
        assert all(cloud["machine_model_name"] is None for cloud in clouds)
        assert all(cloud["machine_model_id"] is None for cloud in clouds)
    finally:
        ConfigLoader._config = backup
