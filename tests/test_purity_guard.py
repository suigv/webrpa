import new.core.data_store as data_store
from fastapi.testclient import TestClient

from new.api.server import app


def test_removed_migrate_route_stays_unavailable():
    client = TestClient(app)
    response = client.post("/api/data/migrate")
    assert response.status_code == 404


def test_removed_migration_symbol_is_absent():
    removed_symbol = "migrate_" + "legacy_txt_to_json"
    assert not hasattr(data_store, removed_symbol)
