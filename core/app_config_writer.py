from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.app_config import AppConfigManager
from core.data_store import write_json_atomic
from core.paths import data_dir

_DEFAULT_THRESHOLD = 3


def _learned_ids_path() -> Path:
    return data_dir() / "learned_ids.json"


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _dedupe_texts(values: object) -> list[str]:
    if isinstance(values, str):
        candidate = values.strip()
        return [candidate] if candidate else []
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        item_str = str(item).strip()
        if item_str and item_str not in result:
            result.append(item_str)
    return result


def _coerce_stage_entry(raw: object) -> dict[str, list[str]]:
    if not isinstance(raw, Mapping):
        return {"resource_ids": [], "focus_markers": [], "text_markers": []}
    return {
        "resource_ids": _dedupe_texts(raw.get("resource_ids") or raw.get("resource_id_markers")),
        "focus_markers": _dedupe_texts(raw.get("focus_markers") or raw.get("window_markers")),
        "text_markers": _dedupe_texts(
            raw.get("text_markers")
            or raw.get("texts")
            or raw.get("p95_text_markers")
            or raw.get("content_descs")
        ),
    }


class AppConfigWriter:
    def __init__(self, *, threshold: int = _DEFAULT_THRESHOLD) -> None:
        self._threshold = max(1, int(threshold))

    def merge_stage_resource_ids(
        self, app_id: str, learned: Mapping[str, list[str]]
    ) -> dict[str, object]:
        app_key = str(app_id or "").strip().lower()
        if not app_key:
            return {"updated": False, "added": {}, "threshold": self._threshold}

        document = AppConfigManager.load_app_config(app_key) or {"version": "v1"}
        document.setdefault("version", "v1")
        if not isinstance(document.get("states"), list):
            document["states"] = []
        if not isinstance(document.get("schemes"), dict):
            document["schemes"] = {}
        if not isinstance(document.get("selectors"), dict):
            document["selectors"] = {}

        stage_patterns_raw = document.get("stage_patterns")
        if not isinstance(stage_patterns_raw, dict):
            stage_patterns_raw = {}
        stage_patterns: dict[str, dict[str, list[str]]] = {
            str(state_id).strip(): _coerce_stage_entry(entry)
            for state_id, entry in stage_patterns_raw.items()
            if str(state_id).strip()
        }

        counts_path = _learned_ids_path()
        counts_doc = _load_json_dict(counts_path)
        counts_root = counts_doc.get("counts")
        if not isinstance(counts_root, dict):
            counts_root = {}
        app_counts_raw = counts_root.get(app_key)
        if not isinstance(app_counts_raw, dict):
            app_counts_raw = {}

        added: dict[str, list[str]] = {}
        counts_changed = False
        config_changed = False

        for state_id, resource_ids in learned.items():
            state_key = str(state_id or "").strip()
            if not state_key:
                continue
            unique_ids = _dedupe_texts(resource_ids)
            if not unique_ids:
                continue

            stage_entry = stage_patterns.setdefault(
                state_key, {"resource_ids": [], "focus_markers": [], "text_markers": []}
            )
            stage_counts_raw = app_counts_raw.get(state_key)
            if not isinstance(stage_counts_raw, dict):
                stage_counts_raw = {}

            for resource_id in unique_ids:
                new_count = int(stage_counts_raw.get(resource_id, 0) or 0) + 1
                stage_counts_raw[resource_id] = new_count
                counts_changed = True
                if new_count < self._threshold:
                    continue
                if resource_id in stage_entry["resource_ids"]:
                    continue
                stage_entry["resource_ids"].append(resource_id)
                added.setdefault(state_key, []).append(resource_id)
                config_changed = True

            app_counts_raw[state_key] = stage_counts_raw

        counts_root[app_key] = app_counts_raw
        counts_doc["version"] = "v1"
        counts_doc["threshold"] = self._threshold
        counts_doc["counts"] = counts_root
        if counts_changed:
            write_json_atomic(counts_path, counts_doc)

        if config_changed:
            document["stage_patterns"] = {
                state_id: {
                    "resource_ids": entry["resource_ids"],
                    "focus_markers": entry["focus_markers"],
                    "text_markers": entry["text_markers"],
                }
                for state_id, entry in stage_patterns.items()
            }
            AppConfigManager.write_app_config(app_key, document)

        return {
            "updated": config_changed,
            "added": added,
            "threshold": self._threshold,
            "counts_path": str(counts_path),
        }
