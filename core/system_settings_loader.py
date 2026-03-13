"""
core/system_settings_loader.py

Loader for config/system.yaml — system-level settings (single source of truth).

Hierarchy:
  config/system.yaml   ← all non-secret settings live here
  env vars             ← only for secrets: MYT_LLM_API_KEY, UITARS_API_KEY

Usage:
    from core.system_settings_loader import get_redis_url, get_llm_base_url, ...
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from models.system_settings import SystemSettings

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
    return load().features.enable_rpc


def get_vlm_enabled() -> bool:
    return load().features.enable_vlm


# ─── Service URLs / config (from yaml) ───────────────────────────────────────

def get_redis_url() -> str:
    return load().services.redis_url


def get_llm_base_url() -> str:
    return load().services.llm.base_url


def get_llm_model() -> str:
    return load().services.llm.model


def get_llm_provider() -> str:
    return load().services.llm.provider


def get_vlm_base_url() -> str:
    return load().services.vlm.base_url


def get_vlm_model() -> str:
    return load().services.vlm.model


# ─── Secrets (env vars ONLY — never from yaml) ───────────────────────────────

def get_llm_api_key() -> str:
    """LLM API key — must be set via env var MYT_LLM_API_KEY. Never in yaml."""
    return (os.environ.get("MYT_LLM_API_KEY") or "").strip()


def get_vlm_api_key() -> str:
    """VLM API key — must be set via env var UITARS_API_KEY. Never in yaml."""
    return (os.environ.get("UITARS_API_KEY") or "").strip()


# ─── Paths (from yaml) ────────────────────────────────────────────────────────

def get_browser_profiles_dir() -> Path:
    return Path(load().paths.browser_profiles_dir)


def get_ai_work_dir() -> Path:
    return Path(load().paths.ai_work_dir)


# ─── Credentials (from yaml) ─────────────────────────────────────────────────

def get_credential_allowlist() -> str:
    """Colon-separated allowlist of credential root paths."""
    return load().credentials.allowlist
