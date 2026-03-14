from __future__ import annotations

import base64
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Mapping, Callable

import httpx

from core.vlm.vlm_output_parser import VLMOutputParser, VLMAction
from core.system_settings_loader import get_vlm_provider, get_vlm_provider_config, get_vlm_api_key

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


class VLMProvider(Protocol):
    """Protocol for VLM service providers."""
    def predict(
        self,
        image_b64: str,
        task: str,
        history: Optional[list[dict[str, object]]] = None,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
        timeout: float | None = None,
    ) -> VLMAction:
        ...

    def close(self) -> None:
        ...


class StandardVLMProvider:
    """Standard VLM provider using OpenAI-compatible chat completions API."""
    
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        system_prompt: str,
        http_client: httpx.Client,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.system_prompt = system_prompt
        self._http = http_client
        self._parser = VLMOutputParser()

    def predict(
        self,
        image_b64: str,
        task: str,
        history: Optional[list[dict[str, object]]] = None,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
        timeout: float | None = None,
    ) -> VLMAction:
        messages = self._build_messages(image_b64, task, history or [])
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
            timeout=timeout or 60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
        return self._parser.parse(raw_text, screen_width=screen_width, screen_height=screen_height)

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

    def close(self) -> None:
        pass


def create_vlm_provider_by_type(
    provider_type: str,
    provider_name: str,
    http_client: httpx.Client,
    system_prompt: str,
) -> VLMProvider:
    """Factory function to create VLM providers."""
    config = get_vlm_provider_config(provider_name)
    api_key = get_vlm_api_key(provider_name)
    
    if provider_type == "standard":
        return StandardVLMProvider(
            base_url=config.base_url,
            model=config.model,
            api_key=api_key,
            system_prompt=system_prompt,
            http_client=http_client
        )
    # Default fallback
    return StandardVLMProvider(
        base_url=config.base_url,
        model=config.model,
        api_key=api_key,
        system_prompt=system_prompt,
        http_client=http_client
    )


class VLMClient:
    """Client for Visual Language Models with multi-provider support."""

    DEFAULT_SYSTEM_PROMPT = (
        "You are a GUI automation agent. "
        "Given a screenshot and a task description, output the next action to perform. "
        "Use the action format: Action: action_type(params)"
    )

    def __init__(
        self,
        provider: Optional[str] = None,
        system_prompt: Optional[str] = None,
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.provider_name = provider or get_vlm_provider()
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.timeout = timeout
        self._http = http_client or _get_shared_http_client(timeout=timeout)
        self._providers: dict[str, VLMProvider] = {}

    def _get_provider(self, name: str) -> VLMProvider:
        if name not in self._providers:
            config = get_vlm_provider_config(name)
            p_type = getattr(config, "provider_type", "standard")
            self._providers[name] = create_vlm_provider_by_type(
                p_type, name, self._http, self.system_prompt
            )
        return self._providers[name]

    def close(self) -> None:
        for p in self._providers.values():
            p.close()
        self._providers.clear()

    def evaluate(
        self,
        image_ref: str,
        prompt: str,
        *,
        screen_width: int | None = None,
        screen_height: int | None = None,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Legacy single-shot evaluate (keeps backward compat with stub interface)."""
        action = self.predict(
            image_ref,
            prompt,
            screen_width=screen_width,
            screen_height=screen_height,
            provider=provider,
        )
        return {
            "ok": True,
            "image_ref": image_ref,
            "prompt": prompt,
            "result": action.raw_text,
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
        provider: Optional[str] = None,
    ) -> VLMAction:
        """Send screenshot + task to VLM, return parsed action."""
        p_name = provider or self.provider_name
        vlm = self._get_provider(p_name)
        
        image_b64, size = self._load_image_payload(
            image_ref,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        screen_width, screen_height = size if size else (None, None)
        
        return vlm.predict(
            image_b64,
            task,
            history=history,
            screen_width=screen_width,
            screen_height=screen_height,
            timeout=self.timeout
        )

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
