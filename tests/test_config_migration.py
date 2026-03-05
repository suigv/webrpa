import json

import new.core.config_loader as config_loader


def test_config_migration_idempotent(tmp_path):
    config_path = tmp_path / "devices.json"
    raw = {
        "host_ip": "127.0.0.1",
        "device_ips": ["127.0.0.2", "127.0.0.3"],
        "total_devices": 2,
    }
    config_path.write_text(json.dumps(raw), encoding="utf-8")

    backup_file = config_loader.CONFIG_FILE
    backup_cache = config_loader.ConfigLoader._config
    try:
        config_loader.CONFIG_FILE = config_path
        config_loader.ConfigLoader._config = None

        changed_first = config_loader.ConfigLoader.migrate()
        changed_second = config_loader.ConfigLoader.migrate()

        assert changed_first is True
        assert changed_second is False

        migrated = json.loads(config_path.read_text(encoding="utf-8"))
        assert migrated["schema_version"] == 2
        assert migrated["allocation_version"] == 1
        assert migrated["cloud_machines_per_device"] == 12
        assert migrated["sdk_port"] == 8000
        assert migrated["device_ips"] == {"1": "127.0.0.2", "2": "127.0.0.3"}
        assert "humanized" in migrated
        assert isinstance(migrated["humanized"], dict)
        assert "enabled" in migrated["humanized"]
        assert "typing_delay_min" in migrated["humanized"]
        assert "move_steps_max" in migrated["humanized"]
    finally:
        config_loader.CONFIG_FILE = backup_file
        config_loader.ConfigLoader._config = backup_cache
