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


class PluginCapabilities(BaseModel):
    account_binding: bool = False
    totp_2fa: bool = False
    email_code: bool = False
    sms_code: bool = False
    graphic_captcha: bool = False
    slider_captcha: bool = False
    human_takeover: bool = False


class PluginOutputType(StrEnum):
    pure_yaml = "pure_yaml"
    yaml_with_ai = "yaml_with_ai"
    yaml_with_channel = "yaml_with_channel"
    human_assisted = "human_assisted"
    context_only = "context_only"


class PluginDistillMode(BaseModel):
    output_type: PluginOutputType = PluginOutputType.pure_yaml
    requires_ai_runtime: bool = False
    requires_channel_runtime: bool = False


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
    capabilities: PluginCapabilities = Field(default_factory=PluginCapabilities)
    distill_mode: PluginDistillMode = Field(default_factory=PluginDistillMode)
