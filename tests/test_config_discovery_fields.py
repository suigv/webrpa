from fastapi.testclient import TestClient

from new.api.server import app
from new.core.config_loader import ConfigLoader
from new.core.lan_discovery import LanDeviceDiscovery


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
        monkeypatch.setattr(
            LanDeviceDiscovery,
            "get_discovered_device_map",
            lambda self: {"1": "192.168.1.214", "2": "192.168.1.216"},
        )

        client = TestClient(app)
        response = client.get("/api/config/")
        assert response.status_code == 200
        payload = response.json()
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
