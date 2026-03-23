# pyright: reportPrivateUsage=false

from typing import cast

import core.config_loader as config_loader
from api.routes import config as config_route
from models.config import Config, ConfigUpdate, HumanizedConfigSchema


def test_config_route_serializes_humanized_subset_and_legacy_fields_from_normalized_config() -> (
    None
):
    backup = config_loader.ConfigLoader._config
    try:
        config_loader.ConfigLoader._config = config_loader.ConfigStore.model_validate(
            {
                "host_ip": "127.0.0.1",
                "device_ips": {},
                "total_devices": 1,
                "sdk_port": 8000,
                "humanized": {
                    "enabled": True,
                    "typing_delay_min": 0.11,
                    "typing_delay_max": 0.22,
                    "typo_probability": 0.4,
                    "fallback_policy": "skip",
                    "move_steps_min": 3,
                    "move_steps_max": 4,
                    "random_seed": None,
                },
            }
        ).model_dump(mode="python")

        payload = cast(dict[str, object], config_route.get_config().model_dump())
        payload_humanized = cast(dict[str, object], payload["humanized"])

        assert payload["humanization_enabled"] is True
        assert payload["humanization_seed"] == 0
        assert "default_ai" not in payload
        expected_humanized = HumanizedConfigSchema.model_validate(
            {
                "enabled": True,
                "typing_delay_min": 0.11,
                "typing_delay_max": 0.22,
                "typo_probability": 0.4,
                "fallback_policy": "skip",
                "move_steps_min": 3,
                "move_steps_max": 4,
                "random_seed": None,
            }
        ).model_dump()
        assert payload_humanized == expected_humanized
        assert "fallback_policy" not in payload_humanized
    finally:
        config_loader.ConfigLoader._config = backup


def test_config_route_update_ignores_public_default_ai_field(monkeypatch) -> None:
    observed: dict[str, object] = {}
    current = Config(
        host_ip="127.0.0.1",
        device_ips={"1": "127.0.0.1"},
        total_devices=1,
        sdk_port=8000,
    )

    monkeypatch.setattr(config_route, "get_config", lambda: current)
    monkeypatch.setattr(
        config_route.ConfigLoader, "update", lambda **kwargs: observed.update(kwargs)
    )

    class _Discovery:
        def scan_now(self) -> None:
            return None

    monkeypatch.setattr(config_route, "LanDeviceDiscovery", lambda: _Discovery())

    response = config_route.update_config(
        ConfigUpdate.model_validate({"default_ai": "openai", "host_ip": "127.0.0.1"})
    )

    assert observed == {
        "host_ip": "127.0.0.1",
        "total_devices": 1,
        "device_ips": {"1": "127.0.0.1"},
        "stop_hour": 18,
    }
    assert "default_ai" not in response.model_dump()
