from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from core.model_trace_store import ModelTraceContext, ModelTraceStore

_RESOURCE_ID_KEYS = {"resource_id", "resource-id", "resourceId"}
_SENSITIVE_TYPE_KEYS = {
    "class",
    "class_name",
    "classname",
    "node_class",
    "node_type",
    "type",
    "query_type",
    "input_type",
    "widget_type",
    "view_type",
}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, str, Mapping)):
        items: list[str] = []
        for item in value:
            item_str = str(item).strip()
            if item_str:
                items.append(item_str)
        return items
    return []


def _normalize_resource_id(value: object) -> str:
    candidate = str(value or "").strip()
    if ":id/" not in candidate:
        return ""
    return candidate


class TraceLearner:
    def __init__(self, *, trace_store: ModelTraceStore | None = None) -> None:
        self._trace_store = trace_store or ModelTraceStore()

    def learn_from_context(self, context: ModelTraceContext) -> dict[str, list[str]]:
        return self.learn_from_records(self._trace_store.read_records(context))

    def learn_from_trace_file(self, trace_file: str | Path) -> dict[str, list[str]]:
        path = Path(trace_file)
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return self.learn_from_records(records)

    def learn_from_records(self, records: Iterable[object]) -> dict[str, list[str]]:
        learned: dict[str, list[str]] = {}
        for raw_record in records:
            record = _mapping(raw_record)
            if str(record.get("record_type") or "") != "step":
                continue
            state_id = self._extract_state_id(record)
            if not state_id or state_id == "unknown":
                continue
            if self._is_sensitive_step(record):
                continue
            for resource_id in self._extract_resource_ids(record):
                bucket = learned.setdefault(state_id, [])
                if resource_id not in bucket:
                    bucket.append(resource_id)
        return learned

    def _extract_state_id(self, record: Mapping[str, object]) -> str:
        observation = _mapping(record.get("observation"))
        data = _mapping(observation.get("data"))
        state = _mapping(data.get("state"))
        state_id = str(state.get("state_id") or "").strip()
        if state_id:
            return state_id
        for item in _string_list(observation.get("observed_state_ids")):
            if item:
                return item
        return ""

    def _extract_resource_ids(self, record: Mapping[str, object]) -> list[str]:
        candidates: list[str] = []
        for source in (
            _mapping(record.get("action_result")).get("data"),
            record.get("action_result"),
            record.get("action_params"),
        ):
            for resource_id in self._find_resource_ids(source):
                if resource_id not in candidates:
                    candidates.append(resource_id)
        return candidates

    def _find_resource_ids(self, value: object) -> list[str]:
        matches: list[str] = []
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key) in _RESOURCE_ID_KEYS:
                    resource_id = _normalize_resource_id(item)
                    if resource_id and resource_id not in matches:
                        matches.append(resource_id)
                for nested in self._find_resource_ids(item):
                    if nested not in matches:
                        matches.append(nested)
            return matches
        if isinstance(value, list):
            for item in value:
                for nested in self._find_resource_ids(item):
                    if nested not in matches:
                        matches.append(nested)
        return matches

    def _is_sensitive_step(self, record: Mapping[str, object]) -> bool:
        for source in (
            record.get("action_params"),
            _mapping(record.get("action_result")).get("data"),
            _mapping(_mapping(record.get("observation")).get("data")).get("state"),
        ):
            if self._contains_sensitive_widget(source):
                return True
        return False

    def _contains_sensitive_widget(self, value: object) -> bool:
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_norm = str(key).strip().lower()
                if key_norm in _SENSITIVE_TYPE_KEYS:
                    item_norm = str(item).strip().lower()
                    if "password" in item_norm or "secure" in item_norm:
                        return True
                if self._contains_sensitive_widget(item):
                    return True
            return False
        if isinstance(value, list):
            return any(self._contains_sensitive_widget(item) for item in value)
        return False
