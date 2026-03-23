from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]


class ErrorType(StrEnum):
    """标准化错误码类别。"""

    OK = "ok"
    ENV_ERROR = "env_error"  # 环境故障（RPC断连、驱动缺失）
    BUSINESS_ERROR = "business_error"  # 业务逻辑错误（找不到元素、流程逻辑失败）
    AUTH_ERROR = "auth_error"  # 认证/权限错误（登录失败、账号封禁）
    TIMEOUT = "timeout"  # 执行超时
    UNKNOWN = "unknown"  # 未知错误


class ActionResult(BaseModel):
    ok: bool
    code: str = "ok"
    error_type: ErrorType = ErrorType.OK
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: Any | None = None


class ExecutionCancelledError(Exception):
    pass


ExecutionCancelled = ExecutionCancelledError


class ExecutionContext:
    """Mutable runtime context shared across steps. Not a Pydantic model
    because it holds non-serializable objects (browser session)."""

    def __init__(
        self,
        payload: dict[str, Any],
        session: dict[str, Any] | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> None:
        self.payload = payload
        self.session: dict[str, Any] = session if isinstance(session, dict) else {}
        self.runtime: dict[str, Any] = runtime if isinstance(runtime, dict) else {}
        self.vars: dict[str, Any] = {}
        self.last_result: ActionResult | None = None
        self.browser: Any = None  # BrowserClient instance, lazily assigned
        self.pc: int = 0
        self.transitions: int = 0
        self.jumped: bool = False
        self.should_cancel: Callable[[], bool] | None = None
        self.emit_event: Callable[[str, dict[str, Any]], None] | None = None
        self._humanized: Any | None = None  # HumanizedHelper instance
        self._wait_signal: Any | None = None  # WaitSignal (lazy)

    @property
    def humanized(self) -> Any:
        """极简访问拟人化助手。优先使用 payload/runtime 中的 humanized 覆盖配置。"""
        if self._humanized is None:
            import dataclasses

            from core.config_loader import get_humanized_wrapper_config
            from engine.humanized_helper import HumanizedHelper

            config = get_humanized_wrapper_config()
            override = self.payload.get("humanized") or self.runtime.get("humanized")
            if override and isinstance(override, dict):
                valid = {f.name for f in dataclasses.fields(config)}
                filtered = {k: v for k, v in override.items() if k in valid}
                if filtered:
                    config = dataclasses.replace(config, **filtered)
            self._humanized = HumanizedHelper(
                config,
                speed_profile=self.payload.get("_speed") or self.runtime.get("_speed") or "normal",
            )
        return self._humanized

    @property
    def session_defaults(self) -> dict[str, Any]:
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
            raise ExecutionCancelledError("Task execution cancelled by user request")

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
