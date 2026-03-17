# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from typing import cast

import httpx

from ai_services.llm_client import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    LLMClient,
    LLMError,
    LLMRequest,
    ProviderInvocationError,
    ResolvedLLMRequest,
    retry_backoff_seconds,
)
from ai_services.vlm_client import VLMClient


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


def test_llm_client_normalizes_success_envelope(monkeypatch):
    monkeypatch.setenv("MYT_LLM_MODEL", "gpt-5.2")
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
            "configured_model": "gpt-5.2",
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


def test_llm_client_retries_retryable_provider_errors():
    sleep_calls: list[int] = []

    def _fake_sleep(duration: float) -> None:
        sleep_calls.append(int(duration))

    class _SequencedProvider:
        provider_name: str = "fake"

        def __init__(self, results: list[dict[str, object] | Exception]):
            self._results: list[dict[str, object] | Exception] = list(results)
            self.requests: list[ResolvedLLMRequest] = []

        def invoke(self, request: ResolvedLLMRequest) -> dict[str, object]:
            self.requests.append(request)
            result = self._results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    provider = _SequencedProvider(
        results=[
            ProviderInvocationError(
                code="provider_http_error",
                message="temporary upstream failure",
                provider_status=503,
                retryable=True,
            ),
            ProviderInvocationError(
                code="provider_http_error",
                message="temporary upstream failure",
                provider_status=503,
                retryable=True,
            ),
            {"model": DEFAULT_LLM_MODEL, "output_text": "ok"},
        ]
    )
    client = LLMClient(
        provider_registry={DEFAULT_LLM_PROVIDER: provider},
        config_resolver=lambda: {},
        request_id_factory=lambda: "req-retry",
        sleep=_fake_sleep,
    )

    response = client.evaluate(LLMRequest(prompt="retry please"))

    assert response.ok is True
    assert response.output_text == "ok"
    assert len(provider.requests) == 3
    assert sleep_calls == [retry_backoff_seconds(0), retry_backoff_seconds(1)]


def test_llm_client_retries_empty_model_output():
    sleep_calls: list[int] = []

    def _fake_sleep(duration: float) -> None:
        sleep_calls.append(int(duration))

    class _SequencedProvider:
        provider_name: str = "fake"

        def __init__(self, results: list[dict[str, object]]):
            self._results = list(results)
            self.requests: list[ResolvedLLMRequest] = []

        def invoke(self, request: ResolvedLLMRequest) -> dict[str, object]:
            self.requests.append(request)
            return self._results.pop(0)

    provider = _SequencedProvider(
        [
            {
                "model": DEFAULT_LLM_MODEL,
                "output_text": "",
                "finish_reason": "stop",
                "provider_request_id": "resp-empty",
            },
            {
                "model": DEFAULT_LLM_MODEL,
                "output_text": '{"done": false}',
                "finish_reason": "stop",
                "provider_request_id": "resp-ok",
            },
        ]
    )
    client = LLMClient(
        provider_registry={DEFAULT_LLM_PROVIDER: provider},
        config_resolver=lambda: {},
        request_id_factory=lambda: "req-empty-retry",
        sleep=_fake_sleep,
    )

    response = client.evaluate(LLMRequest(prompt="retry empty output"))

    assert response.ok is True
    assert response.output_text == '{"done": false}'
    assert len(provider.requests) == 2
    assert sleep_calls == [retry_backoff_seconds(0)]


def test_llm_client_returns_explicit_error_after_empty_model_output_retries_exhausted():
    sleep_calls: list[int] = []

    def _fake_sleep(duration: float) -> None:
        sleep_calls.append(int(duration))

    class _AlwaysEmptyProvider:
        provider_name: str = "fake"

        def __init__(self):
            self.requests: list[ResolvedLLMRequest] = []

        def invoke(self, request: ResolvedLLMRequest) -> dict[str, object]:
            self.requests.append(request)
            return {
                "model": DEFAULT_LLM_MODEL,
                "output_text": "",
                "finish_reason": "stop",
                "provider_request_id": "resp-empty",
            }

    provider = _AlwaysEmptyProvider()
    client = LLMClient(
        provider_registry={DEFAULT_LLM_PROVIDER: provider},
        config_resolver=lambda: {},
        request_id_factory=lambda: "req-empty-fail",
        sleep=_fake_sleep,
        max_retries=2,
    )

    response = client.evaluate(LLMRequest(prompt="still empty"))

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "empty_model_output"
    assert len(provider.requests) == 2
    assert sleep_calls == [retry_backoff_seconds(0)]


class _FakeVLMResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload: dict[str, object] = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeVLMHttpClient:
    def __init__(self, *args, **kwargs):
        _ = (args, kwargs)
        self.posts: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
        timeout: float | None = None,
        **kwargs: object,
    ):
        _ = (timeout, kwargs)
        self.posts.append({"url": url, "json": json, "headers": headers})
        return _FakeVLMResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Action: click(start_box='<|box_start|>(500,250)<|box_end|>')"
                        }
                    }
                ]
            }
        )


def test_vlm_client_predict_converts_normalized_coordinates_to_pixels(monkeypatch):
    fake_http = _FakeVLMHttpClient()

    def mock_get_config(name):
        from models.system_settings import VLMProviderSettings

        return VLMProviderSettings(base_url="http://vlm.local/v1", model="ui-tars-test")

    monkeypatch.setattr("ai_services.vlm_client.get_vlm_provider_config", mock_get_config)
    monkeypatch.setattr("ai_services.vlm_client.get_vlm_api_key", lambda n: "secret")

    client = VLMClient(
        http_client=cast(httpx.Client, cast(object, fake_http)),
    )

    action = client.predict(
        "data:image/png;base64,AA==", "tap the button", screen_width=200, screen_height=100
    )

    assert action.action == "ui.click"
    assert action.coord_space == "pixel"
    assert action.x == 100
    assert action.y == 25
    assert action.params["x"] == 100
    assert action.params["y"] == 25
    assert fake_http.posts[0]["url"] == "http://vlm.local/v1/chat/completions"


def test_vlm_client_exposes_explicit_cleanup_lifecycle():
    close_calls: list[bool] = []

    class _FakeSharedClient:
        def post(self, *args, **kwargs):
            _ = (args, kwargs)
            raise AssertionError("should not be used in this test")

        def close(self) -> None:
            close_calls.append(True)

    fake_shared = _FakeSharedClient()

    client = VLMClient(http_client=cast(httpx.Client, cast(object, fake_shared)))
    peer = VLMClient(http_client=cast(httpx.Client, cast(object, fake_shared)))

    assert hasattr(client, "close")
    assert client.close() is None
    assert peer.close() is None
    assert close_calls == []
