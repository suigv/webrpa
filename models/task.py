from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class TaskType(StrEnum):
    SCRIPT = "script"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskTarget(BaseModel):
    device_id: int = Field(ge=1)
    cloud_id: int = Field(default=1, ge=1)


class TaskRequest(BaseModel):
    script: dict[str, Any] | None = None
    task: str | None = Field(default=None, min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    targets: list[TaskTarget] = Field(default_factory=list)
    devices: list[int] = Field(default_factory=list)
    ai_type: str = "volc"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    max_retries: int = Field(default=0, ge=0, le=20)
    retry_backoff_seconds: int = Field(default=2, ge=0, le=3600)
    priority: int = Field(default=50, ge=0, le=100)
    run_at: datetime | None = None

    @model_validator(mode="after")
    def validate_submission_mode(self):
        if self.script is None and (self.task is None or not str(self.task).strip()):
            raise ValueError("either script or task must be provided")
        if not self.targets and not self.devices:
            raise ValueError("either targets or devices must be provided")
        return self


class TaskResponse(BaseModel):
    task_id: str
    task_type: TaskType
    task_name: str = "anonymous"
    display_name: str | None = None
    devices: list[int]
    targets: list[TaskTarget] = Field(default_factory=list)
    ai_type: str
    idempotency_key: str | None = None
    status: TaskStatus
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 0
    retry_backoff_seconds: int = 2
    next_retry_at: datetime | None = None
    priority: int = 50
    run_at: datetime | None = None


class TaskDetailResponse(TaskResponse):
    result: dict[str, Any] | None = None
    error: str | None = None


class TaskMetricsResponse(BaseModel):
    generated_at: datetime
    window_seconds: int
    since: datetime
    status_counts: dict[str, int]
    event_type_counts: dict[str, int]
    terminal_outcomes: dict[str, int]
    rates: dict[str, float]
    alerts: dict[str, Any]
