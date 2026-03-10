import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Literal, Optional, Any

from .config_loader import (
    get_allocation_version,
    get_cloud_machines_per_device,
    get_discovery_enabled,
    get_device_ip,
    get_schema_version,
    get_sdk_port,
    get_stop_hour,
    get_total_devices,
)
from .port_calc import calculate_ports
from hardware_adapters.myt_client import BaseHTTPClient
from models.device import AIType, DeviceStatus

logger = logging.getLogger(__name__)


class Device:
    def __init__(self, device_id: int, ai_type: AIType = AIType.VOLC):
        self.device_id = device_id
        self.ai_type = ai_type
        self.status = DeviceStatus.IDLE
        self.current_task: Optional[str] = None
        self.message: Optional[str] = None
        self.updated_at = datetime.now()


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
            self._devices: Dict[int, Device] = {}
            self._devices_lock = threading.Lock()
            self._probe_lock = threading.Lock()
            self._probe_cache: dict[tuple[int, int], dict[str, object]] = {}
            self._probe_interval_seconds = 3.0
            self._probe_timeout_seconds = 0.8
            self._probe_retry_count = 1
            self._probe_stale_seconds = 10.0
            self._probe_success_threshold = 1
            self._probe_failure_threshold = 2
            self._probe_state_hold_seconds = 3.0
            self._probe_stop_event = threading.Event()
            self._probe_thread: Optional[threading.Thread] = None
            self._cloud_model_lock = threading.Lock()
            self._cloud_model_cache: dict[tuple[str, int], dict[str, object]] = {}
            self._cloud_model_timeout_seconds = 1.0
            self._cloud_model_retries = 2
            self._cloud_model_success_ttl_seconds = 30.0
            self._cloud_model_error_ttl_seconds = 5.0
            self._device_snapshot_lock = threading.Lock()
            self._device_snapshot_cache: dict[str, list[dict[str, Any]]] = {}
            self._device_snapshot_at: dict[str, float] = {}
            self._initialized = True

    def _query_cloud_model_map(self, device_ip: str, refresh_if_missing: bool = False) -> dict[int, dict[str, Optional[str]]]:
        key = (device_ip, get_sdk_port())
        now = time.time()
        
        with self._cloud_model_lock:
            cached = self._cloud_model_cache.get(key)
            if cached:
                expires_at = float(cached.get("expires_at", 0))
                if expires_at > now or not refresh_if_missing:
                    map_raw = cached.get("models_by_api_port")
                    if isinstance(map_raw, dict):
                        return {int(port): values for port, values in map_raw.items()}

        if not refresh_if_missing:
            return {}

        client = BaseHTTPClient(
            device_ip,
            get_sdk_port(),
            timeout_seconds=self._cloud_model_timeout_seconds,
            retries=self._cloud_model_retries,
        )
        response = client.get("/android")

        models_by_api_port: dict[int, dict[str, Optional[str]]] = {}
        ttl_seconds = self._cloud_model_error_ttl_seconds
        if response.get("ok"):
            data = response.get("data")
            if isinstance(data, dict):
                list_raw = data.get("list")
                if list_raw is None:
                    nested_data = data.get("data")
                    if isinstance(nested_data, dict):
                        list_raw = nested_data.get("list")
                if isinstance(list_raw, list):
                    for item in list_raw:
                        if not isinstance(item, dict):
                            continue
                        model_name = str(item.get("modelPath") or "").strip()
                        model_id = str(item.get("id") or "").strip()

                        bindings = item.get("portBindings")
                        if not isinstance(bindings, dict):
                            continue
                        api_bindings = bindings.get("9082/tcp")
                        if not isinstance(api_bindings, list) or not api_bindings:
                            continue
                        try:
                            api_port = int(api_bindings[0].get("HostPort"))
                            models_by_api_port[api_port] = {
                                "machine_model_name": model_name or None,
                                "machine_model_id": model_id or None,
                            }
                        except (TypeError, ValueError, KeyError):
                            continue
            ttl_seconds = self._cloud_model_success_ttl_seconds

        with self._cloud_model_lock:
            self._cloud_model_cache[key] = {
                "models_by_api_port": models_by_api_port,
                "expires_at": now + ttl_seconds,
            }

        return models_by_api_port

    def _resolve_device_endpoints(self) -> list[tuple[int, str]]:
        endpoints: list[tuple[int, str]] = []
        total = get_total_devices()
        for device_id in range(1, total + 1):
            endpoints.append((device_id, get_device_ip(device_id)))
        endpoints.sort(key=lambda item: item[0])
        return endpoints

    def start_cloud_probe_worker(self) -> None:
        thread = self._probe_thread
        if thread is not None and thread.is_alive():
            return
        self._probe_stop_event.clear()
        self._probe_thread = threading.Thread(target=self._probe_loop, name="cloud-probe-worker", daemon=True)
        self._probe_thread.start()

    def stop_cloud_probe_worker(self) -> None:
        self._probe_stop_event.set()
        thread = self._probe_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        self._probe_thread = None

    def _probe_loop(self) -> None:
        while not self._probe_stop_event.is_set():
            started = time.monotonic()
            self._run_probe_sweep()
            elapsed = time.monotonic() - started
            remaining = max(0.0, self._probe_interval_seconds - elapsed)
            if self._probe_stop_event.wait(remaining):
                break

    def _run_probe_sweep(self) -> None:
        self._sync_devices_with_config()
        endpoints = self._resolve_device_endpoints()
        cloud_machines_per_device = get_cloud_machines_per_device()

        targets: list[tuple[int, int, str, int]] = []
        device_ips = set()
        for device_id, device_ip in endpoints:
            device_ips.add(device_ip)
            for cloud_id in range(1, cloud_machines_per_device + 1):
                _api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
                targets.append((device_id, cloud_id, device_ip, rpa_port))

        if not targets:
            return

        max_workers = min(128, max(8, len(targets)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 1. 探测 RPA 端口获取可用性
            futures = [executor.submit(self._probe_target, target) for target in targets]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    continue
            
            # 2. 对每个 IP 尝试在后台异步更新型号映射 (非阻塞)
            for ip in device_ips:
                executor.submit(self._query_cloud_model_map, ip, refresh_if_missing=True)

        # 3. 更新快照缓存，供 API 快速读取
        self._refresh_device_snapshots()

    def _probe_target(self, target: tuple[int, int, str, int]) -> None:
        device_id, cloud_id, device_ip, rpa_port = target
        ok = False
        latency_ms: Optional[int] = None
        reason = "connect_failed"
        for attempt in range(self._probe_retry_count + 1):
            ok, latency_ms, reason = self._probe_rpa_port(device_ip, rpa_port)
            if ok:
                break
            if attempt < self._probe_retry_count:
                time.sleep(0.1)
        self._update_probe_cache(device_id, cloud_id, ok, latency_ms, reason)

    def _probe_rpa_port(self, device_ip: str, rpa_port: int) -> tuple[bool, Optional[int], str]:
        started = time.monotonic()
        try:
            with socket.create_connection((device_ip, rpa_port), timeout=self._probe_timeout_seconds):
                latency = int((time.monotonic() - started) * 1000)
                return True, latency, "ok"
        except Exception as exc:
            latency = int((time.monotonic() - started) * 1000)
            reason = str(exc).strip() or "connect_failed"
            return False, latency, reason

    def _update_probe_cache(
        self,
        device_id: int,
        cloud_id: int,
        ok: bool,
        latency_ms: Optional[int],
        reason: str,
    ) -> None:
        now = time.time()
        key = (device_id, cloud_id)
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
            success_streak = int(current.get("success_streak", 0))
            failure_streak = int(current.get("failure_streak", 0))
            state_changed_at = float(current.get("state_changed_at", now))

            if ok:
                success_streak += 1
                failure_streak = 0
                if state != "available" and (success_streak >= self._probe_success_threshold or state == "unknown"):
                    state = "available"
                    state_changed_at = now
            else:
                failure_streak += 1
                success_streak = 0
                if state != "unavailable" and (failure_streak >= self._probe_failure_threshold or state == "unknown"):
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

        last_checked = current.get("last_checked_at")
        stale = (now - last_checked) > self._probe_stale_seconds if last_checked else True
        last_checked_at = datetime.fromtimestamp(last_checked).isoformat() if last_checked else None

        return {
            "availability_state": str(current.get("state", "unknown")),
            "availability_reason": str(current.get("reason", "not_checked")),
            "last_checked_at": last_checked_at,
            "latency_ms": current.get("latency_ms"),
            "streak_up": current.get("streak_up", 0),
            "streak_down": current.get("streak_down", 0),
            "stale": stale,
        }

    def _sync_devices_with_config(self) -> None:
        endpoints = self._resolve_device_endpoints()
        with self._devices_lock:
            existing = self._devices
            next_devices: Dict[int, Device] = {}
            for device_id, _ip in endpoints:
                next_devices[device_id] = existing.get(device_id, Device(device_id))
            self._devices = next_devices

    def get_device(self, device_id: int, ai_type: AIType = AIType.VOLC) -> Device:
        self._sync_devices_with_config()
        with self._devices_lock:
            if device_id not in self._devices:
                raise KeyError(f"device_id out of range: {device_id}")
            device = self._devices[device_id]
            device.ai_type = ai_type
            return device

    def get_all_devices(self) -> Dict[int, Device]:
        self._sync_devices_with_config()
        with self._devices_lock:
            return dict(self._devices)

    def _build_devices_snapshot(self, availability: Literal["all", "available_only"]) -> list[dict[str, Any]]:
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

    def get_devices_snapshot(self, availability: Literal["all", "available_only"] = "all") -> list[dict[str, Any]]:
        with self._device_snapshot_lock:
            cached = list(self._device_snapshot_cache.get(availability, []))
        if cached:
            return cached
        snapshot = self._build_devices_snapshot(availability)
        with self._device_snapshot_lock:
            self._device_snapshot_cache[availability] = snapshot
            self._device_snapshot_at[availability] = time.time()
        return snapshot

    def get_device_info(self, device_id: int, availability: Literal["all", "available_only"] = "all") -> dict[str, Any]:
        device = self.get_device(device_id)
        cloud_machines_per_device = get_cloud_machines_per_device()
        endpoint_map = dict(self._resolve_device_endpoints())
        device_ip = endpoint_map.get(device_id, get_device_ip(device_id))

        clouds: list[dict[str, Any]] = []
        # API 期间仅读取缓存，不发起任何网络 IO (refresh_if_missing=False)
        cloud_models_by_api_port = self._query_cloud_model_map(device_ip, refresh_if_missing=False)
        available_count = 0
        probe_partial = False
        probe_stale = False
        
        for cloud_id in range(1, cloud_machines_per_device + 1):
            api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
            probe = self._get_probe_snapshot(device_id, cloud_id)
            state = str(probe.get("availability_state", "unknown"))
            if state == "available":
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
                "streak_up": probe.get("streak_up"),
                "streak_down": probe.get("streak_down"),
                "stale": bool(probe.get("stale", False)),
                "machine_model_name": None,
                "machine_model_id": None,
            }
            model_info = cloud_models_by_api_port.get(api_port)
            if model_info:
                cloud_info["machine_model_name"] = model_info.get("machine_model_name")
                cloud_info["machine_model_id"] = model_info.get("machine_model_id")
            if availability == "available_only" and state != "available":
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
            "ai_type": device.ai_type.value,
            "status": effective_status.value,
            "current_task": device.current_task,
            "message": device.message,
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
        task: Optional[str] = None,
        message: Optional[str] = None,
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
        if not token: continue
        if "-" in token:
            start, end = token.split("-", 1)
            devices.update(range(int(start), int(end) + 1))
        else:
            devices.add(int(token))
    return sorted(devices)


def parse_ai_type(ai_type: str) -> str:
    value = ai_type.lower().strip()
    if value in ["volc", "volcano", "huoshan"]: return "volc"
    return "volc"


def check_stop_condition(stop_hour: Optional[int] = None) -> bool:
    hour = get_stop_hour() if stop_hour is None else stop_hour
    return datetime.now().hour >= hour
