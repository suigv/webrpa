import pytest

from new.core.config_loader import ConfigLoader, get_device_ip, get_device_ips
from new.core.device_manager import DeviceManager


def test_get_device_ip_uses_mapping_then_fallback():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11", "2": "10.0.0.12"},
            "cloud_machines_per_device": 10,
        }
        assert get_device_ip(1) == "10.0.0.11"
        assert get_device_ip(2) == "10.0.0.12"
        assert get_device_ip(3) == "10.0.0.1"
    finally:
        ConfigLoader._config = backup


def test_get_device_ips_supports_list_format():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": ["10.0.0.21", "10.0.0.22"],
            "cloud_machines_per_device": 10,
        }
        assert get_device_ips() == {"1": "10.0.0.21", "2": "10.0.0.22"}
    finally:
        ConfigLoader._config = backup


def test_device_manager_returns_nested_cloud_topology():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "10.0.0.1",
            "device_ips": {"2": "10.0.0.52"},
            "total_devices": 3,
            "cloud_machines_per_device": 10,
            "sdk_port": 8000,
        }
        manager = DeviceManager()
        info = manager.get_device_info(2)
        assert info["device_id"] == 2
        assert info["ip"] == "10.0.0.52"
        assert info["schema_version"] == 2
        assert info["allocation_version"] == 1
        assert info["sdk_port"] == 8000
        clouds = info["cloud_machines"]
        assert len(clouds) == 10
        assert clouds[0]["cloud_id"] == 1
        assert clouds[0]["api_port"] == 30101
        assert clouds[0]["rpa_port"] == 30102
    finally:
        ConfigLoader._config = backup


def test_device_manager_rejects_unknown_device_id():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {},
            "total_devices": 2,
            "cloud_machines_per_device": 10,
        }
        manager = DeviceManager()
        with pytest.raises(KeyError):
            manager.get_device(3)
    finally:
        ConfigLoader._config = backup
