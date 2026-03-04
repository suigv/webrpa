from __future__ import annotations

import json
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from new.core.task_events import TaskEventStore
from new.core.task_control import get_task_controller
from new.models.task import TaskDetailResponse, TaskRequest, TaskResponse, TaskStatus, TaskType

router = APIRouter()
event_store = TaskEventStore()


def _to_task_response(record) -> TaskResponse:
    return TaskResponse(
        task_id=record.task_id,
        task_type=TaskType.SCRIPT,
        devices=record.devices,
        ai_type=record.ai_type,
        status=TaskStatus(record.status),
        created_at=record.created_at,
        retry_count=record.retry_count,
        max_retries=record.max_retries,
        retry_backoff_seconds=record.retry_backoff_seconds,
        next_retry_at=record.next_retry_at,
        priority=record.priority,
        run_at=record.run_at,
    )


def _to_task_detail(record) -> TaskDetailResponse:
    return TaskDetailResponse(
        task_id=record.task_id,
        task_type=TaskType.SCRIPT,
        devices=record.devices,
        ai_type=record.ai_type,
        status=TaskStatus(record.status),
        created_at=record.created_at,
        retry_count=record.retry_count,
        max_retries=record.max_retries,
        retry_backoff_seconds=record.retry_backoff_seconds,
        next_retry_at=record.next_retry_at,
        priority=record.priority,
        run_at=record.run_at,
        result=record.result,
        error=record.error,
    )


@router.post("/", response_model=TaskResponse)
def create_task(request: TaskRequest):
    controller = get_task_controller()
    record = controller.submit_with_retry(
        payload=request.script,
        devices=list(request.devices),
        ai_type=request.ai_type,
        max_retries=request.max_retries,
        retry_backoff_seconds=request.retry_backoff_seconds,
        priority=request.priority,
        run_at=request.run_at.isoformat() if request.run_at is not None else None,
    )
    return _to_task_response(record)


@router.get("/", response_model=list[TaskResponse])
def list_tasks(limit: int = Query(default=100, ge=1, le=500)):
    controller = get_task_controller()
    records = controller.list(limit=limit)
    return [_to_task_response(item) for item in records]


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task(task_id: str):
    controller = get_task_controller()
    record = controller.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _to_task_detail(record)


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str):
    controller = get_task_controller()
    record = controller.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    if record.status in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
        return {"task_id": task_id, "status": record.status, "cancelled": False}

    state = controller.cancel_state(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")

    cancelled = state in {"cancelled", "cancelling"}
    latest = controller.get(task_id)
    status = latest.status if latest is not None else TaskStatus.CANCELLED.value
    return {"task_id": task_id, "status": status, "cancelled": cancelled, "cancel_state": state}


@router.get("/{task_id}/events")
def task_events(task_id: str, after_event_id: int = Query(default=0, ge=0)):
    controller = get_task_controller()
    record = controller.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    def _stream():
        last = int(after_event_id)
        while True:
            events = event_store.list_events(task_id=task_id, after_event_id=last, limit=200)
            if events:
                for ev in events:
                    last = ev.event_id
                    payload = {
                        "event_id": ev.event_id,
                        "task_id": ev.task_id,
                        "event_type": ev.event_type,
                        "payload": ev.payload,
                        "created_at": ev.created_at,
                    }
                    yield f"id: {ev.event_id}\nevent: {ev.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            latest = controller.get(task_id)
            if latest is None:
                break
            if latest.status in {
                TaskStatus.COMPLETED.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            }:
                final_events = event_store.list_events(task_id=task_id, after_event_id=last, limit=200)
                for ev in final_events:
                    last = ev.event_id
                    payload = {
                        "event_id": ev.event_id,
                        "task_id": ev.task_id,
                        "event_type": ev.event_type,
                        "payload": ev.payload,
                        "created_at": ev.created_at,
                    }
                    yield f"id: {ev.event_id}\nevent: {ev.event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                yield ": close\n\n"
                break
            time.sleep(0.5)

    return StreamingResponse(_stream(), media_type="text/event-stream")
