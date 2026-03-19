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
