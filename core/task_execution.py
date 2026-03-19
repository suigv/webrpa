from __future__ import annotations

import concurrent.futures
import logging
import math
import multiprocessing
import os
import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from core.account_feedback import AccountFeedbackService
from core.device_manager import get_device_manager
from core.task_events import TaskEventStore
from core.task_finalizer import TaskAttemptFinalizer
from core.task_metrics import build_task_metrics_payload
from core.task_queue import QueueBackend, RedisTaskQueue
from core.task_runtime import (
    TaskDispatchRuntimeResolver,
    TaskTargetRuntimeResolver,
    build_queue_schedule,
)
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
    process: Any
    cancel_event: Any
    control_queue: Any | None
    status_queue: Any | None
    started_at: float
    cancel_signaled_at: float | None = None
    terminate_sent_at: float | None = None
    current_target: tuple[int, int] | None = None
    target_trip_sent: bool = False
    breaker_trip: TargetCircuitBreakerTrip | None = None
    tolerate_target_unavailable: bool = False


@dataclass(frozen=True)
class TargetCircuitBreakerTrip:
    code: str
    message: str
    details: dict[str, Any]


def _build_target_trip(
    *,
    device_id: int,
    cloud_id: int,
    snapshot: dict[str, Any],
) -> TargetCircuitBreakerTrip | None:
    state = str(snapshot.get("availability_state") or "unknown")
    if state != "unavailable" or bool(snapshot.get("stale", False)):
        return None
    reason = str(snapshot.get("availability_reason") or "unknown")
    message = f"target became unavailable during execution: device={device_id}, cloud={cloud_id}, reason={reason}"
    return TargetCircuitBreakerTrip(
        code="target_unavailable",
        message=message,
        details={
            "device_id": device_id,
            "cloud_id": cloud_id,
            "availability_state": state,
            "availability_reason": reason,
            "last_checked_at": snapshot.get("last_checked_at"),
            "latency_ms": snapshot.get("latency_ms"),
            "stale": bool(snapshot.get("stale", False)),
        },
    )


def _trip_result(task_name: str, trip: TargetCircuitBreakerTrip) -> dict[str, Any]:
    return {
        "ok": False,
        "task": task_name,
        "status": "failed_circuit_breaker",
        "checkpoint": "availability",
        "code": trip.code,
        "message": trip.message,
        "circuit_breaker": dict(trip.details),
    }


def _tolerate_target_unavailable(task_name: str, payload: dict[str, Any]) -> bool:
    return bool(payload.get("_allow_target_unavailable_during_execution")) or (
        task_name == "one_click_new_device"
    )


class ActiveTargetCircuitBreaker:
    def __init__(
        self,
        *,
        task_id: str,
        target: dict[str, Any],
        enabled: bool = True,
        emit_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._task_id = task_id
        self._device_id = int(target.get("device_id", 0) or 0)
        self._cloud_id = int(target.get("cloud_id", 0) or 0)
        self._emit_event = emit_event
        self._trip: TargetCircuitBreakerTrip | None = None
        self._trip_lock = threading.Lock()
        self._unsubscribe: Callable[[], None] | None = None
        if not enabled:
            return
        if self._device_id < 1 or self._cloud_id < 1:
            return

        # NEW: Check if RPC is enabled; if not, do not activate circuit breaker
        from core.system_settings_loader import get_rpc_enabled

        if not get_rpc_enabled():
            return

        manager = get_device_manager()
        self._unsubscribe = manager.subscribe_cloud_probe(
            self._device_id, self._cloud_id, self._handle_probe_update
        )
        self._handle_probe_update(manager.get_cloud_probe_snapshot(self._device_id, self._cloud_id))

    def _handle_probe_update(self, snapshot: dict[str, Any]) -> None:
        trip = _build_target_trip(
            device_id=self._device_id, cloud_id=self._cloud_id, snapshot=snapshot
        )
        if trip is None:
            return
        should_emit = False
        with self._trip_lock:
            if self._trip is None:
                self._trip = trip
                should_emit = True
        if should_emit and self._emit_event is not None:
            self._emit_event(
                "task.circuit_breaker",
                {
                    "code": trip.code,
                    **trip.details,
                    "message": trip.message,
                    "task_id": self._task_id,
                },
            )

    def should_cancel(self) -> bool:
        return self.trip() is not None

    def trip(self) -> TargetCircuitBreakerTrip | None:
        with self._trip_lock:
            return self._trip

    def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None


class SubprocessCancellationState:
    def __init__(self, cancel_event: Any, control_queue: Any | None) -> None:
        self._cancel_event = cancel_event
        self._control_queue = control_queue
        self._trip: TargetCircuitBreakerTrip | None = None
        self._trip_lock = threading.Lock()

    def _drain_control_queue(self) -> None:
        if self._control_queue is None:
            return
        while True:
            try:
                message = self._control_queue.get_nowait()
            except queue.Empty:
                return
            except Exception:
                return
            if not isinstance(message, dict) or message.get("type") != "trip":
                continue
            payload = message.get("payload")
            if not isinstance(payload, dict):
                continue
            trip = TargetCircuitBreakerTrip(
                code=str(payload.get("code") or "target_unavailable"),
                message=str(payload.get("message") or "target became unavailable during execution"),
                details=dict(payload.get("details") or {}),
            )
            with self._trip_lock:
                if self._trip is None:
                    self._trip = trip

    def should_cancel(self) -> bool:
        self._drain_control_queue()
        if self.trip() is not None:
            return True
        return self._cancel_event.is_set()

    def trip(self) -> TargetCircuitBreakerTrip | None:
        self._drain_control_queue()
        with self._trip_lock:
            return self._trip


def _delay_seconds(next_retry_at: str) -> int:
    dt = datetime.fromisoformat(next_retry_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    delta = (dt - now).total_seconds()
    if delta <= 0:
        return 0
    return int(math.ceil(delta))


def _iso_to_epoch(timestamp: str) -> float:
    dt = datetime.fromisoformat(timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
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
    trip_provider: Callable[[], TargetCircuitBreakerTrip | None] | None = None,
    on_target_started: Callable[[dict[str, Any]], None] | None = None,
    on_target_finished: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
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
    tolerate_target_unavailable = _tolerate_target_unavailable(task_name, record.payload)
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

            target_label = prepared.runtime.get("cloud_target")

            def emit_event(
                event_type: str, data: dict[str, Any], target: Any = target_label
            ) -> None:
                with suppress(Exception):
                    data["target"] = target
                    events.append_event(task_id, event_type, data)

            runtime = dict(prepared.runtime)
            runtime["emit_event"] = emit_event

            if task_name == "agent_executor":
                runtime.update(
                    {
                        "retry_count": record.retry_count,
                        "attempt_number": record.retry_count + 1,
                        "run_id": f"{task_id}-run-{record.retry_count + 1}",
                    }
                )

            local_breaker = ActiveTargetCircuitBreaker(
                task_id=task_id,
                target=prepared.target,
                enabled=not tolerate_target_unavailable,
                emit_event=emit_event,
            )
            single_result: dict[str, Any] = {
                "ok": False,
                "status": "failed_runtime_error",
                "message": "target execution did not produce a result",
            }
            try:

                def _target_cancel(_breaker: ActiveTargetCircuitBreaker = local_breaker) -> bool:
                    return _breaker.should_cancel() or _combined_cancel()

                def _current_trip(
                    _breaker: ActiveTargetCircuitBreaker = local_breaker,
                ) -> TargetCircuitBreakerTrip | None:
                    trip = _breaker.trip()
                    if trip is not None:
                        return trip
                    if trip_provider is not None:
                        return trip_provider()
                    return None

                if on_target_started is not None:
                    on_target_started(prepared.target)

                active_trip = _current_trip()
                if active_trip is not None:
                    single_result = _trip_result(task_name, active_trip)
                else:
                    single_result = runner.run(
                        prepared.payload,
                        should_cancel=_target_cancel,
                        runtime=runtime,
                    )
                    active_trip = _current_trip()
                    if active_trip is not None:
                        single_result = _trip_result(task_name, active_trip)
            finally:
                try:
                    if on_target_finished is not None:
                        on_target_finished(prepared.target, single_result)
                finally:
                    local_breaker.close()

            target_results.append({"target": prepared.target, "result": single_result})
            if not bool(single_result.get("ok")) and first_failure is None:
                first_failure = single_result

            # 任务执行完毕后立即释放云机占用，触发探测刷新
            try:
                _device_id = int(prepared.target.get("device_id", 0))
                _cloud_id = int(prepared.target.get("cloud_id", 0))
                if _device_id > 0 and _cloud_id > 0:
                    get_device_manager().mark_cloud_released(_device_id, _cloud_id)
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
        outcome = finalizer.finalize_exception_attempt(
            task_id=task_id, task_name=task_name, error=str(exc)
        )
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


def _process_task_subprocess(
    task_id: str,
    cancel_event: Any,
    control_queue: Any | None,
    status_queue: Any | None,
) -> None:
    store = TaskStore()
    events = TaskEventStore()
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
    cancellation_state = SubprocessCancellationState(
        cancel_event=cancel_event, control_queue=control_queue
    )

    def _notify_target_started(target: dict[str, Any]) -> None:
        if status_queue is None:
            return
        with suppress(Exception):
            status_queue.put(
                {
                    "type": "target_started",
                    "device_id": int(target.get("device_id", 0) or 0),
                    "cloud_id": int(target.get("cloud_id", 0) or 0),
                }
            )

    def _notify_target_finished(_target: dict[str, Any], _result: dict[str, Any]) -> None:
        if status_queue is None:
            return
        with suppress(Exception):
            status_queue.put({"type": "target_finished"})

    _execute_task(
        task_id=task_id,
        store=store,
        queue_backend=queue_backend,
        runner=runner,
        events=events,
        finalizer=finalizer,
        dispatch_runtime_resolver=dispatch_runtime_resolver,
        should_cancel=cancellation_state.should_cancel,
        trip_provider=cancellation_state.trip,
        on_target_started=_notify_target_started,
        on_target_finished=_notify_target_finished,
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
            if requested_mode.strip().lower() in {"process", "proc"} and not isinstance(
                self._queue, RedisTaskQueue
            ):
                logger.warning(
                    "process executor requested but queue backend is not redis; falling back to thread"
                )
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="task-worker",
            )
        else:
            self._executor = None
            self._monitor = threading.Thread(
                target=self._monitor_loop, name="task-process-monitor", daemon=True
            )
            self._monitor.start()
        self._worker = threading.Thread(
            target=self._work_loop, name="task-controller-worker", daemon=True
        )
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
        stale_before = (datetime.now(UTC) - timedelta(seconds=stale_after_seconds)).isoformat()
        with self._store.transaction(immediate=True) as conn:
            recovered = self._store.recover_stale_running_tasks(
                stale_before=stale_before, conn=conn
            )
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

    @staticmethod
    def _drain_status_queue(handle: ProcessTaskHandle) -> None:
        if handle.status_queue is None:
            return
        while True:
            try:
                message = handle.status_queue.get_nowait()
            except queue.Empty:
                return
            except Exception:
                return
            if not isinstance(message, dict):
                continue
            message_type = str(message.get("type") or "")
            if message_type == "target_started":
                device_id = int(message.get("device_id", 0) or 0)
                cloud_id = int(message.get("cloud_id", 0) or 0)
                if device_id > 0 and cloud_id > 0:
                    handle.current_target = (device_id, cloud_id)
                    handle.target_trip_sent = False
            elif message_type == "target_finished":
                handle.current_target = None
                handle.target_trip_sent = False

    def _maybe_trip_process_target(self, handle: ProcessTaskHandle, now: float) -> None:
        if (
            handle.cancel_signaled_at is not None
            or handle.current_target is None
            or handle.target_trip_sent
            or handle.tolerate_target_unavailable
        ):
            return
        device_id, cloud_id = handle.current_target
        snapshot = get_device_manager().get_cloud_probe_snapshot(device_id, cloud_id)
        trip = _build_target_trip(device_id=device_id, cloud_id=cloud_id, snapshot=snapshot)
        if trip is None:
            return
        if handle.control_queue is not None:
            with suppress(Exception):
                handle.control_queue.put(
                    {
                        "type": "trip",
                        "payload": {
                            "code": trip.code,
                            "message": trip.message,
                            "details": dict(trip.details),
                        },
                    }
                )
        with suppress(Exception):
            control = handle.cancel_event
            _ = control.set()
        handle.cancel_signaled_at = now
        handle.target_trip_sent = True
        handle.breaker_trip = trip
        with suppress(Exception):
            self._events.append_event(
                handle.task_id,
                "task.circuit_breaker",
                {
                    "code": trip.code,
                    **trip.details,
                    "message": trip.message,
                },
            )

    def _start_process_task(self, task_id: str) -> None:
        with self._active_lock:
            if task_id in self._active:
                logger.warning("task %s already active; skipping duplicate spawn", task_id)
                return
        try:
            record = self._store.get_task(task_id)
            task_name = str(record.payload.get("task") or "anonymous") if record is not None else ""
            tolerate_target_unavailable = (
                _tolerate_target_unavailable(task_name, record.payload)
                if record is not None
                else False
            )
            ctx = multiprocessing.get_context("spawn")
            cancel_event = ctx.Event()
            control_queue = ctx.Queue()
            status_queue = ctx.Queue()
            process = ctx.Process(
                target=_process_task_subprocess,
                args=(task_id, cancel_event, control_queue, status_queue),
                name=f"task-worker-{task_id[:8]}",
            )
            process.daemon = True
            process.start()
            handle = ProcessTaskHandle(
                task_id=task_id,
                process=process,
                cancel_event=cancel_event,
                control_queue=control_queue,
                status_queue=status_queue,
                started_at=time.monotonic(),
                tolerate_target_unavailable=tolerate_target_unavailable,
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
            self._drain_status_queue(handle)
            if not proc.is_alive():
                exit_code = proc.exitcode
                with suppress(Exception):
                    proc.join(timeout=0.1)
                with self._active_lock:
                    self._active.pop(handle.task_id, None)
                if not self._stop_event.is_set():
                    self._handle_process_exit(handle, exit_code)
                continue

            if handle.cancel_signaled_at is None and self._store.is_cancel_requested(
                handle.task_id
            ):
                handle.cancel_event.set()
                handle.cancel_signaled_at = now

            self._maybe_trip_process_target(handle, now)

            if handle.cancel_signaled_at is None:
                continue

            elapsed = now - handle.cancel_signaled_at
            if elapsed >= grace and handle.terminate_sent_at is None:
                with suppress(Exception):
                    proc.terminate()
                handle.terminate_sent_at = now
                continue

            if handle.terminate_sent_at is not None and elapsed >= force_kill:
                with suppress(Exception):
                    if proc.is_alive():
                        proc.kill()

    def _handle_process_exit(self, handle: ProcessTaskHandle, exit_code: int | None) -> None:
        task_id = handle.task_id
        record = self._store.get_task(task_id)
        if record is None:
            return
        if record.status in {"completed", "failed", "cancelled"}:
            return

        if handle.breaker_trip is not None:
            task_name = str(record.payload.get("task") or "anonymous")
            outcome = self._finalizer.finalize_result_attempt(
                task_id=task_id,
                task_name=task_name,
                result=_trip_result(task_name, handle.breaker_trip),
                payload=record.payload,
            )
            self._enqueue_retry(outcome.retry_record, outcome.should_enqueue_retry)
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
        outcome = self._finalizer.finalize_exception_attempt(
            task_id=task_id, task_name=task_name, error=error
        )
        self._enqueue_retry(outcome.retry_record, outcome.should_enqueue_retry)

    def _shutdown_processes(self) -> None:
        with self._active_lock:
            handles = list(self._active.values())
        for handle in handles:
            handle.cancel_event.set()
        for handle in handles:
            with suppress(Exception):
                if handle.process.is_alive():
                    handle.process.terminate()
        deadline = time.monotonic() + 2.0
        for handle in handles:
            remaining = max(0.0, deadline - time.monotonic())
            with suppress(Exception):
                handle.process.join(timeout=remaining)
        for handle in handles:
            with suppress(Exception):
                if handle.process.is_alive():
                    handle.process.kill()
        with self._active_lock:
            self._active.clear()
