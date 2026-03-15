from __future__ import annotations

import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Literal, Optional, Any

from .config_loader import (
    get_cloud_machines_per_device,
    get_device_ip,
    get_sdk_port,
    get_total_devices,
)
from .port_calc import calculate_ports
from hardware_adapters.myt_client import BaseHTTPClient

logger = logging.getLogger(__name__)


class CloudProbeService:
    """专门负责云机（Cloud Machine）的在线探测、型号映射与状态监测服务。"""
    
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
            self._probe_interval_seconds = 3.0
            self._probe_timeout_seconds = 0.8
            self._probe_retry_count = 1
            
            self._probe_stop_event = threading.Event()
            self._probe_thread: Optional[threading.Thread] = None
            
            self._cloud_model_cache: dict[tuple[str, int], dict[str, object]] = {}
            self._cloud_model_lock = threading.Lock()
            self._cloud_model_timeout_seconds = 1.0
            self._cloud_model_success_ttl_seconds = 30.0
            self._cloud_model_error_ttl_seconds = 5.0
            
            self._initialized = True

    def start(self) -> None:
        if self._probe_thread and self._probe_thread.is_alive():
            return
        self._probe_stop_event.clear()
        self._probe_thread = threading.Thread(target=self._probe_loop, name="cloud-probe-service", daemon=True)
        self._probe_thread.start()

    def stop(self) -> None:
        self._probe_stop_event.set()
        if self._probe_thread and self._probe_thread.is_alive():
            self._probe_thread.join(timeout=2)
        self._probe_thread = None

    def _probe_loop(self) -> None:
        from .device_manager import get_device_manager, DeviceManager
        manager: DeviceManager = get_device_manager()
        
        while not self._probe_stop_event.is_set():
            started = time.monotonic()
            self._run_probe_sweep(manager)
            elapsed = time.monotonic() - started
            remaining = max(0.0, self._probe_interval_seconds - elapsed)
            if self._probe_stop_event.wait(remaining):
                break

    def _run_probe_sweep(self, manager: Any) -> None:
        total = get_total_devices()
        cloud_machines_per_device = get_cloud_machines_per_device()

        targets: list[tuple[int, int, str, int]] = []
        device_ips = set()
        for device_id in range(1, total + 1):
            ip = get_device_ip(device_id)
            device_ips.add(ip)
            for cloud_id in range(1, cloud_machines_per_device + 1):
                _api_port, rpa_port = calculate_ports(device_id, cloud_id, cloud_machines_per_device)
                targets.append((device_id, cloud_id, ip, rpa_port))

        if not targets:
            return

        max_workers = min(128, max(8, len(targets)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 1. 探测 RPA 端口
            futures = [executor.submit(self._probe_target, target, manager) for target in targets]
            for f in as_completed(futures):
                try: f.result()
                except Exception: continue
            
            # 2. 异步更新型号映射
            for ip in device_ips:
                executor.submit(self.query_cloud_model_map, ip, refresh_if_missing=True)

        # 3. 驱动 DeviceManager 刷新快照
        try:
            refresh_device_snapshots = getattr(manager, "refresh_device_snapshots", None)
            if callable(refresh_device_snapshots):
                refresh_device_snapshots()
            else:
                legacy_refresh = getattr(manager, "_refresh_device_snapshots", None)
                if callable(legacy_refresh):
                    legacy_refresh()
        except Exception:
            pass

    def _probe_target(self, target: tuple[int, int, str, int], manager: Any) -> None:
        device_id, cloud_id, device_ip, rpa_port = target
        ok, latency_ms, reason = self._probe_rpa_port(device_ip, rpa_port)
        # 将结果写回 manager
        try:
            update_cloud_probe = getattr(manager, "update_cloud_probe", None)
            if callable(update_cloud_probe):
                update_cloud_probe(device_id, cloud_id, ok, latency_ms, reason)
            else:
                legacy_update = getattr(manager, "_update_probe_cache", None)
                if callable(legacy_update):
                    legacy_update(device_id, cloud_id, ok, latency_ms, reason)
        except Exception:
            pass

    def _probe_rpa_port(self, device_ip: str, rpa_port: int) -> tuple[bool, Optional[int], str]:
        started = time.monotonic()
        try:
            with socket.create_connection((device_ip, rpa_port), timeout=self._probe_timeout_seconds):
                latency = int((time.monotonic() - started) * 1000)
                return True, latency, "ok"
        except Exception as exc:
            latency = int((time.monotonic() - started) * 1000)
            return False, latency, str(exc)

    def query_cloud_model_map(self, device_ip: str, refresh_if_missing: bool = False) -> dict[int, dict[str, Optional[str]]]:
        sdk_port = get_sdk_port()
        key = (device_ip, sdk_port)
        now = time.time()
        
        with self._cloud_model_lock:
            cached = self._cloud_model_cache.get(key)
            if cached and (float(cached.get("expires_at", 0)) > now or not refresh_if_missing):
                return cached.get("models_by_api_port", {})

        if not refresh_if_missing: return {}

        client = BaseHTTPClient(device_ip, sdk_port, timeout_seconds=1.0)
        response = client.get("/android")

        models: dict[int, dict[str, Optional[str]]] = {}
        if response.get("ok"):
            # 解析逻辑保持不变...
            try:
                data = response.get("data", {})
                items = data.get("list") or data.get("data", {}).get("list") or []
                for item in items:
                    model_name = str(item.get("modelPath") or "").strip()
                    model_id = str(item.get("id") or "").strip()
                    bindings = item.get("portBindings") or {}
                    api_bindings = bindings.get("9082/tcp") or []
                    if api_bindings:
                        port = int(api_bindings[0].get("HostPort"))
                        models[port] = {
                            "machine_model_name": model_name or None,
                            "machine_model_id": model_id or None,
                        }
            except Exception: pass

        ttl = self._cloud_model_success_ttl_seconds if response.get("ok") else self._cloud_model_error_ttl_seconds
        with self._cloud_model_lock:
            self._cloud_model_cache[key] = {
                "models_by_api_port": models,
                "expires_at": now + ttl,
            }
        return models


_cloud_probe_service_instance: CloudProbeService | None = None
_cloud_probe_service_lock = __import__('threading').Lock()


def get_cloud_probe_service() -> CloudProbeService:
    global _cloud_probe_service_instance
    if _cloud_probe_service_instance is None:
        with _cloud_probe_service_lock:
            if _cloud_probe_service_instance is None:
                _cloud_probe_service_instance = CloudProbeService()
    return _cloud_probe_service_instance
