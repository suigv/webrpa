from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.paths import project_root


def load_runtime_profile(name: str) -> dict[str, Any]:
    normalized = str(name or "").strip()
    if not normalized:
        return {}
    filename = normalized if normalized.endswith(".json") else f"{normalized}.json"
    path = project_root() / "config" / filename
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    runtime = raw.get("runtime") if isinstance(raw.get("runtime"), dict) else raw
    if not isinstance(runtime, dict):
        return {}
    runtime_dict = dict(runtime)
    if "llm" not in runtime_dict and isinstance(runtime_dict.get("gpt"), dict):
        runtime_dict["llm"] = dict(runtime_dict.get("gpt", {}))
    return runtime_dict
