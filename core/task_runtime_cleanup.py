from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.paths import traces_dir
from core.task_events import TaskEventStore
from core.task_store import TaskRecord, TaskStore

logger = logging.getLogger(__name__)


# Lightweight typing: allow any object that exposes a `get` method returning
# an object with a `manifest` attribute. We rely on structural typing at runtime.


def _env_nonnegative_int(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        parsed = int(str(raw).strip())
    except ValueError:
        return default
    return max(0, parsed)


def _task_finished_at(record: TaskRecord) -> datetime:
    raw = str(record.finished_at or record.updated_at or record.created_at)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _trace_path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return int(path.stat().st_size)
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            total += int(child.stat().st_size)
    return total


def trace_root_size() -> int:
    root = traces_dir()
    if not root.exists():
        return 0
    total = 0
    for child in root.iterdir():
        total += _trace_path_size(child)
    return total


def remove_task_traces(task_id: str) -> int:
    removed_bytes = 0
    try:
        t_dir = traces_dir()
        trace_file = t_dir / f"{task_id}.jsonl"
        if trace_file.exists():
            removed_bytes += int(trace_file.stat().st_size)
            trace_file.unlink()

        screenshots = t_dir / task_id
        if screenshots.exists() and screenshots.is_dir():
            import shutil

            removed_bytes += _trace_path_size(screenshots)
            shutil.rmtree(screenshots)
    except Exception as exc:
        logger.warning(f"Failed to cleanup traces for task {task_id}: {exc}")
    return removed_bytes


def task_visible_in_catalog(task_name: str, plugin_loader: Any) -> bool:
    entry = plugin_loader.get(task_name)
    if entry is None:
        return True
    try:
        return bool(getattr(entry.manifest, "visible_in_task_catalog"))
    except Exception:
        return True


class TaskRuntimeCleanupService:
    _store: TaskStore
    _events: TaskEventStore
    _plugin_loader: Any

    def __init__(
        self,
        *,
        store: TaskStore,
        event_store: TaskEventStore,
        plugin_loader: Any,
    ) -> None:
        self._store = store
        self._events = event_store
        self._plugin_loader = plugin_loader

    def cleanup_runtime_artifacts(
        self,
        *,
        hidden_task_retention_days: int | None = None,
        event_retention_days: int | None = None,
        trace_retention_days: int | None = None,
        max_event_rows: int | None = None,
        max_trace_bytes: int | None = None,
    ) -> dict[str, int]:
        hidden_task_retention_days = (
            _env_nonnegative_int("MYT_HIDDEN_TASK_RETENTION_DAYS", 3)
            if hidden_task_retention_days is None
            else max(0, hidden_task_retention_days)
        )
        event_retention_days = (
            _env_nonnegative_int("MYT_TASK_EVENT_RETENTION_DAYS", 30)
            if event_retention_days is None
            else max(0, event_retention_days)
        )
        trace_retention_days = (
            _env_nonnegative_int("MYT_TASK_TRACE_RETENTION_DAYS", 14)
            if trace_retention_days is None
            else max(0, trace_retention_days)
        )
        max_event_rows = (
            _env_nonnegative_int("MYT_TASK_EVENT_MAX_ROWS", 50000)
            if max_event_rows is None
            else max(0, max_event_rows)
        )
        max_trace_bytes = (
            _env_nonnegative_int("MYT_TASK_TRACE_MAX_BYTES", 1_073_741_824)
            if max_trace_bytes is None
            else max(0, max_trace_bytes)
        )

        active_task_ids = set(self._store.list_active_task_ids())
        terminal_records = [
            record
            for record in self._store.list_terminal_tasks_oldest_first()
            if record.task_id not in active_task_ids
        ]
        now = datetime.now(UTC)
        event_cleared_tasks: set[str] = set()
        trace_cleared_tasks: set[str] = set()
        removed_event_rows = 0
        removed_trace_bytes = 0

        def _maybe_clear_for_age(record: TaskRecord) -> None:
            nonlocal removed_event_rows, removed_trace_bytes
            task_name = str(record.payload.get("task") or "anonymous")
            finished_at = _task_finished_at(record)
            hidden = not task_visible_in_catalog(task_name, self._plugin_loader)
            if (
                hidden
                and hidden_task_retention_days is not None
                and hidden_task_retention_days >= 0
                and finished_at <= now - timedelta(days=hidden_task_retention_days)
            ):
                if record.task_id not in event_cleared_tasks:
                    removed_event_rows += self._events.clear_task_events(record.task_id)
                    event_cleared_tasks.add(record.task_id)
                if record.task_id not in trace_cleared_tasks:
                    removed_trace_bytes += remove_task_traces(record.task_id)
                    trace_cleared_tasks.add(record.task_id)
                return
            if (
                event_retention_days is not None
                and event_retention_days >= 0
                and finished_at <= now - timedelta(days=event_retention_days)
                and record.task_id not in event_cleared_tasks
            ):
                removed_event_rows += self._events.clear_task_events(record.task_id)
                event_cleared_tasks.add(record.task_id)
            if (
                trace_retention_days is not None
                and trace_retention_days >= 0
                and finished_at <= now - timedelta(days=trace_retention_days)
                and record.task_id not in trace_cleared_tasks
            ):
                removed_trace_bytes += remove_task_traces(record.task_id)
                trace_cleared_tasks.add(record.task_id)

        for record in terminal_records:
            _maybe_clear_for_age(record)

        if max_event_rows is not None and max_event_rows > 0:
            current_event_rows = self._events.count_events()
            if current_event_rows > max_event_rows:
                for record in terminal_records:
                    if current_event_rows <= max_event_rows:
                        break
                    if record.task_id in event_cleared_tasks:
                        continue
                    deleted = self._events.clear_task_events(record.task_id)
                    if deleted <= 0:
                        continue
                    removed_event_rows += deleted
                    current_event_rows -= deleted
                    event_cleared_tasks.add(record.task_id)

        if max_trace_bytes is not None and max_trace_bytes > 0:
            current_trace_bytes = trace_root_size()
            if current_trace_bytes > max_trace_bytes:
                for record in terminal_records:
                    if current_trace_bytes <= max_trace_bytes:
                        break
                    if record.task_id in trace_cleared_tasks:
                        continue
                    deleted_bytes = remove_task_traces(record.task_id)
                    if deleted_bytes <= 0:
                        continue
                    removed_trace_bytes += deleted_bytes
                    current_trace_bytes = max(0, current_trace_bytes - deleted_bytes)
                    trace_cleared_tasks.add(record.task_id)

        return {
            "events_tasks_cleared": len(event_cleared_tasks),
            "event_rows_removed": removed_event_rows,
            "trace_tasks_cleared": len(trace_cleared_tasks),
            "trace_bytes_removed": removed_trace_bytes,
        }
