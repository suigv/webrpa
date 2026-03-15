from __future__ import annotations

import enum
from typing import Any, Callable, Dict, Optional, List

from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]


class ErrorType(str, enum.Enum):
    """标准化错误码类别。"""
    OK = "ok"
    ENV_ERROR = "env_error"           # 环境故障（RPC断连、驱动缺失）
    BUSINESS_ERROR = "business_error" # 业务逻辑错误（找不到元素、流程逻辑失败）
    AUTH_ERROR = "auth_error"         # 认证/权限错误（登录失败、账号封禁）
    TIMEOUT = "timeout"               # 执行超时
    UNKNOWN = "unknown"               # 未知错误


class ActionResult(BaseModel):
    ok: bool
    code: str = "ok"
    error_type: ErrorType = ErrorType.OK
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)
    evidence: Optional[Any] = None


class ExecutionCancelled(Exception):
    pass


class ExecutionContext:
    """Mutable runtime context shared across steps. Not a Pydantic model
    because it holds non-serializable objects (browser session)."""

    def __init__(
        self,
        payload: Dict[str, Any],
        session: Optional[Dict[str, Any]] = None,
        runtime: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.payload = payload
        self.session: Dict[str, Any] = session if isinstance(session, dict) else {}
        self.runtime: Dict[str, Any] = runtime if isinstance(runtime, dict) else {}
        self.vars: Dict[str, Any] = {}
        self.last_result: Optional[ActionResult] = None
        self.browser: Any = None  # BrowserClient instance, lazily assigned
        self.pc: int = 0
        self.transitions: int = 0
        self.jumped: bool = False
        self.should_cancel: Optional[Callable[[], bool]] = None
        self.emit_event: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._humanized: Optional[Any] = None  # HumanizedHelper instance
        self._wait_signal: Optional[Any] = None  # WaitSignal (lazy)

    @property
    def humanized(self) -> Any:
        """极简访问拟人化助手。优先使用 payload/runtime 中的 humanized 覆盖配置。"""
        if self._humanized is None:
            from core.config_loader import get_humanized_wrapper_config
            from engine.humanized_helper import HumanizedHelper
            import dataclasses
            config = get_humanized_wrapper_config()
            override = self.payload.get("humanized") or self.runtime.get("humanized")
            if override and isinstance(override, dict):
                valid = {f.name for f in dataclasses.fields(config)}
                filtered = {k: v for k, v in override.items() if k in valid}
                if filtered:
                    config = dataclasses.replace(config, **filtered)
            self._humanized = HumanizedHelper(config)
        return self._humanized

    @property
    def session_defaults(self) -> Dict[str, Any]:
        defaults = self.session.get("defaults")
        return defaults if isinstance(defaults, dict) else {}

    @property
    def device_id(self) -> int:
        value = self.runtime.get("device_id")
        if value is None and "target" in self.runtime:
            value = self.runtime["target"].get("device_id")
        return int(value) if value is not None else 0

    @property
    def cloud_id(self) -> int:
        value = self.runtime.get("cloud_id")
        if value is None and "target" in self.runtime:
            value = self.runtime["target"].get("cloud_id")
        return int(value) if value is not None else 0

    @property
    def cloud_target(self) -> str:
        value = self.runtime.get("cloud_target")
        return str(value) if value is not None else ""

    def get_session_default(self, key: str, default: Any = None) -> Any:
        return self.session_defaults.get(key, default)

    def check_cancelled(self) -> None:
        """检查任务是否已被请求取消。如果已取消，则抛出异常以终止当前动作。"""
        if self.should_cancel and self.should_cancel():
            raise ExecutionCancelled("Task execution cancelled by user request")

    @property
    def wait_signal(self) -> Any:
        if self._wait_signal is None:
            from engine.wait_signal import WaitSignal

            self._wait_signal = WaitSignal(name=f"wait-signal-{id(self):x}")
        return self._wait_signal

    @property
    def physical_width(self) -> int | None:
        return self.session.get("physical_width")

    @physical_width.setter
    def physical_width(self, value: int | None) -> None:
        self.session["physical_width"] = value

    @property
    def physical_height(self) -> int | None:
        return self.session.get("physical_height")

    @physical_height.setter
    def physical_height(self, value: int | None) -> None:
        self.session["physical_height"] = value

    def notify_wait_signal(self) -> None:
        if self._wait_signal is not None:
            self._wait_signal.notify()

    def reset_wait_signal(self) -> None:
        if self._wait_signal is not None:
            self._wait_signal.reset()

    def close(self) -> None:
        if self._wait_signal is not None:
            self._wait_signal.close()
            self._wait_signal = None
