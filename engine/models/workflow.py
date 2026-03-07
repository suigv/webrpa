from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# ---- Failure handling ----

class FailStrategy(str, Enum):
    abort = "abort"
    skip = "skip"
    retry = "retry"
    goto = "goto"


class OnFail(BaseModel):
    strategy: FailStrategy = FailStrategy.abort
    retries: int = 0
    delay_ms: int = 300
    goto: Optional[str] = None


# ---- Conditions ----

class ConditionType(str, Enum):
    exists = "exists"
    text_contains = "text_contains"
    url_contains = "url_contains"
    var_equals = "var_equals"
    var_truthy = "var_truthy"
    result_ok = "result_ok"


class Condition(BaseModel):
    type: ConditionType
    selector: Optional[str] = None
    text: Optional[str] = None
    value: Optional[str] = None
    var: Optional[str] = None
    equals: Any = None


class ConditionExpr(BaseModel):
    all: Optional[List[Condition]] = None
    any: Optional[List[Condition]] = None


# ---- Step types ----

class ActionStep(BaseModel):
    label: Optional[str] = None
    kind: Literal["action"]
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    save_as: Optional[str] = None
    timeout_ms: Optional[int] = None
    on_fail: Optional[OnFail] = None


class IfStep(BaseModel):
    label: Optional[str] = None
    kind: Literal["if"]
    when: ConditionExpr
    then: str
    otherwise: Optional[str] = None
    timeout_ms: Optional[int] = None
    on_fail: Optional[OnFail] = None


class WaitUntilStep(BaseModel):
    label: Optional[str] = None
    kind: Literal["wait_until"]
    check: ConditionExpr
    interval_ms: int = 500
    timeout_ms: int = 10000
    on_timeout: Optional[OnFail] = None
    on_fail: Optional[OnFail] = None


class GotoStep(BaseModel):
    label: Optional[str] = None
    kind: Literal["goto"]
    target: str
    timeout_ms: Optional[int] = None
    on_fail: Optional[OnFail] = None


class StopStep(BaseModel):
    label: Optional[str] = None
    kind: Literal["stop"]
    status: Literal["success", "failed"] = "success"
    message: str = ""
    timeout_ms: Optional[int] = None
    on_fail: Optional[OnFail] = None


Step = Annotated[Union[ActionStep, IfStep, WaitUntilStep, GotoStep, StopStep], Field(discriminator="kind")]


# ---- Workflow script ----

class WorkflowScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"]
    workflow: str
    vars: Dict[str, Any] = Field(default_factory=dict)
    steps: List[Step] = Field(default_factory=list)
