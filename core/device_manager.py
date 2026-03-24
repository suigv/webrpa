import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from models.device import DeviceStatus

from .config_loader import (
    get_allocation_version,
    get_cloud_machines_per_device,
    get_device_ip,
    get_schema_version,
    get_sdk_port,
    get_stop_hour,
    get_total_devices,
)
from .port_calc import calculate_ports

logger = logging.getLogger(__name__)

ProbeSubscriber = Callable[[dict[str, Any]], None]


class Device:
    def __init__(self, device_id: int):
        self.device_id = device_id
        self.status = DeviceStatus.IDLE
        self.current_task: str | None = None
        self.message: str | None = None
        self.updated_at = datetime.now()
        self.physical_width: int | None = None
        self.physical_height: int | None = None


class DeviceManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._devices: dict[int, Device] = {}
            self._devices_lock = threading.Lock()
            self._probe_lock = threading.Lock()
            self._probe_cache: dict[tuple[int, int], dict[str, object]] = {}
            self._probe_subscribers_lock = threading.Lock()
            self._probe_subscribers: dict[tuple[int, int], dict[int, ProbeSubscriber]] = {}
            self._next_probe_subscription_id = 0
            self._probe_stale_seconds = 10.0
            self._probe_success_threshold = 1
            self._probe_failure_threshold = 2
            self._probe_state_hold_seconds = 3.0
            self._device_snapshot_lock = threading.Lock()
            self._device_snapshot_cache: dict[str, list[dict[str, Any]]] = {}
            self._device_snapshot_at: dict[str, float] = {}
            self._device_snapshot_ttl_seconds = self._load_snapshot_ttl_seconds()
            self._resolution_cache: dict[int, tuple[int, int]] = {}
            self._initialized = True

    @staticmethod
    def _load_snapshot_ttl_seconds() -> float:
        raw = os.environ.get("MYT_DEVICE_SNAPSHOT_TTL_SECONDS", "2").strip()
        try:
            parsed = float(raw)
        except ValueError:
            parsed = 2.0
        return max(0.0, parsed)

    def _resolve_device_endpoints(self) -> list[tuple[int, str]]:
        endpoints: list[tuple[int, str]] = []
        total = get_total_devices()
        for device_id in range(1, total + 1):
            endpoints.append((device_id, get_device_ip(device_id)))
        endpoints.sort(key=lambda item: item[0])
        return endpoints

    def _coerce_int(self, value: object, default: int) -> int:
        if isinstance(value, (int, float, str, bool)):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return default

    def _coerce_float(self, value: object, default: float) -> float:
        if isinstance(value, (int, float, str, bool)):
            try:
                return float(value)
            except (TypeError, ValueError):
                return default
        return default

    def _update_probe_cache(
        self,
        device_id: int,
        cloud_id: int,
        ok: bool,
        latency_ms: int | None,
        reason: str,
    ) -> None:
        now = time.time()
        key = (device_id, cloud_id)
        callbacks: list[ProbeSubscriber] = []
        with self._probe_lock:
            current = self._probe_cache.get(
                key,
                {
                    "state": "unknown",
                    "success_streak": 0,
                    "failure_streak": 0,
                    "state_changed_at": now,
                    "last_checked_at": None,
                    "latency_ms": None,
                    "reason": None,
                    "streak_up": 0,
                    "streak_down": 0,
                },
            )

            state = str(current.get("state", "unknown"))
            success_streak = self._coerce_int(current.get("success_streak", 0), 0)
            failure_streak = self._coerce_int(current.get("failure_streak", 0), 0)
            state_changed_at = self._coerce_float(current.get("state_changed_at", now), now)

            if ok:
                success_streak += 1
                failure_streak = 0
                if state != "available" and (
                    success_streak >= self._probe_success_threshold or state == "unknown"
                ):
                    state = "available"
                    state_changed_at = now
            else:
                failure_streak += 1
                success_streak = 0
                if state != "unavailable" and (
                    failure_streak >= self._probe_failure_threshold or state == "unknown"
                ):
                    state = "unavailable"
                    state_changed_at = now

            self._probe_cache[key] = {
                "state": state,
                "success_streak": success_streak,
                "failure_streak": failure_streak,
                "streak_up": success_streak,
                "streak_down": failure_streak,
                "state_changed_at": state_changed_at,
                "last_checked_at": now,
                "latency_ms": latency_ms,
                "reason": reason,
            }
        with self._probe_subscribers_lock:
            callbacks = list(self._probe_subscribers.get(key, {}).values())

        if callbacks:
            snapshot = self.get_cloud_probe_snapshot(device_id, cloud_id)
            for callback in callbacks:
                try:
                    callback(dict(snapshot))
                except Exception:
                    logger.exception(
                        "cloud probe subscriber failed for device %s cloud %s",
                        device_id,
                        cloud_id,
                    )

    def update_cloud_probe(
        self,
        device_id: int,
        cloud_id: int,
        ok: bool,
        latency_ms: int | None,
        reason: str,
    ) -> None:
        self._update_probe_cache(device_id, cloud_id, ok, latency_ms, reason)

    def mark_cloud_released(self, device_id: int, cloud_id: int) -> None:
        try:
            self.refresh_device_snapshots()
        except Exception:
            logger.debug(
                "failed to refresh device snapshots after releasing cloud %s-%s",
                device_id,
                cloud_id,
                exc_info=True,
            )

    def refresh_device_snapshots(self) -> None:
        self._refresh_device_snapshots()

    def _get_probe_snapshot(self, device_id: int, cloud_id: int) -> dict[str, Any]:
        key = (device_id, cloud_id)
        now = time.time()
        with self._probe_lock:
            current = dict(self._probe_cache.get(key, {}))

        if not current:
            return {
                "availability_state": "unknown",
                "availability_reason": "not_checked",
                "last_checked_at": None,
                "latency_ms": None,
                "streak_up": 0,
                "streak_down": 0,
                "stale": True,
            }

        last_checked_raw = current.get("last_checked_at")
        last_checked: float | None = None
        if isinstance(last_checked_raw, (int, float, str, bool)):
            candidate = self._coerce_float(last_checked_raw, -1.0)
            if candidate >= 0:
                last_checked = candidate

        if last_checked is None:
            stale = True
            last_checked_at = None
        else:
            stale = (now - last_checked) > self._probe_stale_seconds
            last_checked_at = datetime.fromtimestamp(last_checked, tz=UTC).isoformat()

        return {
            "availability_state": str(current.get("state", "unknown")),
            "availability_reason": str(current.get("reason", "not_checked")),
            "last_checked_at": last_checked_at,
            "latency_ms": current.get("latency_ms"),
            "streak_up": current.get("streak_up", 0),
            "streak_down": current.get("streak_down", 0),
            "stale": stale,
        }

    @staticmethod
    def _is_effectively_available(probe: dict[str, Any]) -> bool:
        return str(probe.get("availability_state", "unknown")) == "available" and not bool(
            probe.get("stale", False)
        )

    def get_cloud_probe_snapshot(self, device_id: int, cloud_id: int) -> dict[str, Any]:
        snapshot = self._get_probe_snapshot(device_id, cloud_id)
        snapshot["device_id"] = device_id
        snapshot["cloud_id"] = cloud_id
        return snapshot

    def subscribe_cloud_probe(
        self,
        device_id: int,
        cloud_id: int,
        callback: ProbeSubscriber,
    ) -> Callable[[], None]:
        key = (device_id, cloud_id)
        with self._probe_subscribers_lock:
            self._next_probe_subscription_id += 1
            subscription_id = self._next_probe_subscription_id
            bucket = self._probe_subscribers.setdefault(key, {})
            bucket[subscription_id] = callback

        def _unsubscribe() -> None:
            with self._probe_subscribers_lock:
                bucket = self._probe_subscribers.get(key)
                if bucket is None:
                    return
                bucket.pop(subscription_id, None)
                if not bucket:
                    self._probe_subscribers.pop(key, None)

        return _unsubscribe

    def _sync_devices_with_config(self) -> None:
        endpoints = self._resolve_device_endpoints()
        with self._devices_lock:
            existing = self._devices
            next_devices: dict[int, Device] = {}
            for device_id, _ip in endpoints:
                next_devices[device_id] = existing.get(device_id, Device(device_id))
            self._devices = next_devices

    def get_device(self, device_id: int) -> Device:
        self._sync_devices_with_config()
        with self._devices_lock:
            if device_id not in self._devices:
                raise KeyError(f"device_id out of range: {device_id}")
            return self._devices[device_id]

    def get_all_devices(self) -> dict[int, Device]:
        self._sync_devices_with_config()
        with self._devices_lock:
            return dict(self._devices)

    def _build_devices_snapshot(
        self, availability: Literal["all", "available_only"]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for device_id in sorted(self.get_all_devices().keys()):
            try:
                info = self.get_device_info(device_id, availability=availability)
                result.append(info)
            except Exception:
                continue
        return result

    def _refresh_device_snapshots(self) -> None:
        snapshot_all = self._build_devices_snapshot("all")
        snapshot_available = self._build_devices_snapshot("available_only")
        now = time.time()
        with self._device_snapshot_lock:
            self._device_snapshot_cache["all"] = snapshot_all
            self._device_snapshot_cache["available_only"] = snapshot_available
            self._device_snapshot_at["all"] = now
            self._device_snapshot_at["available_only"] = now

    def get_devices_snapshot(
        self, availability: Literal["all", "available_only"] = "all"
    ) -> list[dict[str, Any]]:
        ttl = self._device_snapshot_ttl_seconds
        with self._device_snapshot_lock:
            cached = list(self._device_snapshot_cache.get(availability, []))
            cached_at = float(self._device_snapshot_at.get(availability, 0.0) or 0.0)
        if cached and ttl > 0 and (time.time() - cached_at) <= ttl:
            return cached
        snapshot = self._build_devices_snapshot(availability)
        with self._device_snapshot_lock:
            self._device_snapshot_cache[availability] = snapshot
            self._device_snapshot_at[availability] = time.time()
        return snapshot

    def update_device_resolution(self, device_id: int, width: int, height: int) -> None:
        with self._devices_lock:
            if device_id in self._devices:
                device = self._devices[device_id]
                device.physical_width = width
                device.physical_height = height
            self._resolution_cache[device_id] = (width, height)

    def get_device_resolution(self, device_id: int) -> tuple[int, int] | None:
        with self._devices_lock:
            val = self._resolution_cache.get(device_id)
            if val:
                return val
            if device_id in self._devices:
                device = self._devices[device_id]
                if device.physical_width is not None and device.physical_height is not None:
                    return (device.physical_width, device.physical_height)
            return None

    def get_device_info(
        self, device_id: int, availability: Literal["all", "available_only"] = "all"
    ) -> dict[str, Any]:
        from .cloud_probe_service import get_cloud_probe_service

        device = self.get_device(device_id)
        cloud_machines_per_device = get_cloud_machines_per_device()
        endpoint_map = dict(self._resolve_device_endpoints())
        device_ip = endpoint_map.get(device_id, get_device_ip(device_id))

        clouds: list[dict[str, Any]] = []
        cloud_models_by_api_port = get_cloud_probe_service().query_cloud_model_map(
            device_ip,
            refresh_if_missing=False,
        )
        available_count = 0
        probe_partial = False
        probe_stale = False

        for cloud_id in range(1, cloud_machines_per_device + 1):
            api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
            probe = self._get_probe_snapshot(device_id, cloud_id)
            state = str(probe.get("availability_state", "unknown"))
            is_effectively_available = self._is_effectively_available(probe)
            if is_effectively_available:
                available_count += 1
            if state == "unknown":
                probe_partial = True
            if probe.get("stale", False):
                probe_stale = True

            cloud_info = {
                "cloud_id": cloud_id,
                "api_port": api_port,
                "api_port_role": "cloud_api",
                "rpa_port": rpa_port,
                "rpa_port_role": "mytrpc_control",
                "status": device.status.value,
                "availability_state": state,
                "availability_reason": probe.get("availability_reason"),
                "last_checked_at": probe.get("last_checked_at"),
                "latency_ms": probe.get("latency_ms"),
                "stale": bool(probe.get("stale", False)),
                "machine_model_name": None,
                "machine_model_id": None,
            }
            model_info = cloud_models_by_api_port.get(api_port)
            if model_info:
                cloud_info["machine_model_name"] = model_info.get("machine_model_name")
                cloud_info["machine_model_id"] = model_info.get("machine_model_id")
            if availability == "available_only" and not is_effectively_available:
                continue
            clouds.append(cloud_info)

        if device.status == DeviceStatus.ERROR:
            effective_status = DeviceStatus.ERROR
        elif device.status == DeviceStatus.OFFLINE:
            effective_status = DeviceStatus.OFFLINE
        elif available_count > 0:
            effective_status = DeviceStatus.RUNNING
        elif probe_partial:
            effective_status = DeviceStatus.IDLE
        else:
            effective_status = DeviceStatus.OFFLINE

        for cloud in clouds:
            cloud["status"] = effective_status.value

        return {
            "schema_version": get_schema_version(),
            "allocation_version": get_allocation_version(),
            "device_id": device_id,
            "ip": device_ip,
            "sdk_port": get_sdk_port(),
            "sdk_port_role": "device_control_api",
            "status": effective_status.value,
            "cloud_slots_total": cloud_machines_per_device,
            "available_cloud_count": available_count,
            "probe_stale": probe_stale,
            "probe_partial": probe_partial,
            "cloud_machines": clouds,
        }

    def set_device_status(
        self,
        device_id: int,
        status: DeviceStatus,
        task: str | None = None,
        message: str | None = None,
    ) -> None:
        with self._devices_lock:
            device = self._devices.get(device_id)
            if device is None:
                raise KeyError(f"device_id out of range: {device_id}")
            device.status = status
            if task is not None:
                device.current_task = task
            if message is not None:
                device.message = message
            device.updated_at = datetime.now()

    def validate_topology_or_raise(self) -> None:
        self._sync_devices_with_config()
        endpoints = self._resolve_device_endpoints()
        cloud_machines_per_device = get_cloud_machines_per_device()
        sdk_port = get_sdk_port()
        seen: set[tuple[str, int]] = set()

        for device_id, ip in endpoints:
            if not str(ip).strip():
                continue
            for cloud_id in range(1, cloud_machines_per_device + 1):
                api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
                for port in (api_port, rpa_port):
                    if port == sdk_port:
                        raise ValueError(f"port conflict with sdk port {sdk_port}")
                    endpoint = (ip, port)
                    if endpoint in seen:
                        raise ValueError(f"duplicate endpoint: {endpoint}")
                    seen.add(endpoint)


def parse_device_range(device_str: str) -> list[int]:
    devices: set[int] = set()
    for part in device_str.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            devices.update(range(int(start), int(end) + 1))
        else:
            devices.add(int(token))
    return sorted(devices)


def check_stop_condition(stop_hour: int | None = None) -> bool:
    hour = get_stop_hour() if stop_hour is None else stop_hour
    if hour is None:
        return False
    return datetime.now().hour >= hour


def get_device_manager() -> DeviceManager:
    return DeviceManager()
