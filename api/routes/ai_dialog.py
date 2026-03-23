from __future__ import annotations

from anyio.to_thread import run_sync
from fastapi import APIRouter, HTTPException, Query

from core.ai_dialog_service import AIDialogService
from core.task_control import get_task_controller
from core.workflow_draft_store import WorkflowDraftStore
from core.workflow_drafts import WorkflowDraftService
from models.ai_dialog import (
    AIDialogHistoryItem,
    AIDialogPlannerRequest,
    AIDialogPlannerResponse,
)

router = APIRouter()


def _service() -> AIDialogService:
    controller = get_task_controller()
    workflow_drafts = WorkflowDraftService(
        store=WorkflowDraftStore(db_path=controller._store._db_path)
    )
    return AIDialogService(workflow_drafts=workflow_drafts)


@router.post("/planner", response_model=AIDialogPlannerResponse)
async def ai_dialog_planner(request: AIDialogPlannerRequest):
    service = _service()
    try:
        return await run_sync(
            lambda: service.plan(
                goal=request.goal,
                app_id=request.app_id,
                selected_account=request.selected_account,
                advanced_prompt=request.advanced_prompt,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/history", response_model=list[AIDialogHistoryItem])
async def ai_dialog_history(limit: int = Query(default=20, ge=1, le=100)):
    service = _service()
    return await run_sync(lambda: service.list_history(limit=limit))
