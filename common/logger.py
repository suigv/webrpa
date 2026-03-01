import asyncio
import logging
import os
import re
import sys


class Logger:
    _instance = None
    _initialized = False
    _ws_broadcast = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        if Logger._initialized:
            return
        self.logger = logging.getLogger("NewStandaloneLogger")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.handlers.clear()

        console = logging.StreamHandler(sys.stdout)
        try:
            console.stream = os.fdopen(sys.stdout.fileno(), "w", buffering=1)
        except Exception:
            console.stream = sys.stdout
        console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"))
        self.logger.addHandler(console)
        Logger._initialized = True

    def set_ws_broadcast(self, broadcast_func):
        self._ws_broadcast = broadcast_func

    def log(self, device_index: int, message: str, level: str = "info") -> None:
        full_msg = f"[Dev {device_index}] {message}"
        if level == "error":
            self.logger.error(full_msg)
        elif level == "warning":
            self.logger.warning(full_msg)
        else:
            self.logger.info(full_msg)

        if self._ws_broadcast:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._ws_broadcast(full_msg))
            except Exception:
                pass


log_manager = Logger()
logger = log_manager.logger
