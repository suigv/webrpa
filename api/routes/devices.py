from typing import List, Literal

from fastapi import APIRouter, HTTPException

from ...core.config_loader import ConfigLoader
from ...core.device_manager import DeviceManager
from ...core.lan_discovery import LanDeviceDiscovery
from ...models.device import AIType, CloudMachineInfo, DeviceInfo, DeviceStatus, DeviceStatusResponse

router = APIRouter()
device_manager = DeviceManager()
discovery = LanDeviceDiscovery()


def _to_device_info(info: dict[str, object]) -> DeviceInfo:
    clouds_raw = info.get("cloud_machines", [])
    if not isinstance(clouds_raw, list):
        clouds_raw = []
    cloud_machines = [CloudMachineInfo(**cloud) for cloud in clouds_raw if isinstance(cloud, dict)]
    cloud_slots_raw = info.get("cloud_slots_total", 12)
    cloud_slots_total = int(cloud_slots_raw) if isinstance(cloud_slots_raw, (int, float, str)) else 12
    available_raw = info.get("available_cloud_count", 0)
    available_cloud_count = int(available_raw) if isinstance(available_raw, (int, float, str)) else 0

    schema_raw = info.get("schema_version", 2)
    schema_version = int(schema_raw) if isinstance(schema_raw, (int, float, str)) else 2
    allocation_raw = info.get("allocation_version", 1)
    allocation_version = int(allocation_raw) if isinstance(allocation_raw, (int, float, str)) else 1
    device_id_raw = info.get("device_id", 0)
    device_id = int(device_id_raw) if isinstance(device_id_raw, (int, float, str)) else 0
    ip_raw = info.get("ip", "")
    ip = str(ip_raw)
    sdk_raw = info.get("sdk_port", 8000)
    sdk_port = int(sdk_raw) if isinstance(sdk_raw, (int, float, str)) else 8000
    ai_raw = str(info.get("ai_type", AIType.VOLC.value))
    status_raw = str(info.get("status", DeviceStatus.IDLE.value))

    return DeviceInfo(
        schema_version=schema_version,
        allocation_version=allocation_version,
        device_id=device_id,
        ip=ip,
        sdk_port=sdk_port,
        ai_type=AIType(ai_raw),
        status=DeviceStatus(status_raw),
        cloud_slots_total=cloud_slots_total,
        available_cloud_count=available_cloud_count,
        probe_stale=bool(info.get("probe_stale", False)),
        probe_partial=bool(info.get("probe_partial", False)),
        cloud_machines=cloud_machines,
    )


@router.get("/", response_model=List[DeviceInfo])
def list_devices(availability: Literal["all", "available_only"] = "all"):
    result = []
    for device_id in sorted(device_manager.get_all_devices().keys()):
        info = device_manager.get_device_info(device_id, availability=availability)
        result.append(_to_device_info(info))
    return result


@router.post("/discover")
@router.post("/discover/")
def discover_devices():
    ips = discovery.scan_now(force=True)
    if ips:
        ConfigLoader.update(
            total_devices=len(ips),
            device_ips={str(index): ip for index, ip in enumerate(ips, start=1)},
        )
    return {
        "count": len(ips),
        "device_ips": {str(index): ip for index, ip in enumerate(ips, start=1)},
    }


@router.get("/{device_id}", response_model=DeviceInfo)
def get_device(device_id: int, availability: Literal["all", "available_only"] = "all"):
    try:
        info = device_manager.get_device_info(device_id, availability=availability)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_device_info(info)


@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
def get_device_status(device_id: int):
    try:
        dev = device_manager.get_device(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeviceStatusResponse(
        device_id=device_id,
        status=DeviceStatus(dev.status),
        current_task=dev.current_task,
        message=dev.message,
    )


@router.post("/{device_id}/start")
def start_device(device_id: int):
    try:
        device_manager.set_device_status(device_id, DeviceStatus.RUNNING, task="runtime_stub", message="started")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"device_id": device_id, "status": "started", "mode": "runtime_stub"}


@router.post("/{device_id}/stop")
def stop_device(device_id: int):
    try:
        device = device_manager.get_device(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if device.status == DeviceStatus.RUNNING:
        device_manager.set_device_status(device_id, DeviceStatus.IDLE, task=None, message="stopped")
        return {"device_id": device_id, "status": "stopped"}
    raise HTTPException(status_code=400, detail="No running task to stop")
