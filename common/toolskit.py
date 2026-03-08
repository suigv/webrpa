import os

from core.paths import project_root


class ToolsKit:
    def get_root_path(self) -> str:
        env_root = os.environ.get("MYT_NEW_ROOT")
        if env_root:
            return env_root
        return str(project_root())
