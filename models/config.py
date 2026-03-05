from pydantic import BaseModel, Field, model_validator
from typing import Optional


class HumanizedConfig(BaseModel):
    enabled: bool = True
    typing_delay_min: float = Field(default=0.04, ge=0)
    typing_delay_max: float = Field(default=0.18, ge=0)
    typo_probability: float = Field(default=0.03, ge=0, le=1)
    typo_delay_min: float = Field(default=0.04, ge=0)
    typo_delay_max: float = Field(default=0.12, ge=0)
    backspace_delay_min: float = Field(default=0.02, ge=0)
    backspace_delay_max: float = Field(default=0.08, ge=0)
    click_offset_x_min: int = -4
    click_offset_x_max: int = 4
    click_offset_y_min: int = -4
    click_offset_y_max: int = 4
    move_duration_min: float = Field(default=0.20, ge=0)
    move_duration_max: float = Field(default=0.70, ge=0)
    move_steps_min: int = Field(default=8, ge=1)
    move_steps_max: int = Field(default=24, ge=1)
    random_seed: Optional[int] = None

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.typing_delay_min > self.typing_delay_max:
            raise ValueError("typing_delay_min must be <= typing_delay_max")
        if self.typo_delay_min > self.typo_delay_max:
            raise ValueError("typo_delay_min must be <= typo_delay_max")
        if self.backspace_delay_min > self.backspace_delay_max:
            raise ValueError("backspace_delay_min must be <= backspace_delay_max")
        if self.click_offset_x_min > self.click_offset_x_max:
            raise ValueError("click_offset_x_min must be <= click_offset_x_max")
        if self.click_offset_y_min > self.click_offset_y_max:
            raise ValueError("click_offset_y_min must be <= click_offset_y_max")
        if self.move_duration_min > self.move_duration_max:
            raise ValueError("move_duration_min must be <= move_duration_max")
        if self.move_steps_min > self.move_steps_max:
            raise ValueError("move_steps_min must be <= move_steps_max")
        return self


class Config(BaseModel):
    schema_version: int
    allocation_version: int
    host_ip: str
    device_ips: dict[str, str] = Field(default_factory=dict)
    total_devices: int
    discovery_enabled: bool = False
    discovery_subnet: str = ""
    discovered_device_ips: dict[str, str] = Field(default_factory=dict)
    discovered_total_devices: int = 0
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
    humanized: HumanizedConfig


class ConfigUpdate(BaseModel):
    schema_version: Optional[int] = None
    allocation_version: Optional[int] = None
    host_ip: Optional[str] = None
    device_ips: Optional[dict[str, str]] = None
    total_devices: Optional[int] = None
    discovery_enabled: Optional[bool] = None
    discovery_subnet: Optional[str] = None
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
    humanized: Optional[HumanizedConfig] = None
