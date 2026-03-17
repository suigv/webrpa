from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.runtime_profiles import load_runtime_profile
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
    return []


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
    def __init__(self, device_manager: Any, task_store: Any = None) -> None:
        self._device_manager = device_manager
        self._task_store = task_store

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
            device_id = int(device_id_raw or 0)
            cloud_id = int(cloud_id_raw or 0)
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

        # 若 probe_cache 为空导致 availability_state=unknown，尝试从快照补充
        clouds_raw = info.get("cloud_machines") if isinstance(info, dict) else []
        clouds = clouds_raw if isinstance(clouds_raw, list) else []
        probe_unknown = any(
            isinstance(c, dict)
            and c.get("cloud_id") == cloud_id
            and c.get("availability_state") == "unknown"
            for c in clouds
        )
        if probe_unknown:
            try:
                snapshots = self._device_manager.get_devices_snapshot("all")
                for snap in snapshots:
                    if not isinstance(snap, dict):
                        continue
                    if int(snap.get("device_id", 0)) == device_id:
                        info = snap
                        break
            except Exception:
                pass

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

        assert cloud is not None
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

        if enforce_availability and self._task_store is not None:
            try:
                occupied = self._task_store.get_running_task_by_cloud(device_id, cloud_id)
                if occupied:
                    return None, {
                        "ok": False,
                        "status": "failed_target_unavailable",
                        "code": "target_occupied",
                        "message": f"cloud {device_id}-{cloud_id} is occupied by running task {occupied}",
                    }
            except Exception:
                pass

        if cloud is None or not isinstance(info, dict):
            return None, {
                "ok": False,
                "status": "failed_target_validation",
                "code": "cloud_not_found",
                "message": f"unexpected state reflecting cloud {device_id}-{cloud_id}",
            }

        return {
            "device_id": device_id,
            "cloud_id": cloud_id,
            "device_ip": str(info.get("ip") or ""),
            "api_port": int(cloud.get("api_port", 0)),
            "rpa_port": int(cloud.get("rpa_port", 0)),
            "availability_state": availability_state,
        }, None


@dataclass
class PreparedTaskTarget:
    target: dict[str, Any]
    payload: dict[str, Any]
    runtime: dict[str, Any]
    error: dict[str, Any] | None = None


class TaskDispatchRuntimeResolver:
    def __init__(
        self, target_runtime_resolver: TaskTargetRuntimeResolver, plugin_loader: Any
    ) -> None:
        self._target_runtime_resolver = target_runtime_resolver
        self._plugin_loader = plugin_loader

    def prepare(
        self,
        task_id: str,
        task_name: str,
        payload: dict[str, Any],
        devices: list[int],
        targets: list[dict[str, int]] | None = None,
        enforce_availability: bool = True,
    ) -> list[PreparedTaskTarget]:
        payload_for_run = dict(payload)
        runtime_overrides = _resolve_runtime_overrides(payload_for_run)
        dispatch_targets = normalize_dispatch_targets(targets, devices)
        from core.system_settings_loader import get_rpc_enabled

        rpc_enabled = get_rpc_enabled()
        is_anonymous = task_name == "anonymous" or not task_name
        has_steps = bool(payload_for_run.get("steps"))
        should_resolve_target = rpc_enabled and (
            self._plugin_loader.has(task_name)
            or task_name == "agent_executor"
            or (is_anonymous and has_steps)
        )

        prepared_targets: list[PreparedTaskTarget] = []
        for target in dispatch_targets:
            target_runtime: dict[str, Any] | None = None
            target_error: dict[str, Any] | None = None
            if should_resolve_target:
                target_runtime, target_error = self._target_runtime_resolver.resolve(
                    target, enforce_availability=enforce_availability
                )

            runtime_target = target_runtime or target
            target_payload = dict(payload_for_run)
            runtime = {
                "task_id": task_id,
                "cloud_target": f"Unit #{target.get('device_id')}-{target.get('cloud_id')}",
                "target": runtime_target,
            }
            if runtime_overrides:
                runtime.update(runtime_overrides)

            prepared_targets.append(
                PreparedTaskTarget(
                    target=runtime_target,
                    payload=target_payload,
                    runtime=runtime,
                    error=target_error,
                )
            )
        return prepared_targets


def _resolve_runtime_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_overrides: dict[str, Any] = {}

    profile_name = str(
        payload.pop("_runtime_profile", "") or payload.pop("_profile", "") or ""
    ).strip()
    if not profile_name:
        profile_name = os.getenv("MYT_RUNTIME_PROFILE", "").strip()
    if profile_name:
        runtime_overrides.update(_extract_runtime_section(load_runtime_profile(profile_name)))

    runtime_payload = payload.pop("_runtime", None)
    if isinstance(runtime_payload, dict):
        runtime_overrides.update(_extract_runtime_section(runtime_payload))

    for key, runtime_key in (
        ("_llm", "llm"),
        ("_ai", "ai"),
        ("_vlm", "vlm"),
    ):
        value = payload.pop(key, None)
        if isinstance(value, dict):
            runtime_overrides[runtime_key] = dict(value)

    return runtime_overrides


def _extract_runtime_section(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    section = source.get("runtime") if isinstance(source.get("runtime"), dict) else source
    if not isinstance(section, dict):
        return {}
    runtime: dict[str, Any] = {}
    if "llm" in section and isinstance(section.get("llm"), dict):
        runtime["llm"] = dict(section["llm"])
    if "ai" in section and isinstance(section.get("ai"), dict):
        runtime["ai"] = dict(section["ai"])
    if "vlm" in section and isinstance(section.get("vlm"), dict):
        runtime["vlm"] = dict(section["vlm"])
    if "llm" not in runtime and isinstance(section.get("gpt"), dict):
        runtime["llm"] = dict(section["gpt"])
    return runtime
