import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from ..models.humanized import FALLBACK_POLICIES, TARGET_STRATEGIES, HumanizedConfig, HumanizedWrapperConfig


def _project_root() -> Path:
    env_root = os.environ.get("MYT_NEW_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[1]


CONFIG_FILE = _project_root() / "config" / "devices.json"

DEFAULT_SCHEMA_VERSION = 2
DEFAULT_ALLOCATION_VERSION = 1
DEFAULT_CLOUD_MACHINES_PER_DEVICE = 10
DEFAULT_SDK_PORT = 8000  # Device-level control API port


def _default_humanized_dict() -> dict[str, Any]:
    return asdict(HumanizedConfig())


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _normalize_humanized(raw: Any, legacy: Dict[str, Any]) -> dict[str, Any]:
    defaults = _default_humanized_dict()
    source = dict(raw) if isinstance(raw, dict) else {}

    if "enabled" not in source and "humanization_enabled" in legacy:
        source["enabled"] = legacy.get("humanization_enabled")
    if "random_seed" not in source and "humanization_seed" in legacy:
        source["random_seed"] = legacy.get("humanization_seed")

    normalized = {
        "enabled": _to_bool(source.get("enabled", defaults["enabled"]), defaults["enabled"]),
        "typing_delay_min": _to_float(source.get("typing_delay_min", defaults["typing_delay_min"]), defaults["typing_delay_min"]),
        "typing_delay_max": _to_float(source.get("typing_delay_max", defaults["typing_delay_max"]), defaults["typing_delay_max"]),
        "typo_probability": _to_float(source.get("typo_probability", defaults["typo_probability"]), defaults["typo_probability"]),
        "typo_delay_min": _to_float(source.get("typo_delay_min", defaults["typo_delay_min"]), defaults["typo_delay_min"]),
        "typo_delay_max": _to_float(source.get("typo_delay_max", defaults["typo_delay_max"]), defaults["typo_delay_max"]),
        "backspace_delay_min": _to_float(source.get("backspace_delay_min", defaults["backspace_delay_min"]), defaults["backspace_delay_min"]),
        "backspace_delay_max": _to_float(source.get("backspace_delay_max", defaults["backspace_delay_max"]), defaults["backspace_delay_max"]),
        "word_pause_probability": _to_float(source.get("word_pause_probability", defaults["word_pause_probability"]), defaults["word_pause_probability"]),
        "word_pause_min": _to_float(source.get("word_pause_min", defaults["word_pause_min"]), defaults["word_pause_min"]),
        "word_pause_max": _to_float(source.get("word_pause_max", defaults["word_pause_max"]), defaults["word_pause_max"]),
        "click_offset_x_min": _to_int(source.get("click_offset_x_min", defaults["click_offset_x_min"]), int(defaults["click_offset_x_min"])),
        "click_offset_x_max": _to_int(source.get("click_offset_x_max", defaults["click_offset_x_max"]), int(defaults["click_offset_x_max"])),
        "click_offset_y_min": _to_int(source.get("click_offset_y_min", defaults["click_offset_y_min"]), int(defaults["click_offset_y_min"])),
        "click_offset_y_max": _to_int(source.get("click_offset_y_max", defaults["click_offset_y_max"]), int(defaults["click_offset_y_max"])),
        "pre_click_pause_min": _to_float(source.get("pre_click_pause_min", defaults["pre_click_pause_min"]), defaults["pre_click_pause_min"]),
        "pre_click_pause_max": _to_float(source.get("pre_click_pause_max", defaults["pre_click_pause_max"]), defaults["pre_click_pause_max"]),
        "click_hold_min": _to_float(source.get("click_hold_min", defaults["click_hold_min"]), defaults["click_hold_min"]),
        "click_hold_max": _to_float(source.get("click_hold_max", defaults["click_hold_max"]), defaults["click_hold_max"]),
        "post_click_pause_min": _to_float(source.get("post_click_pause_min", defaults["post_click_pause_min"]), defaults["post_click_pause_min"]),
        "post_click_pause_max": _to_float(source.get("post_click_pause_max", defaults["post_click_pause_max"]), defaults["post_click_pause_max"]),
        "target_strategy": str(source.get("target_strategy", defaults["target_strategy"])).strip() or defaults["target_strategy"],
        "target_center_bias_probability": _to_float(source.get("target_center_bias_probability", defaults["target_center_bias_probability"]), defaults["target_center_bias_probability"]),
        "pre_hover_enabled": _to_bool(source.get("pre_hover_enabled", defaults["pre_hover_enabled"]), defaults["pre_hover_enabled"]),
        "pre_hover_delay_min": _to_float(source.get("pre_hover_delay_min", defaults["pre_hover_delay_min"]), defaults["pre_hover_delay_min"]),
        "pre_hover_delay_max": _to_float(source.get("pre_hover_delay_max", defaults["pre_hover_delay_max"]), defaults["pre_hover_delay_max"]),
        "movement_jitter_probability": _to_float(source.get("movement_jitter_probability", defaults["movement_jitter_probability"]), defaults["movement_jitter_probability"]),
        "movement_overshoot_probability": _to_float(source.get("movement_overshoot_probability", defaults["movement_overshoot_probability"]), defaults["movement_overshoot_probability"]),
        "move_duration_min": _to_float(source.get("move_duration_min", defaults["move_duration_min"]), defaults["move_duration_min"]),
        "move_duration_max": _to_float(source.get("move_duration_max", defaults["move_duration_max"]), defaults["move_duration_max"]),
        "move_steps_min": _to_int(source.get("move_steps_min", defaults["move_steps_min"]), int(defaults["move_steps_min"])),
        "move_steps_max": _to_int(source.get("move_steps_max", defaults["move_steps_max"]), int(defaults["move_steps_max"])),
        "fallback_policy": str(source.get("fallback_policy", defaults["fallback_policy"])).strip() or defaults["fallback_policy"],
        "fallback_retry_count": _to_int(source.get("fallback_retry_count", defaults["fallback_retry_count"]), int(defaults["fallback_retry_count"])),
        "random_seed": None,
    }

    seed_raw = source.get("random_seed", defaults["random_seed"])
    if seed_raw in (None, "", "null"):
        normalized["random_seed"] = None
    else:
        normalized["random_seed"] = _to_int(seed_raw, 0)

    for probability_key in (
        "typo_probability",
        "word_pause_probability",
        "target_center_bias_probability",
        "movement_jitter_probability",
        "movement_overshoot_probability",
    ):
        value = _to_float(normalized.get(probability_key), float(defaults[probability_key]))
        normalized[probability_key] = max(0.0, min(1.0, value))

    for key in (
        "typing_delay_min",
        "typing_delay_max",
        "typo_delay_min",
        "typo_delay_max",
        "backspace_delay_min",
        "backspace_delay_max",
        "word_pause_min",
        "word_pause_max",
        "pre_click_pause_min",
        "pre_click_pause_max",
        "click_hold_min",
        "click_hold_max",
        "post_click_pause_min",
        "post_click_pause_max",
        "pre_hover_delay_min",
        "pre_hover_delay_max",
        "move_duration_min",
        "move_duration_max",
    ):
        value = _to_float(normalized.get(key), float(defaults[key]))
        normalized[key] = max(0.0, value)

    for key in (
        "move_steps_min",
        "move_steps_max",
    ):
        value = _to_int(normalized.get(key), int(defaults[key]))
        normalized[key] = max(1, value)

    normalized["fallback_retry_count"] = max(
        0,
        _to_int(normalized.get("fallback_retry_count"), int(defaults["fallback_retry_count"])),
    )

    target_strategy = str(normalized.get("target_strategy", defaults["target_strategy"])).strip()
    normalized["target_strategy"] = target_strategy if target_strategy in TARGET_STRATEGIES else defaults["target_strategy"]

    fallback_policy = str(normalized.get("fallback_policy", defaults["fallback_policy"])).strip()
    normalized["fallback_policy"] = fallback_policy if fallback_policy in FALLBACK_POLICIES else defaults["fallback_policy"]

    for min_key, max_key in (
        ("typing_delay_min", "typing_delay_max"),
        ("typo_delay_min", "typo_delay_max"),
        ("backspace_delay_min", "backspace_delay_max"),
        ("word_pause_min", "word_pause_max"),
        ("click_offset_x_min", "click_offset_x_max"),
        ("click_offset_y_min", "click_offset_y_max"),
        ("pre_click_pause_min", "pre_click_pause_max"),
        ("click_hold_min", "click_hold_max"),
        ("post_click_pause_min", "post_click_pause_max"),
        ("pre_hover_delay_min", "pre_hover_delay_max"),
        ("move_duration_min", "move_duration_max"),
        ("move_steps_min", "move_steps_max"),
    ):
        min_default = defaults[min_key]
        max_default = defaults[max_key]
        if isinstance(min_default, int):
            min_value = _to_int(normalized.get(min_key), int(min_default))
            max_value = _to_int(normalized.get(max_key), int(max_default))
        else:
            min_value = _to_float(normalized.get(min_key), float(min_default))
            max_value = _to_float(normalized.get(max_key), float(max_default))
        normalized[min_key] = min_value
        normalized[max_key] = max(min_value, max_value)

    return normalized


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

    normalized["humanized"] = _normalize_humanized(config.get("humanized"), config)

    # Keep legacy fields for backward compatibility.
    normalized["humanization_enabled"] = bool(normalized["humanized"].get("enabled", False))
    normalized["humanization_seed"] = normalized["humanized"].get("random_seed") or 0
    normalized["humanization_intensity"] = _to_int(config.get("humanization_intensity", 50), 50)
    normalized["humanization_delay_ms"] = _to_int(config.get("humanization_delay_ms", 0), 0)
    normalized["humanization_jitter_ms"] = _to_int(config.get("humanization_jitter_ms", 0), 0)

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
    humanized = ConfigLoader.get("humanized", {})
    if isinstance(humanized, dict) and "enabled" in humanized:
        return _to_bool(humanized.get("enabled"), False)
    return bool(ConfigLoader.get("humanization_enabled", False))


def get_humanization_intensity() -> int:
    try:
        return int(ConfigLoader.get("humanization_intensity", 50))
    except (TypeError, ValueError):
        return 50


def get_humanization_seed() -> int:
    humanized = ConfigLoader.get("humanized", {})
    if isinstance(humanized, dict):
        seed = humanized.get("random_seed")
        if seed in (None, "", "null"):
            return 0
        return _to_int(seed, 0)
    return _to_int(ConfigLoader.get("humanization_seed", 0), 0)


def get_humanized_config() -> dict[str, Any]:
    value = ConfigLoader.get("humanized", {})
    return _normalize_humanized(value, ConfigLoader.load())


def get_humanized_wrapper_config() -> HumanizedWrapperConfig:
    return HumanizedWrapperConfig(**get_humanized_config())


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
