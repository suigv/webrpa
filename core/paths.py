from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


def project_root() -> Path:
    env_root = os.environ.get("MYT_NEW_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    return project_root() / "config"


def data_dir() -> Path:
    path = config_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def traces_dir() -> Path:
    path = data_dir() / "traces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_db_path() -> Path:
    return data_dir() / "tasks.db"


def browser_profiles_dir() -> Path:
    """Browser profile cache directory (configurable via config/system.yaml)."""
    from core.system_settings_loader import get_browser_profiles_dir
    return get_browser_profiles_dir()


def ai_work_dir() -> Path:
    """AI vision working directory (configurable via config/system.yaml)."""
    from core.system_settings_loader import get_ai_work_dir
    return get_ai_work_dir()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
