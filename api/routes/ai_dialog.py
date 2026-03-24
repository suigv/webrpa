from __future__ import annotations

from anyio.to_thread import run_sync
from fastapi import APIRouter, HTTPException, Query

from core.ai_dialog_save_service import AIDialogSaveService
from core.ai_dialog_service import AIDialogService
from core.task_control import get_task_controller
from core.workflow_draft_store import WorkflowDraftStore
from core.workflow_drafts import WorkflowDraftService
from models.ai_dialog import (
    AIDialogHistoryItem,
    AIDialogPlannerRequest,
    AIDialogPlannerResponse,
    AIDialogSaveSelectionRequest,
    AITaskAnnotationRequest,
)

router = APIRouter()


def _service() -> AIDialogService:
    controller = get_task_controller()
    workflow_drafts = WorkflowDraftService(
        store=WorkflowDraftStore(db_path=controller._store._db_path)
    )
    return AIDialogService(workflow_drafts=workflow_drafts)


def _save_service() -> AIDialogSaveService:
    controller = get_task_controller()
    workflow_drafts = WorkflowDraftService(
        store=WorkflowDraftStore(db_path=controller._store._db_path)
    )
    return AIDialogSaveService(workflow_drafts=workflow_drafts)


@router.post("/planner", response_model=AIDialogPlannerResponse)
async def ai_dialog_planner(request: AIDialogPlannerRequest):
    service = _service()
    try:
        return await run_sync(
            lambda: service.plan(
                goal=request.goal,
                app_id=request.app_id,
                app_display_name=request.app_display_name,
                package_name=request.package_name,
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


@router.post("/annotations")
async def create_ai_task_annotation(request: AITaskAnnotationRequest):
    service = _save_service()
    return await run_sync(
        lambda: service.create_annotation(
            task_id=request.task_id,
            input_type=request.input_type,
            raw_value=request.raw_value,
            step_id=request.step_id,
        )
    )


@router.get("/tasks/{task_id}/annotations")
async def list_ai_task_annotations(task_id: str):
    service = _save_service()
    return await run_sync(lambda: service.list_annotations(task_id))


@router.get("/drafts/{draft_id}/save_candidates")
async def ai_dialog_save_candidates(draft_id: str):
    service = _save_service()
    try:
        return await run_sync(lambda: service.list_save_candidates(draft_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/drafts/{draft_id}/save_choices")
async def ai_dialog_save_choices(draft_id: str, request: AIDialogSaveSelectionRequest):
    service = _save_service()
    try:
        return await run_sync(lambda: service.apply_save_choices(draft_id, request.candidate_ids))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
