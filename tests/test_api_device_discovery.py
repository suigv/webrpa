from fastapi.testclient import TestClient

from api.server import app
from core.config_loader import ConfigLoader
from core.lan_discovery import LanDeviceDiscovery


def test_api_devices_discover_endpoint(monkeypatch):
    monkeypatch.setattr(
        LanDeviceDiscovery,
        "scan_now",
        lambda self, force=False: ["192.168.1.214", "192.168.1.216"] if force else [],
    )
    with TestClient(app) as client:
        response = client.post("/api/devices/discover")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "started"
        assert "message" in payload


def test_api_devices_discover_updates_config_mapping(monkeypatch):
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "192.168.1.214",
            "device_ips": {"1": "192.168.1.214", "2": "192.168.1.215"},
            "total_devices": 2,
            "sdk_port": 8000,
            "discovery_enabled": False,
            "discovery_subnet": "192.168.1.0/24",
        }
        monkeypatch.setattr(LanDeviceDiscovery, "scan_now", lambda self, force=False: ["192.168.1.214"])

        with TestClient(app) as client:
            response = client.post("/api/devices/discover")
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "started"

            cfg = client.get("/api/config/").json()
            assert cfg["total_devices"] == 1
            assert cfg["device_ips"] == {"1": "192.168.1.214"}
    finally:
        ConfigLoader._config = backup
