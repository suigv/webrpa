"""
core/system_settings_loader.py

Loader for config/system.yaml — system-level settings (single source of truth).

Hierarchy:
  config/system.yaml   ← all non-secret settings live here
  env vars             ← only for secrets: MYT_LLM_API_KEY, MYT_VLM_API_KEY

Usage:
    from core.system_settings_loader import get_redis_url, get_llm_base_url, ...
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from models.system_settings import SystemSettings, VLMProviderSettings

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_settings: Optional[SystemSettings] = None


def _system_yaml_path() -> Path:
    from core.paths import project_root
    return project_root() / "config" / "system.yaml"


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # pyyaml
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if isinstance(raw, dict):
            return raw
        logger.warning("system.yaml is not a mapping; using defaults")
    except FileNotFoundError:
        pass  # normal for fresh installs — defaults will be used
    except Exception as exc:
        logger.warning("Failed to load system.yaml: %s; using defaults", exc)
    return {}


def _build_settings(raw: Dict[str, Any]) -> SystemSettings:
    try:
        return SystemSettings.model_validate(raw)
    except Exception as exc:
        logger.warning("system.yaml validation failed (%s); using defaults", exc)
        return SystemSettings()


def load(refresh: bool = False) -> SystemSettings:
    """Load (and cache) SystemSettings from config/system.yaml."""
    global _settings
    with _lock:
        if _settings is None or refresh:
            raw = _load_yaml_file(_system_yaml_path())
            _settings = _build_settings(raw)
    return _settings


# ─── Feature flags ────────────────────────────────────────────────────────────

def get_rpc_enabled() -> bool:
    env_rpc = os.environ.get("MYT_ENABLE_RPC")
    if env_rpc is not None:
        return env_rpc.strip().lower() not in ("0", "false", "no", "off")
    return load().features.enable_rpc


def get_vlm_enabled() -> bool:
    return load().features.enable_vlm


# ─── Service URLs / config (from yaml) ───────────────────────────────────────

def get_redis_url() -> str:
    return load().services.redis_url


def get_llm_base_url() -> str:
    return get_llm_provider_config().base_url


def get_llm_model() -> str:
    return get_llm_provider_config().model


def get_llm_provider() -> str:
    return load().services.llm.provider


def get_vlm_provider() -> str:
    return load().services.vlm.provider


def get_vlm_provider_config(name: Optional[str] = None) -> Any:
    """Get config for a specific VLM provider, or the active one if name is None."""
    settings = load().services.vlm
    provider_name = name or settings.provider
    config = settings.providers.get(provider_name)
    if config:
        return config
    # Fallback to top-level if not found in dict
    return VLMProviderSettings(
        base_url=settings.base_url,
        model=settings.model,
        provider_type="standard"
    )


def get_llm_provider_config(name: Optional[str] = None) -> Any:
    """Get config for a specific provider, or the active one if name is None."""
    settings = load().services.llm
    provider_name = name or settings.provider
    config = settings.providers.get(provider_name)
    if config:
        return config
    # Fallback to top-level if not found in dict
    from models.system_settings import LLMProviderSettings
    return LLMProviderSettings(
        base_url=settings.base_url,
        model=settings.model,
        provider_type="openai"
    )


def get_vlm_base_url() -> str:
    return get_vlm_provider_config().base_url


def get_vlm_model() -> str:
    return get_vlm_provider_config().model


# ─── Secrets (env vars ONLY — never from yaml) ───────────────────────────────

def get_llm_api_key(provider_name: Optional[str] = None) -> str:
    """
    LLM API key. 
    Priority:
    1. MYT_LLM_API_KEY_{PROVIDER_NAME_UPPER}
    2. MYT_LLM_API_KEY
    """
    if not provider_name:
        provider_name = get_llm_provider()

    # 1. MYT_LLM_API_KEY_DEEPSEEK
    suffix = str(provider_name).upper().replace("-", "_")
    key = os.environ.get(f"MYT_LLM_API_KEY_{suffix}")
    if key:
        return key.strip()

    # 2. MYT_LLM_API_KEY (Shared fallback)
    return (os.environ.get("MYT_LLM_API_KEY") or "").strip()


def get_vlm_api_key(provider_name: Optional[str] = None) -> str:
    """
    VLM API key. 
    Priority:
    1. MYT_VLM_API_KEY_{PROVIDER_NAME_UPPER}
    2. MYT_VLM_API_KEY (Shared fallback)
    """
    if not provider_name:
        provider_name = get_vlm_provider()

    suffix = str(provider_name).upper().replace("-", "_")
    key = os.environ.get(f"MYT_VLM_API_KEY_{suffix}")
    if key:
        return key.strip()

    # 2. MYT_VLM_API_KEY
    return (os.environ.get("MYT_VLM_API_KEY") or "").strip()


# ─── Paths (from yaml) ────────────────────────────────────────────────────────

def get_browser_profiles_dir() -> Path:
    return Path(load().paths.browser_profiles_dir)


def get_ai_work_dir() -> Path:
    return Path(load().paths.ai_work_dir)


# ─── Credentials (from yaml) ─────────────────────────────────────────────────

def get_credential_allowlist() -> str:
    """Colon-separated allowlist of credential root paths."""
    return load().credentials.allowlist
