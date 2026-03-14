"""
models/system_settings.py

Pydantic models for config/system.yaml.
Single source of truth for system-level settings (services, paths, features).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeaturesSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enable_rpc: bool = True
    enable_vlm: bool = True


class LLMProviderSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-5.4"
    provider_type: str = "openai"


class LLMSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # The currently active provider key (points to an entry in the providers dict)
    provider: str = "openai"
    # Detailed configuration for multiple providers
    providers: dict[str, LLMProviderSettings] = Field(default_factory=dict)

    # Legacy fields for backward compatibility
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-5.4"

    @model_validator(mode="before")
    @classmethod
    def bootstrap_providers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        providers = data.get("providers")
        if not providers:
            # If providers dict is missing, migrate top-level fields into an 'openai' entry
            legacy_provider = data.get("provider", "openai")
            base_url = data.get("base_url", "https://api.openai.com/v1")
            model = data.get("model", "gpt-5.4")
            
            data["providers"] = {
                legacy_provider: {
                    "base_url": base_url,
                    "model": model,
                    "provider_type": "openai"
                }
            }
        return data


class VLMProviderSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str = "http://127.0.0.1:9000/v1"
    model: str = "vlm-model"
    provider_type: str = "standard"


class VLMSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # The currently active provider key
    provider: str = "vlm"
    # Detailed configuration for multiple providers
    providers: dict[str, VLMProviderSettings] = Field(default_factory=dict)

    # Legacy fields for backward compatibility
    base_url: str = "http://127.0.0.1:9000/v1"
    model: str = "vlm-model"

    @model_validator(mode="before")
    @classmethod
    def bootstrap_providers(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        providers = data.get("providers")
        if not providers:
            # If providers dict is missing, migrate top-level fields into a 'vlm' entry
            legacy_provider = data.get("provider", "vlm")
            base_url = data.get("base_url", "http://127.0.0.1:9000/v1")
            model = data.get("model", "vlm-model")

            data["providers"] = {
                legacy_provider: {
                    "base_url": base_url,
                    "model": model,
                    "provider_type": "standard"
                }
            }
        return data


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
