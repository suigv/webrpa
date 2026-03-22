from __future__ import annotations

from typing import Any


def _load() -> list[dict[str, Any]]:
    from engine.actions.sdk_config_support import load_prompt_templates_document

    doc = load_prompt_templates_document()
    templates = doc.get("templates", [])
    if not isinstance(templates, list):
        return []
    return [
        {
            "key": str(t.get("key") or ""),
            "name": str(t.get("name") or ""),
            "content": str(t.get("content") or ""),
        }
        for t in templates
        if isinstance(t, dict) and t.get("key")
    ]


def get_prompt_templates() -> list[dict[str, Any]]:
    return _load()
