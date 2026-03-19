from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---- Failure handling ----


class FailStrategy(StrEnum):
    abort = "abort"
    skip = "skip"
    retry = "retry"
    goto = "goto"


class OnFail(BaseModel):
    strategy: FailStrategy = FailStrategy.abort
    retries: int = 0
    delay_ms: int = 300
    goto: str | None = None


# ---- Conditions ----


class ConditionType(StrEnum):
    exists = "exists"
    text_contains = "text_contains"
    url_contains = "url_contains"
    var_equals = "var_equals"
    var_truthy = "var_truthy"
    result_ok = "result_ok"


class Condition(BaseModel):
    type: ConditionType
    selector: str | None = None
    text: str | None = None
    value: str | None = None
    var: str | None = None
    equals: Any = None


class ConditionExpr(BaseModel):
    all: list[Condition] | None = None
    any: list[Condition] | None = None


# ---- Step types ----


class ActionStep(BaseModel):
    label: str | None = None
    kind: Literal["action"]
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    save_as: str | None = None
    timeout_ms: int | None = None
    on_fail: OnFail | None = None


class IfStep(BaseModel):
    label: str | None = None
    kind: Literal["if"]
    when: ConditionExpr
    then: str
    otherwise: str | None = None
    timeout_ms: int | None = None
    on_fail: OnFail | None = None


class WaitUntilStep(BaseModel):
    label: str | None = None
    kind: Literal["wait_until"]
    check: ConditionExpr
    interval_ms: int = 500
    timeout_ms: int = 10000
    on_timeout: OnFail | None = None
    on_fail: OnFail | None = None


class GotoStep(BaseModel):
    label: str | None = None
    kind: Literal["goto"]
    target: str
    timeout_ms: int | None = None
    on_fail: OnFail | None = None


class StopStep(BaseModel):
    label: str | None = None
    kind: Literal["stop"]
    status: Literal["success", "failed"] = "success"
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = None
    on_fail: OnFail | None = None


Step = Annotated[
    ActionStep | IfStep | WaitUntilStep | GotoStep | StopStep, Field(discriminator="kind")
]


# ---- Workflow script ----


class WorkflowScript(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["v1"]
    workflow: str
    vars: dict[str, Any] = Field(default_factory=dict)
    steps: list[Step] = Field(default_factory=list)
