import os

from common.toolskit import ToolsKit
from core.config_loader import ConfigLoader, get_default_ai


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        tools = ToolsKit()
        self.root_path = tools.get_root_path()
        self.log_dir = os.path.join(self.root_path, "log")
        os.makedirs(self.log_dir, exist_ok=True)
        self.runtime_config = {"delay": 5, "schedule_enabled": False}

    def update_runtime(self, key: str, value):
        if key in ("ip", "host_ip"):
            ConfigLoader.update(host_ip=value)
            return
        if key in ("ai_type", "default_ai"):
            ConfigLoader.update(default_ai=value)
            return
        self.runtime_config[key] = value

    @property
    def ai_type(self) -> str:
        return get_default_ai()


cfg = ConfigManager()
