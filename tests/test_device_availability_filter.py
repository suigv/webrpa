import time
from typing import Any, cast

from new.core.config_loader import ConfigLoader
from new.core.device_manager import DeviceManager


def test_device_info_available_only_filters_by_probe_cache():
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
            "cloud_machines_per_device": 3,
            "sdk_port": 8000,
        }

        now = time.time()
        with manager._probe_lock:
            manager._probe_cache.clear()
            for cloud_id in range(1, 13):
                manager._probe_cache[(1, cloud_id)] = {
                    "state": "available" if cloud_id == 2 else "unavailable",
                    "success_streak": 2 if cloud_id == 2 else 0,
                    "failure_streak": 0 if cloud_id == 2 else 3,
                    "state_changed_at": now,
                    "last_checked_at": now,
                    "latency_ms": 50,
                    "reason": "ok" if cloud_id == 2 else "connect_failed",
                }

        all_info = manager.get_device_info(1, availability="all")
        only_available_info = manager.get_device_info(1, availability="available_only")

        assert all_info["cloud_slots_total"] == 12
        all_clouds = cast(list[dict[str, Any]], all_info["cloud_machines"])
        available_clouds = cast(list[dict[str, Any]], only_available_info["cloud_machines"])

        assert len(all_clouds) == 12
        assert all_info["available_cloud_count"] == 1

        assert len(available_clouds) == 1
        assert available_clouds[0]["cloud_id"] == 2
        assert available_clouds[0]["availability_state"] == "available"
    finally:
        ConfigLoader._config = backup
