from new.core.config_loader import get_sdk_port

BASE_PORT = 30000
PORT_STEP = 100


def calculate_ports(device_index: int, cloud_index: int, cloud_machines_per_device: int) -> tuple[int, int]:
    """Calculate API and RPA ports for a given cloud machine.

    Port roles:
        api_port  — Cloud machine HTTP API interface (e.g. 30001)
        rpa_port  — MytRpc control channel for touch/app/key operations (e.g. 30002)
        sdk_port  — Device-level control API, shared across all clouds (default 8000)

    Port is determined ONLY by cloud_index, not device_index.
    Each device has a different IP, so identical ports on different devices don't conflict.

    Formula:
        base_port = 30000 + (cloud_index - 1) * 100
        api_port  = base_port + 1   (cloud API)
        rpa_port  = base_port + 2   (MytRpc control)

    Example (cloud_machines_per_device=10):
        cloud 1  → api 30001, rpa 30002
        cloud 2  → api 30101, rpa 30102
        cloud 10 → api 30901, rpa 30902
    """
    if device_index < 1:
        raise ValueError("device_index must be >= 1")
    if cloud_index < 1:
        raise ValueError("cloud_index must be >= 1")
    if cloud_machines_per_device < 1:
        raise ValueError("cloud_machines_per_device must be >= 1")

    # Port determined by cloud_index only, not device_index
    base_port = BASE_PORT + (cloud_index - 1) * PORT_STEP
    api_port = base_port + 1
    rpa_port = base_port + 2
    sdk_port = get_sdk_port()

    for port in (api_port, rpa_port):
        if port == sdk_port:
            raise ValueError(f"allocated task port conflicts with sdk_port={sdk_port}")
        if not 1 <= port <= 65535:
            raise ValueError(f"allocated task port out of range: {port}")

    return api_port, rpa_port


def build_task_port_map(total_devices: int, cloud_machines_per_device: int) -> dict[tuple[int, int], tuple[int, int]]:
    if total_devices < 1:
        raise ValueError("total_devices must be >= 1")
    result: dict[tuple[int, int], tuple[int, int]] = {}
    for device_id in range(1, total_devices + 1):
        for cloud_id in range(1, cloud_machines_per_device + 1):
            result[(device_id, cloud_id)] = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
    return result
