from __future__ import annotations

from typing import Any, Callable

from core.task_store import TaskRecord


def normalize_dispatch_targets(raw_targets: Any, devices: list[int]) -> list[dict[str, int]]:
    dispatch_targets: list[dict[str, int]] = []
    if isinstance(raw_targets, list):
        for item in raw_targets:
            if not isinstance(item, dict):
                continue
            device_id_raw = item.get("device_id")
            cloud_id_raw = item.get("cloud_id", 1)
            if device_id_raw is None or cloud_id_raw is None:
                continue
            try:
                device_id = int(str(device_id_raw))
                cloud_id = int(str(cloud_id_raw))
            except Exception:
                continue
            if device_id < 1 or cloud_id < 1:
                continue
            dispatch_targets.append({"device_id": device_id, "cloud_id": cloud_id})
    if dispatch_targets:
        return dispatch_targets
    if devices:
        return [{"device_id": int(device_id), "cloud_id": 1} for device_id in devices]
    return [{"device_id": 1, "cloud_id": 1}]


def build_queue_schedule(
    record: TaskRecord,
    iso_to_epoch: Callable[[str], float],
    delay_seconds: Callable[[str], int],
) -> tuple[int, float | None]:
    delay = 0
    run_at_epoch: float | None = None
    if record.run_at is not None:
        run_at_epoch = iso_to_epoch(record.run_at)
        delay = delay_seconds(record.run_at)
    if record.next_retry_at is not None:
        run_at_epoch = iso_to_epoch(record.next_retry_at)
        delay = max(delay, delay_seconds(record.next_retry_at))
    return delay, run_at_epoch


class TaskTargetRuntimeResolver:
    def __init__(self, device_manager: Any) -> None:
        self._device_manager = device_manager

    def resolve(
        self,
        target: dict[str, int],
        enforce_availability: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        try:
            device_id_raw = target.get("device_id")
            cloud_id_raw = target.get("cloud_id")
            if device_id_raw is None or cloud_id_raw is None:
                raise ValueError("missing target keys")
            device_id = int(device_id_raw)
            cloud_id = int(cloud_id_raw)
        except Exception:
            device_id = 0
            cloud_id = 0
        if device_id < 1 or cloud_id < 1:
            return None, {
                "ok": False,
                "status": "failed_target_validation",
                "code": "invalid_target",
                "message": f"invalid target: device_id={device_id}, cloud_id={cloud_id}",
            }

        try:
            info = self._device_manager.get_device_info(device_id)
        except Exception as exc:
            return None, {
                "ok": False,
                "status": "failed_target_validation",
                "code": "target_not_found",
                "message": str(exc),
            }

        clouds_raw = info.get("cloud_machines") if isinstance(info, dict) else []
        clouds = clouds_raw if isinstance(clouds_raw, list) else []
        cloud = None
        for item in clouds:
            if not isinstance(item, dict):
                continue
            cloud_value = item.get("cloud_id", 0)
            try:
                cloud_value_int = int(cloud_value)
            except Exception:
                cloud_value_int = 0
            if cloud_value_int == cloud_id:
                cloud = item
                break
        if cloud is None:
            return None, {
                "ok": False,
                "status": "failed_target_validation",
                "code": "cloud_not_found",
                "message": f"cloud_id out of range for device {device_id}: {cloud_id}",
            }

        availability_state = str(cloud.get("availability_state") or "unknown")
        if enforce_availability and availability_state != "available":
            return None, {
                "ok": False,
                "status": "failed_target_unavailable",
                "code": "target_unavailable",
                "message": (
                    f"target unavailable: device={device_id}, cloud={cloud_id}, "
                    f"state={availability_state}"
                ),
            }

        return {
            "device_id": device_id,
            "cloud_id": cloud_id,
            "device_ip": str(info.get("ip") or ""),
            "api_port": int(cloud.get("api_port", 0)),
            "rpa_port": int(cloud.get("rpa_port", 0)),
            "availability_state": availability_state,
        }, None
