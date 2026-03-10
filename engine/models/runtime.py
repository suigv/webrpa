from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]


class ActionResult(BaseModel):
    ok: bool
    code: str = "ok"
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


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

    @property
    def session_defaults(self) -> Dict[str, Any]:
        defaults = self.session.get("defaults")
        return defaults if isinstance(defaults, dict) else {}

    @property
    def target(self) -> Dict[str, Any]:
        target = self.runtime.get("target")
        return target if isinstance(target, dict) else {}

    @property
    def task_id(self) -> str:
        value = self.runtime.get("task_id")
        return str(value) if value is not None else ""

    @property
    def cloud_target_label(self) -> str:
        value = self.runtime.get("cloud_target")
        return str(value) if value is not None else ""

    def get_session_default(self, key: str, default: Any = None) -> Any:
        return self.session_defaults.get(key, default)
