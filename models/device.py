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
    """Port info for a single cloud machine instance."""

    cloud_id: int
    api_port: int = Field(description="Cloud machine HTTP API interface")
    api_port_role: str = Field(default="cloud_api", description="Role of api_port")
    rpa_port: int = Field(description="MytRpc control channel (touch/app/key operations)")
    rpa_port_role: str = Field(default="mytrpc_control", description="Role of rpa_port")
    status: DeviceStatus = DeviceStatus.IDLE


class DeviceInfo(BaseModel):
    schema_version: int
    allocation_version: int
    device_id: int
    ip: str
    sdk_port: int = Field(default=8000, description="Device-level control API port, shared across all clouds")
    sdk_port_role: str = Field(default="device_control_api", description="Role of sdk_port")
    ai_type: AIType
    status: DeviceStatus = DeviceStatus.IDLE
    cloud_machines: list[CloudMachineInfo] = Field(default_factory=list)


class DeviceStatusResponse(BaseModel):
    device_id: int
    status: DeviceStatus
    current_task: Optional[str] = None
    message: Optional[str] = None
