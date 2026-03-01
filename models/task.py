from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TaskType(str, Enum):
    SCRIPT = "script"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskRequest(BaseModel):
    script: Dict[str, Any]
    devices: List[int] = []
    ai_type: str = "volc"


class TaskResponse(BaseModel):
    task_id: str
    task_type: TaskType
    devices: List[int]
    ai_type: str
    status: TaskStatus
    created_at: datetime


class TaskDetailResponse(TaskResponse):
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
