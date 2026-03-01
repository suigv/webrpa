import logging
import threading
from datetime import datetime
from typing import Dict, Optional

from new.core.config_loader import (
    get_allocation_version,
    get_cloud_machines_per_device,
    get_device_ip,
    get_schema_version,
    get_sdk_port,
    get_stop_hour,
    get_total_devices,
)
from new.core.port_calc import calculate_ports
from new.models.device import AIType, DeviceStatus

logger = logging.getLogger(__name__)


class Device:
    def __init__(self, device_id: int, ai_type: AIType = AIType.VOLC):
        self.device_id = device_id
        self.ai_type = ai_type
        self.status = DeviceStatus.IDLE
        self.current_task: Optional[str] = None
        self.message: Optional[str] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.updated_at = datetime.now()


class DeviceManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._devices: Dict[int, Device] = {}
            self._devices_lock = threading.Lock()
            self._initialized = True

    def _sync_devices_with_config(self) -> None:
        total = get_total_devices()
        with self._devices_lock:
            existing = self._devices
            next_devices: Dict[int, Device] = {}
            for device_id in range(1, total + 1):
                next_devices[device_id] = existing.get(device_id, Device(device_id))
            self._devices = next_devices

    def get_device(self, device_id: int, ai_type: AIType = AIType.VOLC) -> Device:
        self._sync_devices_with_config()
        with self._devices_lock:
            if device_id not in self._devices:
                raise KeyError(f"device_id out of range: {device_id}")
            device = self._devices[device_id]
            device.ai_type = ai_type
            return device

    def get_all_devices(self) -> Dict[int, Device]:
        self._sync_devices_with_config()
        with self._devices_lock:
            return dict(self._devices)

    def get_device_info(self, device_id: int) -> dict[str, object]:
        device = self.get_device(device_id)
        cloud_machines_per_device = get_cloud_machines_per_device()

        clouds: list[dict[str, object]] = []
        for cloud_id in range(1, cloud_machines_per_device + 1):
            api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
            clouds.append(
                {
                    "cloud_id": cloud_id,
                    "api_port": api_port,
                    "rpa_port": rpa_port,
                    "status": device.status.value,
                }
            )

        return {
            "schema_version": get_schema_version(),
            "allocation_version": get_allocation_version(),
            "device_id": device_id,
            "ip": get_device_ip(device_id),
            "sdk_port": get_sdk_port(),
            "ai_type": device.ai_type.value,
            "status": device.status.value,
            "current_task": device.current_task,
            "message": device.message,
            "cloud_machines": clouds,
        }

    def set_device_status(
        self,
        device_id: int,
        status: DeviceStatus,
        task: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        with self._devices_lock:
            device = self._devices.get(device_id)
            if device is None:
                raise KeyError(f"device_id out of range: {device_id}")
            device.status = status
            if task is not None:
                device.current_task = task
            if message is not None:
                device.message = message
            device.updated_at = datetime.now()

    def validate_topology_or_raise(self) -> None:
        self._sync_devices_with_config()
        total_devices = get_total_devices()
        cloud_machines_per_device = get_cloud_machines_per_device()
        sdk_port = get_sdk_port()
        seen: set[tuple[str, int]] = set()

        expected_entries = total_devices * cloud_machines_per_device * 2
        actual_entries = 0

        for device_id in range(1, total_devices + 1):
            ip = get_device_ip(device_id)
            for cloud_id in range(1, cloud_machines_per_device + 1):
                api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
                for port in (api_port, rpa_port):
                    if port == sdk_port:
                        raise ValueError(f"task port conflicts with reserved sdk port {sdk_port}")
                    endpoint = (ip, port)
                    if endpoint in seen:
                        raise ValueError(f"duplicate endpoint detected: {endpoint}")
                    seen.add(endpoint)
                    actual_entries += 1

        if actual_entries != expected_entries:
            raise ValueError(
                f"invalid topology entry count, got={actual_entries}, expected={expected_entries}"
            )


def parse_device_range(device_str: str) -> list[int]:
    devices: set[int] = set()
    for part in device_str.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            devices.update(range(int(start), int(end) + 1))
        else:
            devices.add(int(token))
    return sorted(devices)


def parse_ai_type(ai_type: str) -> str:
    value = ai_type.lower().strip()
    if value in ["volc", "volcano", "huoshan"]:
        return "volc"
    if value in ["part_time", "parttime"]:
        return "part_time"
    return "volc"


def check_stop_condition(stop_hour: Optional[int] = None) -> bool:
    hour = get_stop_hour() if stop_hour is None else stop_hour
    return datetime.now().hour >= hour
