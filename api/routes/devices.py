from typing import List

from fastapi import APIRouter, HTTPException

from new.core.device_manager import DeviceManager
from new.models.device import AIType, DeviceInfo, DeviceStatus, DeviceStatusResponse

router = APIRouter()
device_manager = DeviceManager()


@router.get("/", response_model=List[DeviceInfo])
def list_devices():
    devices = device_manager.get_all_devices()
    result = []
    for idx, dev in devices.items():
        info = device_manager.get_device_info(idx)
        result.append(
            DeviceInfo(
                index=info["index"],
                ip=info["ip"],
                rpa_port=info["rpa_port"],
                api_port=info["api_port"],
                ai_type=AIType(dev.ai_type),
                status=DeviceStatus(dev.status),
            )
        )
    return result


@router.get("/{device_id}", response_model=DeviceInfo)
def get_device(device_id: int):
    info = device_manager.get_device_info(device_id)
    dev = device_manager.get_device(device_id)
    return DeviceInfo(
        index=info["index"],
        ip=info["ip"],
        rpa_port=info["rpa_port"],
        api_port=info["api_port"],
        ai_type=AIType(dev.ai_type),
        status=DeviceStatus(dev.status),
    )


@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
def get_device_status(device_id: int):
    dev = device_manager.get_device(device_id)
    return DeviceStatusResponse(
        index=device_id,
        status=DeviceStatus(dev.status),
        current_task=dev.current_task,
        message=dev.message,
    )


@router.post("/{device_id}/start")
def start_device(device_id: int):
    device_manager.set_device_status(device_id, DeviceStatus.RUNNING, task="runtime_stub", message="started")
    return {"device_id": device_id, "status": "started", "mode": "runtime_stub"}


@router.post("/{device_id}/stop")
def stop_device(device_id: int):
    device = device_manager.get_device(device_id)
    if device.status == DeviceStatus.RUNNING:
        device_manager.set_device_status(device_id, DeviceStatus.IDLE, task=None, message="stopped")
        return {"device_id": device_id, "status": "stopped"}
    raise HTTPException(status_code=400, detail="No running task to stop")
