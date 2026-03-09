from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from api.mappers.task_mapper import to_task_detail_response, to_task_response
from core.task_control import get_task_controller
from core.task_store import ManagedTaskStateClearBlocked
from models.task import TaskDetailResponse, TaskMetricsResponse, TaskRequest, TaskResponse, TaskStatus


router = APIRouter()


@router.post("/", response_model=TaskResponse)
def create_task(request: TaskRequest, x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")):
    controller = get_task_controller()
    if request.idempotency_key and x_idempotency_key and request.idempotency_key != x_idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency key mismatch between body and header")
    idempotency_key = request.idempotency_key or x_idempotency_key

    if request.script is not None:
        script_payload: dict[str, Any] = dict(request.script)
    else:
        script_payload = {"task": str(request.task or "anonymous")}
        if isinstance(request.payload, dict):
            script_payload.update(request.payload)

    try:
        record = controller.submit_with_retry(
            payload=script_payload,
            devices=[int(device_id) for device_id in request.devices],
            targets=[target.model_dump() for target in request.targets] if request.targets else None,
            ai_type=request.ai_type,
            max_retries=request.max_retries,
            retry_backoff_seconds=request.retry_backoff_seconds,
            priority=request.priority,
            run_at=request.run_at.isoformat() if request.run_at is not None else None,
            idempotency_key=idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_task_response(record)


@router.get("/", response_model=list[TaskResponse])
def list_tasks(limit: int = Query(default=100, ge=1, le=500)):
    controller = get_task_controller()
    return [to_task_response(item) for item in controller.list(limit=limit)]


@router.delete("/")
def clear_tasks():
    controller = get_task_controller()
    try:
        controller.clear_all()
    except ManagedTaskStateClearBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok", "message": "managed task state cleared"}


@router.get("/catalog")
def task_catalog():
    from engine.plugin_loader import get_shared_plugin_loader

    loader = get_shared_plugin_loader(refresh=True)
    catalog: list[dict[str, object]] = []
    for name in loader.names:
        entry = loader.get(name)
        if entry is None:
            continue
        manifest = entry.manifest
        required = [item.name for item in manifest.inputs if item.required]
        defaults = {item.name: item.default for item in manifest.inputs if not item.required and item.default is not None}
        example_payload = dict(defaults)
        for field in required:
            example_payload.setdefault(field, f"<{field}>")
        catalog.append(
            {
                "task": manifest.name,
                "display_name": manifest.display_name,
                "category": manifest.category,
                "required": required,
                "defaults": defaults,
                "example_payload": example_payload,
            }
        )
    return {"tasks": catalog}


@router.get("/metrics", response_model=TaskMetricsResponse)
def task_metrics(
    window_seconds: int = Query(default=3600, ge=0, le=7 * 24 * 3600),
    failure_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    cancellation_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    min_terminal_samples: int = Query(default=20, ge=1, le=100000),
):
    controller = get_task_controller()
    return controller.task_metrics(
        window_seconds=window_seconds,
        failure_rate_threshold=failure_rate_threshold,
        cancellation_rate_threshold=cancellation_rate_threshold,
        min_terminal_samples=min_terminal_samples,
    )


@router.get("/metrics/prometheus")
def task_metrics_prometheus(
    window_seconds: int = Query(default=3600, ge=0, le=7 * 24 * 3600),
    failure_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    cancellation_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    min_terminal_samples: int = Query(default=20, ge=1, le=100000),
):
    controller = get_task_controller()
    payload = controller.task_metrics_prometheus(
        window_seconds=window_seconds,
        failure_rate_threshold=failure_rate_threshold,
        cancellation_rate_threshold=cancellation_rate_threshold,
        min_terminal_samples=min_terminal_samples,
    )
    return Response(content=payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task(task_id: str):
    controller = get_task_controller()
    record = controller.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return to_task_detail_response(record)


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
    return {"task_id": task_id, "status": state, "cancel_state": state, "cancelled": True}


@router.get("/{task_id}/events")
def task_events(task_id: str, after_event_id: int = Query(default=0, ge=0)):
    controller = get_task_controller()
    record = controller.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")

    def _stream():
        cursor = after_event_id
        while True:
            events = controller.list_events(task_id=task_id, after_event_id=cursor)
            for event in events:
                yield f"id: {event.event_id}\nevent: {event.event_type}\ndata: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
                cursor = event.event_id

            latest = controller.get(task_id)
            if latest and latest.status in ("completed", "failed", "cancelled"):
                final_events = controller.list_events(task_id=task_id, after_event_id=cursor)
                for event in final_events:
                    yield f"id: {event.event_id}\nevent: {event.event_type}\ndata: {json.dumps(event.payload, ensure_ascii=False)}\n\n"
                yield ": close\n\n"
                break
            time.sleep(0.5)

    return StreamingResponse(_stream(), media_type="text/event-stream")
