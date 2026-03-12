# pyright: reportDeprecated=false, reportUnusedImport=false, reportUnusedFunction=false
from __future__ import annotations

import ipaddress
from typing import Any, Callable, ClassVar, Optional, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.humanized import FALLBACK_POLICIES, TARGET_STRATEGIES, HumanizedWrapperConfig

DEFAULT_SCHEMA_VERSION = 2
DEFAULT_ALLOCATION_VERSION = 1
DEFAULT_CLOUD_MACHINES_PER_DEVICE = 12
DEFAULT_SDK_PORT = 8000
DEFAULT_HOST_IP = "127.0.0.1"
DEFAULT_TOTAL_DEVICES = 1
DEFAULT_DEFAULT_AI = "volc"
DEFAULT_STOP_HOUR = 18
DEFAULT_CYCLE_INTERVAL = 15
DEFAULT_JUDGE_MODE = "lite"
DEFAULT_STEP_PARALLEL = 4
DEFAULT_VISION_MONITOR_ENABLED = False
DEFAULT_VISION_DEVICE_TYPE = "mobile"
DEFAULT_VISION_PIPELINE_TYPE = "agent"
DEFAULT_VISION_MODEL_NAME = ""
DEFAULT_VISION_THOUGHT_LANGUAGE = "chinese"
DEFAULT_VISION_TIMEOUT_SECONDS = 8
DEFAULT_VISION_COOLDOWN_MS = 3000
DEFAULT_VISION_DEDUPE_WINDOW_MS = 5000
DEFAULT_VISION_MAX_FALLBACK_PER_STEP = 2
DEFAULT_HUMANIZATION_INTENSITY = 50
DEFAULT_HUMANIZATION_SEED = 0
DEFAULT_HUMANIZATION_DELAY_MS = 0
DEFAULT_HUMANIZATION_JITTER_MS = 0


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, (int, float, str, bool)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _coerce_optional_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float, str, bool)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _coerce_float(value: object, default: float) -> float:
    if isinstance(value, (int, float, str, bool)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _normalize_device_ips(raw: object) -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(raw, dict):
        raw_dict = cast(dict[object, object], raw)
        for key, value in raw_dict.items():
            key_str = str(key).strip()
            value_str = str(value).strip()
            if key_str and value_str:
                result[key_str] = value_str
        return result
    if isinstance(raw, (list, tuple)):
        raw_list = cast(list[object], raw)
        for index, value in enumerate(raw_list, start=1):
            value_str = str(value).strip()
            if value_str:
                result[str(index)] = value_str
        return result
    return result


DEFAULT_HUMANIZED_CONFIG = HumanizedWrapperConfig()


class HumanizedRuntimeConfigSchema(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    @field_validator("random_seed", mode="before")
    @classmethod
    def coerce_random_seed(cls, v: object) -> object:
        if v is None:
            return v
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    enabled: bool = DEFAULT_HUMANIZED_CONFIG.enabled
    typing_delay_min: float = DEFAULT_HUMANIZED_CONFIG.typing_delay_min
    typing_delay_max: float = DEFAULT_HUMANIZED_CONFIG.typing_delay_max
    typo_probability: float = DEFAULT_HUMANIZED_CONFIG.typo_probability
    typo_delay_min: float = DEFAULT_HUMANIZED_CONFIG.typo_delay_min
    typo_delay_max: float = DEFAULT_HUMANIZED_CONFIG.typo_delay_max
    backspace_delay_min: float = DEFAULT_HUMANIZED_CONFIG.backspace_delay_min
    backspace_delay_max: float = DEFAULT_HUMANIZED_CONFIG.backspace_delay_max
    word_pause_probability: float = DEFAULT_HUMANIZED_CONFIG.word_pause_probability
    word_pause_min: float = DEFAULT_HUMANIZED_CONFIG.word_pause_min
    word_pause_max: float = DEFAULT_HUMANIZED_CONFIG.word_pause_max

    click_offset_x_min: int = DEFAULT_HUMANIZED_CONFIG.click_offset_x_min
    click_offset_x_max: int = DEFAULT_HUMANIZED_CONFIG.click_offset_x_max
    click_offset_y_min: int = DEFAULT_HUMANIZED_CONFIG.click_offset_y_min
    click_offset_y_max: int = DEFAULT_HUMANIZED_CONFIG.click_offset_y_max
    pre_click_pause_min: float = DEFAULT_HUMANIZED_CONFIG.pre_click_pause_min
    pre_click_pause_max: float = DEFAULT_HUMANIZED_CONFIG.pre_click_pause_max
    click_hold_min: float = DEFAULT_HUMANIZED_CONFIG.click_hold_min
    click_hold_max: float = DEFAULT_HUMANIZED_CONFIG.click_hold_max
    post_click_pause_min: float = DEFAULT_HUMANIZED_CONFIG.post_click_pause_min
    post_click_pause_max: float = DEFAULT_HUMANIZED_CONFIG.post_click_pause_max

    target_strategy: str = DEFAULT_HUMANIZED_CONFIG.target_strategy
    target_center_bias_probability: float = DEFAULT_HUMANIZED_CONFIG.target_center_bias_probability
    pre_hover_enabled: bool = DEFAULT_HUMANIZED_CONFIG.pre_hover_enabled
    pre_hover_delay_min: float = DEFAULT_HUMANIZED_CONFIG.pre_hover_delay_min
    pre_hover_delay_max: float = DEFAULT_HUMANIZED_CONFIG.pre_hover_delay_max
    movement_jitter_probability: float = DEFAULT_HUMANIZED_CONFIG.movement_jitter_probability
    movement_overshoot_probability: float = DEFAULT_HUMANIZED_CONFIG.movement_overshoot_probability

    move_duration_min: float = DEFAULT_HUMANIZED_CONFIG.move_duration_min
    move_duration_max: float = DEFAULT_HUMANIZED_CONFIG.move_duration_max
    move_steps_min: int = DEFAULT_HUMANIZED_CONFIG.move_steps_min
    move_steps_max: int = DEFAULT_HUMANIZED_CONFIG.move_steps_max

    fallback_policy: str = DEFAULT_HUMANIZED_CONFIG.fallback_policy
    fallback_retry_count: int = DEFAULT_HUMANIZED_CONFIG.fallback_retry_count
    random_seed: Optional[int] = DEFAULT_HUMANIZED_CONFIG.random_seed

    @model_validator(mode="after")
    def validate_ranges(self):
        # Clamp probabilities to [0, 1]
        self.typo_probability = max(0.0, min(1.0, self.typo_probability))
        self.word_pause_probability = max(0.0, min(1.0, self.word_pause_probability))
        self.target_center_bias_probability = max(0.0, min(1.0, self.target_center_bias_probability))
        self.movement_jitter_probability = max(0.0, min(1.0, self.movement_jitter_probability))
        self.movement_overshoot_probability = max(0.0, min(1.0, self.movement_overshoot_probability))

        # Clamp move_steps to >= 1
        self.move_steps_min = max(1, self.move_steps_min)
        self.move_steps_max = max(1, self.move_steps_max)
        if self.move_steps_min > self.move_steps_max:
            self.move_steps_max = self.move_steps_min

        # Clamp fallback_retry_count to >= 0
        self.fallback_retry_count = max(0, self.fallback_retry_count)

        # Normalize min/max pairs: if min > max, set max = min
        if self.typing_delay_min > self.typing_delay_max:
            self.typing_delay_max = self.typing_delay_min
        if self.typo_delay_min > self.typo_delay_max:
            self.typo_delay_max = self.typo_delay_min
        if self.backspace_delay_min > self.backspace_delay_max:
            self.backspace_delay_max = self.backspace_delay_min
        if self.word_pause_min > self.word_pause_max:
            self.word_pause_max = self.word_pause_min
        if self.click_offset_x_min > self.click_offset_x_max:
            self.click_offset_x_max = self.click_offset_x_min
        if self.click_offset_y_min > self.click_offset_y_max:
            self.click_offset_y_max = self.click_offset_y_min
        if self.pre_click_pause_min > self.pre_click_pause_max:
            self.pre_click_pause_max = self.pre_click_pause_min
        if self.click_hold_min > self.click_hold_max:
            self.click_hold_max = self.click_hold_min
        if self.post_click_pause_min > self.post_click_pause_max:
            self.post_click_pause_max = self.post_click_pause_min
        if self.pre_hover_delay_min > self.pre_hover_delay_max:
            self.pre_hover_delay_max = self.pre_hover_delay_min
        if self.move_duration_min > self.move_duration_max:
            self.move_duration_max = self.move_duration_min

        # Fallback invalid enum values to defaults
        if self.target_strategy not in TARGET_STRATEGIES:
            self.target_strategy = "center_bias"
        if self.fallback_policy not in FALLBACK_POLICIES:
            self.fallback_policy = "raw"

        return self


class HumanizedConfigSchema(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    enabled: bool = True

    @field_validator("random_seed", mode="before")
    @classmethod
    def coerce_random_seed(cls, v: object) -> object:
        if v is None:
            return v
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    typing_delay_min: float = Field(default=0.04, ge=0)
    typing_delay_max: float = Field(default=0.18, ge=0)
    typo_probability: float = Field(default=0.03, ge=0, le=1)
    typo_delay_min: float = Field(default=0.04, ge=0)
    typo_delay_max: float = Field(default=0.12, ge=0)
    backspace_delay_min: float = Field(default=0.02, ge=0)
    backspace_delay_max: float = Field(default=0.08, ge=0)
    word_pause_probability: float = Field(default=0.04, ge=0, le=1)
    word_pause_min: float = Field(default=0.08, ge=0)
    word_pause_max: float = Field(default=0.24, ge=0)

    click_offset_x_min: int = -4
    click_offset_x_max: int = 4
    click_offset_y_min: int = -4
    click_offset_y_max: int = 4
    pre_click_pause_min: float = Field(default=0.02, ge=0)
    pre_click_pause_max: float = Field(default=0.10, ge=0)
    click_hold_min: float = Field(default=0.01, ge=0)
    click_hold_max: float = Field(default=0.05, ge=0)
    post_click_pause_min: float = Field(default=0.02, ge=0)
    post_click_pause_max: float = Field(default=0.08, ge=0)

    target_strategy: str = "center_bias"
    target_center_bias_probability: float = Field(default=0.85, ge=0, le=1)
    move_duration_min: float = Field(default=0.20, ge=0)
    move_duration_max: float = Field(default=0.70, ge=0)
    move_steps_min: int = Field(default=8, ge=1)
    move_steps_max: int = Field(default=24, ge=1)

    random_seed: Optional[int] = None

    @model_validator(mode="after")
    def validate_ranges(self):
        # Clamp probabilities
        self.typo_probability = max(0.0, min(1.0, self.typo_probability))
        self.word_pause_probability = max(0.0, min(1.0, self.word_pause_probability))
        self.target_center_bias_probability = max(0.0, min(1.0, self.target_center_bias_probability))
        # Clamp move_steps to >= 1
        self.move_steps_min = max(1, self.move_steps_min)
        self.move_steps_max = max(1, self.move_steps_max)
        # Normalize min/max pairs
        if self.typing_delay_min > self.typing_delay_max:
            self.typing_delay_max = self.typing_delay_min
        if self.typo_delay_min > self.typo_delay_max:
            self.typo_delay_max = self.typo_delay_min
        if self.backspace_delay_min > self.backspace_delay_max:
            self.backspace_delay_max = self.backspace_delay_min
        if self.word_pause_min > self.word_pause_max:
            self.word_pause_max = self.word_pause_min
        if self.click_offset_x_min > self.click_offset_x_max:
            self.click_offset_x_max = self.click_offset_x_min
        if self.click_offset_y_min > self.click_offset_y_max:
            self.click_offset_y_max = self.click_offset_y_min
        if self.pre_click_pause_min > self.pre_click_pause_max:
            self.pre_click_pause_max = self.pre_click_pause_min
        if self.click_hold_min > self.click_hold_max:
            self.click_hold_max = self.click_hold_min
        if self.post_click_pause_min > self.post_click_pause_max:
            self.post_click_pause_max = self.post_click_pause_min
        if self.move_duration_min > self.move_duration_max:
            self.move_duration_max = self.move_duration_min
        if self.move_steps_min > self.move_steps_max:
            self.move_steps_max = self.move_steps_min
        return self


def _build_humanized_source(raw: object, legacy: dict[str, object]) -> dict[str, object]:
    source: dict[str, object]
    if isinstance(raw, (HumanizedConfigSchema, HumanizedRuntimeConfigSchema)):
        source = cast(dict[str, object], raw.model_dump())
    elif isinstance(raw, dict):
        raw_dict = cast(dict[object, object], raw)
        source = {str(key): value for key, value in raw_dict.items()}
    else:
        source = {}

    if "enabled" not in source and "humanization_enabled" in legacy:
        source["enabled"] = _coerce_bool(legacy.get("humanization_enabled"), True)
    if "random_seed" not in source:
        if "humanization_seed" in legacy:
            source["random_seed"] = _coerce_int(legacy.get("humanization_seed"), DEFAULT_HUMANIZATION_SEED)
    else:
        random_seed_raw = source.get("random_seed")
        if random_seed_raw in ("", "null") and "humanization_seed" in legacy:
            source["random_seed"] = _coerce_int(legacy.get("humanization_seed"), DEFAULT_HUMANIZATION_SEED)
    return source


def _normalize_humanized(raw: object, legacy: dict[str, object]) -> HumanizedConfigSchema:
    source = _build_humanized_source(raw, legacy)
    try:
        return HumanizedConfigSchema.model_validate(source)
    except Exception:
        return HumanizedConfigSchema()


def _normalize_humanized_runtime(raw: object, legacy: dict[str, object]) -> HumanizedRuntimeConfigSchema:
    source = _build_humanized_source(raw, legacy)
    try:
        return HumanizedRuntimeConfigSchema.model_validate(source)
    except Exception:
        return HumanizedRuntimeConfigSchema()


def _normalize_config_payload(raw: dict[str, object], humanized: BaseModel) -> dict[str, object]:
    normalized: dict[str, object] = dict(raw)

    host_ip = str(raw.get("host_ip", DEFAULT_HOST_IP))
    normalized["host_ip"] = host_ip
    normalized["device_ips"] = _normalize_device_ips(raw.get("device_ips", {}))

    discovery_enabled = _coerce_bool(raw.get("discovery_enabled", False), False)
    normalized["discovery_enabled"] = discovery_enabled

    discovery_subnet_raw = str(raw.get("discovery_subnet", "")).strip()
    if not discovery_subnet_raw:
        discovery_subnet_raw = f"{host_ip}/24"
    try:
        subnet = ipaddress.ip_network(discovery_subnet_raw, strict=False)
        normalized["discovery_subnet"] = str(subnet)
    except Exception:
        normalized["discovery_subnet"] = f"{host_ip}/24"

    total_devices = _coerce_int(raw.get("total_devices", DEFAULT_TOTAL_DEVICES), DEFAULT_TOTAL_DEVICES)
    normalized["total_devices"] = max(1, total_devices)

    cloud_machines_per_device = _coerce_int(
        raw.get("cloud_machines_per_device", DEFAULT_CLOUD_MACHINES_PER_DEVICE),
        DEFAULT_CLOUD_MACHINES_PER_DEVICE,
    )
    normalized["cloud_machines_per_device"] = max(1, cloud_machines_per_device)

    schema_version = _coerce_int(raw.get("schema_version", DEFAULT_SCHEMA_VERSION), DEFAULT_SCHEMA_VERSION)
    normalized["schema_version"] = max(1, schema_version)

    allocation_version = _coerce_int(raw.get("allocation_version", DEFAULT_ALLOCATION_VERSION), DEFAULT_ALLOCATION_VERSION)
    normalized["allocation_version"] = max(1, allocation_version)

    sdk_port = _coerce_int(raw.get("sdk_port", DEFAULT_SDK_PORT), DEFAULT_SDK_PORT)
    if not (1 <= sdk_port <= 65535):
        sdk_port = DEFAULT_SDK_PORT
    normalized["sdk_port"] = sdk_port

    normalized["default_ai"] = str(raw.get("default_ai", DEFAULT_DEFAULT_AI))
    stop_hour = _coerce_optional_int(raw.get("stop_hour"))
    if stop_hour is None or not (0 <= stop_hour <= 23):
        stop_hour = DEFAULT_STOP_HOUR
    normalized["stop_hour"] = stop_hour

    cycle_interval = _coerce_int(raw.get("cycle_interval", DEFAULT_CYCLE_INTERVAL), DEFAULT_CYCLE_INTERVAL)
    if not (1 <= cycle_interval <= 3600):
        cycle_interval = DEFAULT_CYCLE_INTERVAL
    normalized["cycle_interval"] = cycle_interval

    judge_mode_raw = str(raw.get("judge_mode", DEFAULT_JUDGE_MODE)).strip().lower()
    normalized["judge_mode"] = judge_mode_raw if judge_mode_raw in {"off", "lite", "full"} else DEFAULT_JUDGE_MODE

    step_parallel = _coerce_int(raw.get("step_parallel", DEFAULT_STEP_PARALLEL), DEFAULT_STEP_PARALLEL)
    if not (1 <= step_parallel <= 64):
        step_parallel = DEFAULT_STEP_PARALLEL
    normalized["step_parallel"] = step_parallel

    normalized["vision_monitor_enabled"] = _coerce_bool(
        raw.get("vision_monitor_enabled", DEFAULT_VISION_MONITOR_ENABLED),
        DEFAULT_VISION_MONITOR_ENABLED,
    )
    normalized["vision_device_type"] = str(raw.get("vision_device_type", DEFAULT_VISION_DEVICE_TYPE))
    normalized["vision_pipeline_type"] = str(raw.get("vision_pipeline_type", DEFAULT_VISION_PIPELINE_TYPE))
    normalized["vision_model_name"] = str(raw.get("vision_model_name", DEFAULT_VISION_MODEL_NAME))
    normalized["vision_thought_language"] = str(raw.get("vision_thought_language", DEFAULT_VISION_THOUGHT_LANGUAGE))
    normalized["vision_timeout_seconds"] = _coerce_int(
        raw.get("vision_timeout_seconds", DEFAULT_VISION_TIMEOUT_SECONDS),
        DEFAULT_VISION_TIMEOUT_SECONDS,
    )
    normalized["vision_cooldown_ms"] = _coerce_int(
        raw.get("vision_cooldown_ms", DEFAULT_VISION_COOLDOWN_MS),
        DEFAULT_VISION_COOLDOWN_MS,
    )
    normalized["vision_dedupe_window_ms"] = _coerce_int(
        raw.get("vision_dedupe_window_ms", DEFAULT_VISION_DEDUPE_WINDOW_MS),
        DEFAULT_VISION_DEDUPE_WINDOW_MS,
    )
    normalized["vision_max_fallback_per_step"] = _coerce_int(
        raw.get("vision_max_fallback_per_step", DEFAULT_VISION_MAX_FALLBACK_PER_STEP),
        DEFAULT_VISION_MAX_FALLBACK_PER_STEP,
    )

    normalized["humanized"] = humanized

    enabled_value = getattr(humanized, "enabled", True)
    normalized["humanization_enabled"] = bool(enabled_value)
    seed_value = getattr(humanized, "random_seed", None)
    normalized["humanization_seed"] = seed_value if seed_value is not None else DEFAULT_HUMANIZATION_SEED
    normalized["humanization_intensity"] = _coerce_int(
        raw.get("humanization_intensity", DEFAULT_HUMANIZATION_INTENSITY),
        DEFAULT_HUMANIZATION_INTENSITY,
    )
    normalized["humanization_delay_ms"] = _coerce_int(
        raw.get("humanization_delay_ms", DEFAULT_HUMANIZATION_DELAY_MS),
        DEFAULT_HUMANIZATION_DELAY_MS,
    )
    normalized["humanization_jitter_ms"] = _coerce_int(
        raw.get("humanization_jitter_ms", DEFAULT_HUMANIZATION_JITTER_MS),
        DEFAULT_HUMANIZATION_JITTER_MS,
    )

    return normalized


class Config(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    schema_version: int = DEFAULT_SCHEMA_VERSION
    allocation_version: int = DEFAULT_ALLOCATION_VERSION
    host_ip: str = DEFAULT_HOST_IP
    device_ips: dict[str, str] = Field(default_factory=dict)
    total_devices: int = DEFAULT_TOTAL_DEVICES
    discovery_enabled: bool = False
    discovery_subnet: str = ""
    discovered_device_ips: dict[str, str] = Field(default_factory=dict)
    discovered_total_devices: int = 0
    cloud_machines_per_device: int = DEFAULT_CLOUD_MACHINES_PER_DEVICE
    sdk_port: int = DEFAULT_SDK_PORT
    default_ai: str = DEFAULT_DEFAULT_AI
    stop_hour: Optional[int] = DEFAULT_STOP_HOUR
    cycle_interval: int = DEFAULT_CYCLE_INTERVAL
    judge_mode: str = DEFAULT_JUDGE_MODE
    step_parallel: int = DEFAULT_STEP_PARALLEL
    vision_monitor_enabled: bool = DEFAULT_VISION_MONITOR_ENABLED
    vision_device_type: str = DEFAULT_VISION_DEVICE_TYPE
    vision_pipeline_type: str = DEFAULT_VISION_PIPELINE_TYPE
    vision_model_name: str = DEFAULT_VISION_MODEL_NAME
    vision_thought_language: str = DEFAULT_VISION_THOUGHT_LANGUAGE
    vision_timeout_seconds: int = DEFAULT_VISION_TIMEOUT_SECONDS
    vision_cooldown_ms: int = DEFAULT_VISION_COOLDOWN_MS
    vision_dedupe_window_ms: int = DEFAULT_VISION_DEDUPE_WINDOW_MS
    vision_max_fallback_per_step: int = DEFAULT_VISION_MAX_FALLBACK_PER_STEP
    humanization_enabled: bool = True
    humanization_intensity: int = DEFAULT_HUMANIZATION_INTENSITY
    humanization_seed: int = DEFAULT_HUMANIZATION_SEED
    humanization_delay_ms: int = DEFAULT_HUMANIZATION_DELAY_MS
    humanization_jitter_ms: int = DEFAULT_HUMANIZATION_JITTER_MS
    humanized: HumanizedConfigSchema | HumanizedRuntimeConfigSchema = Field(default_factory=HumanizedConfigSchema)

    @model_validator(mode="before")
    @classmethod
    def normalize_config(cls, data: object):
        if not isinstance(data, dict):
            return data

        raw = cast(dict[str, object], data)
        humanized = _normalize_humanized(raw.get("humanized"), raw)
        return _normalize_config_payload(raw, humanized)


class ConfigStore(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    schema_version: int = DEFAULT_SCHEMA_VERSION
    allocation_version: int = DEFAULT_ALLOCATION_VERSION
    host_ip: str = DEFAULT_HOST_IP
    device_ips: dict[str, str] = Field(default_factory=dict)
    total_devices: int = DEFAULT_TOTAL_DEVICES
    discovery_enabled: bool = False
    discovery_subnet: str = ""
    discovered_device_ips: dict[str, str] = Field(default_factory=dict)
    discovered_total_devices: int = 0
    cloud_machines_per_device: int = DEFAULT_CLOUD_MACHINES_PER_DEVICE
    sdk_port: int = DEFAULT_SDK_PORT
    default_ai: str = DEFAULT_DEFAULT_AI
    stop_hour: Optional[int] = DEFAULT_STOP_HOUR
    cycle_interval: int = DEFAULT_CYCLE_INTERVAL
    judge_mode: str = DEFAULT_JUDGE_MODE
    step_parallel: int = DEFAULT_STEP_PARALLEL
    vision_monitor_enabled: bool = DEFAULT_VISION_MONITOR_ENABLED
    vision_device_type: str = DEFAULT_VISION_DEVICE_TYPE
    vision_pipeline_type: str = DEFAULT_VISION_PIPELINE_TYPE
    vision_model_name: str = DEFAULT_VISION_MODEL_NAME
    vision_thought_language: str = DEFAULT_VISION_THOUGHT_LANGUAGE
    vision_timeout_seconds: int = DEFAULT_VISION_TIMEOUT_SECONDS
    vision_cooldown_ms: int = DEFAULT_VISION_COOLDOWN_MS
    vision_dedupe_window_ms: int = DEFAULT_VISION_DEDUPE_WINDOW_MS
    vision_max_fallback_per_step: int = DEFAULT_VISION_MAX_FALLBACK_PER_STEP
    humanization_enabled: bool = True
    humanization_intensity: int = DEFAULT_HUMANIZATION_INTENSITY
    humanization_seed: int = DEFAULT_HUMANIZATION_SEED
    humanization_delay_ms: int = DEFAULT_HUMANIZATION_DELAY_MS
    humanization_jitter_ms: int = DEFAULT_HUMANIZATION_JITTER_MS
    humanized: HumanizedRuntimeConfigSchema = Field(default_factory=HumanizedRuntimeConfigSchema)

    @model_validator(mode="before")
    @classmethod
    def normalize_config(cls, data: object):
        if not isinstance(data, dict):
            return data

        raw = cast(dict[str, object], data)
        humanized = _normalize_humanized_runtime(raw.get("humanized"), raw)
        return _normalize_config_payload(raw, humanized)


def _normalize_update_payload(
    raw: dict[str, object],
    normalize_humanized: Callable[[object, dict[str, object]], object],
) -> dict[str, object]:
    normalized: dict[str, object] = dict(raw)

    if "schema_version" in raw:
        normalized["schema_version"] = _coerce_int(raw.get("schema_version"), DEFAULT_SCHEMA_VERSION)
    if "allocation_version" in raw:
        normalized["allocation_version"] = _coerce_int(raw.get("allocation_version"), DEFAULT_ALLOCATION_VERSION)
    if "host_ip" in raw:
        normalized["host_ip"] = str(raw.get("host_ip"))
    if "device_ips" in raw:
        normalized["device_ips"] = _normalize_device_ips(raw.get("device_ips"))
    if "total_devices" in raw:
        total_devices = _coerce_int(raw.get("total_devices"), DEFAULT_TOTAL_DEVICES)
        normalized["total_devices"] = max(1, total_devices)
    if "discovery_enabled" in raw:
        normalized["discovery_enabled"] = _coerce_bool(raw.get("discovery_enabled"), False)
    if "discovery_subnet" in raw:
        normalized["discovery_subnet"] = str(raw.get("discovery_subnet", "")).strip()
    if "cloud_machines_per_device" in raw:
        cloud_machines_per_device = _coerce_int(
            raw.get("cloud_machines_per_device"),
            DEFAULT_CLOUD_MACHINES_PER_DEVICE,
        )
        normalized["cloud_machines_per_device"] = max(1, cloud_machines_per_device)
    if "sdk_port" in raw:
        normalized["sdk_port"] = _coerce_int(raw.get("sdk_port"), DEFAULT_SDK_PORT)
    if "default_ai" in raw:
        normalized["default_ai"] = str(raw.get("default_ai"))
    if "stop_hour" in raw:
        stop_hour = _coerce_optional_int(raw.get("stop_hour"))
        if stop_hour is None or not (0 <= stop_hour <= 23):
            stop_hour = DEFAULT_STOP_HOUR
        normalized["stop_hour"] = stop_hour
    if "cycle_interval" in raw:
        cycle_interval = _coerce_int(raw.get("cycle_interval"), DEFAULT_CYCLE_INTERVAL)
        if not (1 <= cycle_interval <= 3600):
            cycle_interval = DEFAULT_CYCLE_INTERVAL
        normalized["cycle_interval"] = cycle_interval
    if "judge_mode" in raw:
        judge_mode_raw = str(raw.get("judge_mode", "")).strip().lower()
        normalized["judge_mode"] = judge_mode_raw if judge_mode_raw in {"off", "lite", "full"} else DEFAULT_JUDGE_MODE
    if "step_parallel" in raw:
        step_parallel = _coerce_int(raw.get("step_parallel"), DEFAULT_STEP_PARALLEL)
        if not (1 <= step_parallel <= 64):
            step_parallel = DEFAULT_STEP_PARALLEL
        normalized["step_parallel"] = step_parallel
    if "vision_monitor_enabled" in raw:
        normalized["vision_monitor_enabled"] = _coerce_bool(
            raw.get("vision_monitor_enabled"), DEFAULT_VISION_MONITOR_ENABLED
        )
    if "vision_device_type" in raw:
        normalized["vision_device_type"] = str(raw.get("vision_device_type"))
    if "vision_pipeline_type" in raw:
        normalized["vision_pipeline_type"] = str(raw.get("vision_pipeline_type"))
    if "vision_model_name" in raw:
        normalized["vision_model_name"] = str(raw.get("vision_model_name"))
    if "vision_thought_language" in raw:
        normalized["vision_thought_language"] = str(raw.get("vision_thought_language"))
    if "vision_timeout_seconds" in raw:
        normalized["vision_timeout_seconds"] = _coerce_int(
            raw.get("vision_timeout_seconds"),
            DEFAULT_VISION_TIMEOUT_SECONDS,
        )
    if "vision_cooldown_ms" in raw:
        normalized["vision_cooldown_ms"] = _coerce_int(raw.get("vision_cooldown_ms"), DEFAULT_VISION_COOLDOWN_MS)
    if "vision_dedupe_window_ms" in raw:
        normalized["vision_dedupe_window_ms"] = _coerce_int(
            raw.get("vision_dedupe_window_ms"), DEFAULT_VISION_DEDUPE_WINDOW_MS
        )
    if "vision_max_fallback_per_step" in raw:
        normalized["vision_max_fallback_per_step"] = _coerce_int(
            raw.get("vision_max_fallback_per_step"), DEFAULT_VISION_MAX_FALLBACK_PER_STEP
        )
    if "humanization_enabled" in raw:
        normalized["humanization_enabled"] = _coerce_bool(raw.get("humanization_enabled"), True)
    if "humanization_intensity" in raw:
        normalized["humanization_intensity"] = _coerce_int(
            raw.get("humanization_intensity"), DEFAULT_HUMANIZATION_INTENSITY
        )
    if "humanization_seed" in raw:
        normalized["humanization_seed"] = _coerce_int(raw.get("humanization_seed"), DEFAULT_HUMANIZATION_SEED)
    if "humanization_delay_ms" in raw:
        normalized["humanization_delay_ms"] = _coerce_int(
            raw.get("humanization_delay_ms"), DEFAULT_HUMANIZATION_DELAY_MS
        )
    if "humanization_jitter_ms" in raw:
        normalized["humanization_jitter_ms"] = _coerce_int(
            raw.get("humanization_jitter_ms"), DEFAULT_HUMANIZATION_JITTER_MS
        )
    if "humanized" in raw:
        normalized["humanized"] = normalize_humanized(raw.get("humanized"), raw)

    return normalized


class ConfigUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

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
    stop_hour: Optional[int] = DEFAULT_STOP_HOUR
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
    humanized: Optional[HumanizedConfigSchema] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_update(cls, data: object):
        if not isinstance(data, dict):
            return data

        raw = cast(dict[str, object], data)
        return _normalize_update_payload(raw, lambda value, _legacy: value)


class ConfigStoreUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

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
    stop_hour: Optional[int] = DEFAULT_STOP_HOUR
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
    humanized: Optional[HumanizedRuntimeConfigSchema] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_update(cls, data: object):
        if not isinstance(data, dict):
            return data

        raw = cast(dict[str, object], data)
        return _normalize_update_payload(raw, _normalize_humanized_runtime)
