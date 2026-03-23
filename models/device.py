from enum import StrEnum

from pydantic import BaseModel, Field


class DeviceStatus(StrEnum):
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
    availability_state: str = Field(default="unknown")
    availability_reason: str | None = None
    last_checked_at: str | None = None
    latency_ms: int | None = None
    stale: bool = False
    machine_model_name: str | None = None
    machine_model_id: str | None = None


class DeviceInfo(BaseModel):
    schema_version: int
    allocation_version: int
    device_id: int
    ip: str
    sdk_port: int = Field(
        default=8000, description="Device-level control API port, shared across all clouds"
    )
    sdk_port_role: str = Field(default="device_control_api", description="Role of sdk_port")
    status: DeviceStatus = DeviceStatus.IDLE
    cloud_slots_total: int = 12
    available_cloud_count: int = 0
    probe_stale: bool = False
    probe_partial: bool = False
    cloud_machines: list[CloudMachineInfo] = Field(default_factory=list)


class DeviceStatusResponse(BaseModel):
    device_id: int
    status: DeviceStatus
    current_task: str | None = None
    message: str | None = None
