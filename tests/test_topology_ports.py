# pyright: reportPrivateUsage=false

import pytest

from core.config_loader import ConfigLoader
from core.device_manager import DeviceManager
from core.port_calc import build_task_port_map, calculate_ports


def test_allocator_deterministic_repeatability():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {"sdk_port": 8000}
        first = build_task_port_map(total_devices=3, cloud_machines_per_device=4)
        second = build_task_port_map(total_devices=3, cloud_machines_per_device=4)
        third = build_task_port_map(total_devices=3, cloud_machines_per_device=4)
        assert first == second == third
    finally:
        ConfigLoader._config = backup


def test_topology_unique_ports():
    """With new formula, ports are unique per cloud_index, not per device.

    Port = 30000 + (cloud_index - 1) * 100 + offset
    So cloud 1 → 30001/30002, cloud 2 → 30101/30102, etc.
    """
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {"sdk_port": 8000}
        total_devices = 5
        clouds = 7
        mapping = build_task_port_map(total_devices=total_devices, cloud_machines_per_device=clouds)

        # Verify ports don't conflict with SDK port
        for api_port, rpa_port in mapping.values():
            assert api_port != 8000
            assert rpa_port != 8000

        # With new formula, ports are determined by cloud_index only
        # So we expect exactly `clouds` unique port pairs, not `total_devices * clouds`
        port_pairs: set[tuple[int, int]] = set()
        for (_device_id, _cloud_id), (api_port, rpa_port) in mapping.items():
            port_pairs.add((api_port, rpa_port))

        # Each cloud should have its own unique port pair
        assert len(port_pairs) == clouds, f"Expected {clouds} unique port pairs, got {len(port_pairs)}"

        # Verify expected port pairs for each cloud
        expected = {
            1: (30001, 30002),
            2: (30101, 30102),
            3: (30201, 30202),
            4: (30301, 30302),
            5: (30401, 30402),
            6: (30501, 30502),
            7: (30601, 30602),
        }
        for cloud_id, (expected_api, expected_rpa) in expected.items():
            # All devices should have same ports for a given cloud
            for device_id in range(1, total_devices + 1):
                api_port, rpa_port = mapping[(device_id, cloud_id)]
                assert api_port == expected_api, f"cloud {cloud_id}: expected {expected_api}, got {api_port}"
                assert rpa_port == expected_rpa, f"cloud {cloud_id}: expected {expected_rpa}, got {rpa_port}"
    finally:
        ConfigLoader._config = backup


def test_device_manager_topology_validation_accepts_unique_ips():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11", "2": "10.0.0.12"},
            "total_devices": 2,
            "sdk_port": 8000,
        }
        manager = DeviceManager()
        manager.validate_topology_or_raise()
    finally:
        ConfigLoader._config = backup


def test_device_manager_topology_validation_rejects_duplicate_endpoints():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "host_ip": "10.0.0.1",
            "device_ips": {"1": "10.0.0.11", "2": "10.0.0.11"},
            "total_devices": 2,
            "sdk_port": 8000,
        }
        manager = DeviceManager()
        with pytest.raises(ValueError, match="duplicate endpoint"):
            manager.validate_topology_or_raise()
    finally:
        ConfigLoader._config = backup


def test_allocator_rejects_reserved_sdk_port_conflict():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {"sdk_port": 30001}
        with pytest.raises(ValueError, match="sdk_port"):
            _ = calculate_ports(device_index=1, cloud_index=1, cloud_machines_per_device=10)
    finally:
        ConfigLoader._config = backup


def test_allocator_depends_on_cloud_index_not_device_index():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {"sdk_port": 8000}
        assert calculate_ports(device_index=1, cloud_index=3, cloud_machines_per_device=12) == (30201, 30202)
        assert calculate_ports(device_index=9, cloud_index=3, cloud_machines_per_device=12) == (30201, 30202)
    finally:
        ConfigLoader._config = backup
