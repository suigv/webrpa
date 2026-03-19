from __future__ import annotations

import re
from contextlib import suppress
from typing import Any

from core.config_loader import get_cloud_machines_per_device, get_device_ip, get_total_devices
from core.device_manager import get_device_manager
from core.port_calc import calculate_ports
from engine.actions._rpc_bootstrap import is_rpc_enabled


class DeviceControlError(RuntimeError):
    """Base error for direct device-control helpers."""


class RpcDisabledError(DeviceControlError):
    pass


class DeviceNotFoundError(DeviceControlError):
    pass


class CloudNotFoundError(DeviceControlError):
    pass


def validate_rpc_target(device_id: int, cloud_id: int) -> tuple[str, int]:
    if not is_rpc_enabled():
        raise RpcDisabledError("RPC is disabled (MYT_ENABLE_RPC=0)")

    total_devices = get_total_devices()
    if device_id < 1 or device_id > total_devices:
        raise DeviceNotFoundError("device not found")

    cloud_machines_per_device = get_cloud_machines_per_device()
    if cloud_id < 1 or cloud_id > cloud_machines_per_device:
        raise CloudNotFoundError("cloud not found")

    device_ip = get_device_ip(device_id)
    _api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
    return device_ip, rpa_port


def connect_rpc(device_ip: str, rpa_port: int, *, connect_timeout: int = 5) -> Any:
    from hardware_adapters.mytRpc import MytRpc

    rpc = MytRpc()
    connected = rpc.init(device_ip, rpa_port, int(connect_timeout))
    if not connected:
        raise RuntimeError(f"RPC connect failed ({device_ip}:{rpa_port})")
    return rpc


def close_rpc(rpc: Any | None) -> None:
    if rpc is None:
        return
    with suppress(Exception):
        rpc.close()


def parse_wm_size_output(output: str) -> tuple[int, int] | None:
    override_match = re.search(r"Override size:\s*(\d+)x(\d+)", output)
    if override_match:
        return int(override_match.group(1)), int(override_match.group(2))
    physical_match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
    if physical_match:
        return int(physical_match.group(1)), int(physical_match.group(2))
    return None


def discover_device_resolution(
    rpc: Any,
    *,
    device_id: int | None = None,
    use_cache: bool = True,
) -> tuple[int, int]:
    manager = get_device_manager()
    if use_cache and device_id is not None and device_id > 0:
        cached = manager.get_device_resolution(device_id)
        if cached is not None:
            return cached

    output, ok = rpc.exec_cmd("wm size")
    if not ok or not output:
        raise RuntimeError("failed to discover device resolution")

    parsed = parse_wm_size_output(str(output))
    if parsed is None:
        raise RuntimeError(f"failed to parse device resolution: {output}")

    if device_id is not None and device_id > 0:
        manager.update_device_resolution(device_id, parsed[0], parsed[1])
    return parsed


def resolve_rpc_point(
    *,
    x: int | None,
    y: int | None,
    nx: int | None,
    ny: int | None,
    rpc: Any,
    device_id: int | None = None,
) -> tuple[int, int]:
    if x is not None and y is not None:
        return int(x), int(y)
    if nx is None or ny is None:
        raise RuntimeError("missing coordinates")

    width, height = discover_device_resolution(rpc, device_id=device_id)
    px = int(round(float(nx) * float(width) / 1000.0))
    py = int(round(float(ny) * float(height) / 1000.0))
    return px, py


def capture_compressed_image_bytes(
    rpc: Any,
    *,
    channel: int = 0,
    quality: int = 80,
) -> bytes:
    payload = rpc.take_capture_compress(int(channel), int(quality))
    if payload is None:
        raise RuntimeError("take_capture_compress returned None")
    if len(payload) < 4 or (payload[:2] != b"\xff\xd8" and payload[:4] != b"\x89PNG"):
        text = payload[:200].decode("utf-8", errors="replace")
        raise RuntimeError(f"invalid image data: {text}")
    return bytes(payload)
