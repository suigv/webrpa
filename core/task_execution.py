from __future__ import annotations

import concurrent.futures
import logging
import math
import multiprocessing
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from core.account_feedback import AccountFeedbackService
from core.device_manager import get_device_manager
from core.task_events import TaskEventStore
from core.task_finalizer import TaskAttemptFinalizer
from core.task_metrics import build_task_metrics_payload
from core.task_queue import QueueBackend, RedisTaskQueue
from core.task_runtime import TaskDispatchRuntimeResolver, TaskTargetRuntimeResolver, build_queue_schedule
from core.task_store import TaskStore
from engine.plugin_loader import get_shared_plugin_loader
from engine.runner import Runner


class RunnerLike(Protocol):
    def run(
        self,
        script_payload: dict[str, Any],
        should_cancel: Any = None,
        runtime: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

logger = logging.getLogger(__name__)

DEFAULT_CANCEL_GRACE_SECONDS = 10
DEFAULT_FORCE_KILL_SECONDS = 30


@dataclass
class ProcessTaskHandle:
    task_id: str
    process: multiprocessing.Process
    cancel_event: multiprocessing.Event
    started_at: float
    cancel_signaled_at: float | None = None
    terminate_sent_at: float | None = None


def _delay_seconds(next_retry_at: str) -> int:
    dt = datetime.fromisoformat(next_retry_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = (dt - now).total_seconds()
    if delta <= 0:
        return 0
    return int(math.ceil(delta))


def _iso_to_epoch(timestamp: str) -> float:
    dt = datetime.fromisoformat(timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _enqueue_record(queue_backend: QueueBackend, record: Any) -> None:
    delay, run_at_epoch = build_queue_schedule(record, _iso_to_epoch, _delay_seconds)
    queue_backend.enqueue(
        record.task_id,
        delay_seconds=delay,
        priority=record.priority,
        run_at_epoch=run_at_epoch,
    )


def _enqueue_retry(queue_backend: QueueBackend, record: Any, should_enqueue: bool) -> None:
    if not should_enqueue or record is None or record.next_retry_at is None:
        return
    queue_backend.enqueue(
        record.task_id,
        delay_seconds=_delay_seconds(record.next_retry_at),
        priority=record.priority,
        run_at_epoch=_iso_to_epoch(record.next_retry_at),
    )


def _resolve_executor_mode(requested: str, queue_backend: QueueBackend) -> str:
    raw = (requested or "").strip().lower()
    if raw in {"thread", "threads"}:
        return "thread"
    if isinstance(queue_backend, RedisTaskQueue):
        return "process"
    return "thread"


def _cancel_grace_seconds() -> int:
    raw = os.environ.get("MYT_TASK_CANCEL_GRACE_SECONDS", str(DEFAULT_CANCEL_GRACE_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_CANCEL_GRACE_SECONDS
    return max(0, value)


def _force_kill_seconds() -> int:
    raw = os.environ.get("MYT_TASK_FORCE_KILL_SECONDS", str(DEFAULT_FORCE_KILL_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_FORCE_KILL_SECONDS
    return max(0, value)


def _execute_task(
    *,
    task_id: str,
    store: TaskStore,
    queue_backend: QueueBackend | None,
    runner: RunnerLike,
    events: TaskEventStore,
    finalizer: TaskAttemptFinalizer,
    dispatch_runtime_resolver: TaskDispatchRuntimeResolver,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    def _combined_cancel() -> bool:
        if should_cancel is not None and bool(should_cancel()):
            return True
        return store.is_cancel_requested(task_id)

    with store.transaction(immediate=True) as conn:
        marked_running = store.mark_running(task_id, conn=conn)
        record = store.get_task(task_id, conn=conn)
        if marked_running and record is None:
            raise RuntimeError(f"task disappeared after mark_running: {task_id}")
        if marked_running and record is not None:
            events.append_event(
                task_id,
                "task.started",
                {"retry_count": record.retry_count, "priority": record.priority},
                conn=conn,
            )
            task_name = str(record.payload.get("task") or "anonymous")
            events.append_event(
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
        if queue_backend is not None and record is not None and record.status == "pending":
            _enqueue_record(queue_backend, record)
        return

    if record is None:
        return

    task_name = str(record.payload.get("task") or "anonymous")
    result: dict[str, Any]
    try:
        target_results: list[dict[str, Any]] = []
        first_failure: dict[str, Any] | None = None
        prepared_targets = dispatch_runtime_resolver.prepare(
            task_id=task_id,
            task_name=task_name,
            payload=record.payload,
            devices=record.devices,
            targets=record.targets,
            enforce_availability=False,
        )

        for prepared in prepared_targets:
            if _combined_cancel():
                break
            if prepared.error is not None:
                target_results.append({"target": prepared.target, "result": prepared.error})
                if first_failure is None:
                    first_failure = prepared.error
                continue

            def emit_event(event_type: str, data: dict[str, Any]):
                try:
                    target_label = prepared.runtime.get("cloud_target")
                    data["target"] = target_label
                    events.append_event(task_id, event_type, data)
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
            single_result = runner.run(
                prepared.payload,
                should_cancel=_combined_cancel,
                runtime=runtime,
            )
            target_results.append({"target": prepared.target, "result": single_result})
            if not bool(single_result.get("ok")) and first_failure is None:
                first_failure = single_result

            # 任务执行完毕后立即释放云机占用，触发探测刷新
            try:
                _device_id = int(prepared.target.get("device_id", 0))
                _cloud_id = int(prepared.target.get("cloud_id", 0))
                if _device_id > 0 and _cloud_id > 0:
                    get_device_manager()._update_probe_cache(_device_id, _cloud_id, True, 0, "task_released")
            except Exception:
                pass

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
        outcome = finalizer.finalize_exception_attempt(task_id=task_id, task_name=task_name, error=str(exc))
        if queue_backend is not None:
            _enqueue_retry(queue_backend, outcome.retry_record, outcome.should_enqueue_retry)
        time.sleep(0)
        return

    outcome = finalizer.finalize_result_attempt(
        task_id=task_id,
        task_name=task_name,
        result=result,
        payload=record.payload,
    )
    if queue_backend is not None:
        _enqueue_retry(queue_backend, outcome.retry_record, outcome.should_enqueue_retry)
    time.sleep(0)


def _create_process_queue_backend() -> QueueBackend:
    from core.system_settings_loader import get_redis_url
    return RedisTaskQueue(redis_url=get_redis_url())


def _process_task_subprocess(task_id: str, cancel_event: multiprocessing.Event) -> None:
    store = TaskStore()
    events = TaskEventStore(db_path=store._db_path)
    finalizer = TaskAttemptFinalizer(
        store=store,
        event_store=events,
        account_feedback=AccountFeedbackService(),
    )
    device_manager = get_device_manager()
    target_runtime_resolver = TaskTargetRuntimeResolver(device_manager, task_store=store)
    plugin_loader = get_shared_plugin_loader()
    dispatch_runtime_resolver = TaskDispatchRuntimeResolver(
        target_runtime_resolver=target_runtime_resolver,
        plugin_loader=plugin_loader,
    )
    runner = Runner()
    queue_backend = _create_process_queue_backend()
    _execute_task(
        task_id=task_id,
        store=store,
        queue_backend=queue_backend,
        runner=runner,
        events=events,
        finalizer=finalizer,
        dispatch_runtime_resolver=dispatch_runtime_resolver,
        should_cancel=cancel_event.is_set,
    )


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
        self._executor_mode: str | None = None
        self._max_workers: int = 0
        self._monitor: threading.Thread | None = None
        self._active: dict[str, ProcessTaskHandle] = {}
        self._active_lock = threading.Lock()

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._recover_stale_running_tasks()
        self._enqueue_pending_tasks()

        self._max_workers = max(1, int(os.environ.get("MYT_MAX_CONCURRENT_TASKS", "32")))
        requested_mode = os.environ.get("MYT_TASK_EXECUTOR_MODE", "process")
        self._executor_mode = _resolve_executor_mode(requested_mode, self._queue)
        if self._executor_mode == "thread":
            if requested_mode.strip().lower() in {"process", "proc"} and not isinstance(self._queue, RedisTaskQueue):
                logger.warning("process executor requested but queue backend is not redis; falling back to thread")
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="task-worker",
            )
        else:
            self._executor = None
            self._monitor = threading.Thread(target=self._monitor_loop, name="task-process-monitor", daemon=True)
            self._monitor.start()
        self._worker = threading.Thread(target=self._work_loop, name="task-controller-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._executor_mode == "process":
            self._shutdown_processes()
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
        if self._worker is not None:
            self._worker.join(timeout=2)
            self._worker = None
        if self._monitor is not None:
            self._monitor.join(timeout=2)
            self._monitor = None

    def replace_queue_backend(self, queue_backend: QueueBackend) -> None:
        self._queue = queue_backend

    def enqueue_record(self, record: Any) -> None:
        """Public wrapper to enqueue a task record for execution."""
        self._enqueue_record(record)

    def _work_loop(self) -> None:
        while not self._stop_event.is_set():
            task_id = self._queue.dequeue(timeout_seconds=1)
            if not task_id:
                continue

            if self._executor_mode == "process":
                while not self._stop_event.is_set():
                    if self._active_count() < self._max_workers:
                        self._start_process_task(task_id)
                        break
                    time.sleep(0.1)
            elif self._executor is not None:
                self._executor.submit(self._process_task, task_id)
            else:
                self._process_task(task_id)

    def _process_task(self, task_id: str) -> None:
        _execute_task(
            task_id=task_id,
            store=self._store,
            queue_backend=self._queue,
            runner=self._runner,
            events=self._events,
            finalizer=self._finalizer,
            dispatch_runtime_resolver=self._dispatch_runtime_resolver,
        )

    def _enqueue_retry(self, record: Any, should_enqueue: bool) -> None:
        _enqueue_retry(self._queue, record, should_enqueue)

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
        _enqueue_record(self._queue, record)

    def _delay_seconds(self, next_retry_at: str) -> int:
        return _delay_seconds(next_retry_at)

    def _iso_to_epoch(self, timestamp: str) -> float:
        return _iso_to_epoch(timestamp)

    @staticmethod
    def _stale_running_seconds() -> int:
        raw = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS", "300").strip()
        try:
            parsed = int(raw)
        except ValueError:
            return 300
        return max(0, parsed)

    def _active_count(self) -> int:
        with self._active_lock:
            return len(self._active)

    def _start_process_task(self, task_id: str) -> None:
        with self._active_lock:
            if task_id in self._active:
                logger.warning("task %s already active; skipping duplicate spawn", task_id)
                return
        try:
            ctx = multiprocessing.get_context("spawn")
            cancel_event = ctx.Event()
            process = ctx.Process(
                target=_process_task_subprocess,
                args=(task_id, cancel_event),
                name=f"task-worker-{task_id[:8]}",
            )
            process.daemon = True
            process.start()
            handle = ProcessTaskHandle(
                task_id=task_id,
                process=process,
                cancel_event=cancel_event,
                started_at=time.monotonic(),
            )
            with self._active_lock:
                self._active[task_id] = handle
        except Exception as exc:
            logger.exception("failed to start task process %s: %s", task_id, exc)
            record = self._store.get_task(task_id)
            priority = record.priority if record is not None else 50
            self._queue.enqueue(task_id, delay_seconds=1, priority=priority)

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            self._sweep_processes()
            time.sleep(0.5)

    def _sweep_processes(self) -> None:
        now = time.monotonic()
        grace = _cancel_grace_seconds()
        force_kill = _force_kill_seconds()
        with self._active_lock:
            handles = list(self._active.values())

        for handle in handles:
            proc = handle.process
            if not proc.is_alive():
                exit_code = proc.exitcode
                try:
                    proc.join(timeout=0.1)
                except Exception:
                    pass
                with self._active_lock:
                    self._active.pop(handle.task_id, None)
                if not self._stop_event.is_set():
                    self._handle_process_exit(handle.task_id, exit_code)
                continue

            if handle.cancel_signaled_at is None and self._store.is_cancel_requested(handle.task_id):
                handle.cancel_event.set()
                handle.cancel_signaled_at = now

            if handle.cancel_signaled_at is None:
                continue

            elapsed = now - handle.cancel_signaled_at
            if elapsed >= grace and handle.terminate_sent_at is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                handle.terminate_sent_at = now
                continue

            if handle.terminate_sent_at is not None and elapsed >= force_kill:
                try:
                    if proc.is_alive():
                        proc.kill()
                except Exception:
                    pass

    def _handle_process_exit(self, task_id: str, exit_code: int | None) -> None:
        record = self._store.get_task(task_id)
        if record is None:
            return
        if record.status in {"completed", "failed", "cancelled"}:
            return

        if record.cancel_requested:
            self._store.mark_cancelled(task_id, message="cancelled by user (forced)")
            cancelled = self._store.get_task(task_id)
            self._events.append_event(
                task_id,
                "task.cancelled",
                build_task_metrics_payload(cancelled, {"reason": "forced_cancel"}),
            )
            return

        task_name = str(record.payload.get("task") or "anonymous")
        error = f"task worker exited with code {exit_code}"
        outcome = self._finalizer.finalize_exception_attempt(task_id=task_id, task_name=task_name, error=error)
        self._enqueue_retry(outcome.retry_record, outcome.should_enqueue_retry)

    def _shutdown_processes(self) -> None:
        with self._active_lock:
            handles = list(self._active.values())
        for handle in handles:
            handle.cancel_event.set()
        for handle in handles:
            try:
                if handle.process.is_alive():
                    handle.process.terminate()
            except Exception:
                pass
        deadline = time.monotonic() + 2.0
        for handle in handles:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                handle.process.join(timeout=remaining)
            except Exception:
                pass
        for handle in handles:
            try:
                if handle.process.is_alive():
                    handle.process.kill()
            except Exception:
                pass
        with self._active_lock:
            self._active.clear()
