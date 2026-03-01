import os
from pathlib import Path


class ToolsKit:
    def get_root_path(self) -> str:
        env_root = os.environ.get("MYT_NEW_ROOT")
        if env_root:
            return env_root
        return str(Path(__file__).resolve().parents[1])
