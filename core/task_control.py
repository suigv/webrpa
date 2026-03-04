from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
import math
from typing import Any, Protocol

from new.core.task_events import TaskEventStore
from new.core.task_queue import QueueBackend, create_task_queue
from new.core.task_store import TaskRecord, TaskStore
from new.engine.runner import Runner


class RunnerLike(Protocol):
    def run(self, script_payload: dict[str, Any], should_cancel: Any = None) -> dict[str, Any]: ...


class TaskController:
    def __init__(
        self,
        store: TaskStore | None = None,
        queue_backend: QueueBackend | None = None,
        runner: RunnerLike | None = None,
        event_store: TaskEventStore | None = None,
    ) -> None:
        self._store = store or TaskStore()
        self._queue = queue_backend or create_task_queue()
        self._runner = runner or Runner()
        self._events = event_store or TaskEventStore()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._work_loop, name="task-controller-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=2)

    def submit(self, payload: dict[str, Any], devices: list[int], ai_type: str) -> TaskRecord:
        task_id = str(uuid.uuid4())
        self._store.create_task(
            task_id=task_id,
            payload=payload,
            devices=devices,
            ai_type=ai_type,
            max_retries=0,
            retry_backoff_seconds=2,
            priority=50,
            run_at=None,
        )
        self._queue.enqueue(task_id, priority=50)
        self._events.append_event(
            task_id,
            "task.created",
            {"priority": 50, "run_at": None, "max_retries": 0, "retry_backoff_seconds": 2},
        )
        record = self._store.get_task(task_id)
        if record is None:
            raise RuntimeError("failed to create task")
        return record

    def submit_with_retry(
        self,
        payload: dict[str, Any],
        devices: list[int],
        ai_type: str,
        max_retries: int,
        retry_backoff_seconds: int,
        priority: int,
        run_at: str | None,
    ) -> TaskRecord:
        task_id = str(uuid.uuid4())
        self._store.create_task(
            task_id=task_id,
            payload=payload,
            devices=devices,
            ai_type=ai_type,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            priority=priority,
            run_at=run_at,
        )
        delay = 0
        if run_at:
            delay = self._delay_seconds(run_at)
        self._queue.enqueue(task_id, delay_seconds=delay, priority=priority)
        self._events.append_event(
            task_id,
            "task.created",
            {
                "priority": priority,
                "run_at": run_at,
                "max_retries": max_retries,
                "retry_backoff_seconds": retry_backoff_seconds,
            },
        )
        record = self._store.get_task(task_id)
        if record is None:
            raise RuntimeError("failed to create task")
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return self._store.get_task(task_id)

    def list(self, limit: int = 100) -> list[TaskRecord]:
        return self._store.list_tasks(limit=limit)

    def cancel(self, task_id: str) -> bool:
        result = self._store.request_cancel(task_id)
        return result in {"cancelled", "cancelling"}

    def cancel_state(self, task_id: str) -> str | None:
        state = self._store.request_cancel(task_id)
        if state is not None:
            self._events.append_event(task_id, "task.cancel_requested", {"state": state})
        return state

    def _work_loop(self) -> None:
        while not self._stop_event.is_set():
            task_id = self._queue.dequeue(timeout_seconds=1)
            if not task_id:
                continue

            if not self._store.mark_running(task_id):
                record = self._store.get_task(task_id)
                if record is not None and record.status == "pending":
                    delay = 0
                    if record.run_at is not None:
                        delay = self._delay_seconds(record.run_at)
                    if record.next_retry_at is not None:
                        delay = max(delay, self._delay_seconds(record.next_retry_at))
                    self._queue.enqueue(task_id, delay_seconds=delay, priority=record.priority)
                continue

            record = self._store.get_task(task_id)
            if record is None:
                continue
            self._events.append_event(
                task_id,
                "task.started",
                {"retry_count": record.retry_count, "priority": record.priority},
            )

            try:
                result = self._runner.run(
                    record.payload,
                    should_cancel=lambda task_id=task_id: self._store.is_cancel_requested(task_id),
                )
                if self._store.is_cancel_requested(task_id) or str(result.get("status")) == "cancelled":
                    self._store.mark_cancelled(task_id, message="cancelled by user")
                    self._events.append_event(task_id, "task.cancelled", self._metrics_payload(task_id, {"reason": "user"}))
                    time.sleep(0)
                    continue
                if bool(result.get("ok")):
                    self._store.mark_completed(task_id, result=result)
                    self._events.append_event(task_id, "task.completed", self._metrics_payload(task_id, {"ok": True}))
                else:
                    error = str(result.get("message", "task failed"))
                    retry_record = self._store.schedule_retry(task_id, error=error)
                    if retry_record is not None and retry_record.next_retry_at is not None:
                        self._queue.enqueue(
                            task_id,
                            delay_seconds=self._delay_seconds(retry_record.next_retry_at),
                            priority=retry_record.priority,
                        )
                        self._events.append_event(
                            task_id,
                            "task.retry_scheduled",
                            {
                                "retry_count": retry_record.retry_count,
                                "max_retries": retry_record.max_retries,
                                "next_retry_at": retry_record.next_retry_at,
                                "error": error,
                            },
                        )
                    else:
                        self._store.mark_failed(task_id, error=error, result=result)
                        self._events.append_event(
                            task_id,
                            "task.failed",
                            self._metrics_payload(task_id, {"error": error}),
                        )
            except Exception as exc:
                error = str(exc)
                retry_record = self._store.schedule_retry(task_id, error=error)
                if retry_record is not None and retry_record.next_retry_at is not None:
                    self._queue.enqueue(
                        task_id,
                        delay_seconds=self._delay_seconds(retry_record.next_retry_at),
                        priority=retry_record.priority,
                    )
                    self._events.append_event(
                        task_id,
                        "task.retry_scheduled",
                        {
                            "retry_count": retry_record.retry_count,
                            "max_retries": retry_record.max_retries,
                            "next_retry_at": retry_record.next_retry_at,
                            "error": error,
                        },
                    )
                else:
                    self._store.mark_failed(task_id, error=error, result=None)
                    self._events.append_event(
                        task_id,
                        "task.failed",
                        self._metrics_payload(task_id, {"error": error}),
                    )
            time.sleep(0)

    def _delay_seconds(self, next_retry_at: str) -> int:
        dt = datetime.fromisoformat(next_retry_at)
        now = datetime.now(timezone.utc)
        delta = (dt - now).total_seconds()
        if delta <= 0:
            return 0
        return int(math.ceil(delta))

    def _metrics_payload(self, task_id: str, extra: dict[str, Any]) -> dict[str, Any]:
        record = self._store.get_task(task_id)
        if record is None:
            return extra
        started_at = record.started_at
        finished_at = record.finished_at
        duration_ms = None
        if started_at and finished_at:
            try:
                duration_ms = int((datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds() * 1000)
            except Exception:
                duration_ms = None
        payload = {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "retry_count": record.retry_count,
        }
        payload.update(extra)
        return payload


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
