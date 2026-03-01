from new.core.config_loader import get_sdk_port

BASE_PORT = 30000
PORT_STEP = 10


def calculate_ports(device_index: int, cloud_index: int, cloud_machines_per_device: int) -> tuple[int, int]:
    if device_index < 1:
        raise ValueError("device_index must be >= 1")
    if cloud_index < 1:
        raise ValueError("cloud_index must be >= 1")
    if cloud_machines_per_device < 1:
        raise ValueError("cloud_machines_per_device must be >= 1")

    global_index = (device_index - 1) * cloud_machines_per_device + (cloud_index - 1)
    base_port = BASE_PORT + global_index * PORT_STEP
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
