from __future__ import annotations

import sys
from pathlib import Path


def _ensure_parent_has_new_package() -> None:
    project_root = Path(__file__).resolve().parent
    parent_dir = project_root.parent
    package_init = project_root / "__init__.py"
    if not package_init.exists():
        return
    parent_text = str(parent_dir)
    if parent_text in sys.path:
        return
    sys.path.insert(0, parent_text)


_ensure_parent_has_new_package()
