from __future__ import annotations

from datetime import UTC, datetime

from typing import Any

from core.task_store import TaskRecord
from engine.plugin_loader import get_shared_plugin_loader
from models.task import (
    TaskDetailResponse,
    TaskResponse,
    TaskStatus,
    TaskTarget,
    TaskType,
    WorkflowDraftSummary,
)


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


def _base_task_fields(record: TaskRecord) -> dict[str, Any]:
    task_name = "anonymous"
    if isinstance(record.payload, dict):
        task_name = str(record.payload.get("task") or "anonymous")

    display_name = None
    if isinstance(record.payload, dict):
        payload_display_name = str(record.payload.get("_workflow_display_name") or "").strip()
        if payload_display_name:
            display_name = payload_display_name
    if display_name is None and task_name != "anonymous":
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
        "started_at": parse_datetime(getattr(record, "started_at", None)),
        "finished_at": parse_datetime(getattr(record, "finished_at", None)),
        "retry_count": record.retry_count,
        "max_retries": record.max_retries,
        "retry_backoff_seconds": record.retry_backoff_seconds,
        "next_retry_at": parse_datetime(record.next_retry_at),
        "priority": record.priority,
        "run_at": parse_datetime(record.run_at),
    }


def to_task_response(
    record: TaskRecord,
    workflow_draft: WorkflowDraftSummary | dict[str, object] | None = None,
) -> TaskResponse:
    fields = _base_task_fields(record)
    if workflow_draft is not None:
        fields["workflow_draft"] = (
            workflow_draft
            if isinstance(workflow_draft, WorkflowDraftSummary)
            else WorkflowDraftSummary.model_validate(workflow_draft)
        )
    return TaskResponse.model_validate(fields)


def to_task_detail_response(
    record: TaskRecord,
    workflow_draft: WorkflowDraftSummary | dict[str, object] | None = None,
) -> TaskDetailResponse:
    fields = _base_task_fields(record)
    if workflow_draft is not None:
        fields["workflow_draft"] = (
            workflow_draft
            if isinstance(workflow_draft, WorkflowDraftSummary)
            else WorkflowDraftSummary.model_validate(workflow_draft)
        )
    return TaskDetailResponse.model_validate(
        {
            **fields,
            "result": record.result,
            "error": record.error,
        }
    )
