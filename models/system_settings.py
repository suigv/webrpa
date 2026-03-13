"""
models/system_settings.py

Pydantic models for config/system.yaml.
Single source of truth for system-level settings (services, paths, features).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FeaturesSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enable_rpc: bool = True
    enable_vlm: bool = True


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    # api_key is intentionally absent — must be injected via env var MYT_LLM_API_KEY


class VLMSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str = "http://127.0.0.1:9000/v1"
    model: str = "UI-TARS-1.5-7B-6bit"
    # api_key is intentionally absent — must be injected via env var UITARS_API_KEY


class ServicesSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    redis_url: str = "redis://127.0.0.1:6379/0"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    vlm: VLMSettings = Field(default_factory=VLMSettings)


class PathSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    browser_profiles_dir: str = "/tmp/webrpa_browser_profiles"
    ai_work_dir: str = "/tmp/webrpa_ai"


class CredentialSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowlist: str = "/etc/myt"


class SystemSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: FeaturesSettings = Field(default_factory=FeaturesSettings)
    services: ServicesSettings = Field(default_factory=ServicesSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    credentials: CredentialSettings = Field(default_factory=CredentialSettings)
