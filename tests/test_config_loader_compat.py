# pyright: reportPrivateUsage=false

import json
from pathlib import Path
from typing import cast

import core.config_loader as config_loader


def test_normalize_config_preserves_legacy_humanization_compatibility() -> None:
    normalized = config_loader.ConfigStore.model_validate(
        {
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "humanized": {"enabled": False},
            "humanization_enabled": True,
            "humanization_seed": "17",
            "humanization_intensity": "66",
            "humanization_delay_ms": "12",
            "humanization_jitter_ms": "7",
        }
    ).model_dump(mode="python")

    assert normalized["humanized"]["enabled"] is False
    assert normalized["humanized"]["random_seed"] == 17
    assert normalized["humanization_enabled"] is False
    assert normalized["humanization_seed"] == 17
    assert normalized["humanization_intensity"] == 66
    assert normalized["humanization_delay_ms"] == 12
    assert normalized["humanization_jitter_ms"] == 7


def test_config_loader_update_uses_cached_config_seam_and_writes_normalized_payload(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "devices.json"
    _ = config_path.write_text("{}", encoding="utf-8")

    backup_file = config_loader.CONFIG_FILE
    backup_cache = config_loader.ConfigLoader._config
    try:
        config_loader.CONFIG_FILE = config_path
        config_loader.ConfigLoader._config = {
            "host_ip": "127.0.0.1",
            "device_ips": {},
            "total_devices": 1,
            "sdk_port": 8000,
            "humanization_enabled": True,
            "humanization_seed": 41,
        }

        config_loader.ConfigLoader.update(default_ai="openai", humanized={"enabled": False})

        persisted = cast(dict[str, object], json.loads(config_path.read_text(encoding="utf-8")))
        persisted_humanized = cast(dict[str, object], persisted["humanized"])
        assert isinstance(config_loader.ConfigLoader._config, config_loader.ConfigStore)
        assert config_loader.ConfigLoader._config.model_dump(mode="python") == persisted
        assert "default_ai" not in persisted
        assert persisted_humanized["enabled"] is False
        assert persisted_humanized["random_seed"] == 41
        assert persisted["humanization_enabled"] is False
        assert persisted["humanization_seed"] == 41
    finally:
        config_loader.CONFIG_FILE = backup_file
        config_loader.ConfigLoader._config = backup_cache
