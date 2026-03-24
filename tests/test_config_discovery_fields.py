from api.routes import config as config_route
from core.config_loader import ConfigLoader


def test_config_response_includes_discovery_metadata(monkeypatch):
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "192.168.1.214",
            "device_ips": {},
            "total_devices": 1,
            "discovery_enabled": True,
            "discovery_subnet": "192.168.1.0/24",
            "sdk_port": 8000,
        }
        discovery = config_route.LanDeviceDiscovery()
        monkeypatch.setattr(
            discovery,
            "get_discovered_device_map",
            lambda: {"1": "192.168.1.214", "2": "192.168.1.216"},
        )
        monkeypatch.setattr(
            discovery,
            "get_effective_subnet",
            lambda: "192.168.1.0/24",
        )

        payload = config_route.get_config().model_dump(mode="python")
        assert payload["discovery_enabled"] is True
        assert payload["discovery_subnet"] == "192.168.1.0/24"
        assert payload["discovered_total_devices"] == 2
        assert payload["discovered_device_ips"] == {
            "1": "192.168.1.214",
            "2": "192.168.1.216",
        }
        assert payload["total_devices"] == 2
    finally:
        ConfigLoader._config = backup
