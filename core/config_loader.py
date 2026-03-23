# pyright: reportDeprecated=false, reportUnusedImport=false, reportUnusedFunction=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from __future__ import annotations

import json
import logging
import threading
from typing import Any

from core.paths import project_root
from models.config import ConfigStore, ConfigStoreUpdate
from models.humanized import HumanizedWrapperConfig

logger = logging.getLogger(__name__)

CONFIG_FILE = project_root() / "config" / "devices.json"


class ConfigLoader:
    _config: ConfigStore | None = None
    _lock = threading.RLock()

    @classmethod
    def load(cls, refresh: bool = False) -> ConfigStore:
        with cls._lock:
            if cls._config is None or refresh:
                if not CONFIG_FILE.exists():
                    cls._config = ConfigStore()
                else:
                    try:
                        with open(CONFIG_FILE, encoding="utf-8") as f:
                            cls._config = ConfigStore.model_validate(json.load(f))
                    except Exception:
                        cls._config = ConfigStore()
            return cls._config

    @classmethod
    def update(cls, **kwargs) -> dict[str, Any]:
        with cls._lock:
            current_state = cls.load()
            current = (
                current_state
                if isinstance(current_state, dict)
                else current_state.model_dump(mode="python")
            )
            try:
                update_payload = ConfigStoreUpdate.model_validate(kwargs).model_dump(
                    mode="python",
                    exclude_none=True,
                    exclude_unset=True,
                )
            except Exception as exc:
                logger.debug(f"Config update validation failed, using raw payload: {exc}")
                update_payload = dict(kwargs)
            updated = {**current, **update_payload}
            try:
                cls._config = ConfigStore.model_validate(updated)
            except Exception:
                cls._config = ConfigStore()
            normalized = cls._config.model_dump(mode="python")
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(normalized, f, indent=2, ensure_ascii=False)
            return normalized

    @classmethod
    def migrate(cls) -> bool:
        with cls._lock:
            if not CONFIG_FILE.exists():
                cls._config = ConfigStore()
                return False
            try:
                with open(CONFIG_FILE, encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = {}
            if not isinstance(raw, dict):
                raw = {}
            try:
                cls._config = ConfigStore.model_validate(raw)
            except Exception:
                cls._config = ConfigStore()
            normalized = cls._config.model_dump(mode="python")
            changed = normalized != raw
            if changed:
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(normalized, f, indent=2, ensure_ascii=False)
            return changed


# --- 辅助访问器 (由 API 和 Core 强引用) ---
def _c() -> ConfigStore:
    result = ConfigLoader.load()
    if isinstance(result, dict):
        return ConfigStore.model_validate(result)
    return result


def get_host_ip() -> str:
    return _c().host_ip


def get_device_ips() -> dict[str, str]:
    return _c().device_ips


def get_device_ip(device_id: int) -> str:
    return get_device_ips().get(str(device_id), "") or get_host_ip()


def get_total_devices() -> int:
    return _c().total_devices


def get_cloud_machines_per_device() -> int:
    return _c().cloud_machines_per_device


def get_sdk_port() -> int:
    return _c().sdk_port


def get_schema_version() -> int:
    return _c().schema_version


def get_allocation_version() -> int:
    return _c().allocation_version


def get_stop_hour() -> int | None:
    return _c().stop_hour


def get_cycle_interval() -> int:
    return _c().cycle_interval


def get_discovery_enabled() -> bool:
    return _c().discovery_enabled


def get_discovery_subnet() -> str:
    return _c().discovery_subnet


def get_judge_mode() -> str:
    return _c().judge_mode


def get_step_parallel() -> int:
    return _c().step_parallel


# --- 拟人化访问器 ---
def get_humanized_config() -> dict[str, Any]:
    return _c().humanized.model_dump()


def get_humanized_wrapper_config() -> HumanizedWrapperConfig:
    return HumanizedWrapperConfig(**get_humanized_config())


def get_humanization_enabled() -> bool:
    return _c().humanization_enabled


def get_humanization_intensity() -> int:
    return _c().humanization_intensity


def get_humanization_seed() -> int:
    return _c().humanization_seed


def get_humanization_delay_ms() -> int:
    return _c().humanization_delay_ms


def get_humanization_jitter_ms() -> int:
    return _c().humanization_jitter_ms


# --- Vision 访问器 ---
def get_vision_monitor_enabled() -> bool:
    return _c().vision_monitor_enabled


def get_vision_device_type() -> str:
    return _c().vision_device_type


def get_vision_pipeline_type() -> str:
    return _c().vision_pipeline_type


def get_vision_model_name() -> str:
    return _c().vision_model_name


def get_vision_thought_language() -> str:
    return _c().vision_thought_language


def get_vision_timeout_seconds() -> int:
    return _c().vision_timeout_seconds


def get_vision_cooldown_ms() -> int:
    return _c().vision_cooldown_ms


def get_vision_dedupe_window_ms() -> int:
    return _c().vision_dedupe_window_ms


def get_vision_max_fallback_per_step() -> int:
    return _c().vision_max_fallback_per_step
