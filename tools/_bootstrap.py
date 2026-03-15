from __future__ import annotations

import sys
from pathlib import Path


def _script_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_project_root_on_sys_path() -> Path:
    root = _script_project_root()
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    return root


def bootstrap_project_root() -> Path:
    _ = ensure_project_root_on_sys_path()
    from core.paths import project_root

    return project_root()
