import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from .config_loader import get_discovery_enabled, get_discovery_subnet, get_sdk_port


class LanDeviceDiscovery:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._discovered_ips: list[str] = []
            self._last_scan_at: Optional[float] = None
            self._scan_lock = threading.Lock()
            self._stop_event = threading.Event()
            self._thread: Optional[threading.Thread] = None
            self._scan_interval_seconds = 20.0
            self._connect_timeout_seconds = 0.2
            self._max_workers = 128
            self._initialized = True

    def start(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            return
        self._stop_event.clear()
        self.scan_now()
        self._thread = threading.Thread(target=self._loop, name="lan-device-discovery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            started = time.monotonic()
            self.scan_now()
            elapsed = time.monotonic() - started
            remaining = max(0.0, self._scan_interval_seconds - elapsed)
            if self._stop_event.wait(remaining):
                break

    def _scan_targets(self, subnet: str) -> list[str]:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except Exception:
            return []
        if network.version != 4:
            return []
        if network.prefixlen < 24:
            network = ipaddress.ip_network(f"{network.network_address}/24", strict=False)
        return [str(ip) for ip in network.hosts()]

    def _probe_ip(self, ip: str, port: int) -> bool:
        try:
            with socket.create_connection((ip, port), timeout=self._connect_timeout_seconds):
                return True
        except Exception:
            return False

    def scan_now(self, force: bool = False) -> list[str]:
        if not force and not get_discovery_enabled():
            with self._scan_lock:
                self._last_scan_at = time.time()
                return list(self._discovered_ips)

        subnet = get_discovery_subnet()
        targets = self._scan_targets(subnet)
        if not targets:
            with self._scan_lock:
                self._discovered_ips = []
                self._last_scan_at = time.time()
            return []

        sdk_port = get_sdk_port()
        hits: list[str] = []
        workers = min(self._max_workers, max(8, len(targets)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(self._probe_ip, ip, sdk_port): ip for ip in targets}
            for future in as_completed(future_map):
                ip = future_map[future]
                try:
                    if future.result():
                        hits.append(ip)
                except Exception:
                    continue

        hits_sorted = sorted(set(hits), key=lambda value: tuple(int(part) for part in value.split(".")))
        with self._scan_lock:
            self._discovered_ips = hits_sorted
            self._last_scan_at = time.time()
        return hits_sorted

    def get_discovered_ips(self) -> list[str]:
        with self._scan_lock:
            return list(self._discovered_ips)

    def get_discovered_device_map(self) -> dict[str, str]:
        ips = self.get_discovered_ips()
        return {str(index): ip for index, ip in enumerate(ips, start=1)}

    def get_last_scan_at(self) -> Optional[float]:
        with self._scan_lock:
            return self._last_scan_at
