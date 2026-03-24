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
    intent: dict[str, Any] = Field(default_factory=dict)
    branch: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)
    recommended_workflows: list[dict[str, Any]] = Field(default_factory=list)
    draft: dict[str, Any] = Field(default_factory=dict)


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


class AITaskAnnotationRequest(BaseModel):
    task_id: str = Field(min_length=1, max_length=64)
    input_type: str = Field(min_length=1, max_length=64)
    raw_value: str | None = Field(default=None, max_length=500)
    step_id: str | None = Field(default=None, max_length=120)


class AIDialogSaveSelectionRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)


class AppBranchProfilePayload(BaseModel):
    branch_id: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=120)
    search_keywords: list[str] = Field(default_factory=list)
    blacklist_keywords: list[str] = Field(default_factory=list)
    reply_texts: list[str] = Field(default_factory=list)
    resource_namespace: str | None = Field(default=None, max_length=160)
    reply_ai_type: str | None = Field(default=None, max_length=64)
    payload_defaults: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=500)


class AppBranchProfilesUpdateRequest(BaseModel):
    default_branch: str | None = Field(default=None, max_length=64)
    branches: list[AppBranchProfilePayload] = Field(default_factory=list)


class AppConfigCandidateReviewRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    action: str = Field(default="promote", pattern="^(promote|reject)$")
