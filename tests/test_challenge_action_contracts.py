import json

from ai_services.llm_client import LLMResponse
from engine.action_registry import get_registry, register_defaults, resolve_action
from engine.actions import challenge_actions
from engine.models.manifest import PluginManifest
from engine.models.runtime import ActionResult, ExecutionContext


def test_challenge_contract_actions_are_registered_with_metadata():
    register_defaults()
    registry = get_registry()

    solve_meta = registry.get_metadata("ai.solve_captcha")
    email_meta = registry.get_metadata("channel.read_email_code")
    sms_meta = registry.get_metadata("channel.read_sms_code")

    assert solve_meta is not None
    assert solve_meta.tags == ["ai", "challenge", "contract"]
    assert solve_meta.params_schema["required"] == ["captcha_type"]

    assert email_meta is not None
    assert email_meta.tags == ["channel", "challenge", "contract"]
    assert email_meta.params_schema["required"] == ["account_ref"]

    assert sms_meta is not None
    assert sms_meta.tags == ["channel", "challenge", "contract"]
    assert sms_meta.params_schema["required"] == ["account_ref"]


def test_ai_solve_captcha_returns_structured_text_result(monkeypatch):
    context = ExecutionContext(payload={}, runtime={})
    monkeypatch.setattr(
        challenge_actions,
        "capture_compressed",
        lambda params, ctx: ActionResult(
            ok=True,
            code="ok",
            data={
                "save_path": "/tmp/captcha.png",
                "screen_width": 1080,
                "screen_height": 1920,
            },
        ),
    )
    monkeypatch.setattr(
        challenge_actions,
        "_encode_image_ref",
        lambda image_ref, screen_width=None, screen_height=None: (
            "data:image/png;base64,ZmFrZQ==",
            (screen_width or 1080, screen_height or 1920),
        ),
    )

    class _FakeLLMClient:
        def evaluate(self, request, runtime_config=None):
            _ = (request, runtime_config)
            return LLMResponse(
                ok=True,
                request_id="req-1",
                provider="openai",
                model="gpt-5.4",
                output_text=json.dumps(
                    {
                        "challenge_type": "image",
                        "text": "483920",
                        "confidence": 0.96,
                        "instructions": "enter digits",
                    }
                ),
            )

    monkeypatch.setattr(challenge_actions, "LLMClient", _FakeLLMClient)
    solved = resolve_action("ai.solve_captcha")({"captcha_type": "image"}, context)

    assert solved.ok is True
    assert solved.data["text"] == "483920"
    assert solved.data["solver"] == "llm_vision"
    assert solved.data["confidence"] == 0.96


def test_channel_read_email_code_supports_runtime_hook():
    context = ExecutionContext(
        payload={},
        runtime={
            "channel_read_email_code": lambda params, ctx: {
                "code": "718281",
                "channel": "email",
                "message_id": "msg-1",
            }
        },
    )

    email_result = resolve_action("channel.read_email_code")({"account_ref": "creds"}, context)

    assert email_result.ok is True
    assert email_result.data["code"] == "718281"
    assert email_result.data["channel"] == "email"


def test_channel_read_sms_code_extracts_from_messages():
    context = ExecutionContext(payload={}, runtime={})
    sms_result = resolve_action("channel.read_sms_code")(
        {
            "account_ref": "creds",
            "sender": "x",
            "messages": [
                {"sender": "other", "body": "ignore 123456"},
                {"sender": "X", "body": "Your verification code is 483920."},
            ],
        },
        context,
    )

    assert sms_result.ok is True
    assert sms_result.data["code"] == "483920"
    assert sms_result.data["channel"] == "sms"


def test_plugin_manifest_distill_mode_defaults_to_pure_yaml():
    manifest = PluginManifest.model_validate(
        {
            "api_version": "v1",
            "kind": "plugin",
            "name": "demo",
            "version": "1.0.0",
            "display_name": "Demo",
        }
    )

    assert manifest.distill_mode.output_type == "pure_yaml"
    assert manifest.distill_mode.requires_ai_runtime is False
    assert manifest.distill_mode.requires_channel_runtime is False
