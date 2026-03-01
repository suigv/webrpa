from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AIType(str, Enum):
    VOLC = "volc"
    PART_TIME = "part_time"


class DeviceStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    OFFLINE = "offline"
    ERROR = "error"


class CloudMachineInfo(BaseModel):
    cloud_id: int
    api_port: int
    rpa_port: int
    status: DeviceStatus = DeviceStatus.IDLE


class DeviceInfo(BaseModel):
    schema_version: int
    allocation_version: int
    device_id: int
    ip: str
    sdk_port: int = 8000
    ai_type: AIType
    status: DeviceStatus = DeviceStatus.IDLE
    cloud_machines: list[CloudMachineInfo] = Field(default_factory=list)


class DeviceStatusResponse(BaseModel):
    device_id: int
    status: DeviceStatus
    current_task: Optional[str] = None
    message: Optional[str] = None
