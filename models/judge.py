from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StepDecision(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"
    RETRY = "retry"
    UNKNOWN = "unknown"


@dataclass
class StepJudgeResult:
    step: str
    decision: StepDecision
    confidence: float
    reason: str
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
        }


@dataclass
class TaskJudgeSummary:
    task_type: str
    device_index: int
    overall: StepDecision
    confidence: float
    step_count: int
    success_steps: int
    retry_steps: int
    failed_step: Optional[str]
    total_duration_ms: int
    steps: List[StepJudgeResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "device_index": self.device_index,
            "overall": self.overall.value,
            "confidence": self.confidence,
            "step_count": self.step_count,
            "success_steps": self.success_steps,
            "retry_steps": self.retry_steps,
            "failed_step": self.failed_step,
            "total_duration_ms": self.total_duration_ms,
            "steps": [s.to_dict() for s in self.steps],
        }
