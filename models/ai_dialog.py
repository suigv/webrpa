from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AIDialogPlannerRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=400)
    app_id: str | None = Field(default=None, min_length=1, max_length=64)
    app_display_name: str | None = Field(default=None, max_length=120)
    package_name: str | None = Field(default=None, max_length=255)
    selected_account: str | None = Field(default=None, min_length=1, max_length=200)
    advanced_prompt: str | None = Field(default=None, max_length=2000)


class AIDialogPlannerResponse(BaseModel):
    display_name: str
    task: str = "agent_executor"
    source: str = "ai_dialog"
    operator_summary: str
    resolved_app: dict[str, Any] = Field(default_factory=dict)
    resolved_payload: dict[str, Any] = Field(default_factory=dict)
    follow_up: dict[str, Any] = Field(default_factory=dict)
    account: dict[str, Any] = Field(default_factory=dict)


class AIDialogHistoryItem(BaseModel):
    draft_id: str
    display_name: str
    status: str
    updated_at: str | None = None
    app_id: str | None = None
    account: str | None = None
    last_task_id: str | None = None
    can_replay: bool = False
    can_edit: bool = False
    workflow_draft: dict[str, Any] = Field(default_factory=dict)
