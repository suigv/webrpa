import ipaddress
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config_loader import get_discovery_subnet, get_host_ip, get_sdk_port


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
            self._scan_interval_seconds = 20.0
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
        return [str(ip) for ip in network.hosts() if not ipaddress.ip_address(ip).is_loopback]

    def _probe_ip(self, ip: str, port: int) -> bool:
        try:
            with socket.create_connection((ip, port), timeout=self._connect_timeout_seconds):
                return True
        except Exception:
            return False

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
        with self._scan_lock:
            should_refresh = (
                self._last_scan_at is None
                or not self._discovered_ips
                or (time.time() - self._last_scan_at) >= self._scan_interval_seconds
            )
        if should_refresh:
            self.scan_now()
        ips = self.get_discovered_ips()
        return {str(index): ip for index, ip in enumerate(ips, start=1)}

    def get_last_scan_at(self) -> float | None:
        with self._scan_lock:
            return self._last_scan_at
