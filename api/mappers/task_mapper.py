from __future__ import annotations

from datetime import UTC, datetime

from core.task_store import TaskRecord
from engine.plugin_loader import get_shared_plugin_loader
from models.task import TaskDetailResponse, TaskResponse, TaskStatus, TaskTarget, TaskType


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        if "+" in value or value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def extract_targets(record: TaskRecord) -> list[TaskTarget]:
    raw_targets = record.targets

    targets: list[TaskTarget] = []
    if isinstance(raw_targets, list):
        for item in raw_targets:
            if not isinstance(item, dict):
                continue
            try:
                targets.append(TaskTarget.model_validate(item))
            except Exception:
                continue
    return targets


def _base_task_fields(record: TaskRecord) -> dict[str, object]:
    task_name = "anonymous"
    if isinstance(record.payload, dict):
        task_name = str(record.payload.get("task") or "anonymous")

    # 尝试匹配中文名
    display_name = None
    if task_name != "anonymous":
        loader = get_shared_plugin_loader()
        plugin = loader.get(task_name)
        if plugin:
            display_name = plugin.manifest.display_name

    return {
        "task_id": record.task_id,
        "task_type": TaskType.SCRIPT,
        "task_name": task_name,
        "display_name": display_name,
        "devices": record.devices,
        "targets": extract_targets(record),
        "ai_type": record.ai_type,
        "idempotency_key": record.idempotency_key,
        "status": TaskStatus(record.status),
        "created_at": parse_datetime(record.created_at) or datetime.now(UTC),
        "retry_count": record.retry_count,
        "max_retries": record.max_retries,
        "retry_backoff_seconds": record.retry_backoff_seconds,
        "next_retry_at": parse_datetime(record.next_retry_at),
        "priority": record.priority,
        "run_at": parse_datetime(record.run_at),
    }


def to_task_response(record: TaskRecord) -> TaskResponse:
    return TaskResponse(**_base_task_fields(record))


def to_task_detail_response(record: TaskRecord) -> TaskDetailResponse:
    return TaskDetailResponse(**_base_task_fields(record), result=record.result, error=record.error)
