# pyright: reportAttributeAccessIssue=false, reportDeprecated=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnusedCallResult=false, reportAny=false, reportExplicitAny=false

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar, cast

from anyio import to_thread as _to_thread
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from core.device_control import (
    CloudNotFoundError,
    DeviceNotFoundError,
    RpcDisabledError,
    close_rpc,
    connect_rpc,
    resolve_rpc_point,
    validate_api_target,
    validate_rpc_target,
)
from core.device_manager import get_device_manager
from core.lan_discovery import LanDeviceDiscovery
from core.model_trace_store import ModelTraceContext, ModelTraceStore
from hardware_adapters.android_api_client import AndroidApiClient
from hardware_adapters.mytRpc import swipe_transport_acknowledged
from models.device import CloudMachineInfo, DeviceInfo, DeviceStatus, DeviceStatusResponse

to_thread = cast(Any, _to_thread)

router = APIRouter()
device_manager = get_device_manager()
discovery = LanDeviceDiscovery()
_RpcResult = TypeVar("_RpcResult")


class TraceContextRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    target_label: str | None = Field(default=None, min_length=1, max_length=200)
    attempt_number: int = Field(default=1, ge=1, le=100)
    current_declarative_stage: dict[str, Any] | None = None


class TapRequest(BaseModel):
    x: int | None = None
    y: int | None = None
    nx: int | None = Field(default=None, description="normalized x (0-1000)")
    ny: int | None = Field(default=None, description="normalized y (0-1000)")
    finger_id: int = 0
    trace_context: TraceContextRequest | None = None

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
    trace_context: TraceContextRequest | None = None

    @model_validator(mode="after")
    def _validate_coords(self) -> "SwipeRequest":
        has_pixels = None not in (self.x0, self.y0, self.x1, self.y1)
        has_normalized = None not in (self.nx0, self.ny0, self.nx1, self.ny1)
        if not has_pixels and not has_normalized:
            raise ValueError("provide either x0/y0/x1/y1 or nx0/ny0/nx1/ny1")
        return self


class KeyRequest(BaseModel):
    key: Literal["back", "home", "enter", "recent", "delete"]
    trace_context: TraceContextRequest | None = None


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500, description="single-line text to send")
    trace_context: TraceContextRequest | None = None

    @model_validator(mode="after")
    def _validate_text(self) -> "TextRequest":
        if not self.text.strip():
            raise ValueError("text cannot be blank")
        if "\n" in self.text or "\r" in self.text:
            raise ValueError("text must be single-line")
        return self


def _validate_device_target(device_id: int, cloud_id: int) -> tuple[str, int]:
    try:
        return validate_rpc_target(device_id, cloud_id)
    except RpcDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (DeviceNotFoundError, CloudNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _connect_rpc(device_ip: str, rpa_port: int):
    return connect_rpc(device_ip, rpa_port)


async def _run_rpc_action(
    device_id: int,
    cloud_id: int,
    operation: Callable[[Any], _RpcResult],
) -> _RpcResult:
    device_ip, rpa_port = _validate_device_target(device_id, cloud_id)

    def _run() -> _RpcResult:
        rpc = _connect_rpc(device_ip, rpa_port)
        try:
            return operation(rpc)
        finally:
            close_rpc(rpc)

    try:
        return await to_thread.run_sync(_run)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
    status_raw = str(info.get("status", DeviceStatus.IDLE.value))

    return DeviceInfo(
        schema_version=schema_version,
        allocation_version=allocation_version,
        device_id=device_id,
        ip=ip,
        sdk_port=sdk_port,
        status=DeviceStatus(status_raw),
        cloud_slots_total=cloud_slots_total,
        available_cloud_count=available_cloud_count,
        probe_stale=bool(info.get("probe_stale", False)),
        probe_partial=bool(info.get("probe_partial", False)),
        cloud_machines=cloud_machines,
    )


def _append_human_trace(
    *,
    device_id: int,
    cloud_id: int,
    trace_context: TraceContextRequest | None,
    action_name: str,
    action_params: dict[str, object],
    action_result: dict[str, object],
) -> None:
    if trace_context is None:
        return
    now = datetime.now(UTC)
    context = ModelTraceContext(
        task_id=trace_context.task_id,
        run_id=trace_context.run_id,
        target_label=trace_context.target_label or f"Unit #{device_id}-{cloud_id}",
        attempt_number=int(trace_context.attempt_number),
    )
    ModelTraceStore().append_record(
        context,
        {
            "sequence": int(now.timestamp() * 1000),
            "timestamp": now.isoformat(),
            "record_type": "step",
            "source": "human",
            "human_guided": True,
            "action_name": action_name,
            "action_params": action_params,
            "action_result": {"ok": True, "data": action_result},
            "current_declarative_stage": (
                dict(trace_context.current_declarative_stage)
                if isinstance(trace_context.current_declarative_stage, dict)
                else {}
            ),
        },
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
        discovery.refresh_and_persist(force=True)

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
    try:
        device_ip, api_port = validate_api_target(device_id, cloud_id)
    except (DeviceNotFoundError, CloudNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    def _fetch() -> bytes:
        client = AndroidApiClient(device_ip, api_port, timeout_seconds=10.0, retries=1)
        result = client.http.request_bytes("GET", "/snapshot")
        if not result.get("ok"):
            raise RuntimeError(result.get("message") or "screenshot failed")
        data = result.get("data")
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise RuntimeError("screenshot returned no image data")
        return bytes(data)

    try:
        image_bytes = await to_thread.run_sync(_fetch)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    media_type = "image/png" if image_bytes[:4] == b"\x89PNG" else "image/jpeg"
    return Response(content=image_bytes, media_type=media_type)


@router.post("/{device_id}/{cloud_id}/tap")
async def tap_cloud_screen(device_id: int, cloud_id: int, request: TapRequest):
    def _tap(rpc: Any) -> dict[str, object]:
        x, y = resolve_rpc_point(
            x=request.x,
            y=request.y,
            nx=request.nx,
            ny=request.ny,
            rpc=rpc,
            device_id=device_id,
        )
        ok = rpc.touchClick(int(request.finger_id), x, y)
        if not ok:
            raise RuntimeError("touchClick failed")
        return {"x": x, "y": y, "finger_id": int(request.finger_id)}

    result = await _run_rpc_action(device_id, cloud_id, _tap)
    _append_human_trace(
        device_id=device_id,
        cloud_id=cloud_id,
        trace_context=request.trace_context,
        action_name="ui.click",
        action_params={"x": request.x, "y": request.y, "nx": request.nx, "ny": request.ny},
        action_result=cast(dict[str, object], result),
    )
    return {"ok": True, "data": result}


@router.post("/{device_id}/{cloud_id}/swipe")
async def swipe_cloud_screen(device_id: int, cloud_id: int, request: SwipeRequest):
    def _swipe(rpc: Any) -> dict[str, object]:
        x0, y0 = resolve_rpc_point(
            x=request.x0,
            y=request.y0,
            nx=request.nx0,
            ny=request.ny0,
            rpc=rpc,
            device_id=device_id,
        )
        x1, y1 = resolve_rpc_point(
            x=request.x1,
            y=request.y1,
            nx=request.nx1,
            ny=request.ny1,
            rpc=rpc,
            device_id=device_id,
        )
        raw_result = rpc.swipe(int(request.finger_id), x0, y0, x1, y1, int(request.duration))
        ok = swipe_transport_acknowledged(raw_result)
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

    result = await _run_rpc_action(device_id, cloud_id, _swipe)
    _append_human_trace(
        device_id=device_id,
        cloud_id=cloud_id,
        trace_context=request.trace_context,
        action_name="ui.swipe",
        action_params={
            "x0": request.x0,
            "y0": request.y0,
            "x1": request.x1,
            "y1": request.y1,
            "nx0": request.nx0,
            "ny0": request.ny0,
            "nx1": request.nx1,
            "ny1": request.ny1,
            "duration": int(request.duration),
        },
        action_result=cast(dict[str, object], result),
    )
    return {"ok": True, "data": result}


@router.post("/{device_id}/{cloud_id}/key")
async def press_cloud_key(device_id: int, cloud_id: int, request: KeyRequest):
    key_map = {
        "back": "pressBack",
        "home": "pressHome",
        "enter": "pressEnter",
        "recent": "pressRecent",
        "delete": "pressDelete",
    }

    def _press_key(rpc: Any) -> dict[str, str]:
        method_name = key_map[request.key]
        method = getattr(rpc, method_name, None)
        if not callable(method):
            raise RuntimeError(f"{method_name} unavailable")
        ok = bool(method())
        if not ok:
            raise RuntimeError(f"{request.key} key press failed")
        return {"key": request.key}

    result = await _run_rpc_action(device_id, cloud_id, _press_key)
    _append_human_trace(
        device_id=device_id,
        cloud_id=cloud_id,
        trace_context=request.trace_context,
        action_name="ui.key_press",
        action_params={"key": request.key},
        action_result=cast(dict[str, object], result),
    )
    return {"ok": True, "data": result}


@router.post("/{device_id}/{cloud_id}/text")
async def send_cloud_text(device_id: int, cloud_id: int, request: TextRequest):
    def _send_text(rpc: Any) -> dict[str, str]:
        ok = bool(rpc.sendText(request.text))
        if not ok:
            raise RuntimeError("text input failed")
        return {"text": request.text}

    result = await _run_rpc_action(device_id, cloud_id, _send_text)
    _append_human_trace(
        device_id=device_id,
        cloud_id=cloud_id,
        trace_context=request.trace_context,
        action_name="ui.input_text",
        action_params={"text": request.text},
        action_result=cast(dict[str, object], result),
    )
    return {"ok": True, "data": result}
