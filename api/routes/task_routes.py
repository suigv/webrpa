from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from api.mappers.task_mapper import to_task_detail_response, to_task_response
from anyio.to_thread import run_sync
from core.task_api_service import (
    get_task as get_task_record,
    stop_device_tasks as stop_device_tasks_service,
    stream_task_events,
)
from core.task_control import get_task_controller
from core.task_store import ManagedTaskStateClearBlocked
from models.task import TaskDetailResponse, TaskMetricsResponse, TaskRequest, TaskResponse, TaskStatus


router = APIRouter()


@router.post("/", response_model=TaskResponse)
async def create_task(request: TaskRequest, x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")):
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
        record = await run_sync(
            controller.submit_with_retry,
            script_payload,
            [int(device_id) for device_id in request.devices],
            [target.model_dump() for target in request.targets] if request.targets else None,
            request.ai_type,
            request.max_retries,
            request.retry_backoff_seconds,
            request.priority,
            request.run_at.isoformat() if request.run_at is not None else None,
            idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_task_response(record)


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(limit: int = Query(default=100, ge=1, le=500)):
    controller = get_task_controller()
    records = await run_sync(controller.list, limit)
    return [to_task_response(item) for item in records]


@router.delete("/")
async def clear_tasks():
    controller = get_task_controller()
    try:
        await run_sync(controller.clear_all)
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


# 蒸馏门槛定义（与 docs/STATUS.md 保持一致）
_DISTILL_THRESHOLDS: dict[str, int] = {
    "device_reboot": 3,
    "device_soft_reset": 3,
    "hezi_sdk_probe": 3,
    "mytos_device_setup": 3,
}


@router.get("/metrics/plugins")
async def plugin_success_metrics():
    controller = get_task_controller()
    rows = await run_sync(controller._store.plugin_success_counts)
    result = []
    for r in rows:
        name = str(r["task_name"])
        completed = int(r["completed"])
        threshold = _DISTILL_THRESHOLDS.get(name, 3)
        result.append({
            **r,
            "distill_threshold": threshold,
            "distill_ready": completed >= threshold,
            "distill_remaining": max(0, threshold - completed),
        })
    return result


@router.post("/distill/{plugin_name}")
async def distill_plugin(plugin_name: str, force: bool = False):
    """触发指定插件的多轮蒸馏，生成 YAML 插件草稿。"""
    import subprocess
    import sys
    from pathlib import Path
    controller = get_task_controller()
    rows = await run_sync(controller._store.plugin_success_counts)
    stat = next((r for r in rows if r["task_name"] == plugin_name), None)
    completed = int(stat["completed"]) if stat else 0
    threshold = _DISTILL_THRESHOLDS.get(plugin_name, 3)

    if not force and completed < threshold:
        return {
            "ok": False,
            "code": "threshold_not_met",
            "message": f"插件 {plugin_name} 成功次数 {completed} 未达到蒸馏门槛 {threshold}",
            "completed": completed,
            "threshold": threshold,
        }

    script = Path(__file__).resolve().parents[2] / "tools" / "distill_multi_run.py"
    output_dir = Path(__file__).resolve().parents[2] / "plugins" / f"{plugin_name}_distilled"
    cmd = [sys.executable, str(script), "--plugin", plugin_name, "--output-dir", str(output_dir)]
    if force:
        cmd.append("--force")

    def _run():
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode, result.stdout, result.stderr

    code, stdout, stderr = await run_sync(_run)
    return {
        "ok": code == 0,
        "plugin_name": plugin_name,
        "output_dir": str(output_dir),
        "completed_runs": completed,
        "threshold": threshold,
        "stdout": stdout,
        "stderr": stderr,
    }


@router.get("/metrics", response_model=TaskMetricsResponse)
async def task_metrics(
    window_seconds: int = Query(default=3600, ge=0, le=7 * 24 * 3600),
    failure_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    cancellation_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    min_terminal_samples: int = Query(default=20, ge=1, le=100000),
):
    controller = get_task_controller()
    return await run_sync(
        controller.task_metrics,
        window_seconds,
        failure_rate_threshold,
        cancellation_rate_threshold,
        min_terminal_samples,
    )


@router.get("/metrics/prometheus")
async def task_metrics_prometheus(
    window_seconds: int = Query(default=3600, ge=0, le=7 * 24 * 3600),
    failure_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    cancellation_rate_threshold: float = Query(default=0.2, ge=0.0, le=1.0),
    min_terminal_samples: int = Query(default=20, ge=1, le=100000),
):
    controller = get_task_controller()
    payload = await run_sync(
        controller.task_metrics_prometheus,
        window_seconds,
        failure_rate_threshold,
        cancellation_rate_threshold,
        min_terminal_samples,
    )
    return Response(content=payload, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: str):
    controller = get_task_controller()
    record = await run_sync(controller.get, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return to_task_detail_response(record)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    controller = get_task_controller()
    record = await run_sync(controller.get, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    if record.status in {TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value}:
        return {"task_id": task_id, "status": record.status, "cancelled": False}

    state = await run_sync(controller.cancel_state, task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {"task_id": task_id, "status": state, "cancel_state": state, "cancelled": True}


@router.post("/device/{device_id}/stop")
async def stop_device_tasks(device_id: int):
    """停止指定设备上所有正在运行的任务。"""
    cancelled_count, task_ids = await stop_device_tasks_service(device_id)
    return {
        "status": "ok",
        "device_id": device_id,
        "cancelled_count": cancelled_count,
        "active_tasks": task_ids,
    }


@router.get("/{task_id}/events")
async def task_events(task_id: str, after_event_id: int = Query(default=0, ge=0)):
    record = await get_task_record(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return StreamingResponse(stream_task_events(task_id, after_event_id), media_type="text/event-stream")
