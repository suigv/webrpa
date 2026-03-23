# pyright: reportPrivateUsage=false

from typing import cast

from core.config_loader import ConfigLoader, get_device_ip, get_device_ips
from core.device_manager import DeviceManager
from core.port_calc import calculate_ports


def test_get_device_ip_uses_mapping_then_fallback(monkeypatch):
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11", "2": "10.0.0.12"},
            "cloud_machines_per_device": 12,
        }
        monkeypatch.setattr(
            "core.lan_discovery.LanDeviceDiscovery.get_discovered_device_map",
            lambda self: {},
        )
        assert get_device_ip(1) == "10.0.0.11"
        assert get_device_ip(2) == "10.0.0.12"
        assert get_device_ip(3) == "10.0.0.1"
    finally:
        ConfigLoader._config = backup


def test_get_device_ip_prefers_discovered_mapping(monkeypatch):
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11"},
            "total_devices": 1,
            "cloud_machines_per_device": 12,
        }
        monkeypatch.setattr(
            "core.lan_discovery.LanDeviceDiscovery.get_discovered_device_map",
            lambda self: {"1": "192.168.10.3"},
        )

        assert get_device_ip(1) == "192.168.10.3"
    finally:
        ConfigLoader._config = backup


def test_get_total_devices_prefers_discovered_mapping(monkeypatch):
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11", "2": "10.0.0.12"},
            "total_devices": 2,
            "cloud_machines_per_device": 12,
        }
        monkeypatch.setattr(
            "core.lan_discovery.LanDeviceDiscovery.get_discovered_device_map",
            lambda self: {"1": "192.168.10.3"},
        )

        from core.config_loader import get_total_devices

        assert get_total_devices() == 1
    finally:
        ConfigLoader._config = backup


def test_get_device_ips_supports_list_format():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": ["10.0.0.21", "10.0.0.22"],
            "cloud_machines_per_device": 12,
        }
        assert get_device_ips() == {"1": "10.0.0.21", "2": "10.0.0.22"}
    finally:
        ConfigLoader._config = backup


def test_device_manager_returns_nested_cloud_topology(monkeypatch):
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "10.0.0.1",
            "device_ips": {"2": "10.0.0.52"},
            "total_devices": 3,
            "cloud_machines_per_device": 12,
            "sdk_port": 8000,
        }
        monkeypatch.setattr(
            "core.lan_discovery.LanDeviceDiscovery.get_discovered_device_map",
            lambda self: {},
        )
        manager = DeviceManager()
        manager._device_snapshot_cache.clear()
        manager._device_snapshot_at.clear()
        snapshot = manager.get_devices_snapshot()
        device = next(entry for entry in snapshot if entry["device_id"] == 2)
        assert device["ip"] == "10.0.0.52"
        assert device["schema_version"] == 2
        assert device["allocation_version"] == 1

        clouds = cast(list[dict[str, object]], device["cloud_machines"])
        assert len(clouds) == 12
        api_port, rpa_port = calculate_ports(2, 1, 12)
        assert clouds[0]["cloud_id"] == 1
        assert clouds[0]["api_port"] == api_port
        assert clouds[0]["rpa_port"] == rpa_port
    finally:
        ConfigLoader._config = backup


def test_device_manager_syncs_device_count_from_config(monkeypatch):
    backup = ConfigLoader._config
    manager = DeviceManager()
    try:
        monkeypatch.setattr(
            "core.lan_discovery.LanDeviceDiscovery.get_discovered_device_map",
            lambda self: {},
        )
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {},
            "total_devices": 2,
            "cloud_machines_per_device": 12,
        }
        assert set(manager.get_all_devices().keys()) == {1, 2}

        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 12,
        }
        assert set(manager.get_all_devices().keys()) == {1}
    finally:
        ConfigLoader._config = backup
