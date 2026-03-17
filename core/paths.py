from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    return project_root() / "config"


def plugins_dir() -> Path:
    return project_root() / "plugins"


def data_dir() -> Path:
    path = config_dir() / "data"
    subdir = (os.environ.get("MYT_DATA_SUBDIR") or "").strip()
    if subdir:
        # Keep data within config/data. Reject absolute paths and traversal.
        subdir_norm = subdir.replace("\\", "/").strip("/")
        parts = [p for p in subdir_norm.split("/") if p]
        if any(p in {".", ".."} for p in parts) or (":" in subdir_norm):
            raise ValueError("MYT_DATA_SUBDIR must be a safe relative path under config/data")
        path = path.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def traces_dir() -> Path:
    path = data_dir() / "traces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_db_path() -> Path:
    return data_dir() / "tasks.db"


def account_db_path() -> Path:
    return data_dir() / "accounts.json.db"


def browser_profiles_dir() -> Path:
    """Browser profile cache directory (configurable via config/system.yaml)."""
    from core.system_settings_loader import get_browser_profiles_dir

    return get_browser_profiles_dir()


def ai_work_dir() -> Path:
    """AI vision working directory (configurable via config/system.yaml)."""
    from core.system_settings_loader import get_ai_work_dir

    return get_ai_work_dir()


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
