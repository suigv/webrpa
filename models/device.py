from enum import Enum
from typing import Optional

from pydantic import BaseModel


class AIType(str, Enum):
    VOLC = "volc"
    PART_TIME = "part_time"


class DeviceStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    OFFLINE = "offline"
    ERROR = "error"


class DeviceInfo(BaseModel):
    index: int
    ip: str
    rpa_port: int
    api_port: int
    ai_type: AIType
    status: DeviceStatus = DeviceStatus.IDLE


class DeviceStatusResponse(BaseModel):
    index: int
    status: DeviceStatus
    current_task: Optional[str] = None
    message: Optional[str] = None
