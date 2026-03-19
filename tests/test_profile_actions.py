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
    assert reg.has("generator.generate_env_bundle")

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

    ctx = ExecutionContext(payload={"device_ip": "192.168.1.214", "sdk_port": 8000})

    inventory_res = reg.resolve("inventory.get_phone_models")({"source": "online"}, ctx)
    selector_res = reg.resolve("selector.select_phone_model")(
        {"source": "online", "filters": {"name_contains": "Pixel"}},
        ctx,
    )
    generator_res = reg.resolve("generator.generate_env_bundle")(
        {"country_profile": "jp_mobile", "seed": "bundle-seed"},
        ctx,
    )

    assert inventory_res.ok is True
    assert inventory_res.data["count"] == 1
    assert selector_res.ok is True
    assert selector_res.data["apply"]["model_id"] == "m-1"
    assert generator_res.ok is True
    assert generator_res.data["country"] == "JP"
