# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import TypedDict

from ai_services.llm_client import LLMError, LLMRequest, LLMResponse
from engine.actions import ai_actions
from engine.models.runtime import ExecutionContext


class CallRecord(TypedDict):
    request: LLMRequest
    runtime_config: dict[str, object] | None


class FakeLLMClient:
    def __init__(self, response: LLMResponse):
        self.response: LLMResponse = response
        self.calls: list[CallRecord] = []

    def evaluate(
        self, request: LLMRequest, *, runtime_config: dict[str, object] | None = None
    ) -> LLMResponse:
        self.calls.append({"request": request, "runtime_config": runtime_config})
        return self.response


def test_llm_evaluate_uses_boundary_and_runtime_overrides(monkeypatch):
    fake_client = FakeLLMClient(
        LLMResponse(
            ok=True,
            request_id="req-ai",
            provider="runtime-provider",
            model="runtime-model",
            latency_ms=12,
            output_text="next",
            structured_state={"step": "tap"},
            fallback_modalities=["vision"],
            model_metadata={"provider": "runtime-provider"},
        )
    )
    monkeypatch.setattr(ai_actions, "LLMClient", lambda: fake_client)

    result = ai_actions.llm_evaluate(
        {
            "prompt": "plan",
            "response_format": {"type": "json_schema"},
            "fallback_modalities": ["vision"],
        },
        ExecutionContext(
            payload={}, runtime={"llm": {"provider": "runtime-provider", "model": "runtime-model"}}
        ),
    )

    assert result.ok is True
    assert result.code == "ok"
    assert result.data["request_id"] == "req-ai"
    assert result.data["structured_state"] == {"step": "tap"}
    assert fake_client.calls[0]["runtime_config"] == {
        "provider": "runtime-provider",
        "model": "runtime-model",
    }
    captured_request = fake_client.calls[0]["request"]
    assert captured_request.fallback_modalities == ["vision"]


def test_llm_evaluate_normalizes_boundary_errors(monkeypatch):
    fake_client = FakeLLMClient(
        LLMResponse(
            ok=False,
            request_id="req-ai-error",
            provider="openai",
            model="gpt-5.4",
            latency_ms=3,
            error=LLMError(code="provider_http_error", message="rate limited"),
        )
    )
    monkeypatch.setattr(ai_actions, "LLMClient", lambda: fake_client)

    result = ai_actions.llm_evaluate({"prompt": "plan"}, ExecutionContext(payload={}, runtime={}))

    assert result.ok is False
    assert result.code == "provider_http_error"
    assert result.message == "rate limited"
    assert result.data["error"] == {
        "code": "provider_http_error",
        "message": "rate limited",
        "provider_code": "",
        "provider_status": None,
        "retryable": False,
        "details": {},
    }
