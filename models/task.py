from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TaskType(str, Enum):
    SCRIPT = "script"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskTarget(BaseModel):
    device_id: int = Field(ge=1)
    cloud_id: int = Field(default=1, ge=1)


class TaskRequest(BaseModel):
    script: Optional[Dict[str, Any]] = None
    task: Optional[str] = Field(default=None, min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    targets: List[TaskTarget] = Field(default_factory=list)
    devices: List[int] = Field(default_factory=list)
    ai_type: str = "volc"
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=128)
    max_retries: int = Field(default=0, ge=0, le=20)
    retry_backoff_seconds: int = Field(default=2, ge=0, le=3600)
    priority: int = Field(default=50, ge=0, le=100)
    run_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_submission_mode(self):
        if self.script is not None:
            return self
        if self.task is None or not str(self.task).strip():
            raise ValueError("either script or task must be provided")
        return self


class TaskResponse(BaseModel):
    task_id: str
    task_type: TaskType
    task_name: str = "anonymous"
    devices: List[int]
    targets: List[TaskTarget] = Field(default_factory=list)
    ai_type: str
    idempotency_key: Optional[str] = None
    status: TaskStatus
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 0
    retry_backoff_seconds: int = 2
    next_retry_at: Optional[datetime] = None
    priority: int = 50
    run_at: Optional[datetime] = None


class TaskDetailResponse(TaskResponse):
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskMetricsResponse(BaseModel):
    generated_at: datetime
    window_seconds: int
    since: datetime
    status_counts: Dict[str, int]
    event_type_counts: Dict[str, int]
    terminal_outcomes: Dict[str, int]
    rates: Dict[str, float]
    alerts: Dict[str, Any]
