from __future__ import annotations

import concurrent.futures
import math
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from core.task_events import TaskEventStore
from core.task_finalizer import TaskAttemptFinalizer
from core.task_queue import QueueBackend
from core.task_runtime import TaskDispatchRuntimeResolver, build_queue_schedule
from core.task_store import TaskStore


class RunnerLike(Protocol):
    def run(
        self,
        script_payload: dict[str, Any],
        should_cancel: Any = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class TaskExecutionService:
    def __init__(
        self,
        store: TaskStore,
        queue_backend: QueueBackend,
        runner: RunnerLike,
        event_store: TaskEventStore,
        finalizer: TaskAttemptFinalizer,
        dispatch_runtime_resolver: TaskDispatchRuntimeResolver,
    ) -> None:
        self._store = store
        self._queue = queue_backend
        self._runner = runner
        self._events = event_store
        self._finalizer = finalizer
        self._dispatch_runtime_resolver = dispatch_runtime_resolver
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._recover_stale_running_tasks()
        self._enqueue_pending_tasks()

        max_workers = int(os.environ.get("MYT_MAX_CONCURRENT_TASKS", "32"))
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="task-worker",
        )
        self._worker = threading.Thread(target=self._work_loop, name="task-controller-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
        if self._worker is not None:
            self._worker.join(timeout=2)
            self._worker = None

    def replace_queue_backend(self, queue_backend: QueueBackend) -> None:
        self._queue = queue_backend

    def _work_loop(self) -> None:
        while not self._stop_event.is_set():
            task_id = self._queue.dequeue(timeout_seconds=1)
            if not task_id:
                continue

            if self._executor is not None:
                self._executor.submit(self._process_task, task_id)
            else:
                self._process_task(task_id)

    def _process_task(self, task_id: str) -> None:
        with self._store.transaction(immediate=True) as conn:
            marked_running = self._store.mark_running(task_id, conn=conn)
            record = self._store.get_task(task_id, conn=conn)
            if marked_running and record is None:
                raise RuntimeError(f"task disappeared after mark_running: {task_id}")
            if marked_running and record is not None:
                self._events.append_event(
                    task_id,
                    "task.started",
                    {"retry_count": record.retry_count, "priority": record.priority},
                    conn=conn,
                )
                task_name = str(record.payload.get("task") or "anonymous")
                self._events.append_event(
                    task_id,
                    "task.dispatching",
                    {
                        "task": task_name,
                        "retry_count": record.retry_count,
                        "priority": record.priority,
                    },
                    conn=conn,
                )

        if not marked_running:
            if record is not None and record.status == "pending":
                self._enqueue_record(record)
            return

        if record is None:
            return

        task_name = str(record.payload.get("task") or "anonymous")
        result: dict[str, Any]
        try:
            target_results: list[dict[str, Any]] = []
            first_failure: dict[str, Any] | None = None
            prepared_targets = self._dispatch_runtime_resolver.prepare(
                task_id=task_id,
                task_name=task_name,
                payload=record.payload,
                devices=record.devices,
                targets=record.targets,
            )

            for prepared in prepared_targets:
                if prepared.error is not None:
                    target_results.append({"target": prepared.target, "result": prepared.error})
                    if first_failure is None:
                        first_failure = prepared.error
                    continue

                def emit_event(event_type: str, data: Dict[str, Any]):
                    try:
                        # 1. 存入数据库（持久化）
                        target_label = prepared.runtime.get("cloud_target")
                        data["target"] = target_label
                        self._events.append_event(task_id, event_type, data)
                        
                        # 直接推送到实时日志流
                        # 我们已经通过 TaskEventStore 的订阅机制实现了 WebSocket 广播，
                        # 这里不需要手动调用 log_manager.log，避免重复。
                    except Exception:
                        pass

                runtime = dict(prepared.runtime)
                runtime["emit_event"] = emit_event
                
                if task_name == "gpt_executor":
                    runtime.update(
                        {
                            "retry_count": record.retry_count,
                            "attempt_number": record.retry_count + 1,
                            "run_id": f"{task_id}-run-{record.retry_count + 1}",
                        }
                    )
                single_result = self._runner.run(
                    prepared.payload,
                    should_cancel=lambda task_id=task_id: self._store.is_cancel_requested(task_id),
                    runtime=runtime,
                )
                target_results.append({"target": prepared.target, "result": single_result})
                if not bool(single_result.get("ok")) and first_failure is None:
                    first_failure = single_result

            if first_failure is None:
                result = {
                    "ok": True,
                    "task": task_name,
                    "status": "completed",
                    "target_count": len(target_results),
                    "targets": target_results,
                }
            else:
                result = {
                    "ok": False,
                    "task": task_name,
                    "status": str(first_failure.get("status") or "failed"),
                    "message": str(first_failure.get("message") or "task failed"),
                    "target_count": len(target_results),
                    "targets": target_results,
                }
        except Exception as exc:
            outcome = self._finalizer.finalize_exception_attempt(task_id=task_id, task_name=task_name, error=str(exc))
            self._enqueue_retry(outcome.retry_record, outcome.should_enqueue_retry)
            time.sleep(0)
            return

        outcome = self._finalizer.finalize_result_attempt(
            task_id=task_id,
            task_name=task_name,
            result=result,
            payload=record.payload,
        )
        self._enqueue_retry(outcome.retry_record, outcome.should_enqueue_retry)
        time.sleep(0)

    def _enqueue_retry(self, record: Any, should_enqueue: bool) -> None:
        if not should_enqueue or record is None or record.next_retry_at is None:
            return
        self._queue.enqueue(
            record.task_id,
            delay_seconds=self._delay_seconds(record.next_retry_at),
            priority=record.priority,
            run_at_epoch=self._iso_to_epoch(record.next_retry_at),
        )

    def _recover_stale_running_tasks(self) -> None:
        stale_after_seconds = self._stale_running_seconds()
        stale_before = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
        with self._store.transaction(immediate=True) as conn:
            recovered = self._store.recover_stale_running_tasks(stale_before=stale_before, conn=conn)
            for record in recovered:
                self._events.append_event(
                    record.task_id,
                    "task.recovered_stale_running",
                    {
                        "stale_after_seconds": stale_after_seconds,
                        "previous_status": "running",
                    },
                    conn=conn,
                )

        for record in recovered:
            self._enqueue_record(record)

    def _enqueue_pending_tasks(self) -> None:
        for record in self._store.list_pending_tasks():
            self._enqueue_record(record)

    def _enqueue_record(self, record: Any) -> None:
        delay, run_at_epoch = build_queue_schedule(record, self._iso_to_epoch, self._delay_seconds)
        self._queue.enqueue(
            record.task_id,
            delay_seconds=delay,
            priority=record.priority,
            run_at_epoch=run_at_epoch,
        )

    def _delay_seconds(self, next_retry_at: str) -> int:
        dt = datetime.fromisoformat(next_retry_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (dt - now).total_seconds()
        if delta <= 0:
            return 0
        return int(math.ceil(delta))

    def _iso_to_epoch(self, timestamp: str) -> float:
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()

    @staticmethod
    def _stale_running_seconds() -> int:
        raw = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS", "300").strip()
        try:
            parsed = int(raw)
        except ValueError:
            return 300
        return max(0, parsed)
