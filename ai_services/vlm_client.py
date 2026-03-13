from __future__ import annotations

import base64
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from core.vlm.uitars_output_parser import UITarsOutputParser, UITarsAction

_shared_http_client: httpx.Client | None = None
_CLIENT_LOCK = threading.Lock()


def _get_shared_http_client(timeout: float = 60.0) -> httpx.Client:
    global _shared_http_client
    if _shared_http_client is None:
        with _CLIENT_LOCK:
            if _shared_http_client is None:
                limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
                try:
                    _shared_http_client = httpx.Client(timeout=timeout, limits=limits)
                except TypeError:
                    _shared_http_client = httpx.Client(timeout=timeout)
    return _shared_http_client


class VLMClient:
    """Client for UI-TARS visual language model."""

    DEFAULT_BASE_URL = "http://127.0.0.1:9000/v1"
    DEFAULT_MODEL = "UI-TARS-1.5-7B-6bit"
    DEFAULT_SYSTEM_PROMPT = (
        "You are a GUI automation agent. "
        "Given a screenshot and a task description, output the next action to perform. "
        "Use the action format: Action: action_type(params)"
    )

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        system_prompt: Optional[str] = None,
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        from core.system_settings_loader import get_vlm_base_url, get_vlm_model, get_vlm_api_key
        self.base_url = (base_url or get_vlm_base_url()).rstrip("/")
        self.model = model or get_vlm_model()
        self.api_key = api_key or get_vlm_api_key() or os.environ.get("UITARS_API_KEY", "token")
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.timeout = timeout
        self._parser = UITarsOutputParser()
        self._http = http_client or _get_shared_http_client(timeout=timeout)

    def close(self) -> None:
        return None

    def evaluate(
        self,
        image_ref: str,
        prompt: str,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> Dict[str, Any]:
        """Legacy single-shot evaluate (keeps backward compat with stub interface)."""
        action = self.predict(
            image_ref,
            prompt,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        raw = getattr(action, "raw", None)
        return {
            "ok": True,
            "image_ref": image_ref,
            "prompt": prompt,
            "result": raw,
            "action": action.to_dict(),
        }

    def predict(
        self,
        image_ref: str,
        task: str,
        history: Optional[list[dict[str, object]]] = None,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> UITarsAction:
        """Send screenshot + task to UI-TARS, return parsed action."""
        image_b64, size = self._load_image_payload(
            image_ref,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        messages = self._build_messages(image_b64, task, history or [])
        raw_text = self._call_api(messages)
        screen_width, screen_height = size if size else (None, None)
        return self._parser.parse(raw_text, screen_width=screen_width, screen_height=screen_height)

    def _load_image_payload(
        self,
        image_ref: str,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
    ) -> tuple[str, tuple[int, int] | None]:
        """Load image bytes + base64 string; returns (base64, (width,height)|None)."""
        raw_bytes = b""
        path = Path(image_ref)
        if path.exists():
            raw_bytes = path.read_bytes()
        elif image_ref.startswith("data:image"):
            _, _, b64_payload = image_ref.partition(",")
            raw_bytes = _safe_b64decode(b64_payload)
        else:
            raw_bytes = _safe_b64decode(image_ref)

        if raw_bytes:
            size = (int(screen_width), int(screen_height)) if screen_width and screen_height else _image_size_from_bytes(raw_bytes)
            return base64.b64encode(raw_bytes).decode(), size
        return image_ref, (int(screen_width), int(screen_height)) if screen_width and screen_height else None

    def _build_messages(
        self,
        image_b64: str,
        task: str,
        history: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            {"type": "text", "text": task},
        ]
        messages: list[dict[str, object]] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages

    def _call_api(self, messages: list[dict[str, object]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 512,
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = self._http.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


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


def get_shared_vlm_client() -> VLMClient:
    return VLMClient()
