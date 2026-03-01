from typing import List

from fastapi import APIRouter, HTTPException

from new.core.device_manager import DeviceManager
from new.models.device import AIType, CloudMachineInfo, DeviceInfo, DeviceStatus, DeviceStatusResponse

router = APIRouter()
device_manager = DeviceManager()


def _to_device_info(info: dict[str, object]) -> DeviceInfo:
    clouds_raw = info.get("cloud_machines", [])
    if not isinstance(clouds_raw, list):
        clouds_raw = []
    cloud_machines = [CloudMachineInfo(**cloud) for cloud in clouds_raw if isinstance(cloud, dict)]
    return DeviceInfo(
        schema_version=info["schema_version"],
        allocation_version=info["allocation_version"],
        device_id=info["device_id"],
        ip=info["ip"],
        sdk_port=info["sdk_port"],
        ai_type=AIType(info["ai_type"]),
        status=DeviceStatus(info["status"]),
        cloud_machines=cloud_machines,
    )


@router.get("/", response_model=List[DeviceInfo])
def list_devices():
    result = []
    for device_id in sorted(device_manager.get_all_devices().keys()):
        info = device_manager.get_device_info(device_id)
        result.append(_to_device_info(info))
    return result


@router.get("/{device_id}", response_model=DeviceInfo)
def get_device(device_id: int):
    try:
        info = device_manager.get_device_info(device_id)
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
