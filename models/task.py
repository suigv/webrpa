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


class WorkflowFailureAdvice(BaseModel):
    summary: str
    checkpoint: str | None = None
    missing: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    suggested_prompt: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class WorkflowDraftSummary(BaseModel):
    draft_id: str
    display_name: str
    task_name: str
    status: str
    plugin_name_candidate: str
    success_count: int = 0
    failure_count: int = 0
    cancelled_count: int = 0
    success_threshold: int = 3
    remaining_successes: int = 0
    can_continue: bool = False
    can_distill: bool = False
    latest_prompt_text: str | None = None
    latest_failure_advice: WorkflowFailureAdvice | None = None
    last_success_snapshot_available: bool = False
    last_distilled_manifest_path: str | None = None
    last_distilled_script_path: str | None = None
    latest_terminal_task_id: str | None = None
    latest_completed_task_id: str | None = None
    successful_task_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    message: str | None = None
    next_action: str | None = None


class TaskRequest(BaseModel):
    script: dict[str, Any] | None = None
    task: str | None = Field(default=None, min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    targets: list[TaskTarget] = Field(default_factory=list)
    devices: list[int] = Field(default_factory=list)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    draft_id: str | None = Field(default=None, min_length=1, max_length=64)
    success_threshold: int | None = Field(default=None, ge=1, le=20)
    ai_type: str = "default"
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
    workflow_draft: WorkflowDraftSummary | None = None
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


class WorkflowDraftContinueRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=10)


class WorkflowDraftDistillRequest(BaseModel):
    plugin_name: str | None = Field(default=None, min_length=1, max_length=64)
    force: bool = False
