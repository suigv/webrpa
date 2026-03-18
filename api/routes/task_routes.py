from __future__ import annotations

import re
from typing import Any

from anyio.to_thread import run_sync
from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse

from api.mappers.task_mapper import to_task_detail_response, to_task_response
from core.task_api_service import (
    get_task as get_task_record,
)
from core.task_api_service import (
    stop_device_tasks as stop_device_tasks_service,
)
from core.task_api_service import (
    stream_task_events,
)
from core.task_control import get_task_controller
from core.task_store import ManagedTaskStateClearBlockedError
from models.task import (
    TaskDetailResponse,
    TaskMetricsResponse,
    TaskRequest,
    TaskResponse,
    TaskStatus,
    WorkflowDraftContinueRequest,
    WorkflowDraftDistillRequest,
    WorkflowDraftSummary,
)

router = APIRouter()

_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _validate_plugin_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="plugin_name is required")
    if "/" in raw or "\\" in raw or ".." in raw:
        raise HTTPException(status_code=400, detail="invalid plugin_name")
    if _PLUGIN_NAME_RE.fullmatch(raw) is None:
        raise HTTPException(status_code=400, detail="invalid plugin_name")
    return raw


def _distill_threshold_for(task_name: str) -> int:
    from engine.plugin_loader import get_shared_plugin_loader

    loader = get_shared_plugin_loader()
    entry = loader.get(task_name)
    if entry is None:
        return 3
    try:
        return int(entry.manifest.distill_threshold)
    except Exception:
        return 3


def _task_response_for(controller: Any, record: Any) -> TaskResponse:
    workflow_draft = controller.workflow_draft_summary_for_task(record)
    return to_task_response(record, workflow_draft=workflow_draft)


def _task_detail_response_for(controller: Any, record: Any) -> TaskDetailResponse:
    workflow_draft = controller.workflow_draft_summary_for_task(record)
    return to_task_detail_response(record, workflow_draft=workflow_draft)


@router.post("/", response_model=TaskResponse)
async def create_task(
    request: TaskRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    controller = get_task_controller()
    if (
        request.idempotency_key
        and x_idempotency_key
        and request.idempotency_key != x_idempotency_key
    ):
        raise HTTPException(
            status_code=400, detail="idempotency key mismatch between body and header"
        )
    idempotency_key = request.idempotency_key or x_idempotency_key

    if request.script is not None:
        script_payload: dict[str, Any] = dict(request.script)
    else:
        script_payload = {"task": str(request.task or "anonymous")}
        if isinstance(request.payload, dict):
            script_payload.update(request.payload)

    try:
        record = await run_sync(
            lambda: controller.submit_with_retry(
                script_payload,
                [int(device_id) for device_id in request.devices],
                [target.model_dump() for target in request.targets] if request.targets else None,
                request.ai_type,
                request.max_retries,
                request.retry_backoff_seconds,
                request.priority,
                request.run_at.isoformat() if request.run_at is not None else None,
                idempotency_key,
                display_name=request.display_name,
                draft_id=request.draft_id,
                success_threshold=request.success_threshold,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _task_response_for(controller, record)


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(limit: int = Query(default=100, ge=1, le=500)):
    controller = get_task_controller()
    records = await run_sync(controller.list, limit)
    return [_task_response_for(controller, item) for item in records]


async def _cleanup_failed_tasks_response() -> dict[str, object]:
    """清理所有已停止但未成功的任务轨迹与记录。"""
    controller = get_task_controller()
    count = await run_sync(controller.cleanup_failed_tasks)
    return {
        "status": "ok",
        "count": count,
        "message": f"Successfully cleaned up {count} failed tasks",
    }


@router.delete("/cleanup_failed")
async def cleanup_failed_tasks_delete():
    return await _cleanup_failed_tasks_response()


@router.post("/cleanup_failed")
async def cleanup_failed_tasks_post():
    return await _cleanup_failed_tasks_response()


@router.delete("/")
async def clear_tasks():
    controller = get_task_controller()
    try:
        await run_sync(controller.clear_all)
    except ManagedTaskStateClearBlockedError as exc:
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
        defaults = {
            item.name: item.default
            for item in manifest.inputs
            if not item.required and item.default is not None
        }
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


@router.get("/catalog/apps")
def list_apps():
    """列出 config/apps/ 目录下所有已定义的应用程序。"""
    import yaml

    from core.paths import config_dir

    apps_dir = config_dir() / "apps"
    if not apps_dir.exists():
        return {"apps": []}

    apps = []
    # 始终包含默认选项
    apps.append({"id": "default", "name": "默认 (系统)"})

    for f in apps_dir.glob("*.yaml"):
        app_id = f.stem
        if app_id == "default":
            continue
        try:
            with open(f, encoding="utf-8") as stream:
                data = yaml.safe_load(stream)
                # 尝试从配置中获取友好名称，如果没有则使用 ID
                display_name = data.get("name") or data.get("display_name") or app_id.upper()
                apps.append({"id": app_id, "name": display_name})
        except Exception:
            apps.append({"id": app_id, "name": app_id.upper()})

    return {"apps": apps}


@router.get("/prompt_templates")
def list_prompt_templates():
    from engine.prompt_templates import get_prompt_templates

    return {"templates": get_prompt_templates()}


@router.get("/metrics/plugins")
async def plugin_success_metrics():
    controller = get_task_controller()
    rows = await run_sync(controller.plugin_success_counts)
    result = []
    for r in rows:
        name = str(r["task_name"])
        completed = int(r["completed"])
        threshold = _distill_threshold_for(name)
        result.append(
            {
                **r,
                "distill_threshold": threshold,
                "distill_ready": completed >= threshold,
                "distill_remaining": max(0, threshold - completed),
            }
        )
    return result


@router.get("/drafts", response_model=list[WorkflowDraftSummary])
async def list_workflow_drafts(limit: int = Query(default=100, ge=1, le=500)):
    controller = get_task_controller()
    return await run_sync(controller.list_workflow_drafts, limit)


@router.get("/drafts/{draft_id}", response_model=WorkflowDraftSummary)
async def get_workflow_draft(draft_id: str):
    controller = get_task_controller()
    summary = await run_sync(controller.workflow_draft_summary, draft_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="workflow draft not found")
    return summary


@router.post("/drafts/{draft_id}/continue", response_model=list[TaskResponse])
async def continue_workflow_draft(
    draft_id: str,
    request: WorkflowDraftContinueRequest | None = None,
):
    controller = get_task_controller()
    try:
        records = await run_sync(
            controller.continue_workflow_draft,
            draft_id,
            request.count if request is not None else 1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_task_response_for(controller, item) for item in records]


@router.post("/drafts/{draft_id}/distill")
async def distill_workflow_draft(
    draft_id: str,
    request: WorkflowDraftDistillRequest | None = None,
):
    controller = get_task_controller()
    try:
        return await run_sync(
            lambda: controller.distill_workflow_draft(
                draft_id,
                plugin_name=request.plugin_name if request is not None else None,
                force=request.force if request is not None else False,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/distill/{plugin_name}")
async def distill_plugin(plugin_name: str, force: bool = False):
    """触发指定插件的多轮蒸馏，生成 YAML 插件草稿。"""
    import subprocess
    import sys

    from core.paths import project_root
    from engine.plugin_loader import get_shared_plugin_loader

    plugin_name = _validate_plugin_name(plugin_name)
    loader = get_shared_plugin_loader(refresh=True)
    entry = loader.get(plugin_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"plugin not found: {plugin_name}")
    controller = get_task_controller()
    rows = await run_sync(controller.plugin_success_counts)
    stat = next((r for r in rows if r["task_name"] == plugin_name), None)
    completed = int(stat["completed"]) if stat else 0
    threshold = int(entry.manifest.distill_threshold or 3)

    if not force and completed < threshold:
        return {
            "ok": False,
            "code": "threshold_not_met",
            "message": f"插件 {plugin_name} 成功次数 {completed} 未达到蒸馏门槛 {threshold}",
            "completed": completed,
            "threshold": threshold,
        }

    repo_root = project_root()
    script = repo_root / "tools" / "distill_multi_run.py"
    plugins_root = (repo_root / "plugins").resolve()
    output_dir = (plugins_root / f"{plugin_name}_distilled").resolve()
    if plugins_root not in output_dir.parents:
        raise HTTPException(status_code=400, detail="invalid output_dir")
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
    return _task_detail_response_for(controller, record)


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    controller = get_task_controller()
    record = await run_sync(controller.get, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    if record.status in {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    }:
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
    return StreamingResponse(
        stream_task_events(task_id, after_event_id), media_type="text/event-stream"
    )
