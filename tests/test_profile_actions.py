import importlib

from engine.models.runtime import ExecutionContext


def test_profile_actions_are_registered_and_callable(monkeypatch):
    registry_module = importlib.import_module("engine.action_registry")
    profile_actions_module = importlib.import_module("engine.actions.profile_actions")

    reg = registry_module.ActionRegistry()
    monkeypatch.setattr(registry_module, "_registry", reg)
    registry_module.register_defaults()

    assert reg.has("inventory.get_phone_models")
    assert reg.has("inventory.refresh_phone_models")
    assert reg.has("selector.select_phone_model")
    assert reg.has("selector.resolve_cloud_container")
    assert reg.has("generator.generate_env_bundle")
    assert reg.has("profile.apply_env_bundle")
    assert reg.has("profile.wait_cloud_available")

    monkeypatch.setattr(
        profile_actions_module,
        "get_phone_models",
        lambda *args, **kwargs: {
            "ok": True,
            "data": {
                "inventory_type": "phone_models",
                "source": "online",
                "device_ip": "192.168.1.214",
                "sdk_port": 8000,
                "count": 1,
                "items": [{"source": "online", "id": "m-1", "name": "Pixel"}],
                "refreshed_at": "2026-03-19T00:00:00+00:00",
                "from_cache": False,
            },
        },
    )
    monkeypatch.setattr(
        profile_actions_module,
        "refresh_phone_models",
        lambda *args, **kwargs: {
            "ok": True,
            "data": {
                "inventory_type": "phone_models",
                "source": "online",
                "device_ip": "192.168.1.214",
                "sdk_port": 8000,
                "count": 1,
                "items": [{"source": "online", "id": "m-1", "name": "Pixel"}],
                "refreshed_at": "2026-03-19T00:00:00+00:00",
                "from_cache": False,
            },
        },
    )
    monkeypatch.setattr(
        profile_actions_module,
        "select_phone_model",
        lambda **kwargs: {
            "ok": True,
            "data": {
                "source": kwargs["source"],
                "seed": "seed-1",
                "candidate_count": 1,
                "selected_index": 0,
                "filters": kwargs.get("filters") or {},
                "selected": {"source": "online", "id": "m-1", "name": "Pixel"},
                "apply": {
                    "source": "online",
                    "model_id": "m-1",
                    "local_model": "",
                    "model_name": "Pixel",
                },
            },
        },
    )
    monkeypatch.setattr(
        profile_actions_module,
        "resolve_cloud_container",
        lambda **kwargs: {
            "ok": True,
            "data": {
                "container_name": "android-02",
                "cloud_id": kwargs.get("cloud_id"),
                "selected": {"name": "android-02", "indexNum": 2},
                "candidate_count": 1,
            },
        },
    )

    class _FakeAndroidClient:
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        def set_language_country(self, language, country):
            return {"ok": True, "data": {"language": language, "country": country}}

        def set_device_fingerprint(self, data):
            return {"ok": True, "data": {"fingerprint": data}}

        def set_google_id(self, adid):
            return {"ok": True, "data": {"adid": adid}}

        def add_contact(self, contacts=None, **kwargs):
            _ = kwargs
            return {"ok": True, "data": {"count": len(contacts or [])}}

        def set_shake(self, enabled=None, **kwargs):
            _ = kwargs
            return {"ok": True, "data": {"enabled": enabled}}

        def screenshot(self, level=2, **kwargs):
            _ = kwargs
            return {"ok": True, "data": {"level": level}}

    monkeypatch.setattr(profile_actions_module, "AndroidApiClient", _FakeAndroidClient)

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "sdk_port": 8000})

    inventory_res = reg.resolve("inventory.get_phone_models")({"source": "online"}, ctx)
    selector_res = reg.resolve("selector.select_phone_model")(
        {"source": "online", "filters": {"name_contains": "Pixel"}},
        ctx,
    )
    container_res = reg.resolve("selector.resolve_cloud_container")(
        {},
        ExecutionContext(
            payload={"device_ip": "192.168.1.214", "sdk_port": 8000},
            runtime={"api_port": 30101, "cloud_id": 2},
        ),
    )
    generator_res = reg.resolve("generator.generate_env_bundle")(
        {"country_profile": "jp_mobile", "seed": "bundle-seed"},
        ctx,
    )
    apply_res = reg.resolve("profile.apply_env_bundle")(
        {
            "language": "ja",
            "country": "JP",
            "fingerprint": {"imei": "123456789012345"},
            "google_adid": "8b15e5c7-8481-40ca-9ec8-4122f1c47fb6",
            "contacts": [{"user": "Sato Yui", "tel": "09012345678"}],
            "set_google_id": True,
            "write_contacts": True,
            "take_screenshot": True,
        },
        ctx,
    )

    assert inventory_res.ok is True
    assert inventory_res.data["count"] == 1
    assert selector_res.ok is True
    assert selector_res.data["apply"]["model_id"] == "m-1"
    assert container_res.ok is True
    assert container_res.data["container_name"] == "android-02"
    assert generator_res.ok is True
    assert generator_res.data["country"] == "JP"
    assert apply_res.ok is True
    assert "screenshot" in apply_res.data


def test_profile_apply_env_bundle_uses_runtime_target_endpoint(monkeypatch):
    profile_actions_module = importlib.import_module("engine.actions.profile_actions")

    seen: dict[str, object] = {}

    class _FakeAndroidClient:
        def __init__(self, device_ip, api_port, timeout_seconds=30.0, retries=3):
            seen["device_ip"] = device_ip
            seen["api_port"] = api_port
            seen["timeout_seconds"] = timeout_seconds
            seen["retries"] = retries

        def set_language_country(self, language, country):
            return {"ok": True, "data": {"language": language, "country": country}}

        def set_device_fingerprint(self, data):
            return {"ok": True, "data": {"fingerprint": data}}

        def set_shake(self, enabled=None, **kwargs):
            _ = kwargs
            return {"ok": True, "data": {"enabled": enabled}}

        def screenshot(self, level=2, **kwargs):
            _ = kwargs
            return {"ok": True, "data": {"level": level}}

    monkeypatch.setattr(profile_actions_module, "AndroidApiClient", _FakeAndroidClient)

    result = profile_actions_module.profile_apply_env_bundle(
        {
            "language": "ja",
            "country": "JP",
            "fingerprint": {"imei": "123456789012345"},
            "set_google_id": False,
            "write_contacts": False,
            "take_screenshot": False,
        },
        ExecutionContext(
            payload={},
            runtime={
                "target": {
                    "device_ip": "192.168.1.214",
                    "api_port": 30201,
                    "sdk_port": 8000,
                    "cloud_id": 3,
                }
            },
        ),
    )

    assert result.ok is True
    assert seen["device_ip"] == "192.168.1.214"
    assert seen["api_port"] == 30201


def test_profile_wait_cloud_available_waits_for_reboot_cycle(monkeypatch):
    profile_actions_module = importlib.import_module("engine.actions.profile_actions")

    snapshots = iter(
        [
            {
                "device_id": 1,
                "cloud_id": 2,
                "availability_state": "available",
                "availability_reason": "ok",
                "stale": False,
            },
            {
                "device_id": 1,
                "cloud_id": 2,
                "availability_state": "unavailable",
                "availability_reason": "restarting",
                "stale": False,
            },
            {
                "device_id": 1,
                "cloud_id": 2,
                "availability_state": "available",
                "availability_reason": "ok",
                "stale": False,
            },
        ]
    )

    class _FakeManager:
        def get_cloud_probe_snapshot(self, device_id, cloud_id):
            snapshot = next(snapshots)
            assert snapshot["device_id"] == device_id
            assert snapshot["cloud_id"] == cloud_id
            return snapshot

    monkeypatch.setattr(profile_actions_module, "get_device_manager", lambda: _FakeManager())
    monkeypatch.setattr(profile_actions_module.time, "sleep", lambda _seconds: None)

    result = profile_actions_module.profile_wait_cloud_available(
        {
            "timeout_ms": 5000,
            "transition_timeout_ms": 2000,
            "poll_interval_ms": 200,
            "require_cycle": True,
        },
        ExecutionContext(payload={}, runtime={"target": {"device_id": 1, "cloud_id": 2}}),
    )

    assert result.ok is True
    assert result.data["transition_observed"] is True
