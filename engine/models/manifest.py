from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class InputType(StrEnum):
    string = "string"
    integer = "integer"
    number = "number"
    boolean = "boolean"


class PluginInput(BaseModel):
    name: str
    type: InputType
    required: bool = True
    default: Any = None


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
    distill_threshold: int = Field(
        default=3, ge=1, description="Min completed runs required before distillation"
    )
