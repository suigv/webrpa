from __future__ import annotations

import imaplib
import json
import re
import time
from email import message_from_bytes
from email.message import Message

from ai_services.llm_client import LLMClient, LLMRequest
from core.credentials_loader import Credentials, load_credentials_from_ref
from engine.action_registry import ActionMetadata
from engine.actions.ai_actions import _encode_image_ref, _runtime_ai_config, _to_int
from engine.actions.ui_actions import capture_compressed
from engine.models.runtime import ActionResult, ExecutionContext

_DEFAULT_CODE_RE = re.compile(r"\b(\d{4,8})\b")
_COMMON_IMAP_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "yahoo.co.jp": "imap.mail.yahoo.co.jp",
    "qq.com": "imap.qq.com",
    "163.com": "imap.163.com",
    "126.com": "imap.126.com",
}

AI_SOLVE_CAPTCHA_METADATA = ActionMetadata(
    description=(
        "AI-assisted captcha solving contract. Intended for image or slider captcha nodes in "
        "yaml_with_ai workflows. Runtime implementation may use VLM/LLM or specialized solvers."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "captcha_type": {
                "type": "string",
                "enum": ["image", "slider", "text"],
                "description": "Captcha subtype expected by the workflow branch.",
            },
            "image_source": {
                "type": "string",
                "description": "Image source descriptor, for example current_screen or a saved image var.",
            },
            "image_url": {"type": "string"},
            "prompt": {"type": "string", "description": "Optional solver hint for the AI runtime."},
            "timeout_seconds": {"type": "number"},
            "save_as": {"type": "string", "description": "Context var name used to persist solver output."},
        },
        "required": ["captcha_type"],
    },
    returns_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Resolved captcha text when applicable."},
            "confidence": {"type": "number"},
            "solver": {"type": "string"},
            "challenge_type": {"type": "string"},
            "offset_ratio": {"type": "number"},
            "instructions": {"type": "string"},
        },
    },
    tags=["ai", "challenge", "contract"],
)

CHANNEL_READ_EMAIL_CODE_METADATA = ActionMetadata(
    description=(
        "Channel-driven email verification code reader. Supports IMAP polling and runtime reader hooks."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "account_ref": {
                "type": "string",
                "description": "Credential or account reference used to resolve the mailbox context.",
            },
            "folder": {"type": "string", "description": "IMAP folder name. Defaults to INBOX."},
            "sender": {"type": "string", "description": "Optional sender filter."},
            "subject_contains": {"type": "string", "description": "Optional subject filter."},
            "code_regex": {"type": "string", "description": "Optional custom verification code regex."},
            "timeout_seconds": {"type": "integer", "minimum": 1},
            "poll_interval_seconds": {"type": "number", "minimum": 0.2},
            "save_as": {"type": "string"},
        },
        "required": ["account_ref"],
    },
    returns_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "channel": {"type": "string", "enum": ["email"]},
            "message_id": {"type": "string"},
            "received_at": {"type": "string"},
            "matched_text": {"type": "string"},
        },
    },
    tags=["channel", "challenge", "contract"],
)

CHANNEL_READ_SMS_CODE_METADATA = ActionMetadata(
    description=(
        "Channel-driven SMS verification code reader. Supports runtime hooks, in-memory inbox payloads, "
        "and explicit message extraction."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "account_ref": {
                "type": "string",
                "description": "Credential or account reference used to resolve the SMS context.",
            },
            "message_text": {"type": "string", "description": "Explicit inbound SMS body to parse."},
            "messages": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional inbound SMS records; newest matching item wins.",
            },
            "sender": {"type": "string", "description": "Optional sender filter."},
            "code_regex": {"type": "string", "description": "Optional custom verification code regex."},
            "save_as": {"type": "string"},
        },
        "required": ["account_ref"],
    },
    returns_schema={
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "channel": {"type": "string", "enum": ["sms"]},
            "message_id": {"type": "string"},
            "received_at": {"type": "string"},
            "matched_text": {"type": "string"},
        },
    },
    tags=["channel", "challenge", "contract"],
)


def _code_pattern(raw_pattern: object) -> re.Pattern[str]:
    text = str(raw_pattern or "").strip()
    if not text:
        return _DEFAULT_CODE_RE
    return re.compile(text)


def _extract_code(text: object, *, pattern: re.Pattern[str]) -> tuple[str, str]:
    content = str(text or "").strip()
    if not content:
        return "", ""
    match = pattern.search(content)
    if match is None:
        return "", content
    if match.groups():
        return str(next((group for group in match.groups() if group), "")).strip(), content
    return str(match.group(0)).strip(), content


def _resolve_credentials(account_ref: object, context: ExecutionContext) -> Credentials | None:
    raw = str(account_ref or "").strip() or str(context.payload.get("credentials_ref") or "").strip()
    if not raw:
        return None
    try:
        return load_credentials_from_ref(raw)
    except Exception:
        return None


def _imap_host_for_email(email_addr: str) -> str:
    domain = email_addr.split("@", 1)[1].strip().lower() if "@" in email_addr else ""
    return _COMMON_IMAP_HOSTS.get(domain, f"imap.{domain}" if domain else "")


def _collect_message_text(message: Message) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            content_type = str(part.get_content_type() or "").lower()
            disposition = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition:
                continue
            if content_type not in {"text/plain", "text/html"}:
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            try:
                parts.append(payload.decode(charset, errors="ignore"))
            except Exception:
                parts.append(payload.decode("utf-8", errors="ignore"))
    else:
        payload = message.get_payload(decode=True) or b""
        charset = message.get_content_charset() or "utf-8"
        try:
            parts.append(payload.decode(charset, errors="ignore"))
        except Exception:
            parts.append(payload.decode("utf-8", errors="ignore"))
    text = "\n".join(parts)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _message_matches(message: Message, *, sender: str, subject_contains: str) -> bool:
    from_header = str(message.get("From") or "")
    subject = str(message.get("Subject") or "")
    if sender and sender.lower() not in from_header.lower():
        return False
    return not (subject_contains and subject_contains.lower() not in subject.lower())


def ai_solve_captcha(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    captcha_type = str(params.get("captcha_type") or "").strip().lower()
    if captcha_type not in {"image", "slider", "text"}:
        return ActionResult(
            ok=False,
            code="invalid_params",
            message="captcha_type must be one of image/slider/text",
        )

    image_ref = str(
        params.get("image_url") or params.get("image_source") or params.get("image_ref") or ""
    ).strip()
    screen_width: int | None = (
        _to_int(params.get("screen_width")) if params.get("screen_width") is not None else None
    )
    screen_height: int | None = (
        _to_int(params.get("screen_height")) if params.get("screen_height") is not None else None
    )

    if not image_ref or image_ref == "current_screen":
        capture_result = capture_compressed({"quality": 80}, context)
        if not capture_result.ok:
            return ActionResult(ok=False, code=capture_result.code, message=capture_result.message)
        image_ref = str(capture_result.data.get("save_path") or "").strip()
        if not image_ref:
            return ActionResult(
                ok=False,
                code="invalid_image",
                message="captcha capture succeeded but no image path was returned",
            )
        if screen_width is None and capture_result.data.get("screen_width") is not None:
            screen_width = int(capture_result.data.get("screen_width"))
        if screen_height is None and capture_result.data.get("screen_height") is not None:
            screen_height = int(capture_result.data.get("screen_height"))

    image_url, size = _encode_image_ref(
        image_ref,
        screen_width=screen_width,
        screen_height=screen_height,
    )
    if not image_url:
        return ActionResult(ok=False, code="invalid_image", message="unable to load captcha image")
    if size and (screen_width is None or screen_height is None):
        screen_width, screen_height = size

    user_prompt = str(params.get("prompt") or "").strip()
    if captcha_type == "slider":
        base_prompt = (
            "Analyze this slider captcha image and return JSON only. "
            "Use keys challenge_type, offset_ratio, confidence, and instructions. "
            "offset_ratio must be a number between 0 and 1 describing how far the slider should move."
        )
    else:
        base_prompt = (
            "Analyze this captcha image and return JSON only. "
            "Use keys challenge_type, text, confidence, and instructions. "
            "text should contain only the solved verification text."
        )
    if user_prompt:
        base_prompt = f"{base_prompt}\nAdditional hint: {user_prompt}"
    if screen_width and screen_height:
        base_prompt = f"{base_prompt}\nImage size: {screen_width}x{screen_height}."

    request = LLMRequest(
        prompt=base_prompt,
        system_prompt="Return strict JSON only.",
        response_format={"type": "json_object"},
        modality="vision",
        attachments=[{"image_url": image_url}],
        timeout_seconds=float(params.get("timeout_seconds") or 30),
    )
    client = LLMClient()
    response = client.evaluate(request, runtime_config=_runtime_ai_config(context))
    if not response.ok:
        error = response.error.to_dict() if response.error else {}
        return ActionResult(
            ok=False,
            code=str(error.get("code") or "llm_error"),
            message=str(error.get("message") or "captcha solver request failed"),
            data={"error": error},
        )
    try:
        payload = json.loads(str(response.output_text or "").strip())
    except Exception as exc:
        return ActionResult(ok=False, code="invalid_json", message=str(exc))
    if not isinstance(payload, dict):
        return ActionResult(ok=False, code="invalid_response", message="captcha solver must return an object")

    text = str(payload.get("text") or "").strip()
    instructions = str(payload.get("instructions") or "").strip()
    offset_ratio_raw = payload.get("offset_ratio")
    offset_ratio = None
    if isinstance(offset_ratio_raw, (int, float, str)) and str(offset_ratio_raw).strip():
        try:
            offset_ratio = float(offset_ratio_raw)
        except Exception:
            offset_ratio = None
    if captcha_type == "slider":
        if offset_ratio is None:
            return ActionResult(
                ok=False,
                code="invalid_response",
                message="slider captcha response must include offset_ratio",
                data={"raw": payload},
            )
    elif not text:
        return ActionResult(
            ok=False,
            code="invalid_response",
            message="captcha response must include text",
            data={"raw": payload},
        )

    return ActionResult(
        ok=True,
        code="ok",
        data={
            "challenge_type": str(payload.get("challenge_type") or captcha_type),
            "text": text,
            "offset_ratio": offset_ratio,
            "confidence": float(payload.get("confidence") or 0.0),
            "instructions": instructions,
            "solver": "llm_vision",
            "raw": payload,
            "model": response.model,
        },
    )


def channel_read_email_code(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    runtime_reader = context.runtime.get("channel_read_email_code")
    if callable(runtime_reader):
        result = runtime_reader(params, context)
        return result if isinstance(result, ActionResult) else ActionResult(ok=True, data=dict(result or {}))

    creds = _resolve_credentials(params.get("account_ref"), context)
    if creds is None or not str(creds.email or "").strip():
        return ActionResult(
            ok=False,
            code="missing_email_credentials",
            message="email address is required in credentials for channel.read_email_code",
        )
    password = str(creds.email_password or creds.email_token or "").strip()
    if not password:
        return ActionResult(
            ok=False,
            code="missing_email_credentials",
            message="email_password or email_token is required for channel.read_email_code",
        )

    email_addr = str(creds.email or "").strip()
    host = str(params.get("imap_host") or "").strip() or _imap_host_for_email(email_addr)
    if not host:
        return ActionResult(ok=False, code="invalid_params", message="unable to infer imap_host from email")
    folder = str(params.get("folder") or "INBOX").strip() or "INBOX"
    sender = str(params.get("sender") or "").strip()
    subject_contains = str(params.get("subject_contains") or "").strip()
    timeout_seconds = max(1, int(params.get("timeout_seconds") or 30))
    poll_interval = max(0.2, float(params.get("poll_interval_seconds") or 2))
    code_pattern = _code_pattern(params.get("code_regex"))

    started = time.monotonic()
    last_error = ""
    while (time.monotonic() - started) <= timeout_seconds:
        try:
            with imaplib.IMAP4_SSL(host, int(params.get("imap_port") or 993)) as client:
                client.login(email_addr, password)
                client.select(folder)
                status, payload = client.search(None, "ALL")
                if status != "OK":
                    last_error = f"imap search failed: {status}"
                else:
                    ids = payload[0].split() if payload and payload[0] else []
                    for message_id in reversed(ids):
                        fetch_status, fetched = client.fetch(message_id, "(RFC822)")
                        if fetch_status != "OK":
                            continue
                        raw_message = next(
                            (
                                item[1]
                                for item in fetched
                                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes)
                            ),
                            b"",
                        )
                        if not raw_message:
                            continue
                        message = message_from_bytes(raw_message)
                        if not _message_matches(
                            message, sender=sender, subject_contains=subject_contains
                        ):
                            continue
                        text = _collect_message_text(message)
                        code, matched_text = _extract_code(text, pattern=code_pattern)
                        if code:
                            return ActionResult(
                                ok=True,
                                code="ok",
                                data={
                                    "code": code,
                                    "channel": "email",
                                    "message_id": message_id.decode("utf-8", errors="ignore"),
                                    "received_at": str(message.get("Date") or "").strip(),
                                    "matched_text": matched_text,
                                },
                            )
        except Exception as exc:
            last_error = str(exc)
        time.sleep(poll_interval)
    return ActionResult(
        ok=False,
        code="verification_code_not_found",
        message=last_error or "no email verification code found within timeout",
    )


def channel_read_sms_code(params: dict[str, object], context: ExecutionContext) -> ActionResult:
    runtime_reader = context.runtime.get("channel_read_sms_code")
    if callable(runtime_reader):
        result = runtime_reader(params, context)
        return result if isinstance(result, ActionResult) else ActionResult(ok=True, data=dict(result or {}))

    code_pattern = _code_pattern(params.get("code_regex"))
    sender_filter = str(params.get("sender") or "").strip().lower()

    candidates: list[dict[str, str]] = []
    direct_message = str(params.get("message_text") or params.get("body") or "").strip()
    if direct_message:
        candidates.append(
            {
                "body": direct_message,
                "sender": str(params.get("sender") or "").strip(),
                "message_id": str(params.get("message_id") or "").strip(),
                "received_at": str(params.get("received_at") or "").strip(),
            }
        )

    runtime_inbox = context.runtime.get("sms_inbox")
    if isinstance(runtime_inbox, list):
        for item in runtime_inbox:
            if isinstance(item, dict):
                candidates.append(
                    {
                        "body": str(item.get("body") or item.get("message_text") or "").strip(),
                        "sender": str(item.get("sender") or item.get("address") or "").strip(),
                        "message_id": str(item.get("message_id") or "").strip(),
                        "received_at": str(item.get("received_at") or "").strip(),
                    }
                )

    raw_messages = params.get("messages")
    if isinstance(raw_messages, list):
        for item in raw_messages:
            if isinstance(item, dict):
                candidates.append(
                    {
                        "body": str(item.get("body") or item.get("message_text") or "").strip(),
                        "sender": str(item.get("sender") or item.get("address") or "").strip(),
                        "message_id": str(item.get("message_id") or "").strip(),
                        "received_at": str(item.get("received_at") or "").strip(),
                    }
                )

    for item in reversed(candidates):
        if sender_filter and sender_filter not in item["sender"].lower():
            continue
        code, matched_text = _extract_code(item["body"], pattern=code_pattern)
        if code:
            return ActionResult(
                ok=True,
                code="ok",
                data={
                    "code": code,
                    "channel": "sms",
                    "message_id": item["message_id"] or None,
                    "received_at": item["received_at"] or None,
                    "matched_text": matched_text,
                },
            )

    return ActionResult(
        ok=False,
        code="verification_code_not_found",
        message=(
            "no sms verification code found; provide message_text/messages, runtime sms_inbox, "
            "or wire channel_read_sms_code runtime hook"
        ),
    )
