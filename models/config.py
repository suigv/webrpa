from pydantic import BaseModel, Field
from typing import Optional


class Config(BaseModel):
    schema_version: int
    allocation_version: int
    host_ip: str
    device_ips: dict[str, str] = Field(default_factory=dict)
    total_devices: int
    cloud_machines_per_device: int
    sdk_port: int
    default_ai: str
    stop_hour: int
    cycle_interval: int
    judge_mode: str
    step_parallel: int
    vision_monitor_enabled: bool
    vision_device_type: str
    vision_pipeline_type: str
    vision_model_name: str
    vision_thought_language: str
    vision_timeout_seconds: int
    vision_cooldown_ms: int
    vision_dedupe_window_ms: int
    vision_max_fallback_per_step: int
    humanization_enabled: bool
    humanization_intensity: int
    humanization_seed: int
    humanization_delay_ms: int
    humanization_jitter_ms: int


class ConfigUpdate(BaseModel):
    schema_version: Optional[int] = None
    allocation_version: Optional[int] = None
    host_ip: Optional[str] = None
    device_ips: Optional[dict[str, str]] = None
    total_devices: Optional[int] = None
    cloud_machines_per_device: Optional[int] = None
    sdk_port: Optional[int] = None
    default_ai: Optional[str] = None
    stop_hour: Optional[int] = None
    cycle_interval: Optional[int] = None
    judge_mode: Optional[str] = None
    step_parallel: Optional[int] = None
    vision_monitor_enabled: Optional[bool] = None
    vision_device_type: Optional[str] = None
    vision_pipeline_type: Optional[str] = None
    vision_model_name: Optional[str] = None
    vision_thought_language: Optional[str] = None
    vision_timeout_seconds: Optional[int] = None
    vision_cooldown_ms: Optional[int] = None
    vision_dedupe_window_ms: Optional[int] = None
    vision_max_fallback_per_step: Optional[int] = None
    humanization_enabled: Optional[bool] = None
    humanization_intensity: Optional[int] = None
    humanization_seed: Optional[int] = None
    humanization_delay_ms: Optional[int] = None
    humanization_jitter_ms: Optional[int] = None
