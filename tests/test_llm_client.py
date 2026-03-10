# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from ai_services.llm_client import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    LLMClient,
    LLMError,
    LLMRequest,
    LLMResponse,
    ProviderInvocationError,
    ResolvedLLMRequest,
)


class FakeProvider:
    provider_name: str = "fake"

    def __init__(self, response: dict[str, object] | None = None, error: Exception | None = None):
        self.response: dict[str, object] = response or {}
        self.error: Exception | None = error
        self.requests: list[ResolvedLLMRequest] = []

    def invoke(self, request: ResolvedLLMRequest) -> dict[str, object]:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def test_llm_client_defaults_to_gpt_5_4_selection(monkeypatch):
    monkeypatch.delenv("MYT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MYT_LLM_MODEL", raising=False)
    provider = FakeProvider(response={"model": DEFAULT_LLM_MODEL, "output_text": "done"})
    client = LLMClient(
        provider_registry={DEFAULT_LLM_PROVIDER: provider},
        config_resolver=lambda: {},
        request_id_factory=lambda: "req-default",
    )

    response = client.evaluate(LLMRequest(prompt="plan next step"))

    assert response.ok is True
    assert response.request_id == "req-default"
    assert response.provider == DEFAULT_LLM_PROVIDER
    assert response.model == DEFAULT_LLM_MODEL
    assert provider.requests[0].provider == DEFAULT_LLM_PROVIDER
    assert provider.requests[0].model == DEFAULT_LLM_MODEL
    assert provider.requests[0].planning == {"mode": "structured_state_first"}


def test_llm_client_uses_runtime_over_environment_and_config_overrides(monkeypatch):
    monkeypatch.setenv("MYT_LLM_PROVIDER", "env-provider")
    monkeypatch.setenv("MYT_LLM_MODEL", "env-model")
    provider = FakeProvider(response={"model": "runtime-model", "output_text": "runtime"})
    client = LLMClient(
        provider_registry={"runtime-provider": provider},
        config_resolver=lambda: {"provider": "config-provider", "model": "config-model"},
        request_id_factory=lambda: "req-runtime",
    )

    response = client.evaluate(
        LLMRequest(prompt="hello"),
        runtime_config={"provider": "runtime-provider", "model": "runtime-model"},
    )

    assert response.ok is True
    assert response.provider == "runtime-provider"
    assert response.model == "runtime-model"
    assert provider.requests[0].provider == "runtime-provider"
    assert provider.requests[0].model == "runtime-model"


def test_llm_client_normalizes_success_envelope():
    provider = FakeProvider(
        response={
            "provider_request_id": "provider-123",
            "model": "gpt-5.4-mini",
            "output_text": "next",
            "structured_state": {"step": "open_app"},
            "modality": "text",
            "fallback_modalities": ["vision"],
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            "finish_reason": "completed",
            "raw": {"id": "provider-123"},
        }
    )
    ticks = iter([1.0, 1.125])
    client = LLMClient(
        provider_registry={DEFAULT_LLM_PROVIDER: provider},
        config_resolver=lambda: {},
        clock=lambda: next(ticks),
        request_id_factory=lambda: "req-success",
    )

    response = client.evaluate(
        LLMRequest(
            prompt="state first",
            response_format={"type": "json_schema", "name": "plan_state"},
            fallback_modalities=["vision"],
        )
    )

    assert response.to_dict() == {
        "ok": True,
        "request_id": "req-success",
        "provider": DEFAULT_LLM_PROVIDER,
        "model": "gpt-5.4-mini",
        "latency_ms": 125,
        "output_text": "next",
        "structured_state": {"step": "open_app"},
        "modality": "text",
        "fallback_modalities": ["vision"],
        "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        "finish_reason": "completed",
        "model_metadata": {
            "provider": DEFAULT_LLM_PROVIDER,
            "provider_request_id": "provider-123",
            "configured_model": DEFAULT_LLM_MODEL,
            "planning": {"mode": "structured_state_first"},
            "response_format": {"type": "json_schema", "name": "plan_state"},
        },
        "error": None,
        "raw": {"id": "provider-123"},
    }


def test_llm_client_normalizes_provider_errors(monkeypatch):
    monkeypatch.delenv("MYT_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MYT_LLM_MODEL", raising=False)
    provider = FakeProvider(
        error=ProviderInvocationError(
            code="provider_http_error",
            message="rate limited",
            provider_code="rate_limit",
            provider_status=429,
            retryable=True,
            details={"limit": "rpm"},
        )
    )
    ticks = iter([2.0, 2.01])
    client = LLMClient(
        provider_registry={DEFAULT_LLM_PROVIDER: provider},
        config_resolver=lambda: {},
        clock=lambda: next(ticks),
        request_id_factory=lambda: "req-error",
    )

    response = client.evaluate("hello")

    assert response.ok is False
    assert response.request_id == "req-error"
    assert response.provider == DEFAULT_LLM_PROVIDER
    assert response.model == DEFAULT_LLM_MODEL
    assert response.latency_ms == 10
    assert response.error == LLMError(
        code="provider_http_error",
        message="rate limited",
        provider_code="rate_limit",
        provider_status=429,
        retryable=True,
        details={"limit": "rpm"},
    )
