from __future__ import annotations

import os
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


def task_db_path() -> Path:
    return data_dir() / "tasks.db"
