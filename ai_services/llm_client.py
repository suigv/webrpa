# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportDeprecated=false

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.client import HTTPResponse
from typing import Protocol, cast
from uuid import uuid4

from core.config_loader import ConfigLoader

DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "gpt-5.4"
JSONValue = object
JSONDict = dict[str, JSONValue]
StructuredState = dict[str, JSONValue] | list[JSONValue] | None


def _as_dict(value: object) -> JSONDict:
    return dict(value) if isinstance(value, Mapping) else {}


def _coerce_modalities(value: object) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            item_str = str(item).strip()
            if item_str:
                result.append(item_str)
        return result
    return []


def _get_llm_config() -> JSONDict:
    loaded: JSONDict = ConfigLoader.load()
    raw = loaded.get("llm", {})
    config = dict(raw) if isinstance(raw, Mapping) else {}

    legacy_provider = str(loaded.get("default_ai", "")).strip()
    if legacy_provider:
        _ = config.setdefault("provider", legacy_provider)

    legacy_model = str(loaded.get("llm_model", "")).strip()
    if legacy_model:
        _ = config.setdefault("model", legacy_model)

    return config


def _as_usage(value: object) -> dict[str, int | None]:
    usage = _as_dict(value)
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    return {
        "input_tokens": input_tokens if isinstance(input_tokens, int) else None,
        "output_tokens": output_tokens if isinstance(output_tokens, int) else None,
        "total_tokens": total_tokens if isinstance(total_tokens, int) else None,
    }


def _as_structured_state(value: object) -> StructuredState:
    if isinstance(value, dict):
        return cast(dict[str, JSONValue], value)
    if isinstance(value, list):
        return cast(list[JSONValue], value)
    return None


@dataclass(slots=True)
class LLMError:
    code: str
    message: str
    provider_code: str = ""
    provider_status: int | None = None
    retryable: bool = False
    details: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "code": self.code,
            "message": self.message,
            "provider_code": self.provider_code,
            "provider_status": self.provider_status,
            "retryable": self.retryable,
            "details": self.details,
        }


@dataclass(slots=True)
class LLMRequest:
    prompt: str
    system_prompt: str = ""
    provider: str = ""
    model: str = ""
    request_id: str = ""
    metadata: JSONDict = field(default_factory=dict)
    options: JSONDict = field(default_factory=dict)
    response_format: JSONDict = field(default_factory=dict)
    planning: JSONDict = field(default_factory=lambda: {"mode": "structured_state_first"})
    modality: str = "text"
    fallback_modalities: list[str] = field(default_factory=list)
    attachments: list[JSONDict] = field(default_factory=list)
    timeout_seconds: float | None = None


@dataclass(slots=True)
class ResolvedLLMRequest(LLMRequest):
    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    request_id: str = ""


@dataclass(slots=True)
class LLMResponse:
    ok: bool
    request_id: str
    provider: str
    model: str
    latency_ms: int | None = None
    output_text: str = ""
    structured_state: StructuredState = None
    modality: str = "text"
    fallback_modalities: list[str] = field(default_factory=list)
    usage: dict[str, int | None] = field(
        default_factory=lambda: {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }
    )
    finish_reason: str = ""
    model_metadata: JSONDict = field(default_factory=dict)
    error: LLMError | None = None
    raw: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "ok": self.ok,
            "request_id": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "output_text": self.output_text,
            "structured_state": self.structured_state,
            "modality": self.modality,
            "fallback_modalities": self.fallback_modalities,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "model_metadata": self.model_metadata,
            "error": self.error.to_dict() if self.error else None,
            "raw": self.raw,
        }


class LLMProvider(Protocol):
    provider_name: str

    def invoke(self, request: ResolvedLLMRequest) -> JSONDict: ...


@dataclass(slots=True)
class ProviderInvocationError(Exception):
    code: str
    message: str
    provider_code: str = ""
    provider_status: int | None = None
    retryable: bool = False
    details: JSONDict = field(default_factory=dict)


class OpenAIResponsesProvider:
    provider_name: str = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: Callable[[str, JSONDict, dict[str, str], float | None], JSONDict] | None = None,
    ) -> None:
        self._api_key: str = (api_key or os.getenv("MYT_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        self._base_url: str = (base_url or os.getenv("MYT_LLM_API_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self._transport: Callable[[str, JSONDict, dict[str, str], float | None], JSONDict] = transport or self._http_transport

    def invoke(self, request: ResolvedLLMRequest) -> JSONDict:
        if not self._api_key:
            raise ProviderInvocationError(
                code="provider_not_configured",
                message="Missing OpenAI API key",
                retryable=False,
                details={"provider": self.provider_name},
            )

        payload = self._build_payload(request)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Request-Id": request.request_id,
        }
        raw = self._transport(f"{self._base_url}/responses", payload, headers, request.timeout_seconds)
        return self._normalize_response(request, raw)

    def _build_payload(self, request: ResolvedLLMRequest) -> JSONDict:
        input_parts: list[JSONDict] = []
        if request.system_prompt:
            input_parts.append(
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": request.system_prompt}],
                }
            )

        user_content: list[JSONDict] = [{"type": "input_text", "text": request.prompt}]
        for attachment in request.attachments:
            attachment_dict = _as_dict(attachment)
            image_url = str(attachment_dict.get("image_url", "")).strip()
            if image_url:
                user_content.append({"type": "input_image", "image_url": image_url})

        input_parts.append({"role": "user", "content": user_content})

        payload: JSONDict = {
            "model": request.model,
            "input": input_parts,
            "metadata": {
                **request.metadata,
                "planning": request.planning,
                "response_format": request.response_format,
                "fallback_modalities": request.fallback_modalities,
                "modality": request.modality,
            },
        }
        if request.options:
            payload.update(request.options)
        return payload

    def _normalize_response(self, request: ResolvedLLMRequest, raw: JSONDict) -> JSONDict:
        output_text = str(raw.get("output_text") or "")
        if not output_text:
            output_text = self._extract_output_text(raw)

        usage_raw = _as_dict(raw.get("usage"))
        input_tokens = usage_raw.get("input_tokens")
        output_tokens = usage_raw.get("output_tokens")
        total_tokens = usage_raw.get("total_tokens")
        if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
            total_tokens = input_tokens + output_tokens

        return {
            "provider_request_id": str(raw.get("id") or ""),
            "model": str(raw.get("model") or request.model),
            "output_text": output_text,
            "structured_state": _as_structured_state(raw.get("structured_state") or raw.get("output_parsed")),
            "modality": str(raw.get("modality") or request.modality or "text"),
            "fallback_modalities": _coerce_modalities(raw.get("fallback_modalities") or request.fallback_modalities),
            "usage": _as_usage({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }),
            "finish_reason": str(raw.get("status") or raw.get("finish_reason") or ""),
            "raw": raw,
        }

    def _extract_output_text(self, raw: JSONDict) -> str:
        outputs = raw.get("output")
        if not isinstance(outputs, list):
            return ""
        parts: list[str] = []
        for item in outputs:
            item_dict = _as_dict(item)
            content = item_dict.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                part_dict = _as_dict(part)
                text = part_dict.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n".join(parts)

    def _http_transport(
        self,
        url: str,
        payload: JSONDict,
        headers: dict[str, str],
        timeout_seconds: float | None,
    ) -> JSONDict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        timeout = timeout_seconds or 30.0
        try:
            response = cast(HTTPResponse, urllib.request.urlopen(request, timeout=timeout))
            with response:
                body = response.read().decode("utf-8")
            return _as_dict(json.loads(body))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            details = _as_dict(json.loads(body)) if body else {}
            error_payload = _as_dict(details.get("error"))
            raise ProviderInvocationError(
                code="provider_http_error",
                message=str(error_payload.get("message") or exc.reason or "Provider request failed"),
                provider_code=str(error_payload.get("code") or ""),
                provider_status=exc.code,
                retryable=exc.code >= 500,
                details=details,
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderInvocationError(
                code="provider_connection_error",
                message=str(getattr(exc, "reason", exc) or "Provider connection failed"),
                retryable=True,
                details={"provider": self.provider_name},
            ) from exc


def get_default_provider_registry() -> dict[str, LLMProvider]:
    return {"openai": OpenAIResponsesProvider()}


class LLMClient:
    def __init__(
        self,
        *,
        provider_registry: Mapping[str, LLMProvider] | None = None,
        config_resolver: Callable[[], JSONDict] | None = None,
        clock: Callable[[], float] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._providers: dict[str, LLMProvider] = dict(provider_registry or get_default_provider_registry())
        self._config_resolver: Callable[[], JSONDict] = config_resolver or _get_llm_config
        self._clock: Callable[[], float] = clock or time.perf_counter
        self._request_id_factory: Callable[[], str] = request_id_factory or (lambda: f"llm-{uuid4()}")

    def evaluate(self, request: LLMRequest | str, *, runtime_config: JSONDict | None = None) -> LLMResponse:
        llm_request = request if isinstance(request, LLMRequest) else LLMRequest(prompt=str(request))
        resolved = self._resolve_request(llm_request, runtime_config=runtime_config)
        provider = self._providers.get(resolved.provider)
        if provider is None:
            return self._error_response(
                resolved,
                latency_ms=0,
                error=LLMError(
                    code="unsupported_provider",
                    message=f"Unsupported LLM provider: {resolved.provider}",
                    details={"provider": resolved.provider},
                ),
            )

        started_at = self._clock()
        try:
            result = provider.invoke(resolved)
            latency_ms = self._elapsed_ms(started_at)
            return LLMResponse(
                ok=True,
                request_id=resolved.request_id,
                provider=resolved.provider,
                model=str(result.get("model") or resolved.model),
                latency_ms=latency_ms,
                output_text=str(result.get("output_text") or ""),
                structured_state=_as_structured_state(result.get("structured_state")),
                modality=str(result.get("modality") or resolved.modality or "text"),
                fallback_modalities=_coerce_modalities(result.get("fallback_modalities") or resolved.fallback_modalities),
                usage=_as_usage(result.get("usage")),
                finish_reason=str(result.get("finish_reason") or ""),
                model_metadata={
                    "provider": resolved.provider,
                    "provider_request_id": str(result.get("provider_request_id") or ""),
                    "configured_model": resolved.model,
                    "planning": resolved.planning,
                    "response_format": resolved.response_format,
                },
                raw=_as_dict(result.get("raw")),
            )
        except ProviderInvocationError as exc:
            latency_ms = self._elapsed_ms(started_at)
            return self._error_response(
                resolved,
                latency_ms=latency_ms,
                error=LLMError(
                    code=exc.code,
                    message=exc.message,
                    provider_code=exc.provider_code,
                    provider_status=exc.provider_status,
                    retryable=exc.retryable,
                    details=exc.details,
                ),
            )
        except Exception as exc:
            latency_ms = self._elapsed_ms(started_at)
            return self._error_response(
                resolved,
                latency_ms=latency_ms,
                error=LLMError(
                    code="llm_unexpected_error",
                    message=str(exc) or exc.__class__.__name__,
                    details={"provider": resolved.provider},
                ),
            )

    def _resolve_request(self, request: LLMRequest, *, runtime_config: JSONDict | None) -> ResolvedLLMRequest:
        runtime_dict = _as_dict(runtime_config)
        runtime_llm = _as_dict(runtime_dict.get("llm")) if "llm" in runtime_dict else runtime_dict
        config = _as_dict(self._config_resolver())

        provider = (
            request.provider.strip()
            or str(runtime_llm.get("provider") or "").strip()
            or os.getenv("MYT_LLM_PROVIDER", "").strip()
            or str(config.get("provider") or "").strip()
            or DEFAULT_LLM_PROVIDER
        )
        model = (
            request.model.strip()
            or str(runtime_llm.get("model") or "").strip()
            or os.getenv("MYT_LLM_MODEL", "").strip()
            or str(config.get("model") or "").strip()
            or DEFAULT_LLM_MODEL
        )
        request_id = request.request_id.strip() or self._request_id_factory()

        return ResolvedLLMRequest(
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            provider=provider,
            model=model,
            request_id=request_id,
            metadata=_as_dict(request.metadata),
            options=_as_dict(request.options),
            response_format=_as_dict(request.response_format),
            planning=_as_dict(request.planning) or {"mode": "structured_state_first"},
            modality=str(request.modality or "text"),
            fallback_modalities=_coerce_modalities(request.fallback_modalities),
            attachments=[_as_dict(item) for item in request.attachments],
            timeout_seconds=request.timeout_seconds,
        )

    def _error_response(self, request: ResolvedLLMRequest, *, latency_ms: int, error: LLMError) -> LLMResponse:
        return LLMResponse(
            ok=False,
            request_id=request.request_id,
            provider=request.provider,
            model=request.model,
            latency_ms=latency_ms,
            modality=request.modality,
            fallback_modalities=request.fallback_modalities,
            model_metadata={
                "provider": request.provider,
                "configured_model": request.model,
                "planning": request.planning,
                "response_format": request.response_format,
            },
            error=error,
        )

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int(round((self._clock() - started_at) * 1000)))
