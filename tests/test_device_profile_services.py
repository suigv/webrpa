import json

from core.device_profile_generator import generate_env_bundle
from core.device_profile_inventory import get_phone_models, refresh_phone_models
from core.device_profile_selector import resolve_cloud_container, select_phone_model


class _FakeSdkClient:
    def __init__(
        self,
        device_ip: str,
        sdk_port: int = 8000,
        timeout_seconds: float = 30.0,
        retries: int = 3,
    ) -> None:
        _ = (timeout_seconds, retries)
        self.device_ip = device_ip
        self.sdk_port = sdk_port

    def list_phone_models_online(self):
        return {
            "ok": True,
            "data": {
                "data": {
                    "list": [
                        {
                            "id": "m-1",
                            "name": "GooglePixel9Pro",
                            "status": "online",
                            "sdk_ver": "34",
                        },
                        {
                            "id": "m-2",
                            "name": "SM-S9260",
                            "status": "online",
                            "sdk_ver": "34",
                        },
                    ]
                }
            },
        }

    def list_local_phone_models(self):
        return {
            "ok": True,
            "data": {
                "list": [
                    {"modelName": "PixelLocal01", "status": "ready"},
                    {"modelName": "PixelLocal02", "status": "ready"},
                ]
            },
        }

    def list_androids(self):
        return {
            "ok": True,
            "data": {
                "list": [
                    {"name": "android-01", "indexNum": 1, "status": "running"},
                    {"name": "android-02", "indexNum": 2, "status": "running"},
                ]
            },
        }


def test_refresh_phone_models_online_writes_cache(monkeypatch):
    import core.device_profile_inventory as inventory_module

    monkeypatch.setattr(inventory_module, "MytSdkClient", _FakeSdkClient)

    result = refresh_phone_models("online", device_ip="192.168.1.214", sdk_port=8000)

    assert result["ok"] is True
    data = result["data"]
    assert data["source"] == "online"
    assert data["count"] == 2
    assert data["items"][0]["name"] in {"GooglePixel9Pro", "SM-S9260"}


def test_get_phone_models_reads_cache_without_refresh(monkeypatch):
    import core.device_profile_inventory as inventory_module

    monkeypatch.setattr(inventory_module, "MytSdkClient", _FakeSdkClient)
    refresh_phone_models("local", device_ip="192.168.1.214", sdk_port=8000)

    class _FailingSdkClient(_FakeSdkClient):
        def list_local_phone_models(self):
            raise AssertionError("cache should be used before live fetch")

    monkeypatch.setattr(inventory_module, "MytSdkClient", _FailingSdkClient)
    cached = get_phone_models("local", device_ip="192.168.1.214", sdk_port=8000, refresh=False)

    assert cached["ok"] is True
    assert cached["data"]["from_cache"] is True
    assert cached["data"]["count"] == 2


def test_select_phone_model_is_deterministic():
    items = [
        {"source": "online", "id": "m-1", "name": "GooglePixel9Pro", "status": "online"},
        {"source": "online", "id": "m-2", "name": "SM-S9260", "status": "online"},
        {"source": "online", "id": "m-3", "name": "SM-S9210", "status": "offline"},
    ]

    first = select_phone_model(
        source="online",
        items=items,
        filters={"status": "online", "name_contains": "SM-"},
        seed="device-7-cloud-2",
    )
    second = select_phone_model(
        source="online",
        items=items,
        filters={"status": "online", "name_contains": "SM-"},
        seed="device-7-cloud-2",
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["data"]["selected"] == second["data"]["selected"]
    assert first["data"]["apply"]["model_id"] == "m-2"


def test_generate_env_bundle_jp_profile_has_expected_shape():
    result = generate_env_bundle(country_profile="jp_mobile", seed="jp-seed", contact_count=2)

    assert result["country_profile"] == "jp_mobile"
    assert result["language"] == "ja"
    assert result["country"] == "JP"
    assert result["timezone"] == "Asia/Tokyo"
    assert result["google_adid"] == result["fingerprint"]["gaid"]
    assert len(result["contacts"]) == 2
    assert result["fingerprint"]["mcc"] == "440"
    assert result["fingerprint"]["imei"].isdigit()
    assert len(result["fingerprint"]["imei"]) == 15

    # Keep payload JSON-safe for direct API / plugin consumption.
    json.dumps(result, ensure_ascii=False)


def test_resolve_cloud_container_prefers_cloud_index(monkeypatch):
    import core.device_profile_selector as selector_module

    monkeypatch.setattr(selector_module, "MytSdkClient", _FakeSdkClient)

    result = resolve_cloud_container(
        device_ip="192.168.1.214",
        sdk_port=8000,
        cloud_id=2,
    )

    assert result["ok"] is True
    assert result["data"]["container_name"] == "android-02"


def test_resolve_cloud_container_falls_back_to_cloud_id_when_sdk_list_unavailable(monkeypatch):
    import core.device_profile_selector as selector_module

    class _UnavailableSdkClient(_FakeSdkClient):
        def list_androids(self):
            return {"ok": False, "error": "http_503: Service Unavailable"}

    monkeypatch.setattr(selector_module, "MytSdkClient", _UnavailableSdkClient)

    result = resolve_cloud_container(
        device_ip="192.168.1.214",
        sdk_port=8000,
        cloud_id=2,
        api_port=30101,
    )

    assert result["ok"] is True
    assert result["data"]["container_name"] == "android-02"
    assert result["data"]["degraded"] is True
    assert result["data"]["fallback_reason"] == "http_503: Service Unavailable"
