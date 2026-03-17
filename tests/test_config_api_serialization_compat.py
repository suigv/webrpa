# pyright: reportPrivateUsage=false

from typing import cast

import core.config_loader as config_loader
from api.routes import config as config_route
from models.config import HumanizedConfigSchema


def test_config_route_serializes_humanized_subset_and_legacy_fields_from_normalized_config() -> (
    None
):
    backup = config_loader.ConfigLoader._config
    try:
        config_loader.ConfigLoader._config = config_loader.normalize_config(
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
        )

        payload = cast(dict[str, object], config_route.get_config().model_dump())
        payload_humanized = cast(dict[str, object], payload["humanized"])

        assert payload["humanization_enabled"] is True
        assert payload["humanization_seed"] == 0
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
