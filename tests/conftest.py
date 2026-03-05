import os
import sys
from pathlib import Path


def pytest_sessionstart(session: object) -> None:
    _ = session
    project_root = Path(__file__).resolve().parents[1]
    project_parent = project_root.parent
    parent_text = str(project_parent)
    if parent_text not in sys.path:
        sys.path.insert(0, parent_text)
    _ = os.environ.setdefault("MYT_NEW_ROOT", str(project_root))
