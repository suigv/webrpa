from fastapi.testclient import TestClient

from api.server import app


def test_profile_routes(monkeypatch):
    import api.routes.profiles as profiles_route

    monkeypatch.setattr(
        profiles_route,
        "refresh_phone_models",
        lambda *args, **kwargs: {
            "ok": True,
            "data": {
                "inventory_type": "phone_models",
                "source": args[0],
                "device_ip": kwargs["device_ip"],
                "sdk_port": kwargs["sdk_port"],
                "count": 1,
                "items": [{"source": args[0], "id": "m-1", "name": "Pixel"}],
                "refreshed_at": "2026-03-19T00:00:00+00:00",
                "from_cache": False,
            },
        },
    )
    monkeypatch.setattr(
        profiles_route,
        "get_phone_models",
        lambda *args, **kwargs: {
            "ok": True,
            "data": {
                "inventory_type": "phone_models",
                "source": args[0],
                "device_ip": kwargs["device_ip"],
                "sdk_port": kwargs["sdk_port"],
                "count": 1,
                "items": [{"source": args[0], "id": "m-2", "name": "SM-S9260"}],
                "refreshed_at": "2026-03-19T00:00:00+00:00",
                "from_cache": True,
            },
        },
    )
    monkeypatch.setattr(
        profiles_route,
        "select_phone_model",
        lambda **kwargs: {
            "ok": True,
            "data": {
                "source": kwargs["source"],
                "seed": kwargs["seed"] or "seed",
                "candidate_count": 1,
                "selected_index": 0,
                "filters": kwargs.get("filters") or {},
                "selected": {"source": kwargs["source"], "id": "m-2", "name": "SM-S9260"},
                "apply": {
                    "source": kwargs["source"],
                    "model_id": "m-2" if kwargs["source"] == "online" else "",
                    "local_model": "SM-S9260" if kwargs["source"] == "local" else "",
                    "model_name": "SM-S9260",
                },
            },
        },
    )

    with TestClient(app) as client:
        refresh_resp = client.post(
            "/api/inventory/phone-models/online/refresh",
            params={"device_ip": "192.168.1.214", "sdk_port": 8000},
        )
        assert refresh_resp.status_code == 200
        assert refresh_resp.json()["count"] == 1

        get_resp = client.get(
            "/api/inventory/phone-models/online",
            params={"device_ip": "192.168.1.214", "sdk_port": 8000},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["from_cache"] is True

        select_resp = client.post(
            "/api/selectors/phone-model",
            json={
                "source": "online",
                "device_ip": "192.168.1.214",
                "seed": "device-1-cloud-1",
                "filters": {"name_contains": "SM-"},
            },
        )
        assert select_resp.status_code == 200
        assert select_resp.json()["apply"]["model_id"] == "m-2"

        env_resp = client.post(
            "/api/generators/env-bundle",
            json={"country_profile": "jp_mobile", "seed": "bundle-seed", "contact_count": 2},
        )
        assert env_resp.status_code == 200
        assert env_resp.json()["country"] == "JP"
        assert len(env_resp.json()["contacts"]) == 2
