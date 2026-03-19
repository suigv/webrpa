# pyright: reportAttributeAccessIssue=false, reportDeprecated=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnusedCallResult=false, reportAny=false, reportExplicitAny=false

import re
from contextlib import suppress
from typing import Any, Literal, cast

from anyio import to_thread as _to_thread
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

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


class TapRequest(BaseModel):
    x: int | None = None
    y: int | None = None
    nx: int | None = Field(default=None, description="normalized x (0-1000)")
    ny: int | None = Field(default=None, description="normalized y (0-1000)")
    finger_id: int = 0

    @model_validator(mode="after")
    def _validate_coords(self) -> "TapRequest":
        has_pixels = self.x is not None and self.y is not None
        has_normalized = self.nx is not None and self.ny is not None
        if not has_pixels and not has_normalized:
            raise ValueError("provide either x/y or nx/ny")
        return self


class SwipeRequest(BaseModel):
    x0: int | None = None
    y0: int | None = None
    x1: int | None = None
    y1: int | None = None
    nx0: int | None = Field(default=None, description="normalized start x (0-1000)")
    ny0: int | None = Field(default=None, description="normalized start y (0-1000)")
    nx1: int | None = Field(default=None, description="normalized end x (0-1000)")
    ny1: int | None = Field(default=None, description="normalized end y (0-1000)")
    duration: int = 300
    finger_id: int = 0

    @model_validator(mode="after")
    def _validate_coords(self) -> "SwipeRequest":
        has_pixels = None not in (self.x0, self.y0, self.x1, self.y1)
        has_normalized = None not in (self.nx0, self.ny0, self.nx1, self.ny1)
        if not has_pixels and not has_normalized:
            raise ValueError("provide either x0/y0/x1/y1 or nx0/ny0/nx1/ny1")
        return self


class KeyRequest(BaseModel):
    key: Literal["back", "home", "enter", "recent"]


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500, description="single-line text to send")

    @model_validator(mode="after")
    def _validate_text(self) -> "TextRequest":
        if not self.text.strip():
            raise ValueError("text cannot be blank")
        if "\n" in self.text or "\r" in self.text:
            raise ValueError("text must be single-line")
        return self


def _validate_device_target(device_id: int, cloud_id: int) -> tuple[str, int]:
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
    return device_ip, rpa_port


def _connect_rpc(device_ip: str, rpa_port: int):
    from hardware_adapters.mytRpc import MytRpc

    rpc = MytRpc()
    connected = rpc.init(device_ip, rpa_port, 5)
    if not connected:
        raise RuntimeError(f"RPC connect failed ({device_ip}:{rpa_port})")
    return rpc


def _parse_wm_size(output: str) -> tuple[int, int] | None:
    override_match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
    if override_match:
        return int(override_match.group(1)), int(override_match.group(2))
    physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    if physical_match:
        return int(physical_match.group(1)), int(physical_match.group(2))
    return None


def _discover_device_resolution(rpc: Any) -> tuple[int, int]:
    output, ok = rpc.exec_cmd("wm size")
    if not ok or not output:
        raise RuntimeError("failed to discover device resolution")
    parsed = _parse_wm_size(str(output))
    if parsed is None:
        raise RuntimeError(f"failed to parse device resolution: {output}")
    return parsed


def _resolve_point(
    x: int | None, y: int | None, nx: int | None, ny: int | None, rpc: Any
) -> tuple[int, int]:
    if x is not None and y is not None:
        return int(x), int(y)
    if nx is None or ny is None:
        raise RuntimeError("missing coordinates")
    width, height = _discover_device_resolution(rpc)
    px = int(round(float(nx) * float(width) / 1000.0))
    py = int(round(float(ny) * float(height) / 1000.0))
    return px, py


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
    device_ip, rpa_port = _validate_device_target(device_id, cloud_id)

    def _take_screenshot() -> bytes:
        rpc = _connect_rpc(device_ip, rpa_port)
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


@router.post("/{device_id}/{cloud_id}/tap")
async def tap_cloud_screen(device_id: int, cloud_id: int, request: TapRequest):
    device_ip, rpa_port = _validate_device_target(device_id, cloud_id)

    def _tap() -> dict[str, object]:
        rpc = _connect_rpc(device_ip, rpa_port)
        try:
            x, y = _resolve_point(request.x, request.y, request.nx, request.ny, rpc)
            ok = rpc.touchClick(int(request.finger_id), x, y)
            if not ok:
                raise RuntimeError("touchClick failed")
            return {"x": x, "y": y, "finger_id": int(request.finger_id)}
        finally:
            with suppress(Exception):
                rpc.close()

    try:
        result = await to_thread.run_sync(_tap)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "data": result}


@router.post("/{device_id}/{cloud_id}/swipe")
async def swipe_cloud_screen(device_id: int, cloud_id: int, request: SwipeRequest):
    device_ip, rpa_port = _validate_device_target(device_id, cloud_id)

    def _swipe() -> dict[str, object]:
        rpc = _connect_rpc(device_ip, rpa_port)
        try:
            x0, y0 = _resolve_point(request.x0, request.y0, request.nx0, request.ny0, rpc)
            x1, y1 = _resolve_point(request.x1, request.y1, request.nx1, request.ny1, rpc)
            raw_result = rpc.swipe(int(request.finger_id), x0, y0, x1, y1, int(request.duration))
            ok = bool(raw_result)
            if not ok:
                raise RuntimeError("swipe failed")
            return {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "duration": int(request.duration),
                "finger_id": int(request.finger_id),
            }
        finally:
            with suppress(Exception):
                rpc.close()

    try:
        result = await to_thread.run_sync(_swipe)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "data": result}


@router.post("/{device_id}/{cloud_id}/key")
async def press_cloud_key(device_id: int, cloud_id: int, request: KeyRequest):
    device_ip, rpa_port = _validate_device_target(device_id, cloud_id)
    key_map = {
        "back": "pressBack",
        "home": "pressHome",
        "enter": "pressEnter",
        "recent": "pressRecent",
    }

    def _press_key() -> dict[str, str]:
        rpc = _connect_rpc(device_ip, rpa_port)
        try:
            method_name = key_map[request.key]
            method = getattr(rpc, method_name, None)
            if not callable(method):
                raise RuntimeError(f"{method_name} unavailable")
            ok = bool(method())
            if not ok:
                raise RuntimeError(f"{request.key} key press failed")
            return {"key": request.key}
        finally:
            with suppress(Exception):
                rpc.close()

    try:
        result = await to_thread.run_sync(_press_key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "data": result}


@router.post("/{device_id}/{cloud_id}/text")
async def send_cloud_text(device_id: int, cloud_id: int, request: TextRequest):
    device_ip, rpa_port = _validate_device_target(device_id, cloud_id)

    def _send_text() -> dict[str, str]:
        rpc = _connect_rpc(device_ip, rpa_port)
        try:
            ok = bool(rpc.sendText(request.text))
            if not ok:
                raise RuntimeError("text input failed")
            return {"text": request.text}
        finally:
            with suppress(Exception):
                rpc.close()

    try:
        result = await to_thread.run_sync(_send_text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "data": result}
