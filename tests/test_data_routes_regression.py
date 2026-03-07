from fastapi.testclient import TestClient

from api.server import app


def test_data_routes_and_removed_migrate_route():
    client = TestClient(app)

    for route in ("/api/data/accounts", "/api/data/location", "/api/data/website"):
        response = client.get(route)
        assert response.status_code == 200
        payload = response.json()
        assert "data" in payload

    removed = client.post("/api/data/migrate")
    assert removed.status_code == 404
