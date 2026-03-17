import os
from unittest.mock import patch

import pytest

from ai_services.llm_client import LLMClient, LLMRequest
from models.system_settings import SystemSettings


@pytest.fixture
def mock_settings():
    settings_dict = {
        "services": {
            "llm": {
                "provider": "deepseek",
                "providers": {
                    "openai": {
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4o",
                        "provider_type": "openai",
                    },
                    "deepseek": {
                        "base_url": "https://api.deepseek.com/v1",
                        "model": "deepseek-chat",
                        "provider_type": "openai",
                    },
                },
            }
        }
    }
    return SystemSettings.model_validate(settings_dict)


def test_resolve_request_with_default_provider(mock_settings):
    # Clear env vars that might interfere
    with (
        patch("core.system_settings_loader.load", return_value=mock_settings),
        patch.dict(os.environ, {}, clear=True),
    ):
        client = LLMClient()
        request = LLMRequest(prompt="hello")
        resolved = client._resolve_request(request, runtime_config=None)

        # Default should be 'deepseek' as per mock_settings
        assert resolved.provider == "deepseek"
        assert resolved.base_url == "https://api.deepseek.com/v1"
        assert resolved.model == "deepseek-chat"


def test_resolve_request_with_explicit_provider(mock_settings):
    with (
        patch("core.system_settings_loader.load", return_value=mock_settings),
        patch.dict(os.environ, {}, clear=True),
    ):
        client = LLMClient()
        request = LLMRequest(prompt="hello", provider="openai")
        resolved = client._resolve_request(request, runtime_config=None)

        assert resolved.provider == "openai"
        assert resolved.base_url == "https://api.openai.com/v1"
        assert resolved.model == "gpt-4o"


def test_api_key_priority(mock_settings):
    env_vars = {
        "MYT_LLM_API_KEY": "global-key",
        "MYT_LLM_API_KEY_DEEPSEEK": "deepseek-specific-key",
    }
    with (
        patch("core.system_settings_loader.load", return_value=mock_settings),
        patch.dict(os.environ, env_vars, clear=True),
    ):
        client = LLMClient()

        # Case 1: Active provider is deepseek
        request = LLMRequest(prompt="hello")
        resolved = client._resolve_request(request, runtime_config=None)
        assert resolved.api_key == "deepseek-specific-key"

        # Case 2: Explicitly request openai (should fallback to global-key)
        request_openai = LLMRequest(prompt="hello", provider="openai")
        resolved_openai = client._resolve_request(request_openai, runtime_config=None)
        assert resolved_openai.api_key == "global-key"


def test_runtime_config_override(mock_settings):
    with (
        patch("core.system_settings_loader.load", return_value=mock_settings),
        patch.dict(os.environ, {"MYT_LLM_API_KEY": "key"}, clear=True),
    ):
        client = LLMClient()
        runtime_config = {"llm": {"provider": "openai", "model": "gpt-3.5-turbo"}}
        request = LLMRequest(prompt="hello")
        resolved = client._resolve_request(request, runtime_config=runtime_config)

        assert resolved.provider == "openai"
        assert resolved.model == "gpt-3.5-turbo"
        assert resolved.base_url == "https://api.openai.com/v1"  # From system settings
