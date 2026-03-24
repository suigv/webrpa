from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class InputType(StrEnum):
    string = "string"
    integer = "integer"
    number = "number"
    boolean = "boolean"


class InputWidget(StrEnum):
    text = "text"
    number = "number"
    checkbox = "checkbox"
    select = "select"
    hidden = "hidden"


class PluginInputOption(BaseModel):
    value: Any
    label: str
    description: str | None = None


class PluginInput(BaseModel):
    name: str
    type: InputType
    required: bool = True
    default: Any = None
    label: str | None = None
    description: str | None = None
    placeholder: str | None = None
    advanced: bool = False
    system: bool = False
    widget: InputWidget | None = None
    options: list[PluginInputOption] = Field(default_factory=list)


class PluginDistillRule(BaseModel):
    decision: str = Field(default="rejected")
    business_outcome: str = Field(default="partial")
    reason: str
    match_message_any: list[str] = Field(default_factory=list)
    match_data_count_positive: bool = False
    match_data_count_zero: bool = False
    match_data_count_present: bool = False
    match_terminal_message_present: bool = False
    match_always: bool = False
    retained_value: list[str] = Field(default_factory=list)
    value_level: str | None = None


class PluginDistillPolicy(BaseModel):
    data_count_keys: list[str] = Field(default_factory=list)
    data_count_list_keys: list[str] = Field(default_factory=list)
    completed_rules: list[PluginDistillRule] = Field(default_factory=list)


class PluginAIHints(BaseModel):
    objective: str
    label: str
    task_family: str = "exploration"
    keywords: list[str] = Field(default_factory=list)
    plugin_keywords: list[str] = Field(default_factory=list)
    requires_account: bool = True
    prefers_branch: bool = False
    needs_shared_resource: bool = False
    expects_keyword_input: bool = False
    expects_reply_strategy: bool = False
    expected_outcome: str = ""
    memory_hints: dict[str, str] = Field(default_factory=dict)
    distill_policy: PluginDistillPolicy | None = None


class PluginManifest(BaseModel):
    api_version: Literal["v1"]
    kind: Literal["plugin"]
    name: str
    version: str
    display_name: str
    category: str = "其他"
    entry_script: str = "script.yaml"
    description: str = ""
    inputs: list[PluginInput] = Field(default_factory=list)
    distillable: bool = Field(
        default=True,
        description="Whether this plugin is suitable for AI-run distillation into YAML.",
    )
    visible_in_task_catalog: bool = Field(
        default=True,
        description="Whether this plugin should appear in the default task catalog.",
    )
    distill_threshold: int = Field(
        default=3, ge=1, description="Min completed runs required before distillation"
    )
    ai_hints: PluginAIHints | None = None
