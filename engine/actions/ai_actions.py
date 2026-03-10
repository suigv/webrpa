# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportDeprecated=false

from collections.abc import Mapping
from typing import cast

from ai_services.llm_client import JSONDict, LLMClient, LLMRequest, LLMResponse
from engine.models.runtime import ActionResult, ExecutionContext


def _runtime_ai_config(context: ExecutionContext) -> JSONDict:
    for key in ("llm", "ai"):
        value = context.runtime.get(key)
        if isinstance(value, Mapping):
            return {str(item_key): item_value for item_key, item_value in value.items()}
    return {}


def _dict_param(params: dict[str, object], key: str) -> JSONDict:
    value = params.get(key)
    if not isinstance(value, Mapping):
        return {}
    return {str(item_key): item_value for item_key, item_value in value.items()}


def _string_list_param(params: dict[str, object], key: str) -> list[str]:
    value = params.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _float_param(params: dict[str, object], key: str) -> float | None:
    value = params.get(key)
    if value is None:
        return None
    if not isinstance(value, (str, int, float)):
        return None
    numeric_value = cast(str | int | float, value)
    return float(numeric_value)


def _build_llm_request(params: dict[str, object], *, modality: str, attachments: list[dict[str, object]] | None = None) -> LLMRequest:
    normalized_attachments: list[JSONDict] = [
        {str(item_key): item_value for item_key, item_value in attachment.items()} for attachment in (attachments or [])
    ]
    return LLMRequest(
        prompt=str(params.get("prompt", "")),
        system_prompt=str(params.get("system_prompt", "")),
        provider=str(params.get("provider", "")),
        model=str(params.get("model", "")),
        request_id=str(params.get("request_id", "")),
        metadata=_dict_param(params, "metadata"),
        options=_dict_param(params, "options"),
        response_format=_dict_param(params, "response_format"),
        planning=_dict_param(params, "planning") or {"mode": "structured_state_first"},
        modality=modality,
        fallback_modalities=_string_list_param(params, "fallback_modalities"),
        attachments=normalized_attachments,
        timeout_seconds=_float_param(params, "timeout_seconds"),
    )


def _response_to_action_result(response: LLMResponse) -> ActionResult:
    payload = response.to_dict()
    if response.ok:
        return ActionResult(ok=True, code="ok", data=payload)
    error = payload.get("error") if isinstance(payload, dict) else None
    code = str(error.get("code") or "llm_error") if isinstance(error, dict) else "llm_error"
    message = str(error.get("message") or "") if isinstance(error, dict) else ""
    return ActionResult(ok=False, code=code, message=message, data=payload)


def llm_evaluate(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    try:
        client = LLMClient()
        request = _build_llm_request(params, modality="text")
        response = client.evaluate(request, runtime_config=_runtime_ai_config(context))
        return _response_to_action_result(response)
    except Exception as e:
        return ActionResult(ok=False, code="llm_error", message=str(e))


def vlm_evaluate(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    try:
        attachments: list[dict[str, object]] = []
        image_url = str(params.get("image_url") or params.get("image_data") or "").strip()
        if image_url:
            attachments.append({"image_url": image_url})
        client = LLMClient()
        request = _build_llm_request(params, modality="vision", attachments=attachments)
        response = client.evaluate(request, runtime_config=_runtime_ai_config(context))
        return _response_to_action_result(response)
    except Exception as e:
        return ActionResult(ok=False, code="vlm_error", message=str(e))
