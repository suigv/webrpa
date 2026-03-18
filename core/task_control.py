from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from core.account_feedback import AccountFeedbackService
from core.device_manager import get_device_manager
from core.paths import traces_dir
from core.task_events import TaskEventStore
from core.task_execution import TaskExecutionService
from core.task_finalizer import AccountFeedbackLike, TaskAttemptFinalizer
from core.task_metrics import TaskMetricsService, build_task_metrics_payload
from core.task_queue import QueueBackend, create_task_queue
from core.task_runtime import (
    TaskDispatchRuntimeResolver,
    TaskTargetRuntimeResolver,
    normalize_dispatch_targets,
)
from core.task_store import TaskRecord, TaskStore
from core.workflow_draft_store import WorkflowDraftStore
from core.workflow_drafts import WorkflowDraftService
from engine.plugin_loader import get_shared_plugin_loader
from engine.runner import Runner

logger = logging.getLogger(__name__)


def _remove_task_traces(task_id: str):
    """Cleanup physical trace files from disk."""
    try:
        t_dir = traces_dir()
        # JSONL trace
        trace_file = t_dir / f"{task_id}.jsonl"
        if trace_file.exists():
            trace_file.unlink()

        # Screenshot directory (if any)
        screenshots = t_dir / task_id
        if screenshots.exists() and screenshots.is_dir():
            import shutil

            shutil.rmtree(screenshots)
    except Exception as exc:
        logger.warning(f"Failed to cleanup traces for task {task_id}: {exc}")


def _dedupe_ints(values: list[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for raw in values:
        try:
            value = int(raw)
        except Exception:
            continue
        if value < 1:
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _normalize_targets_and_devices(
    devices: list[int],
    targets: list[dict[str, int]] | None,
) -> tuple[list[int], list[dict[str, int]]]:
    has_targets = bool(targets)
    normalized_targets = normalize_dispatch_targets(targets or [], [])
    if has_targets and not normalized_targets:
        raise ValueError("either targets or devices must be provided")

    if normalized_targets:
        target_device_ids = _dedupe_ints([item.get("device_id", 0) for item in normalized_targets])
        if devices:
            device_ids = _dedupe_ints(devices)
            if set(device_ids) != set(target_device_ids):
                raise ValueError("devices and targets must refer to the same device set")
        return target_device_ids, normalized_targets

    device_ids = _dedupe_ints(devices)
    if not device_ids:
        raise ValueError("either targets or devices must be provided")
    normalized_targets = normalize_dispatch_targets([], device_ids)
    return device_ids, normalized_targets


class RunnerLike(Protocol):
    def run(
        self,
        script_payload: dict[str, Any],
        should_cancel: Any = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class TaskController:
    def __init__(
        self,
        store: TaskStore | None = None,
        queue_backend: QueueBackend | None = None,
        runner: RunnerLike | None = None,
        event_store: TaskEventStore | None = None,
        account_feedback: AccountFeedbackLike | None = None,
    ) -> None:
        # 1. 基础 Store 初始化 (此时不应触发繁重查询)
        self._store = store or TaskStore()
        self._queue = queue_backend or create_task_queue()
        self._runner = runner or Runner()

        # 确保 EventStore 共享同一个路径
        self._events = event_store or TaskEventStore(db_path=self._store._db_path)
        self._account_feedback = account_feedback or AccountFeedbackService()

        # 2. 外部服务注入
        self._device_manager = get_device_manager()
        self._target_runtime_resolver = TaskTargetRuntimeResolver(
            self._device_manager, task_store=self._store
        )
        self._plugin_loader = get_shared_plugin_loader()
        self._dispatch_runtime_resolver = TaskDispatchRuntimeResolver(
            target_runtime_resolver=self._target_runtime_resolver,
            plugin_loader=self._plugin_loader,
        )
        self._workflow_drafts = WorkflowDraftService(
            store=WorkflowDraftStore(db_path=self._store._db_path)
        )

        # 3. 延迟初始化子服务
        self._metrics_service: TaskMetricsService | None = None
        self._execution_service: TaskExecutionService | None = None
        self._attempt_finalizer: TaskAttemptFinalizer | None = None

    def _ensure_services(self):
        """阶梯式初始化子服务，防止启动瞬间死锁。"""
        if self._execution_service is not None:
            return

        self._metrics_service = TaskMetricsService(store=self._store, event_store=self._events)
        self._attempt_finalizer = TaskAttemptFinalizer(
            store=self._store,
            event_store=self._events,
            account_feedback=self._account_feedback,
            workflow_drafts=self._workflow_drafts,
        )
        self._execution_service = TaskExecutionService(
            store=self._store,
            queue_backend=self._queue,
            runner=self._runner,
            event_store=self._events,
            finalizer=self._attempt_finalizer,
            dispatch_runtime_resolver=self._dispatch_runtime_resolver,
        )

    def start(self) -> None:
        logger.info("Starting TaskController services...")
        self._ensure_services()
        if self._execution_service:
            self._execution_service.start()

    def stop(self) -> None:
        if self._execution_service:
            self._execution_service.stop()

    def submit_with_retry(
        self,
        payload: dict[str, Any],
        devices: list[int],
        targets: list[dict[str, int]] | None,
        ai_type: str,
        max_retries: int,
        retry_backoff_seconds: int,
        priority: int,
        run_at: str | None,
        idempotency_key: str | None = None,
        *,
        display_name: str | None = None,
        draft_id: str | None = None,
        success_threshold: int | None = None,
    ) -> TaskRecord:
        self._ensure_services()
        normalized_devices, normalized_targets = _normalize_targets_and_devices(devices, targets)
        task_name = str(payload.get("task") or "anonymous")
        is_named_plugin = self._plugin_loader.has(task_name)

        if idempotency_key:
            existing = self._store.find_active_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing

        with self._store.transaction(immediate=True) as conn:
            enriched_payload, workflow_summary = self._workflow_drafts.prepare_submission(
                payload=payload,
                devices=normalized_devices,
                targets=normalized_targets,
                ai_type=ai_type,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                priority=priority,
                display_name=display_name,
                draft_id=draft_id,
                success_threshold=success_threshold,
                is_named_plugin=is_named_plugin,
                conn=conn,
            )
            record = self._store.create_task(
                task_id=str(uuid.uuid4()),
                payload=enriched_payload,
                devices=normalized_devices,
                targets=normalized_targets,
                ai_type=ai_type,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                priority=priority,
                run_at=run_at,
                idempotency_key=idempotency_key,
                conn=conn,
            )
            self._events.append_event(
                record.task_id,
                "task.created",
                {
                    "task": str(enriched_payload.get("task") or "anonymous"),
                    "priority": record.priority,
                    "run_at": record.run_at,
                    "workflow_draft": workflow_summary,
                },
                conn=conn,
            )

        if self._execution_service:
            self._execution_service.enqueue_record(record)
        return record

    def list(self, limit: int = 100):
        return self._store.list_tasks(limit=limit)

    def get(self, task_id: str) -> TaskRecord | None:
        return self._store.get_task(task_id)

    def list_events(self, task_id: str, after_event_id: int = 0, limit: int = 200):
        return self._events.list_events(task_id=task_id, after_event_id=after_event_id, limit=limit)

    def cancel_state(self, task_id: str) -> str | None:
        with self._store.transaction(immediate=True) as conn:
            current = self._store.get_task(task_id, conn=conn)
            if current is None:
                return None
            state = self._store.request_cancel(task_id, conn=conn)
            if state is None:
                return None
            if state == "cancelled":
                self._events.append_event(
                    task_id,
                    "task.cancel_requested",
                    {"status": "pending"},
                    conn=conn,
                )
                cancelled = self._store.get_task(task_id, conn=conn)
                self._events.append_event(
                    task_id,
                    "task.cancelled",
                    build_task_metrics_payload(cancelled, {"reason": "user"}),
                    conn=conn,
                )
                if cancelled is not None:
                    workflow_payload = self._workflow_drafts.record_terminal(
                        task_record=cancelled,
                        result={"status": "cancelled", "ok": False, "message": "cancelled by user"},
                        conn=conn,
                    )
                    if workflow_payload:
                        self._events.append_event(
                            task_id,
                            "workflow_draft.updated",
                            workflow_payload,
                            conn=conn,
                        )
            elif state == "cancelling":
                self._events.append_event(
                    task_id,
                    "task.cancel_requested",
                    {"status": "running"},
                    conn=conn,
                )
            return state

    def clear_all(self):
        # 强制级连清理
        with self._store.transaction(immediate=True) as conn:
            self._store.clear_all_tasks(conn=conn, require_no_running=True)
            self._events.clear_all_events(conn=conn)
            self._workflow_drafts.clear_all(conn=conn)

    def cleanup_failed_tasks(self) -> int:
        """清理所有已停止但未成功的任务 (failed, cancelled)，返回被清理的数量。"""
        task_ids = self._store.clear_failed_tasks()
        for tid in task_ids:
            _remove_task_traces(tid)
            self._events.clear_task_events(tid)
        self._workflow_drafts.cleanup_task_references(task_ids)
        return len(task_ids)

    def list_running_task_ids_by_device(self, device_id: int) -> list[str]:
        return self._store.get_running_tasks_by_device(device_id)

    def task_metrics(
        self,
        window_seconds: int,
        failure_rate_threshold: float,
        cancellation_rate_threshold: float,
        min_terminal_samples: int,
    ):
        self._ensure_services()
        if not self._metrics_service:
            return {}
        return self._metrics_service.task_metrics(
            window_seconds=window_seconds,
            failure_rate_threshold=failure_rate_threshold,
            cancellation_rate_threshold=cancellation_rate_threshold,
            min_terminal_samples=min_terminal_samples,
        )

    def task_metrics_prometheus(
        self,
        window_seconds: int,
        failure_rate_threshold: float,
        cancellation_rate_threshold: float,
        min_terminal_samples: int,
    ) -> str:
        self._ensure_services()
        if not self._metrics_service:
            return ""
        return self._metrics_service.task_metrics_prometheus(
            window_seconds=window_seconds,
            failure_rate_threshold=failure_rate_threshold,
            cancellation_rate_threshold=cancellation_rate_threshold,
            min_terminal_samples=min_terminal_samples,
        )

    def plugin_success_counts(self) -> list[dict[str, object]]:
        return self._store.plugin_success_counts()

    def workflow_draft_summary(self, draft_id: str) -> dict[str, Any] | None:
        return self._workflow_drafts.summary(draft_id)

    def workflow_draft_summary_for_task(self, record: TaskRecord) -> dict[str, Any] | None:
        return self._workflow_drafts.summary_for_payload(record.payload)

    def list_workflow_drafts(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._workflow_drafts.list_summaries(limit=limit)

    def continue_workflow_draft(self, draft_id: str, count: int = 1) -> list[TaskRecord]:
        snapshot_bundle = self._workflow_drafts.continuation_snapshot(draft_id)
        snapshot = dict(snapshot_bundle["snapshot"])
        payload = dict(snapshot.get("payload") or {})
        devices = [int(item) for item in snapshot.get("devices") or []]
        targets = snapshot.get("targets")
        ai_type = str(snapshot.get("ai_type") or "volc")
        max_retries = int(snapshot.get("max_retries") or 0)
        retry_backoff_seconds = int(snapshot.get("retry_backoff_seconds") or 2)
        priority = int(snapshot.get("priority") or 50)
        created: list[TaskRecord] = []
        for _ in range(max(1, int(count))):
            created.append(
                self.submit_with_retry(
                    payload=dict(payload),
                    devices=devices,
                    targets=targets if isinstance(targets, list) else None,
                    ai_type=ai_type,
                    max_retries=max_retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                    priority=priority,
                    run_at=None,
                    display_name=str(snapshot_bundle["display_name"]),
                    draft_id=str(snapshot_bundle["draft_id"]),
                    success_threshold=int(snapshot_bundle["success_threshold"]),
                )
            )
        return created

    def distill_workflow_draft(
        self,
        draft_id: str,
        *,
        plugin_name: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        return self._workflow_drafts.distill_draft(
            draft_id,
            plugin_name=plugin_name,
            force=force,
        )

    def subscribe_events(self, observer: Callable[[Any], None]) -> None:
        self._events.subscribe(observer)


_controller: TaskController | None = None
_controller_lock = threading.Lock()


def get_task_controller() -> TaskController:
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = TaskController()
    return _controller


def override_task_controller_for_tests(controller: TaskController) -> None:
    global _controller
    with _controller_lock:
        if _controller is not None:
            _controller.stop()
        _controller = controller


def reset_task_controller_for_tests() -> None:
    global _controller
    with _controller_lock:
        if _controller is not None:
            _controller.stop()
        _controller = None
