from __future__ import annotations

import threading
from typing import Any, Protocol

from core.account_feedback import AccountFeedbackService
from core.device_manager import DeviceManager
from core.task_events import TaskEventStore
from core.task_execution import TaskExecutionService
from core.task_finalizer import AccountFeedbackLike, TaskAttemptFinalizer
from core.task_metrics import TaskMetricsService, build_task_metrics_payload
from core.task_queue import QueueBackend, create_task_queue
from core.task_runtime import (
    TaskDispatchRuntimeResolver,
    TaskTargetRuntimeResolver,
    build_queue_schedule,
    normalize_dispatch_targets,
)
from core.task_store import TaskRecord, TaskStore
from engine.plugin_loader import get_shared_plugin_loader
from engine.runner import Runner


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
        self._store = store or TaskStore()
        self._queue = queue_backend or create_task_queue()
        self._runner = runner or Runner()
        default_event_store = TaskEventStore(db_path=self._store._db_path)
        self._events = event_store or default_event_store
        self._account_feedback = account_feedback or AccountFeedbackService()
        self._device_manager = DeviceManager()
        self._target_runtime_resolver = TaskTargetRuntimeResolver(self._device_manager)
        self._plugin_loader = get_shared_plugin_loader()
        self._dispatch_runtime_resolver = TaskDispatchRuntimeResolver(
            target_runtime_resolver=self._target_runtime_resolver,
            plugin_loader=self._plugin_loader,
        )
        self._metrics_service = TaskMetricsService(store=self._store, event_store=self._events)
        self._attempt_finalizer = TaskAttemptFinalizer(
            store=self._store,
            event_store=self._events,
            account_feedback=self._account_feedback,
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
        self._execution_service.start()

    def stop(self) -> None:
        self._execution_service.stop()

    def submit(self, payload: dict[str, Any], devices: list[int], ai_type: str) -> TaskRecord:
        return self.submit_with_retry(
            payload=payload,
            devices=devices,
            targets=None,
            ai_type=ai_type,
            max_retries=0,
            retry_backoff_seconds=2,
            priority=50,
            run_at=None,
            idempotency_key=None,
        )

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
    ) -> TaskRecord:
        normalized_devices, normalized_targets = self._normalize_submit_targets(devices=devices, targets=targets)
        with self._store.transaction(immediate=True) as conn:
            record, created = self._store.create_or_get_active_task(
                payload=payload,
                devices=normalized_devices,
                targets=normalized_targets,
                ai_type=ai_type,
                idempotency_key=idempotency_key,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                priority=priority,
                run_at=run_at,
                conn=conn,
            )
            if created:
                self._events.append_event(
                    record.task_id,
                    "task.created",
                    {
                        "priority": priority,
                        "run_at": run_at,
                        "idempotency_key": idempotency_key,
                        "max_retries": max_retries,
                        "retry_backoff_seconds": retry_backoff_seconds,
                    },
                    conn=conn,
                )
        if not created:
            self._events.append_event(
                record.task_id,
                "task.duplicate_submit_ignored",
                {"idempotency_key": idempotency_key},
            )
            return record

        task_id = record.task_id
        delay, run_at_epoch = build_queue_schedule(record, self._iso_to_epoch, self._delay_seconds)
        self._queue.enqueue(task_id, delay_seconds=delay, priority=priority, run_at_epoch=run_at_epoch)
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return self._store.get_task(task_id)

    def list(self, limit: int = 100) -> list[TaskRecord]:
        return self._store.list_tasks(limit=limit)

    def list_events(self, task_id: str, after_event_id: int = 0, limit: int = 200):
        return self._events.list_events(task_id=task_id, after_event_id=after_event_id, limit=limit)

    def cancel(self, task_id: str) -> bool:
        result = self.cancel_state(task_id)
        return result in {"cancelled", "cancelling"}

    def cancel_state(self, task_id: str) -> str | None:
        with self._store.transaction(immediate=True) as conn:
            state = self._store.request_cancel(task_id, conn=conn)
            if state is not None:
                self._events.append_event(task_id, "task.cancel_requested", {"state": state}, conn=conn)
                if state == "cancelled":
                    record = self._store.get_task(task_id, conn=conn)
                    self._events.append_event(
                        task_id,
                        "task.cancelled",
                        build_task_metrics_payload(record, {"reason": "user_pending"}),
                        conn=conn,
                    )
        return state

    def clear_all(self) -> None:
        with self._store.transaction(immediate=True) as conn:
            self._store.clear_all_tasks(conn=conn, require_no_running=True)
            self._events.clear_all_events(conn=conn)
        new_queue = create_task_queue()
        self._queue = new_queue
        self._execution_service.replace_queue_backend(new_queue)

    def _normalize_submit_targets(
        self,
        devices: list[int],
        targets: list[dict[str, int]] | None,
    ) -> tuple[list[int], list[dict[str, int]]]:
        normalized_devices = self._normalize_device_ids(devices)
        raw_targets = list(targets or [])
        normalized_targets = normalize_dispatch_targets(raw_targets, [])
        if raw_targets and len(normalized_targets) != len(raw_targets):
            raise ValueError("targets must contain valid device_id/cloud_id pairs")
        if normalized_targets:
            target_devices = self._device_ids_from_targets(normalized_targets)
            if normalized_devices and set(normalized_devices) != set(target_devices):
                raise ValueError("devices and targets must refer to the same device set")
            return target_devices, normalized_targets
        if normalized_devices:
            return normalized_devices, normalize_dispatch_targets(None, normalized_devices)
        raise ValueError("either targets or devices must be provided")

    def _normalize_device_ids(self, devices: list[int]) -> list[int]:
        normalized: list[int] = []
        seen: set[int] = set()
        for raw_device_id in devices:
            try:
                device_id = int(str(raw_device_id))
            except Exception as exc:
                raise ValueError("devices must contain positive integers") from exc
            if device_id < 1:
                raise ValueError("devices must contain positive integers")
            if device_id in seen:
                continue
            seen.add(device_id)
            normalized.append(device_id)
        return normalized

    def _device_ids_from_targets(self, targets: list[dict[str, int]]) -> list[int]:
        device_ids: list[int] = []
        seen: set[int] = set()
        for target in targets:
            device_id = int(target["device_id"])
            if device_id in seen:
                continue
            seen.add(device_id)
            device_ids.append(device_id)
        return device_ids

    def task_metrics(
        self,
        window_seconds: int = 3600,
        failure_rate_threshold: float = 0.2,
        cancellation_rate_threshold: float = 0.2,
        min_terminal_samples: int = 20,
    ) -> dict[str, Any]:
        return self._metrics_service.task_metrics(
            window_seconds=window_seconds,
            failure_rate_threshold=failure_rate_threshold,
            cancellation_rate_threshold=cancellation_rate_threshold,
            min_terminal_samples=min_terminal_samples,
        )

    def task_metrics_prometheus(
        self,
        window_seconds: int = 3600,
        failure_rate_threshold: float = 0.2,
        cancellation_rate_threshold: float = 0.2,
        min_terminal_samples: int = 20,
    ) -> str:
        return self._metrics_service.task_metrics_prometheus(
            window_seconds=window_seconds,
            failure_rate_threshold=failure_rate_threshold,
            cancellation_rate_threshold=cancellation_rate_threshold,
            min_terminal_samples=min_terminal_samples,
        )

    def _delay_seconds(self, next_retry_at: str) -> int:
        return self._execution_service._delay_seconds(next_retry_at)

    def _iso_to_epoch(self, timestamp: str) -> float:
        return self._execution_service._iso_to_epoch(timestamp)


_controller: TaskController | None = None
_controller_lock = threading.Lock()


def get_task_controller() -> TaskController:
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = TaskController()
        return _controller


def reset_task_controller_for_tests() -> None:
    global _controller
    with _controller_lock:
        if _controller is not None:
            _controller.stop()
        _controller = None


def override_task_controller_for_tests(controller: TaskController) -> None:
    global _controller
    with _controller_lock:
        if _controller is not None:
            _controller.stop()
        _controller = controller
