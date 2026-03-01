import pytest

from new.core.config_loader import ConfigLoader
from new.core.port_calc import build_task_port_map, calculate_ports


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
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {"sdk_port": 8000}
        total_devices = 5
        clouds = 7
        mapping = build_task_port_map(total_devices=total_devices, cloud_machines_per_device=clouds)
        unique_ports: set[int] = set()
        for api_port, rpa_port in mapping.values():
            unique_ports.add(api_port)
            unique_ports.add(rpa_port)
            assert api_port != 8000
            assert rpa_port != 8000
        assert len(unique_ports) == total_devices * clouds * 2
    finally:
        ConfigLoader._config = backup


def test_allocator_rejects_reserved_sdk_port_conflict():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {"sdk_port": 30001}
        with pytest.raises(ValueError, match="sdk_port"):
            calculate_ports(device_index=1, cloud_index=1, cloud_machines_per_device=10)
    finally:
        ConfigLoader._config = backup
