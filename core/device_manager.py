import logging
import threading
from datetime import datetime
from typing import Dict, Optional

from new.core.config_loader import get_device_ip, get_stop_hour, get_total_devices
from new.core.port_calc import calculate_ports
from new.models.device import AIType, DeviceStatus

logger = logging.getLogger(__name__)


class Device:
    def __init__(self, index: int, ai_type: AIType = AIType.VOLC):
        self.index = index
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

    def get_device(self, index: int, ai_type: AIType = AIType.VOLC) -> Device:
        with self._devices_lock:
            if index not in self._devices:
                self._devices[index] = Device(index, ai_type)
            return self._devices[index]

    def get_all_devices(self) -> Dict[int, Device]:
        with self._devices_lock:
            if not self._devices:
                total = get_total_devices()
                for index in range(1, total + 1):
                    self._devices[index] = Device(index)
            return dict(self._devices)

    def get_device_info(self, index: int) -> dict[str, object]:
        device = self.get_device(index)
        rpa_port, api_port = calculate_ports(index)
        return {
            "index": index,
            "ip": get_device_ip(index),
            "rpa_port": rpa_port,
            "api_port": api_port,
            "ai_type": device.ai_type.value,
            "status": device.status.value,
            "current_task": device.current_task,
            "message": device.message,
        }

    def set_device_status(
        self,
        index: int,
        status: DeviceStatus,
        task: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        with self._devices_lock:
            device = self._devices.get(index)
            if device is None:
                device = Device(index)
                self._devices[index] = device
            device.status = status
            if task is not None:
                device.current_task = task
            if message is not None:
                device.message = message
            device.updated_at = datetime.now()


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
