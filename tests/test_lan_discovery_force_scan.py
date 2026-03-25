import time

from core.config_loader import ConfigLoader
from core.lan_discovery import LanDeviceDiscovery
from models.config import ConfigStore


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

        assert discovery.scan_now(force=True) == ["192.168.1.214"]
        assert discovery.scan_now() == ["192.168.1.214"]
    finally:
        ConfigLoader._config = backup


def test_get_effective_subnet_prefers_auto_detected_local_network(monkeypatch):
    discovery = LanDeviceDiscovery()
    monkeypatch.setattr(discovery, "_candidate_local_ipv4s", lambda: ["192.168.10.3", "10.0.0.8"])

    assert discovery.get_effective_subnet() == "192.168.10.0/24"


def test_get_discovered_device_map_returns_cached_mapping_without_refresh(monkeypatch):
    discovery = LanDeviceDiscovery()
    discovery._discovered_ips = ["192.168.1.214"]
    discovery._last_scan_at = time.time() - 30

    def _fake_scan(force: bool = False) -> list[str]:
        raise AssertionError("get_discovered_device_map should not trigger scans")

    monkeypatch.setattr(discovery, "scan_now", _fake_scan)

    assert discovery.get_discovered_device_map() == {"1": "192.168.1.214"}


def test_probe_ip_accepts_valid_myt_sdk_response(monkeypatch):
    discovery = LanDeviceDiscovery()

    class _FakeSdkClient:
        def __init__(
            self, device_ip: str, sdk_port: int, timeout_seconds: float, retries: int
        ) -> None:
            assert device_ip == "192.168.1.214"
            assert sdk_port == 8000
            assert timeout_seconds == discovery._connect_timeout_seconds
            assert retries == 1

        def get_api_version(self) -> dict[str, object]:
            return {
                "code": 0,
                "message": "ok",
                "data": {"latestVersion": 110, "currentVersion": 108},
            }

        def get_device_info(self) -> dict[str, object]:
            raise AssertionError("version probe should already be enough")

    monkeypatch.setattr("core.lan_discovery.MytSdkClient", _FakeSdkClient)

    assert discovery._probe_ip("192.168.1.214", 8000) is True


def test_probe_ip_accepts_wrapped_sdk_response(monkeypatch):
    discovery = LanDeviceDiscovery()

    class _FakeSdkClient:
        def __init__(
            self, device_ip: str, sdk_port: int, timeout_seconds: float, retries: int
        ) -> None:
            return None

        def get_api_version(self) -> dict[str, object]:
            return {
                "ok": True,
                "data": {
                    "code": 0,
                    "message": "OK",
                    "data": {"latestVersion": 90, "currentVersion": 89},
                },
            }

        def get_device_info(self) -> dict[str, object]:
            raise AssertionError("wrapped version probe should already be enough")

    monkeypatch.setattr("core.lan_discovery.MytSdkClient", _FakeSdkClient)

    assert discovery._probe_ip("192.168.1.214", 8000) is True


def test_probe_ip_rejects_non_sdk_http_payload(monkeypatch):
    discovery = LanDeviceDiscovery()

    class _FakeSdkClient:
        def __init__(
            self, device_ip: str, sdk_port: int, timeout_seconds: float, retries: int
        ) -> None:
            return None

        def get_api_version(self) -> dict[str, object]:
            return {"ok": True, "data": {"status": "healthy"}}

        def get_device_info(self) -> dict[str, object]:
            return {"code": 0, "message": "ok", "data": {"status": "healthy"}}

    monkeypatch.setattr("core.lan_discovery.MytSdkClient", _FakeSdkClient)

    assert discovery._probe_ip("192.168.1.214", 8000) is False


def test_refresh_and_persist_writes_discovered_mapping(monkeypatch):
    backup = ConfigLoader._config
    discovery = LanDeviceDiscovery()
    updates: list[dict[str, object]] = []
    try:
        ConfigLoader._config = ConfigStore.model_validate(
            {
                "host_ip": "192.168.1.214",
                "device_ips": {},
                "total_devices": 1,
                "sdk_port": 8000,
                "discovery_enabled": True,
                "discovered_device_ips": {},
                "discovered_total_devices": 0,
            }
        )

        def _fake_update(**kwargs):
            updates.append(dict(kwargs))
            current = (
                ConfigLoader._config.model_dump(mode="python")
                if isinstance(ConfigLoader._config, ConfigStore)
                else dict(ConfigLoader._config or {})
            )
            ConfigLoader._config = ConfigStore.model_validate({**current, **kwargs})
            return current

        monkeypatch.setattr(discovery, "scan_now", lambda force=False: ["192.168.1.215"])
        monkeypatch.setattr("core.lan_discovery.ConfigLoader.update", _fake_update)

        assert discovery.refresh_and_persist(force=True) == ["192.168.1.215"]
        assert updates == [
            {
                "discovered_device_ips": {"1": "192.168.1.215"},
                "discovered_total_devices": 1,
            }
        ]
    finally:
        ConfigLoader._config = backup


def test_refresh_and_persist_skips_redundant_config_write(monkeypatch):
    backup = ConfigLoader._config
    discovery = LanDeviceDiscovery()
    try:
        ConfigLoader._config = ConfigStore.model_validate(
            {
                "host_ip": "192.168.1.214",
                "device_ips": {},
                "total_devices": 1,
                "sdk_port": 8000,
                "discovery_enabled": True,
                "discovered_device_ips": {"1": "192.168.1.215"},
                "discovered_total_devices": 1,
            }
        )

        monkeypatch.setattr(discovery, "scan_now", lambda force=False: ["192.168.1.215"])

        def _unexpected_update(**kwargs):
            raise AssertionError(f"ConfigLoader.update should not be called: {kwargs}")

        monkeypatch.setattr("core.lan_discovery.ConfigLoader.update", _unexpected_update)

        assert discovery.refresh_and_persist(force=True) == ["192.168.1.215"]
    finally:
        ConfigLoader._config = backup
