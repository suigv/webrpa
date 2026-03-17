# pyright: reportAttributeAccessIssue=false, reportDeprecated=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnusedCallResult=false, reportAny=false, reportExplicitAny=false

from contextlib import suppress
from typing import Any, Literal, cast

from anyio import to_thread as _to_thread
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response

from core.config_loader import (
    ConfigLoader,
    get_cloud_machines_per_device,
    get_device_ip,
    get_total_devices,
)
from core.device_manager import get_device_manager
from core.lan_discovery import LanDeviceDiscovery
from core.port_calc import calculate_ports
from engine.actions._rpc_bootstrap import is_rpc_enabled
from models.device import CloudMachineInfo, DeviceInfo, DeviceStatus, DeviceStatusResponse

to_thread = cast(Any, _to_thread)

router = APIRouter()
device_manager = get_device_manager()
discovery = LanDeviceDiscovery()


def _to_device_info(info: dict[str, object]) -> DeviceInfo:
    clouds_raw = info.get("cloud_machines", [])
    if not isinstance(clouds_raw, list):
        clouds_raw = []
    cloud_machines = [CloudMachineInfo(**cloud) for cloud in clouds_raw if isinstance(cloud, dict)]
    cloud_slots_raw = info.get("cloud_slots_total", 12)
    cloud_slots_total = (
        int(cloud_slots_raw) if isinstance(cloud_slots_raw, (int, float, str)) else 12
    )
    available_raw = info.get("available_cloud_count", 0)
    available_cloud_count = (
        int(available_raw) if isinstance(available_raw, (int, float, str)) else 0
    )

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
    ai_raw = str(info.get("ai_type", "default"))
    status_raw = str(info.get("status", DeviceStatus.IDLE.value))

    return DeviceInfo(
        schema_version=schema_version,
        allocation_version=allocation_version,
        device_id=device_id,
        ip=ip,
        sdk_port=sdk_port,
        ai_type=ai_raw,
        status=DeviceStatus(status_raw),
        cloud_slots_total=cloud_slots_total,
        available_cloud_count=available_cloud_count,
        probe_stale=bool(info.get("probe_stale", False)),
        probe_partial=bool(info.get("probe_partial", False)),
        cloud_machines=cloud_machines,
    )


@router.get("/", response_model=list[DeviceInfo])
async def list_devices(availability: Literal["all", "available_only"] = "all"):
    # Return snapshot cache to keep UI fast; background probe worker refreshes it.
    snapshot = await to_thread.run_sync(device_manager.get_devices_snapshot, availability)
    return [_to_device_info(info) for info in snapshot if isinstance(info, dict)]


@router.post("/discover")
@router.post("/discover/")
async def discover_devices(background_tasks: BackgroundTasks):
    def run_scan() -> None:
        ips = discovery.scan_now(force=True)
        if ips:
            ConfigLoader.update(
                total_devices=len(ips),
                device_ips={str(index): ip for index, ip in enumerate(ips, start=1)},
            )

    background_tasks.add_task(run_scan)
    return {"status": "started", "message": "Background scan initiated"}


@router.get("/{device_id}", response_model=DeviceInfo)
async def get_device(device_id: int, availability: Literal["all", "available_only"] = "all"):
    try:
        info = await to_thread.run_sync(device_manager.get_device_info, device_id, availability)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_device_info(info)


@router.get("/{device_id}/status", response_model=DeviceStatusResponse)
async def get_device_status(device_id: int):
    try:
        # 这里需要稍微改动 DeviceManager 增加 get_device 或者直接使用 get_all_devices
        devices = await to_thread.run_sync(device_manager.get_all_devices)
        dev = devices.get(device_id)
        if not dev:
            raise HTTPException(status_code=404, detail="device not found")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DeviceStatusResponse(
        device_id=device_id,
        status=DeviceStatus(dev.status),
        current_task=dev.current_task,
        message=dev.message,
    )


@router.post("/{device_id}/start")
async def start_device(device_id: int):
    try:
        await to_thread.run_sync(
            device_manager.set_device_status,
            device_id,
            DeviceStatus.IDLE,
            None,
            "connection enabled",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"device_id": device_id, "status": "enabled"}


@router.post("/{device_id}/stop")
async def stop_device(device_id: int):
    try:
        await to_thread.run_sync(
            device_manager.set_device_status,
            device_id,
            DeviceStatus.OFFLINE,
            None,
            "connection disabled",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"device_id": device_id, "status": "disabled"}


@router.get("/{device_id}/{cloud_id}/screenshot")
async def get_cloud_screenshot(device_id: int, cloud_id: int):
    if not is_rpc_enabled():
        raise HTTPException(status_code=503, detail="RPC is disabled (MYT_ENABLE_RPC=0)")

    total_devices = get_total_devices()
    if device_id < 1 or device_id > total_devices:
        raise HTTPException(status_code=404, detail="device not found")

    cloud_machines_per_device = get_cloud_machines_per_device()
    if cloud_id < 1 or cloud_id > cloud_machines_per_device:
        raise HTTPException(status_code=404, detail="cloud not found")

    device_ip = get_device_ip(device_id)
    _api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)

    def _take_screenshot() -> bytes:
        from hardware_adapters.mytRpc import MytRpc

        rpc = MytRpc()
        connected = rpc.init(device_ip, rpa_port, 5)
        if not connected:
            raise RuntimeError(f"RPC connect failed ({device_ip}:{rpa_port})")
        try:
            payload = rpc.take_capture_compress(0, 80)
            if payload is None:
                raise RuntimeError(f"take_capture_compress returned None ({device_ip}:{rpa_port})")
            # 验证返回的是有效图片（JPEG/PNG magic bytes），而非错误字符串
            if len(payload) < 4 or (payload[:2] != b"\xff\xd8" and payload[:4] != b"\x89PNG"):
                text = payload[:200].decode("utf-8", errors="replace")
                raise RuntimeError(f"invalid image data: {text}")
            return bytes(payload)
        finally:
            with suppress(Exception):
                rpc.close()

    try:
        image_bytes = await to_thread.run_sync(_take_screenshot)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    media_type = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
    return Response(content=image_bytes, media_type=media_type)
