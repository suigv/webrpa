from fastapi.testclient import TestClient

from api.server import app
from core.config_loader import ConfigLoader


def test_api_devices_nested_contract():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 2,
            "cloud_machines_per_device": 3,
            "sdk_port": 8000,
        }
        client = TestClient(app)
        response = client.get("/api/devices/")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 2

        first = payload[0]
        assert first["schema_version"] == 2
        assert first["allocation_version"] == 1
        assert first["device_id"] == 1
        assert first["sdk_port"] == 8000
        assert first["sdk_port_role"] == "device_control_api"
        assert first["cloud_slots_total"] == 12
        assert len(first["cloud_machines"]) == 12
        assert "api_port" in first["cloud_machines"][0]
        assert first["cloud_machines"][0]["api_port_role"] == "cloud_api"
        assert "rpa_port" in first["cloud_machines"][0]
        assert first["cloud_machines"][0]["rpa_port_role"] == "mytrpc_control"
        assert "machine_model_name" in first["cloud_machines"][0]
        assert "machine_model_id" in first["cloud_machines"][0]
    finally:
        ConfigLoader._config = backup


def test_api_device_not_found_for_out_of_range_id():
    backup = ConfigLoader._config
    try:
        ConfigLoader._config = {
            "schema_version": 2,
            "allocation_version": 1,
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "cloud_machines_per_device": 2,
            "sdk_port": 8000,
        }
        client = TestClient(app)
        response = client.get("/api/devices/999")
        assert response.status_code == 404
    finally:
        ConfigLoader._config = backup
