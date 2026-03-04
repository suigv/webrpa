import pytest

from new.core.config_loader import ConfigLoader
from new.core.device_manager import DeviceManager


def test_startup_fails_on_port_collision():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 2,
            "sdk_port": 30001,
        }
        with pytest.raises(ValueError, match="sdk"):
            DeviceManager().validate_topology_or_raise()
    finally:
        ConfigLoader._config = backup


def test_startup_validation_passes_for_valid_topology():
    """With new formula (port determined by cloud only), devices need different IPs.
    
    This is because: device 1 cloud 1 → 30001, device 2 cloud 1 → 30001 (same port).
    If all devices share the same IP, ports would conflict.
    """
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "127.0.0.1",
            # Different IPs for different devices - required for new port formula
            "device_ips": {
                "1": "10.0.0.1",
                "2": "10.0.0.2",
                "3": "10.0.0.3",
            },
            "total_devices": 3,
            "cloud_machines_per_device": 4,
            "sdk_port": 8000,
        }
        # Should not raise - endpoints are unique (different IPs)
        DeviceManager().validate_topology_or_raise()
    finally:
        ConfigLoader._config = backup
