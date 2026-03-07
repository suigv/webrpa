from __future__ import annotations

from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class InputType(str, Enum):
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
    inputs: List[PluginInput] = Field(default_factory=list)
