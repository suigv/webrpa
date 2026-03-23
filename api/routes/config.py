import ipaddress

from fastapi import APIRouter, HTTPException

from core.config_loader import (
    ConfigLoader,
    get_allocation_version,
    get_cloud_machines_per_device,
    get_cycle_interval,
    get_device_ips,
    get_discovery_enabled,
    get_discovery_subnet,
    get_host_ip,
    get_humanization_delay_ms,
    get_humanization_enabled,
    get_humanization_intensity,
    get_humanization_jitter_ms,
    get_humanization_seed,
    get_humanized_config,
    get_judge_mode,
    get_schema_version,
    get_sdk_port,
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
from core.lan_discovery import LanDeviceDiscovery
from models.config import Config, ConfigUpdate, HumanizedConfigSchema

router = APIRouter()


def _validate_ipv4(host_ip: str) -> str:
    value = str(host_ip).strip()
    try:
        ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise HTTPException(status_code=400, detail="host_ip must be a valid IPv4 address") from exc
    return value


def _normalize_and_validate_device_ips(
    raw_device_ips: object, total_devices: int, host_ip: str
) -> dict[str, str]:
    if not isinstance(raw_device_ips, dict):
        raise HTTPException(status_code=400, detail="device_ips must be a JSON object")

    normalized: dict[str, str] = {}
    duplicate_guard: set[str] = set()
    for key, value in raw_device_ips.items():
        device_id_text = str(key).strip()
        ip_text = str(value).strip()
        if not device_id_text:
            raise HTTPException(status_code=400, detail="device_ips contains empty device id")
        if not ip_text:
            raise HTTPException(status_code=400, detail=f"device_ips[{device_id_text}] is empty")
        try:
            device_id = int(device_id_text)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"device_ips key must be integer-like, got: {device_id_text}",
            ) from exc
        if device_id < 1 or device_id > total_devices:
            raise HTTPException(
                status_code=400,
                detail=f"device_ips key {device_id} out of range 1..{total_devices}",
            )
        validated_ip = _validate_ipv4(ip_text)
        if validated_ip in duplicate_guard:
            raise HTTPException(
                status_code=400, detail=f"duplicate device ip detected: {validated_ip}"
            )
        duplicate_guard.add(validated_ip)
        normalized[str(device_id)] = validated_ip

    if total_devices == 1 and not normalized:
        normalized = {"1": host_ip}

    return normalized


@router.get("/", response_model=Config)
def get_config():
    discovery = LanDeviceDiscovery()
    discovered = discovery.get_discovered_device_map()
    discovery_enabled = get_discovery_enabled()
    total_devices = len(discovered) if discovery_enabled and discovered else get_total_devices()
    return Config(
        schema_version=get_schema_version(),
        allocation_version=get_allocation_version(),
        host_ip=get_host_ip(),
        device_ips=get_device_ips(),
        total_devices=total_devices,
        discovery_enabled=discovery_enabled,
        discovery_subnet=get_discovery_subnet(),
        discovered_device_ips=discovered,
        discovered_total_devices=len(discovered),
        cloud_machines_per_device=get_cloud_machines_per_device(),
        sdk_port=get_sdk_port(),
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
        humanized=HumanizedConfigSchema.model_validate(get_humanized_config()),
    )


@router.put("/", response_model=Config)
def update_config(config: ConfigUpdate):
    update_data = config.model_dump(exclude_none=True)
    current = get_config()
    host_value = update_data.get("host_ip", current.host_ip)
    host_value = _validate_ipv4(str(host_value))
    update_data["host_ip"] = host_value

    total_devices_value = update_data.get("total_devices", current.total_devices)
    try:
        total_devices = int(total_devices_value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="total_devices must be an integer") from exc
    if total_devices < 1:
        raise HTTPException(status_code=400, detail="total_devices must be >= 1")
    update_data["total_devices"] = total_devices

    device_ips_raw = update_data.get("device_ips", current.device_ips)
    update_data["device_ips"] = _normalize_and_validate_device_ips(
        device_ips_raw, total_devices, host_value
    )

    if "discovery_subnet" in update_data:
        update_data["discovery_subnet"] = str(update_data["discovery_subnet"]).strip()

    if update_data:
        ConfigLoader.update(**update_data)
        LanDeviceDiscovery().scan_now()
    return get_config()
