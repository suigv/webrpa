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


class ConfigLoader:
    _config: Optional[Dict[str, Any]] = None

    @classmethod
    def load(cls) -> Dict[str, Any]:
        if cls._config is None:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cls._config = json.load(f)
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
        config = cls.load()
        config.update(kwargs)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        cls._config = config


def get_host_ip() -> str:
    return str(ConfigLoader.get("host_ip", "127.0.0.1"))


def get_device_ips() -> dict[str, str]:
    raw = ConfigLoader.get("device_ips", {})
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
