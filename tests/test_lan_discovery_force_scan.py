from new.core.config_loader import ConfigLoader
from new.core.lan_discovery import LanDeviceDiscovery


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

        monkeypatch.setattr(discovery, "_scan_targets", lambda subnet: ["192.168.1.214", "192.168.1.215"])
        monkeypatch.setattr(discovery, "_probe_ip", lambda ip, port: ip == "192.168.1.214")

        assert discovery.scan_now() == []
        assert discovery.scan_now(force=True) == ["192.168.1.214"]
        assert discovery.scan_now() == ["192.168.1.214"]
    finally:
        ConfigLoader._config = backup
