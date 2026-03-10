import asyncio
import logging
import os
import sys
import json
from datetime import datetime


class Logger:
    _instance = None
    _initialized = False
    _ws_broadcast = None
    _main_loop = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        if Logger._initialized:
            return
        self.logger = logging.getLogger("WebRPALogger")
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
        try:
            self._main_loop = asyncio.get_running_loop()
        except Exception:
            self._main_loop = None

    def log(self, message: str, level: str = "info", task_id: str = "", target: str = "") -> None:
        """
        Log a message with structured context.
        Sends a JSON object to WebSocket clients.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 1. Console Logging (Formatted String)
        prefix = f"[{target or 'System'}] " if target else ""
        console_msg = f"{prefix}{message}"
        if level == "error":
            self.logger.error(console_msg)
        elif level == "warning":
            self.logger.warning(console_msg)
        else:
            self.logger.info(console_msg)

        # 2. WebSocket Broadcasting (Structured JSON)
        if self._ws_broadcast and self._main_loop:
            log_entry = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "task_id": task_id,
                "target": target or "System"
            }
            try:
                # 跨线程安全调度：任务往往在 ThreadPoolExecutor 的 worker 线程中运行
                # 所以必须使用 run_coroutine_threadsafe
                asyncio.run_coroutine_threadsafe(
                    self._ws_broadcast(json.dumps(log_entry, ensure_ascii=False)), 
                    self._main_loop
                )
            except Exception as e:
                pass


log_manager = Logger()
logger = log_manager.logger
