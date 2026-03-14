import os
import pytest
from unittest.mock import MagicMock, patch
from ai_services.vlm_client import VLMClient
from models.system_settings import SystemSettings

@pytest.fixture
def mock_vlm_settings():
    settings_dict = {
        "services": {
            "vlm": {
                "provider": "vlm",
                "providers": {
                    "vlm": {
                        "base_url": "http://127.0.0.1:9000/v1",
                        "model": "VLM-1.5",
                        "provider_type": "standard"
                    },
                    "custom": {
                        "base_url": "http://custom-vlm:8000/v1",
                        "model": "custom-vlm-v1",
                        "provider_type": "standard"
                    }
                }
            }
        }
    }
    return SystemSettings.model_validate(settings_dict)

def test_vlm_client_default_provider(mock_vlm_settings):
    with patch("core.system_settings_loader.load", return_value=mock_vlm_settings):
        with patch.dict(os.environ, {}, clear=True):
            client = VLMClient()
            assert client.provider_name == "vlm"
            
            # Provider should be created on first use
            provider = client._get_provider("vlm")
            assert provider.base_url == "http://127.0.0.1:9000/v1"
            assert provider.model == "VLM-1.5"

def test_vlm_client_explicit_provider(mock_vlm_settings):
    with patch("core.system_settings_loader.load", return_value=mock_vlm_settings):
        with patch.dict(os.environ, {}, clear=True):
            client = VLMClient(provider="custom")
            assert client.provider_name == "custom"
            
            provider = client._get_provider("custom")
            assert provider.base_url == "http://custom-vlm:8000/v1"
            assert provider.model == "custom-vlm-v1"

def test_vlm_api_key_priority(mock_vlm_settings):
    with patch("core.system_settings_loader.load", return_value=mock_vlm_settings):
        env_vars = {
            "MYT_VLM_API_KEY": "global-vlm-key",
            "MYT_VLM_API_KEY_VLM": "vlm-specific-key"
        }
        with patch.dict(os.environ, env_vars, clear=True):
            client = VLMClient()
            provider = client._get_provider("vlm")
            assert provider.api_key == "vlm-specific-key"
            
            # Custom provider should fallback to global key
            custom_provider = client._get_provider("custom")
            assert custom_provider.api_key == "global-vlm-key"

def test_vlm_predict_delegation(mock_vlm_settings):
    with patch("core.system_settings_loader.load", return_value=mock_vlm_settings):
        client = VLMClient()
        mock_provider = MagicMock()
        client._providers["vlm"] = mock_provider
        
        # Mock load_image_payload to return dummy values
        with patch.object(client, "_load_image_payload", return_value=("base64_data", (1024, 768))):
            client.predict("test.png", "click the button")
            
            mock_provider.predict.assert_called_once_with(
                "base64_data",
                "click the button",
                history=None,
                screen_width=1024,
                screen_height=768,
                timeout=60.0
            )
