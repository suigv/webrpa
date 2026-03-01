import ipaddress

from fastapi import APIRouter, HTTPException

from new.core.config_loader import (
    ConfigLoader,
    get_cycle_interval,
    get_default_ai,
    get_device_ips,
    get_host_ip,
    get_humanization_delay_ms,
    get_humanization_enabled,
    get_humanization_intensity,
    get_humanization_jitter_ms,
    get_humanization_seed,
    get_judge_mode,
    get_step_parallel,
    get_stop_hour,
    get_total_devices,
    get_vision_cooldown_ms,
    get_vision_dedupe_window_ms,
    get_vision_device_type,
    get_vision_max_fallback_per_step,
    get_vision_model_name,
    get_vision_monitor_enabled,
    get_vision_pipeline_type,
    get_vision_thought_language,
    get_vision_timeout_seconds,
)
from new.models.config import Config, ConfigUpdate

router = APIRouter()


def _validate_ipv4(host_ip: str) -> str:
    value = str(host_ip).strip()
    try:
        ipaddress.IPv4Address(value)
    except Exception:
        raise HTTPException(status_code=400, detail="host_ip must be a valid IPv4 address")
    return value


@router.get("/", response_model=Config)
def get_config():
    return Config(
        host_ip=get_host_ip(),
        device_ips=get_device_ips(),
        total_devices=get_total_devices(),
        default_ai=get_default_ai(),
        stop_hour=get_stop_hour(),
        cycle_interval=get_cycle_interval(),
        judge_mode=get_judge_mode(),
        step_parallel=get_step_parallel(),
        vision_monitor_enabled=get_vision_monitor_enabled(),
        vision_device_type=get_vision_device_type(),
        vision_pipeline_type=get_vision_pipeline_type(),
        vision_model_name=get_vision_model_name(),
        vision_thought_language=get_vision_thought_language(),
        vision_timeout_seconds=get_vision_timeout_seconds(),
        vision_cooldown_ms=get_vision_cooldown_ms(),
        vision_dedupe_window_ms=get_vision_dedupe_window_ms(),
        vision_max_fallback_per_step=get_vision_max_fallback_per_step(),
        humanization_enabled=get_humanization_enabled(),
        humanization_intensity=get_humanization_intensity(),
        humanization_seed=get_humanization_seed(),
        humanization_delay_ms=get_humanization_delay_ms(),
        humanization_jitter_ms=get_humanization_jitter_ms(),
    )


@router.put("/", response_model=Config)
def update_config(config: ConfigUpdate):
    update_data = config.model_dump(exclude_none=True)
    if "host_ip" in update_data:
        update_data["host_ip"] = _validate_ipv4(update_data["host_ip"])
    if update_data:
        ConfigLoader.update(**update_data)
    return get_config()
