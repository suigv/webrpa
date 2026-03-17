# pyright: reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportDeprecated=false

import base64
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from ai_services.llm_client import JSONDict, LLMClient, LLMRequest, LLMResponse
from engine.actions.ui_actions import capture_compressed
from engine.models.runtime import ActionResult, ExecutionContext
from engine.action_registry import ActionMetadata


LLM_EVALUATE_METADATA = ActionMetadata(
    description="Evaluate a text-based LLM prompt",
    params_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "The prompt to send to LLM"},
            "system_prompt": {"type": "string", "description": "Optional system personality/instructions"}
        },
        "required": ["prompt"]
    },
    tags=["skill"]
)

VLM_EVALUATE_METADATA = ActionMetadata(
    description="Evaluate a vision-based LLM prompt with an image",
    params_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "The prompt to send to VLM"},
            "image_url": {"type": "string", "description": "Image URL or base64 data"},
            "system_prompt": {"type": "string"}
        },
        "required": ["prompt"]
    },
    tags=["skill"]
)

LOCATE_POINT_METADATA = ActionMetadata(
    description="Locate a specific point/UI element using AI description (physical-resolution aware)",
    params_schema={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Natural language description of the target (e.g. 'the like button')"},
            "image_url": {"type": "string", "description": "Optional image data (will screenshot if omitted)"}
        },
        "required": ["prompt"]
    },
    returns_schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
            "found": {"type": "boolean"}
        }
    },
    tags=["skill"]
)


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


def _safe_b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=False)
    except Exception:
        return b""


def _image_size_from_bytes(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return (width, height)
    if data[:2] == b"\xff\xd8":
        idx = 2
        length = len(data)
        while idx < length - 1:
            if data[idx] != 0xFF:
                idx += 1
                continue
            marker = data[idx + 1]
            if marker in (
                0xC0, 0xC1, 0xC2, 0xC3,
                0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB,
                0xCD, 0xCE, 0xCF,
            ):
                if idx + 8 >= length:
                    return None
                height = int.from_bytes(data[idx + 5:idx + 7], "big")
                width = int.from_bytes(data[idx + 7:idx + 9], "big")
                return (width, height)
            if idx + 3 >= length:
                break
            segment_len = int.from_bytes(data[idx + 2:idx + 4], "big")
            if segment_len < 2:
                break
            idx += 2 + segment_len
    return None


def _detect_image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/png"


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except Exception:
        return default


def _coerce_point(
    x: float,
    y: float,
    *,
    width: int | None,
    height: int | None,
    coord_mode: str,
    clamp: bool,
) -> tuple[int, int]:
    mode = coord_mode.strip().lower()
    final_x = x
    final_y = y
    if width and height:
        if mode in {"norm_1", "0-1", "zero_to_one", "normalized"}:
            final_x = x * width
            final_y = y * height
        elif mode in {"norm_1000", "0-1000", "zero_to_1000"}:
            final_x = (x / 1000.0) * width
            final_y = (y / 1000.0) * height
        elif mode in {"auto"}:
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                final_x = x * width
                final_y = y * height
    if clamp and width and height:
        final_x = max(0.0, min(float(width - 1), final_x))
        final_y = max(0.0, min(float(height - 1), final_y))
    return (int(round(final_x)), int(round(final_y)))


def _extract_point(payload: object) -> tuple[float, float] | None:
    if isinstance(payload, dict):
        if "x" in payload and "y" in payload:
            try:
                return (float(payload["x"]), float(payload["y"]))
            except Exception:
                return None
        for key in ("point", "center"):
            value = payload.get(key)
            if isinstance(value, dict) and "x" in value and "y" in value:
                try:
                    return (float(value["x"]), float(value["y"]))
                except Exception:
                    return None
        for key in ("bbox", "box"):
            value = payload.get(key)
            if isinstance(value, (list, tuple)) and len(value) == 4:
                try:
                    x0, y0, x1, y1 = (float(item) for item in value)
                except Exception:
                    return None
                return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
            if isinstance(value, dict):
                coords = []
                for k in ("x0", "y0", "x1", "y1"):
                    if k not in value:
                        coords = []
                        break
                    coords.append(value[k])
                if coords:
                    try:
                        x0, y0, x1, y1 = (float(item) for item in coords)
                    except Exception:
                        return None
                    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
    return None


def _encode_image_ref(
    image_ref: str,
    *,
    screen_width: int | None,
    screen_height: int | None,
) -> tuple[str, tuple[int, int] | None]:
    trimmed = str(image_ref or "").strip()
    if not trimmed:
        return "", None
    if trimmed.startswith("data:image"):
        size = (screen_width, screen_height) if screen_width and screen_height else None
        return trimmed, size
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        size = (screen_width, screen_height) if screen_width and screen_height else None
        return trimmed, size

    path = Path(trimmed)
    raw_bytes = b""
    if path.exists():
        raw_bytes = path.read_bytes()
    else:
        raw_bytes = _safe_b64decode(trimmed)

    if not raw_bytes:
        return "", None
    size = (
        (screen_width, screen_height)
        if screen_width and screen_height
        else _image_size_from_bytes(raw_bytes)
    )
    mime = _detect_image_mime(raw_bytes)
    payload = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime};base64,{payload}", size


def locate_point(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    prompt = str(params.get("prompt") or params.get("query") or params.get("instruction") or params.get("text") or "").strip()
    if not prompt:
        return ActionResult(ok=False, code="invalid_params", message="prompt is required")

    screen_width = _to_int(params.get("screen_width")) if params.get("screen_width") is not None else None
    screen_height = _to_int(params.get("screen_height")) if params.get("screen_height") is not None else None

    image_ref = str(params.get("image_url") or params.get("image_ref") or params.get("image_data") or "").strip()
    physical_width: int | None = None
    physical_height: int | None = None

    if not image_ref:
        save_dir = Path(str(params.get("save_dir") or "/tmp/webrpa_ai")).resolve()
        save_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        save_path = str(params.get("save_path") or (save_dir / f"locate-point-{timestamp}.png"))
        capture_params = {
            "save_path": save_path,
            "image_type": _to_int(params.get("image_type"), 0),
            "quality": _to_int(params.get("quality"), 80),
        }
        capture_result = capture_compressed(capture_params, context)
        if not capture_result.ok:
            return ActionResult(ok=False, code=capture_result.code, message=capture_result.message)
        image_ref = str(capture_result.data.get("save_path") or save_path)
        # 提取物理及截图分辨率
        physical_w = capture_result.data.get("physical_width")
        physical_h = capture_result.data.get("physical_height")
        physical_width = int(physical_w) if physical_w else None
        physical_height = int(physical_h) if physical_h else None

        # 如果用户未显式传入截图比例，使用截图中提取的比例 (VLM看到的比例)
        raw_screen_w = capture_result.data.get("screen_width")
        raw_screen_h = capture_result.data.get("screen_height")
        if screen_width is None and raw_screen_w:
            screen_width = int(raw_screen_w)
        if screen_height is None and raw_screen_h:
            screen_height = int(raw_screen_h)

    image_url, size = _encode_image_ref(
        image_ref,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    if not image_url:
        return ActionResult(ok=False, code="invalid_image", message="unable to load image for locate_point")

    if size and (screen_width is None or screen_height is None):
        screen_width, screen_height = size

    if screen_width and screen_height:
        prompt = f"{prompt}\nImage size: {screen_width}x{screen_height}. Return pixel coordinates as JSON."

    system_prompt = str(params.get("system_prompt") or "").strip()
    if not system_prompt:
        system_prompt = "Return JSON only. Use keys x and y for the click coordinate."

    request = LLMRequest(
        prompt=prompt,
        system_prompt=system_prompt,
        response_format={"type": "json_object"},
        modality="vision",
        attachments=[{"image_url": image_url}],
        timeout_seconds=_float_param(params, "timeout_seconds"),
    )
    client = LLMClient()
    response = client.evaluate(request, runtime_config=_runtime_ai_config(context))
    if not response.ok:
        error = response.error.to_dict() if response.error else {}
        message = str(error.get("message") or "llm_request_failed")
        code = str(error.get("code") or "llm_error")
        return ActionResult(ok=False, code=code, message=message, data={"error": error})

    output = str(response.output_text or "").strip()
    if not output:
        return ActionResult(ok=False, code="empty_response", message="llm returned empty output")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        return ActionResult(ok=False, code="invalid_json", message=str(exc))

    if isinstance(payload, dict) and payload.get("error"):
        return ActionResult(ok=False, code="not_found", message=str(payload.get("error")))

    point = _extract_point(payload)
    if point is None:
        return ActionResult(ok=False, code="invalid_response", message="missing x/y in llm response")

    coord_mode = str(params.get("coord_mode") or "pixel")
    clamp = bool(params.get("clamp", True))

    # 第一步：根据 AI 返回值和它所看到的图片尺寸（screen_width/height）计算出它在图片上的真实相对位置（归一化）
    # 由于 VLM 在返回 pixel 坐标时，基于的是我们提供的 prompt 里的 screen_widthxscreen_height，
    # 因此使用 _coerce_point 并指定当前 coord_mode 和 screen_width/height，能得到它在图片上的真实像素。
    img_x, img_y = _coerce_point(
        point[0],
        point[1],
        width=screen_width,
        height=screen_height,
        coord_mode=coord_mode,
        clamp=clamp,
    )

    # 第二步：将图片上的像素位置重新投影到物理屏幕尺寸上 (如果可用)
    # 因为设备底层 RPC 的 touch/click 指令必须按照物理屏幕的尺径发送。
    x, y = img_x, img_y
    if physical_width and physical_height and screen_width and screen_height:
        # 检测是否因横屏导致物理宽高的含义发生了互换
        # screen_width > screen_height 意味着当前截获的法向图片是横板的，
        # 而 bottom-level 的 physical_width/height 通常是硬件的固定方向（如 1080x1920，竖板短宽长高）。
        # 判断横屏或竖屏：如果图片长宽关系不同步于物理长宽关系，就进行反转投影
        screen_is_landscape = screen_width > screen_height
        physical_is_landscape = physical_width > physical_height
        
        target_physical_w, target_physical_h = physical_width, physical_height
        if screen_is_landscape != physical_is_landscape:
            target_physical_w, target_physical_h = physical_height, physical_width

        x = int(round((float(img_x) / float(screen_width)) * float(target_physical_w)))
        y = int(round((float(img_y) / float(screen_height)) * float(target_physical_h)))

    return ActionResult(
        ok=True,
        code="ok",
        data={
            "x": x,
            "y": y,
            "screen_width": screen_width,
            "screen_height": screen_height,
            "physical_width": physical_width,
            "physical_height": physical_height,
            "raw": payload,
            "model": response.model,
        },
    )


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
