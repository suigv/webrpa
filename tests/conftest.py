import os
from pathlib import Path


def pytest_sessionstart(session):
    project_root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("MYT_NEW_ROOT", str(project_root))
