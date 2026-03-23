import time

from core.config_loader import ConfigLoader
from core.lan_discovery import LanDeviceDiscovery


def test_scan_now_force_bypasses_discovery_enabled(monkeypatch):
    backup = ConfigLoader._config
    discovery = LanDeviceDiscovery()
    try:
        ConfigLoader._config = {
            "host_ip": "192.168.1.214",
            "device_ips": {"1": "192.168.1.214", "2": "192.168.1.215"},
            "total_devices": 2,
            "sdk_port": 8000,
            "discovery_enabled": False,
            "discovery_subnet": "192.168.1.0/24",
        }

        monkeypatch.setattr(
            discovery, "_scan_targets", lambda subnet: ["192.168.1.214", "192.168.1.215"]
        )
        monkeypatch.setattr(discovery, "_probe_ip", lambda ip, port: ip == "192.168.1.214")
        monkeypatch.setattr(discovery, "get_effective_subnet", lambda: "192.168.1.0/24")

        assert discovery.scan_now() == ["192.168.1.214"]
        assert discovery.scan_now(force=True) == ["192.168.1.214"]
        assert discovery.scan_now() == ["192.168.1.214"]
    finally:
        ConfigLoader._config = backup


def test_get_effective_subnet_prefers_auto_detected_local_network(monkeypatch):
    discovery = LanDeviceDiscovery()
    monkeypatch.setattr(discovery, "_candidate_local_ipv4s", lambda: ["192.168.10.3", "10.0.0.8"])

    assert discovery.get_effective_subnet() == "192.168.10.0/24"


def test_get_discovered_device_map_refreshes_when_cache_is_stale(monkeypatch):
    discovery = LanDeviceDiscovery()
    discovery._discovered_ips = ["192.168.1.214"]
    discovery._last_scan_at = time.time() - 30
    calls: list[bool] = []

    def _fake_scan(force: bool = False) -> list[str]:
        calls.append(force)
        discovery._discovered_ips = ["192.168.1.215"]
        discovery._last_scan_at = time.time()
        return ["192.168.1.215"]

    monkeypatch.setattr(discovery, "scan_now", _fake_scan)

    assert discovery.get_discovered_device_map() == {"1": "192.168.1.215"}
    assert calls == [False]
