from __future__ import annotations

import re
from collections.abc import Mapping
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
    TaskControlRequest,
    TaskDetailResponse,
    TaskMetricsResponse,
    TaskRequest,
    TaskResponse,
    TaskStatus,
    WorkflowDraftContinueRequest,
    WorkflowDraftDistillRequest,
    WorkflowDraftSnapshotResponse,
    WorkflowDraftSummary,
)

router = APIRouter()

_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _pipeline_catalog_entry() -> dict[str, object]:
    return {
        "task": "_pipeline",
        "display_name": "Pipeline 编排",
        "category": "系统编排",
        "description": "按顺序串联多个插件任务，支持重复执行与轮次间等待。",
        "distillable": False,
        "visible_in_task_catalog": True,
        "required": ["steps"],
        "defaults": {"repeat": 1, "repeat_interval_ms": 0, "branch_id": "default"},
        "example_payload": {
            "steps": [
                {"plugin": "x_scrape_blogger", "payload": {}},
                {"plugin": "x_clone_profile", "payload": {}},
            ],
            "repeat": 1,
            "repeat_interval_ms": 0,
            "branch_id": "default",
        },
        "inputs": [
            {
                "name": "steps",
                "type": "string",
                "required": True,
                "default": None,
                "label": "Pipeline Steps",
                "description": "Ordered pipeline step definitions.",
                "placeholder": None,
                "advanced": False,
                "system": True,
                "widget": "hidden",
                "options": [],
            },
            {
                "name": "branch_id",
                "type": "string",
                "required": False,
                "default": "default",
                "label": "业务分支",
                "description": "整条 Pipeline 共用一个业务分支，子步骤不允许覆盖。",
                "placeholder": "例如 default / volc / part_time",
                "advanced": False,
                "system": False,
                "widget": "text",
                "options": [],
            },
            {
                "name": "accepted_account_tags",
                "type": "string",
                "required": False,
                "default": "",
                "label": "账号标签要求",
                "description": "多个标签用英文逗号分隔，命中任一标签即可。",
                "placeholder": "例如 warmup, dating",
                "advanced": True,
                "system": False,
                "widget": "text",
                "options": [],
            },
            {
                "name": "resource_namespace",
                "type": "string",
                "required": False,
                "default": "",
                "label": "资源池命名空间",
                "description": "留空时默认使用当前草稿或应用分支隔离。",
                "placeholder": "可选，自定义资源池",
                "advanced": True,
                "system": False,
                "widget": "text",
                "options": [],
            },
            {
                "name": "repeat",
                "type": "integer",
                "required": False,
                "default": 1,
                "label": "重复轮次",
                "description": "0 表示无限循环直到取消。",
                "placeholder": None,
                "advanced": False,
                "system": False,
                "widget": "number",
                "options": [],
            },
            {
                "name": "repeat_interval_ms",
                "type": "integer",
                "required": False,
                "default": 0,
                "label": "轮次等待 (ms)",
                "description": "每轮 pipeline 之间的等待时间。",
                "placeholder": None,
                "advanced": True,
                "system": False,
                "widget": "number",
                "options": [],
            },
        ],
    }


def _plugin_loader(*, refresh: bool = False):
    from engine.plugin_loader import clear_shared_plugin_loader_cache, get_shared_plugin_loader

    if refresh:
        clear_shared_plugin_loader_cache()
    return get_shared_plugin_loader()


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
    loader = _plugin_loader()
    entry = loader.get(task_name)
    if entry is None:
        return 3
    try:
        return int(entry.manifest.distill_threshold)
    except Exception:
        return 3


def _plugin_distillable(task_name: str) -> bool:
    loader = _plugin_loader()
    entry = loader.get(task_name)
    if entry is None:
        return True
    try:
        return bool(entry.manifest.distillable)
    except Exception:
        return True


def _plugin_visible_in_task_catalog(task_name: str) -> bool:
    loader = _plugin_loader()
    entry = loader.get(task_name)
    if entry is None:
        return True
    try:
        return bool(entry.manifest.visible_in_task_catalog)
    except Exception:
        return True


def _task_response_for(controller: Any, record: Any) -> TaskResponse:
    workflow_draft = controller.workflow_draft_summary_for_task(record)
    return to_task_response(record, workflow_draft=workflow_draft)


def _task_detail_response_for(controller: Any, record: Any) -> TaskDetailResponse:
    workflow_draft = controller.workflow_draft_summary_for_task(record)
    return to_task_detail_response(record, workflow_draft=workflow_draft)


def _reconcile_idempotency_key(
    request: TaskRequest,
    header_idempotency_key: str | None,
) -> str | None:
    body_idempotency_key = request.idempotency_key
    if (
        body_idempotency_key
        and header_idempotency_key
        and body_idempotency_key != header_idempotency_key
    ):
        raise HTTPException(
            status_code=400, detail="idempotency key mismatch between body and header"
        )
    return body_idempotency_key or header_idempotency_key


def _script_payload_for_task_request(request: TaskRequest) -> dict[str, Any]:
    if request.script is not None:
        return dict(request.script)

    script_payload: dict[str, Any] = {"task": str(request.task or "anonymous")}
    script_payload.update(request.payload)
    return script_payload


def _distillability_payload(plugin_name: str) -> dict[str, Any] | None:
    if _plugin_distillable(plugin_name):
        return None
    return {
        "ok": False,
        "code": "distillation_not_supported",
        "message": (
            f"插件 {plugin_name} 不支持蒸馏；它属于初始化/编排类流程，应保留为参数化插件。"
        ),
        "plugin_name": plugin_name,
    }


def _distill_threshold_payload(
    *,
    plugin_name: str,
    completed: int,
    threshold: int,
    force: bool,
) -> dict[str, Any] | None:
    if force or completed >= threshold:
        return None
    return {
        "ok": False,
        "code": "threshold_not_met",
        "message": f"插件 {plugin_name} 成功次数 {completed} 未达到蒸馏门槛 {threshold}",
        "completed": completed,
        "threshold": threshold,
    }


def _plugin_success_completed(row: Mapping[str, object] | None) -> int:
    if row is None:
        return 0
    completed = row.get("completed", 0)
    if isinstance(completed, bool):
        return int(completed)
    if isinstance(completed, int):
        return completed
    if isinstance(completed, str):
        return int(completed)
    raise TypeError("plugin success row completed must be int-compatible")


def _plugin_success_metrics_row(row: Mapping[str, object]) -> dict[str, object]:
    name = str(row["task_name"])
    completed = _plugin_success_completed(row)
    distillable = _plugin_distillable(name)
    threshold = _distill_threshold_for(name)
    return {
        **dict(row),
        "distillable": distillable,
        "visible_in_task_catalog": _plugin_visible_in_task_catalog(name),
        "distill_threshold": threshold,
        "distill_ready": distillable and completed >= threshold,
        "distill_remaining": max(0, threshold - completed),
    }


async def _distill_plugin_response(plugin_name: str, force: bool) -> dict[str, Any]:
    import subprocess
    import sys

    from core.paths import project_root

    plugin_name = _validate_plugin_name(plugin_name)
    loader = _plugin_loader(refresh=True)
    entry = loader.get(plugin_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"plugin not found: {plugin_name}")

    distillability_payload = _distillability_payload(plugin_name)
    if distillability_payload is not None:
        return distillability_payload

    controller = get_task_controller()
    rows = await run_sync(controller.plugin_success_counts)
    stat = next((r for r in rows if r["task_name"] == plugin_name), None)
    completed = _plugin_success_completed(stat)
    threshold = int(entry.manifest.distill_threshold or 3)

    threshold_payload = _distill_threshold_payload(
        plugin_name=plugin_name,
        completed=completed,
        threshold=threshold,
        force=force,
    )
    if threshold_payload is not None:
        return threshold_payload

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
    if code == 0:
        from engine.plugin_loader import clear_shared_plugin_loader_cache

        clear_shared_plugin_loader_cache()
    return {
        "ok": code == 0,
        "plugin_name": plugin_name,
        "output_dir": str(output_dir),
        "completed_runs": completed,
        "threshold": threshold,
        "stdout": stdout,
        "stderr": stderr,
    }


@router.post("/", response_model=TaskResponse)
async def create_task(
    request: TaskRequest,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    controller = get_task_controller()
    maybe_start = getattr(controller, "ensure_started_if_enabled", None)
    if callable(maybe_start):
        await run_sync(maybe_start)
    idempotency_key = _reconcile_idempotency_key(request, x_idempotency_key)
    script_payload = _script_payload_for_task_request(request)

    try:
        record = await run_sync(
            lambda: controller.submit_with_retry(
                **request.controller_submission_kwargs(
                    script_payload=script_payload,
                    idempotency_key=idempotency_key,
                )
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


@router.get("/active", response_model=TaskResponse)
async def get_active_task_for_target(
    device_id: int = Query(ge=1),
    cloud_id: int = Query(ge=1),
    task_name: str | None = Query(default=None, min_length=1),
):
    controller = get_task_controller()
    record = await run_sync(
        lambda: controller.find_active_task_for_target(
            device_id,
            cloud_id,
            task_name=task_name,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="active task not found")
    return _task_response_for(controller, record)


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


async def _cleanup_runtime_artifacts_response(
    *,
    hidden_task_retention_days: int | None = None,
    event_retention_days: int | None = None,
    trace_retention_days: int | None = None,
    max_event_rows: int | None = None,
    max_trace_bytes: int | None = None,
) -> dict[str, object]:
    controller = get_task_controller()
    result = await run_sync(
        lambda: controller.cleanup_runtime_artifacts(
            hidden_task_retention_days=hidden_task_retention_days,
            event_retention_days=event_retention_days,
            trace_retention_days=trace_retention_days,
            max_event_rows=max_event_rows,
            max_trace_bytes=max_trace_bytes,
        )
    )
    return {"status": "ok", **result}


@router.post("/cleanup_runtime")
async def cleanup_runtime_artifacts_post(
    hidden_task_retention_days: int | None = Query(default=None, ge=0),
    event_retention_days: int | None = Query(default=None, ge=0),
    trace_retention_days: int | None = Query(default=None, ge=0),
    max_event_rows: int | None = Query(default=None, ge=0),
    max_trace_bytes: int | None = Query(default=None, ge=0),
):
    return await _cleanup_runtime_artifacts_response(
        hidden_task_retention_days=hidden_task_retention_days,
        event_retention_days=event_retention_days,
        trace_retention_days=trace_retention_days,
        max_event_rows=max_event_rows,
        max_trace_bytes=max_trace_bytes,
    )


@router.delete("/cleanup_runtime")
async def cleanup_runtime_artifacts_delete(
    hidden_task_retention_days: int | None = Query(default=None, ge=0),
    event_retention_days: int | None = Query(default=None, ge=0),
    trace_retention_days: int | None = Query(default=None, ge=0),
    max_event_rows: int | None = Query(default=None, ge=0),
    max_trace_bytes: int | None = Query(default=None, ge=0),
):
    return await _cleanup_runtime_artifacts_response(
        hidden_task_retention_days=hidden_task_retention_days,
        event_retention_days=event_retention_days,
        trace_retention_days=trace_retention_days,
        max_event_rows=max_event_rows,
        max_trace_bytes=max_trace_bytes,
    )


@router.delete("/")
async def clear_tasks():
    controller = get_task_controller()
    try:
        await run_sync(controller.clear_all)
    except ManagedTaskStateClearBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "ok", "message": "managed task state cleared"}


@router.get("/catalog")
def task_catalog(include_hidden: bool = Query(default=False)):
    from engine.plugin_loader import clear_shared_plugin_loader_cache, get_shared_plugin_loader

    clear_shared_plugin_loader_cache()
    loader = get_shared_plugin_loader()
    catalog: list[dict[str, object]] = [_pipeline_catalog_entry()]
    for name in loader.names:
        entry = loader.get(name)
        if entry is None:
            continue
        manifest = entry.manifest
        if not include_hidden and not bool(manifest.visible_in_task_catalog):
            continue
        required = [item.name for item in manifest.inputs if item.required]
        defaults = {
            item.name: item.default
            for item in manifest.inputs
            if not item.required and item.default is not None
        }
        example_payload = dict(defaults)
        rendered_inputs: list[dict[str, object]] = []
        for item in manifest.inputs:
            option_payloads = [
                {
                    "value": option.value,
                    "label": option.label,
                    "description": option.description,
                }
                for option in item.options
            ]
            if item.default is not None:
                example_value = item.default
            elif option_payloads:
                example_value = option_payloads[0]["value"] if item.required else None
            elif item.required:
                example_value = f"<{item.name}>"
            else:
                example_value = None
            if example_value is not None:
                example_payload.setdefault(item.name, example_value)
            rendered_inputs.append(
                {
                    "name": item.name,
                    "type": item.type.value,
                    "required": item.required,
                    "default": item.default,
                    "label": item.label or item.name,
                    "description": item.description,
                    "placeholder": item.placeholder,
                    "advanced": item.advanced,
                    "system": item.system,
                    "widget": item.widget.value if item.widget is not None else None,
                    "options": option_payloads,
                }
            )
        catalog.append(
            {
                "task": manifest.name,
                "display_name": manifest.display_name,
                "category": manifest.category,
                "description": manifest.description,
                "distillable": bool(manifest.distillable),
                "visible_in_task_catalog": bool(manifest.visible_in_task_catalog),
                "required": required,
                "defaults": defaults,
                "example_payload": example_payload,
                "inputs": rendered_inputs,
            }
        )
    return {"tasks": catalog}


@router.get("/catalog/apps")
def list_apps():
    """列出 config/apps/ 目录下所有已定义的应用程序。"""
    from core.app_config import AppConfigManager

    apps = []
    for item in AppConfigManager.list_apps(include_default=True):
        app_id = str(item.get("app_id") or "").strip()
        if not app_id:
            continue
        display_name = str(item.get("display_name") or app_id.upper()).strip()
        package_names = list(item.get("package_names") or [])
        apps.append(
            {
                "id": app_id,
                "name": display_name,
                "display_name": display_name,
                "aliases": list(item.get("aliases") or []),
                "package_name": package_names[0] if package_names else None,
                "package_names": package_names,
            }
        )
    return {"apps": apps}


@router.get("/prompt_templates")
def list_prompt_templates():
    from engine.prompt_templates import get_prompt_templates

    return {"templates": get_prompt_templates()}


@router.get("/metrics/plugins")
async def plugin_success_metrics():
    controller = get_task_controller()
    rows = await run_sync(controller.plugin_success_counts)
    return [_plugin_success_metrics_row(row) for row in rows]


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


@router.get("/drafts/{draft_id}/snapshot", response_model=WorkflowDraftSnapshotResponse)
async def get_workflow_draft_snapshot(draft_id: str):
    controller = get_task_controller()
    try:
        return await run_sync(controller.workflow_draft_snapshot, draft_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc


@router.post("/drafts/{draft_id}/continue", response_model=list[TaskResponse])
async def continue_workflow_draft(
    draft_id: str,
    request: WorkflowDraftContinueRequest | None = None,
):
    controller = get_task_controller()
    maybe_start = getattr(controller, "ensure_started_if_enabled", None)
    if callable(maybe_start):
        await run_sync(maybe_start)
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


@router.post("/plugins/{plugin_name}/distill")
async def distill_plugin_current(plugin_name: str, force: bool = False):
    return await _distill_plugin_response(plugin_name, force)


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


@router.post("/{task_id}/pause")
async def pause_task(task_id: str, request: TaskControlRequest | None = None):
    controller = get_task_controller()
    record = await run_sync(controller.get, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    if record.status in {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    }:
        return {"task_id": task_id, "status": record.status, "paused": False}
    state = await run_sync(
        lambda: controller.pause_state(task_id, reason=request.reason if request else None)
    )
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task_id": task_id,
        "status": state,
        "pause_state": state,
        "paused": state == "paused",
        "pause_requested": state == "pause_requested",
    }


@router.post("/{task_id}/resume")
async def resume_task(task_id: str, request: TaskControlRequest | None = None):
    controller = get_task_controller()
    record = await run_sync(controller.get, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    state = await run_sync(
        lambda: controller.resume_state(task_id, reason=request.reason if request else None)
    )
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")
    resumed = record.status == "paused" and state == "pending"
    resume_requested = record.status == "running" and state == "running"
    return {
        "task_id": task_id,
        "status": state,
        "resume_state": state,
        "resumed": resumed,
        "resume_requested": resume_requested,
    }


@router.post("/{task_id}/takeover")
async def takeover_task(task_id: str, request: TaskControlRequest | None = None):
    controller = get_task_controller()
    record = await run_sync(controller.get, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    try:
        state = await run_sync(
            lambda: controller.takeover_state(
                task_id,
                owner=request.owner if request else None,
                run_id=request.run_id if request else None,
                reason=request.reason if request else None,
                current_declarative_stage=request.current_declarative_stage if request else None,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if state is None:
        raise HTTPException(status_code=404, detail="task not found")
    changed = state == "takeover_requested"
    return {"task_id": task_id, "status": state, "takeover_state": state, "takeover": changed}


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
