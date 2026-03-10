from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Dict, Any, Optional

import httpx

from core.vlm.uitars_output_parser import UITarsOutputParser, UITarsAction


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
    ) -> None:
        self.base_url = (base_url or os.environ.get("UITARS_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.model = model or os.environ.get("UITARS_MODEL", self.DEFAULT_MODEL)
        self.api_key = api_key or os.environ.get("UITARS_API_KEY", "token")
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.timeout = timeout
        self._parser = UITarsOutputParser()
        self._http = httpx.Client(timeout=timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        return {
            "ok": True,
            "image_ref": image_ref,
            "prompt": prompt,
            "result": action.raw,
            "action": action.to_dict(),
        }

    def predict(
        self,
        image_ref: str,
        task: str,
        history: Optional[list] = None,
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _build_messages(self, image_b64: str, task: str, history: list) -> list:
        user_content = [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            {"type": "text", "text": task},
        ]
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages

    def _call_api(self, messages: list) -> str:
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
    # PNG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return (width, height)
    # JPEG
    if data[:2] == b"\xff\xd8":
        idx = 2
        length = len(data)
        while idx < length - 1:
            if data[idx] != 0xFF:
                idx += 1
                continue
            marker = data[idx + 1]
            # SOF markers
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
