from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from core.paths import traces_dir


def _safe_part(value: object, *, default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    sanitized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw)
    sanitized = sanitized.strip("-._")
    return sanitized or default


def _trace_root() -> Path:
    return traces_dir()


@dataclass(frozen=True, slots=True)
class ModelTraceContext:
    task_id: str
    run_id: str
    target_label: str
    attempt_number: int


class ModelTraceStoreError(RuntimeError):
    pass


class ModelTraceStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        self._root_dir: Path = root_dir or _trace_root()
        self._lock: threading.RLock = threading.RLock()

    def trace_file_path(self, context: ModelTraceContext) -> Path:
        task_part = _safe_part(context.task_id, default="task")
        run_part = _safe_part(context.run_id, default="run")
        target_part = _safe_part(context.target_label, default="target")
        attempt_part = _safe_part(context.attempt_number, default="1")
        directory = self._root_dir / task_part / run_part
        return directory / f"{target_part}.attempt-{attempt_part}.jsonl"

    def append_record(self, context: ModelTraceContext, record: dict[str, object]) -> Path:
        path = self.trace_file_path(context)
        payload = {
            "task_id": context.task_id,
            "run_id": context.run_id,
            "target_label": context.target_label,
            "attempt_number": context.attempt_number,
            **record,
        }
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        try:
            with self._lock:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as handle:
                    _ = handle.write(line)
                    _ = handle.write("\n")
        except OSError as exc:
            raise ModelTraceStoreError(f"failed to append model trace: {path}") from exc
        return path

    def read_records(self, context: ModelTraceContext) -> list[dict[str, object]]:
        path = self.trace_file_path(context)
        if not path.exists():
            return []
        records: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                item = line.strip()
                if not item:
                    continue
                loaded = json.loads(item)
                if isinstance(loaded, Mapping):
                    records.append(
                        cast(dict[str, object], {str(key): value for key, value in loaded.items()})
                    )
        return records
