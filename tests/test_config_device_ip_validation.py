from fastapi.testclient import TestClient

from api.server import app
from core.config_loader import ConfigLoader


def test_config_update_accepts_partial_device_ips_mapping_for_compat_mode():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "192.168.1.214",
            "device_ips": {"1": "192.168.1.214"},
            "total_devices": 1,
            "sdk_port": 8000,
        }
        client = TestClient(app)
        response = client.put(
            "/api/config/",
            json={
                "total_devices": 3,
                "device_ips": {
                    "1": "192.168.1.214",
                    "2": "192.168.1.215",
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_devices"] == 3
    finally:
        ConfigLoader._config = backup


def test_config_update_rejects_duplicate_device_ips():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "192.168.1.214",
            "device_ips": {"1": "192.168.1.214"},
            "total_devices": 1,
            "sdk_port": 8000,
        }
        client = TestClient(app)
        response = client.put(
            "/api/config/",
            json={
                "total_devices": 2,
                "device_ips": {
                    "1": "192.168.1.214",
                    "2": "192.168.1.214",
                },
            },
        )
        assert response.status_code == 400
        assert "duplicate device ip" in response.json().get("detail", "")
    finally:
        ConfigLoader._config = backup


def test_config_update_accepts_full_unique_mapping():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "192.168.1.214",
            "device_ips": {"1": "192.168.1.214"},
            "total_devices": 1,
            "sdk_port": 8000,
        }
        client = TestClient(app)
        response = client.put(
            "/api/config/",
            json={
                "host_ip": "192.168.1.214",
                "total_devices": 2,
                "device_ips": {
                    "1": "192.168.1.214",
                    "2": "192.168.1.215",
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_devices"] == 2
        assert payload["device_ips"] == {
            "1": "192.168.1.214",
            "2": "192.168.1.215",
        }
    finally:
        ConfigLoader._config = backup
