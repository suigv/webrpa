from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field


class ActionResult(BaseModel):
    ok: bool
    code: str = "ok"
    message: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class ExecutionContext:
    """Mutable runtime context shared across steps. Not a Pydantic model
    because it holds non-serializable objects (browser session)."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.vars: Dict[str, Any] = {}
        self.last_result: Optional[ActionResult] = None
        self.browser: Any = None  # BrowserClient instance, lazily assigned
        self.pc: int = 0
        self.transitions: int = 0
        self.jumped: bool = False
        self.should_cancel: Optional[Callable[[], bool]] = None
