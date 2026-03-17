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


# 向后兼容：模块级访问时懒加载
class _LazyList(list):
    _loaded = False

    def _ensure(self):
        if not self._loaded:
            self._loaded = True
            self.extend(_load())

    def __iter__(self):
        self._ensure()
        return super().__iter__()

    def __len__(self):
        self._ensure()
        return super().__len__()

    def __getitem__(self, idx):
        self._ensure()
        return super().__getitem__(idx)


PROMPT_TEMPLATES: list[dict[str, Any]] = _LazyList()
