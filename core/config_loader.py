import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _project_root() -> Path:
    env_root = os.environ.get("MYT_NEW_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[1]


CONFIG_FILE = _project_root() / "config" / "devices.json"

DEFAULT_SCHEMA_VERSION = 2
DEFAULT_ALLOCATION_VERSION = 1
DEFAULT_CLOUD_MACHINES_PER_DEVICE = 10
DEFAULT_SDK_PORT = 8000


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_device_ips(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        result: dict[str, str] = {}
        for key, value in raw.items():
            key_str = str(key).strip()
            value_str = str(value).strip()
            if key_str and value_str:
                result[key_str] = value_str
        return result

    if isinstance(raw, list):
        result: dict[str, str] = {}
        for index, value in enumerate(raw, start=1):
            value_str = str(value).strip()
            if value_str:
                result[str(index)] = value_str
        return result

    return {}


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = dict(config)
    normalized["host_ip"] = str(config.get("host_ip", "127.0.0.1"))
    normalized["device_ips"] = _normalize_device_ips(config.get("device_ips", {}))

    total_devices = _to_int(config.get("total_devices", 1), 1)
    normalized["total_devices"] = max(1, total_devices)

    cloud_machines = _to_int(
        config.get("cloud_machines_per_device", DEFAULT_CLOUD_MACHINES_PER_DEVICE),
        DEFAULT_CLOUD_MACHINES_PER_DEVICE,
    )
    normalized["cloud_machines_per_device"] = max(1, cloud_machines)

    schema_version = _to_int(config.get("schema_version", DEFAULT_SCHEMA_VERSION), DEFAULT_SCHEMA_VERSION)
    normalized["schema_version"] = max(1, schema_version)

    allocation_version = _to_int(
        config.get("allocation_version", DEFAULT_ALLOCATION_VERSION),
        DEFAULT_ALLOCATION_VERSION,
    )
    normalized["allocation_version"] = max(1, allocation_version)

    sdk_port = _to_int(config.get("sdk_port", DEFAULT_SDK_PORT), DEFAULT_SDK_PORT)
    normalized["sdk_port"] = sdk_port if 1 <= sdk_port <= 65535 else DEFAULT_SDK_PORT

    return normalized


class ConfigLoader:
    _config: Optional[Dict[str, Any]] = None

    @classmethod
    def load(cls) -> Dict[str, Any]:
        if cls._config is None:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cls._config = normalize_config(raw)
        return cls._config or {}

    @classmethod
    def reload(cls) -> Dict[str, Any]:
        cls._config = None
        return cls.load()

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        return cls.load().get(key, default)

    @classmethod
    def update(cls, **kwargs: Any) -> None:
        config = normalize_config({**cls.load(), **kwargs})
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        cls._config = config

    @classmethod
    def migrate(cls) -> bool:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        normalized = normalize_config(raw)
        if raw == normalized:
            cls._config = normalized
            return False
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2, ensure_ascii=False)
        cls._config = normalized
        return True


def get_host_ip() -> str:
    return str(ConfigLoader.get("host_ip", "127.0.0.1"))


def get_device_ips() -> dict[str, str]:
    return _normalize_device_ips(ConfigLoader.get("device_ips", {}))


def get_device_ip(device_index: int) -> str:
    device_ips = get_device_ips()
    if str(device_index) in device_ips:
        return device_ips[str(device_index)]
    return get_host_ip()


def get_total_devices() -> int:
    try:
        return max(1, int(ConfigLoader.get("total_devices", 1)))
    except (TypeError, ValueError):
        return 1


def get_cloud_machines_per_device() -> int:
    try:
        value = int(ConfigLoader.get("cloud_machines_per_device", DEFAULT_CLOUD_MACHINES_PER_DEVICE))
    except (TypeError, ValueError):
        return DEFAULT_CLOUD_MACHINES_PER_DEVICE
    return value if value >= 1 else DEFAULT_CLOUD_MACHINES_PER_DEVICE


def get_schema_version() -> int:
    try:
        value = int(ConfigLoader.get("schema_version", DEFAULT_SCHEMA_VERSION))
    except (TypeError, ValueError):
        return DEFAULT_SCHEMA_VERSION
    return value if value >= 1 else DEFAULT_SCHEMA_VERSION


def get_allocation_version() -> int:
    try:
        value = int(ConfigLoader.get("allocation_version", DEFAULT_ALLOCATION_VERSION))
    except (TypeError, ValueError):
        return DEFAULT_ALLOCATION_VERSION
    return value if value >= 1 else DEFAULT_ALLOCATION_VERSION


def get_sdk_port() -> int:
    try:
        value = int(ConfigLoader.get("sdk_port", DEFAULT_SDK_PORT))
    except (TypeError, ValueError):
        return DEFAULT_SDK_PORT
    return value if 1 <= value <= 65535 else DEFAULT_SDK_PORT


def get_default_ai() -> str:
    return str(ConfigLoader.get("default_ai", "volc"))


def get_stop_hour() -> int:
    try:
        value = int(ConfigLoader.get("stop_hour", 18))
    except (TypeError, ValueError):
        return 18
    return value if 0 <= value <= 23 else 18


def get_cycle_interval() -> int:
    try:
        value = int(ConfigLoader.get("cycle_interval", 15))
    except (TypeError, ValueError):
        return 15
    return value if 1 <= value <= 3600 else 15


def get_judge_mode() -> str:
    value = str(ConfigLoader.get("judge_mode", "lite")).strip().lower()
    return value if value in {"off", "lite", "full"} else "lite"


def get_step_parallel() -> int:
    try:
        value = int(ConfigLoader.get("step_parallel", 4))
    except (TypeError, ValueError):
        return 4
    return value if 1 <= value <= 64 else 4


def get_humanization_enabled() -> bool:
    return bool(ConfigLoader.get("humanization_enabled", False))


def get_humanization_intensity() -> int:
    try:
        return int(ConfigLoader.get("humanization_intensity", 50))
    except (TypeError, ValueError):
        return 50


def get_humanization_seed() -> int:
    try:
        return int(ConfigLoader.get("humanization_seed", 0))
    except (TypeError, ValueError):
        return 0


def get_humanization_delay_ms() -> int:
    try:
        return int(ConfigLoader.get("humanization_delay_ms", 0))
    except (TypeError, ValueError):
        return 0


def get_humanization_jitter_ms() -> int:
    try:
        return int(ConfigLoader.get("humanization_jitter_ms", 0))
    except (TypeError, ValueError):
        return 0


def get_vision_monitor_enabled() -> bool:
    return bool(ConfigLoader.get("vision_monitor_enabled", False))


def get_vision_device_type() -> str:
    return str(ConfigLoader.get("vision_device_type", "mobile"))


def get_vision_pipeline_type() -> str:
    return str(ConfigLoader.get("vision_pipeline_type", "agent"))


def get_vision_model_name() -> str:
    return str(ConfigLoader.get("vision_model_name", ""))


def get_vision_thought_language() -> str:
    return str(ConfigLoader.get("vision_thought_language", "chinese"))


def get_vision_timeout_seconds() -> int:
    try:
        return int(ConfigLoader.get("vision_timeout_seconds", 8))
    except (TypeError, ValueError):
        return 8


def get_vision_cooldown_ms() -> int:
    try:
        return int(ConfigLoader.get("vision_cooldown_ms", 3000))
    except (TypeError, ValueError):
        return 3000


def get_vision_dedupe_window_ms() -> int:
    try:
        return int(ConfigLoader.get("vision_dedupe_window_ms", 5000))
    except (TypeError, ValueError):
        return 5000


def get_vision_max_fallback_per_step() -> int:
    try:
        return int(ConfigLoader.get("vision_max_fallback_per_step", 2))
    except (TypeError, ValueError):
        return 2
