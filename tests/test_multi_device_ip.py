from new.core.config_loader import ConfigLoader, get_device_ip, get_device_ips
from new.core.device_manager import DeviceManager


def test_get_device_ip_uses_mapping_then_fallback():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11", "2": "10.0.0.12"},
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
        }
        assert get_device_ips() == {"1": "10.0.0.21", "2": "10.0.0.22"}
    finally:
        ConfigLoader._config = backup


def test_device_manager_keeps_port_calc_and_uses_device_ip():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"2": "10.0.0.52"},
            "total_devices": 3,
        }
        info = DeviceManager().get_device_info(2)
        assert info["ip"] == "10.0.0.52"
        assert info["rpa_port"] == 30102
        assert info["api_port"] == 30101
    finally:
        ConfigLoader._config = backup
