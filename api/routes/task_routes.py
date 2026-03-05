from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi import Response
from fastapi.responses import StreamingResponse

from core.task_control import get_task_controller
from engine.plugin_loader import PluginLoader
from models.task import TaskDetailResponse, TaskMetricsResponse, TaskRequest, TaskResponse, TaskStatus, TaskTarget, TaskType

router = APIRouter()


@router.get("/catalog")
def task_catalog():
    loader = PluginLoader()
    loader.scan()
    catalog: list[dict[str, object]] = []
    for name in loader.names:
        entry = loader.get(name)
        if entry is None:
            continue
        manifest = entry.manifest
        required = [x.name for x in manifest.inputs if x.required]
        defaults = {x.name: x.default for x in manifest.inputs if not x.required and x.default is not None}
        example_payload = dict(defaults)
        for field in required:
            example_payload.setdefault(field, f"<{field}>")
        catalog.append(
            {
                "task": manifest.name,
                "display_name": manifest.display_name,
                "required": required,
                "defaults": defaults,
                "example_payload": example_payload,
            }
        )
    return {"tasks": catalog}


def _to_task_response(record) -> TaskResponse:
    raw_targets = record.payload.get("_dispatch_targets") if isinstance(record.payload, dict) else []
    targets: list[TaskTarget] = []
    if isinstance(raw_targets, list):
        for item in raw_targets:
            if not isinstance(item, dict):
                continue
            try:
                targets.append(TaskTarget.model_validate(item))
            except Exception:
                continue

    return TaskResponse(
        task_id=record.task_id,
        task_type=TaskType.SCRIPT,
        task_name=str(record.payload.get("task") or "anonymous"),
        devices=record.devices,
        targets=targets,
        ai_type=record.ai_type,
        idempotency_key=record.idempotency_key,
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
    raw_targets = record.payload.get("_dispatch_targets") if isinstance(record.payload, dict) else []
    targets: list[TaskTarget] = []
    if isinstance(raw_targets, list):
        for item in raw_targets:
            if not isinstance(item, dict):
                continue
            try:
                targets.append(TaskTarget.model_validate(item))
            except Exception:
                continue

    return TaskDetailResponse(
        task_id=record.task_id,
        task_type=TaskType.SCRIPT,
        task_name=str(record.payload.get("task") or "anonymous"),
        devices=record.devices,
        targets=targets,
        ai_type=record.ai_type,
        idempotency_key=record.idempotency_key,
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
def create_task(request: TaskRequest, x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")):
    controller = get_task_controller()
    if request.idempotency_key and x_idempotency_key and request.idempotency_key != x_idempotency_key:
        raise HTTPException(status_code=400, detail="idempotency key mismatch between body and header")
    idempotency_key = request.idempotency_key or x_idempotency_key

    script_payload: dict[str, Any]
    if request.script is not None:
        script_payload = dict(request.script)
    else:
        script_payload = {"task": str(request.task or "anonymous")}
        if isinstance(request.payload, dict):
            script_payload.update(request.payload)

    targets: list[dict[str, int]] = []
    if request.targets:
        for target in request.targets:
            targets.append({"device_id": int(target.device_id), "cloud_id": int(target.cloud_id)})
    elif request.devices:
        for device_id in request.devices:
            targets.append({"device_id": int(device_id), "cloud_id": 1})

    if targets:
        script_payload["_dispatch_targets"] = targets

    device_ids = sorted({int(item["device_id"]) for item in targets}) if targets else list(request.devices)

    record = controller.submit_with_retry(
        payload=script_payload,
        devices=device_ids,
        ai_type=request.ai_type,
        max_retries=request.max_retries,
        retry_backoff_seconds=request.retry_backoff_seconds,
        priority=request.priority,
        run_at=request.run_at.isoformat() if request.run_at is not None else None,
        idempotency_key=idempotency_key,
    )
    return _to_task_response(record)


@router.get("/", response_model=list[TaskResponse])
def list_tasks(limit: int = Query(default=100, ge=1, le=500)):
    controller = get_task_controller()
    records = controller.list(limit=limit)
    return [_to_task_response(item) for item in records]


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
        final_wait_rounds = 0
        while True:
            events = controller.list_events(task_id=task_id, after_event_id=last, limit=200)
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
                final_events = controller.list_events(task_id=task_id, after_event_id=last, limit=200)
                if final_events:
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
                    final_wait_rounds = 0
                else:
                    final_wait_rounds += 1
                    if final_wait_rounds < 10:
                        time.sleep(0.05)
                        continue
                yield ": close\n\n"
                break
            time.sleep(0.5)

    return StreamingResponse(_stream(), media_type="text/event-stream")
