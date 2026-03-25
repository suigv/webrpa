from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

_IDENTIFIER_PATTERN = r"^[a-z0-9_][a-z0-9_]{2,63}$"
_APP_ID_PATTERN = r"^[a-z0-9][a-z0-9_]{0,63}$"


class DeclarativeScriptVersion(StrEnum):
    v0 = "v0"


class DeclarativeScriptKind(StrEnum):
    declarative_script = "declarative_script"


class DeclarativeScriptRole(StrEnum):
    login = "login"
    collect = "collect"
    filter = "filter"
    nurture = "nurture"
    engage = "engage"
    reply = "reply"
    summarize = "summarize"
    utility = "utility"


class ConsumeKind(StrEnum):
    input = "input"
    state = "state"
    resource = "resource"
    artifact = "artifact"
    policy = "policy"


class ConsumeSource(StrEnum):
    user_input = "user_input"
    runtime_state = "runtime_state"
    shared_resource = "shared_resource"
    upstream_script = "upstream_script"
    branch_policy = "branch_policy"
    system_default = "system_default"


class ProduceKind(StrEnum):
    result = "result"
    resource = "resource"
    artifact = "artifact"
    signal = "signal"


class StageKind(StrEnum):
    setup = "setup"
    decision = "decision"
    loop = "loop"
    finalize = "finalize"


class HandoffAction(StrEnum):
    pause_and_exit = "pause_and_exit"
    pause_and_wait = "pause_and_wait"
    record_and_fail = "record_and_fail"


class ConsumeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_IDENTIFIER_PATTERN)
    kind: ConsumeKind
    description: str = Field(min_length=1, max_length=200)
    required: bool = True
    source: ConsumeSource


class ProduceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_IDENTIFIER_PATTERN)
    kind: ProduceKind
    description: str = Field(min_length=1, max_length=200)
    persistent: bool = False
    exposed: bool = True


class HandoffPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    triggers: list[str] = Field(default_factory=list)
    on_handoff: HandoffAction

    @model_validator(mode="after")
    def validate_allowed_triggers(self) -> HandoffPolicy:
        if not self.allowed and self.triggers:
            raise ValueError("triggers must be empty when handoff is not allowed")
        return self


class StageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_IDENTIFIER_PATTERN)
    title: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    kind: StageKind
    goal: str = Field(min_length=1, max_length=120)
    exit_when: list[str] = Field(default_factory=list)
    handoff_policy: HandoffPolicy

    @model_validator(mode="after")
    def validate_loop_exit_when(self) -> StageItem:
        if self.kind == StageKind.loop and not self.exit_when:
            raise ValueError("loop stages must declare at least one exit condition")
        return self


class TerminalDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=200)
    signals: list[str] = Field(default_factory=list)


class FailureDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=200)
    signals: list[str] = Field(default_factory=list)
    retryable: bool


class DeclarativeScriptV0(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: DeclarativeScriptVersion
    kind: DeclarativeScriptKind
    app_id: str = Field(pattern=_APP_ID_PATTERN)
    app_scope: str = Field(min_length=1, max_length=64)
    name: str = Field(pattern=_IDENTIFIER_PATTERN)
    title: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=120)
    role: DeclarativeScriptRole
    consumes: list[ConsumeItem]
    produces: list[ProduceItem]
    depends_on: list[str]
    stages: list[StageItem] = Field(min_length=1)
    success_definition: TerminalDefinition
    failure_definition: FailureDefinition
    handoff_policy: HandoffPolicy

    @model_validator(mode="after")
    def validate_structure(self) -> DeclarativeScriptV0:
        if self.name in self.depends_on:
            raise ValueError("depends_on cannot contain self")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on contains duplicate entries")

        stage_names = [item.name for item in self.stages]
        if len(set(stage_names)) != len(stage_names):
            raise ValueError("stage names must be unique")

        produced_names = [item.name for item in self.produces if item.exposed]
        if any(not name.strip() for name in produced_names):
            raise ValueError("exposed produces must declare a stable non-empty name")

        return self


__all__ = [
    "ConsumeItem",
    "ConsumeKind",
    "ConsumeSource",
    "DeclarativeScriptKind",
    "DeclarativeScriptRole",
    "DeclarativeScriptV0",
    "DeclarativeScriptVersion",
    "FailureDefinition",
    "HandoffAction",
    "HandoffPolicy",
    "ProduceItem",
    "ProduceKind",
    "StageItem",
    "StageKind",
    "TerminalDefinition",
]
