import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from hardware_adapters.myt_client import MytSdkClient

from .config_loader import (
    ConfigLoader,
    get_discovery_enabled,
    get_discovery_subnet,
    get_host_ip,
    get_persisted_discovered_device_ips,
    get_sdk_port,
)


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
            self._last_scan_at: float | None = None
            self._scan_lock = threading.Lock()
            self._stop_event = threading.Event()
            self._thread: threading.Thread | None = None
            self._scan_interval_seconds = 3600.0
            self._connect_timeout_seconds = 0.2
            self._max_workers = 128
            self._initialized = True

    def start(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            return
        self._stop_event.clear()
        # Initial scan removed from here to avoid blocking server startup.
        # It will be performed in the first iteration of _loop.
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
            self.refresh_and_persist()
            elapsed = time.monotonic() - started
            remaining = max(0.0, self._scan_interval_seconds - elapsed)
            if self._stop_event.wait(remaining):
                break

    @staticmethod
    def _device_map_from_ips(ips: list[str]) -> dict[str, str]:
        return {str(index): ip for index, ip in enumerate(ips, start=1)}

    def persist_scan_results(self, ips: list[str] | None = None) -> dict[str, str]:
        if ips is None:
            ips = self.get_discovered_ips()
        mapping = self._device_map_from_ips(ips)
        persisted = get_persisted_discovered_device_ips()
        if persisted == mapping:
            return mapping
        ConfigLoader.update(
            discovered_device_ips=mapping,
            discovered_total_devices=len(mapping),
        )
        return mapping

    def refresh_and_persist(self, force: bool = False) -> list[str]:
        ips = self.scan_now(force=force)
        self.persist_scan_results(ips)
        return ips

    def _scan_targets(self, subnet: str) -> list[str]:
        try:
            network = ipaddress.ip_network(subnet, strict=False)
        except Exception:
            return []
        if network.version != 4:
            return []
        if network.prefixlen < 24:
            network = ipaddress.ip_network(f"{network.network_address}/24", strict=False)
        return [str(ip) for ip in network.hosts() if not ipaddress.ip_address(ip).is_loopback]

    @staticmethod
    def _looks_like_sdk_info_payload(payload: object) -> bool:
        if not isinstance(payload, dict):
            return False

        # MytSdkClient wraps successful JSON responses as {"ok": True, "data": {...}}.
        if payload.get("ok") is True and isinstance(payload.get("data"), dict):
            nested = payload.get("data")
            if isinstance(nested, dict):
                payload = nested

        code = payload.get("code")
        try:
            code_value = int(code)
        except (TypeError, ValueError):
            return False
        if code_value != 0:
            return False

        data = payload.get("data")
        if not isinstance(data, dict):
            return False

        info_keys = {"latestVersion", "currentVersion"}
        device_keys = {"deviceId", "model", "version", "ip"}
        return bool(info_keys.intersection(data) or device_keys.intersection(data))

    def _probe_ip(self, ip: str, port: int) -> bool:
        client = MytSdkClient(
            ip,
            port,
            timeout_seconds=self._connect_timeout_seconds,
            retries=1,
        )
        try:
            version_info: dict[str, Any] = client.get_api_version()
        except Exception:
            return False
        if self._looks_like_sdk_info_payload(version_info):
            return True

        try:
            device_info: dict[str, Any] = client.get_device_info()
        except Exception:
            return False
        return self._looks_like_sdk_info_payload(device_info)

    def _candidate_local_ipv4s(self) -> list[str]:
        candidates: list[str] = []

        # UDP connect does not send traffic, but gives us the active outbound IPv4.
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.connect(("8.8.8.8", 80))
                ip = str(sock.getsockname()[0]).strip()
                if ip:
                    candidates.append(ip)
            finally:
                sock.close()
        except Exception:
            pass

        try:
            hostname = socket.gethostname()
            for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(
                hostname, None, family=socket.AF_INET
            ):
                if family != socket.AF_INET:
                    continue
                ip = str(sockaddr[0]).strip()
                if ip:
                    candidates.append(ip)
        except Exception:
            pass

        host_ip = str(get_host_ip()).strip()
        if host_ip:
            candidates.append(host_ip)

        deduped: list[str] = []
        seen: set[str] = set()
        for ip in candidates:
            try:
                parsed = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if parsed.version != 4 or parsed.is_loopback:
                continue
            text = str(parsed)
            if text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return deduped

    def _auto_detect_subnet(self) -> str:
        for ip in self._candidate_local_ipv4s():
            try:
                return str(ipaddress.ip_network(f"{ip}/24", strict=False))
            except Exception:
                continue
        return ""

    def get_effective_subnet(self) -> str:
        auto_subnet = self._auto_detect_subnet()
        if auto_subnet:
            return auto_subnet

        configured_subnet = str(get_discovery_subnet()).strip()
        if configured_subnet:
            try:
                return str(ipaddress.ip_network(configured_subnet, strict=False))
            except Exception:
                pass

        host_ip = str(get_host_ip()).strip()
        try:
            return str(ipaddress.ip_network(f"{host_ip}/24", strict=False))
        except Exception:
            return ""

    def scan_now(self, force: bool = False) -> list[str]:
        now = time.time()
        with self._scan_lock:
            if (
                not force
                and self._last_scan_at is not None
                and (now - self._last_scan_at) < self._scan_interval_seconds
            ):
                return list(self._discovered_ips)
            if not force and not get_discovery_enabled():
                return list(self._discovered_ips)

        subnet = self.get_effective_subnet()
        targets = self._scan_targets(subnet)
        if not targets:
            with self._scan_lock:
                self._discovered_ips = []
                self._last_scan_at = now
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

        hits_sorted = sorted(
            {ip for ip in hits if not ipaddress.ip_address(ip).is_loopback},
            key=lambda value: tuple(int(part) for part in value.split(".")),
        )
        with self._scan_lock:
            self._discovered_ips = hits_sorted
            self._last_scan_at = now
        return hits_sorted

    def get_discovered_ips(self) -> list[str]:
        with self._scan_lock:
            return list(self._discovered_ips)

    def get_discovered_device_map(self) -> dict[str, str]:
        ips = self.get_discovered_ips()
        return {str(index): ip for index, ip in enumerate(ips, start=1)}

    def get_last_scan_at(self) -> float | None:
        with self._scan_lock:
            return self._last_scan_at
