from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Protocol

from core.account_feedback import AccountFeedbackService
from core.task_runtime import TaskTargetRuntimeResolver, build_queue_schedule, normalize_dispatch_targets
from core.task_events import TaskEventStore
from core.task_queue import QueueBackend, create_task_queue
from core.task_store import TaskRecord, TaskStore
from core.device_manager import DeviceManager
from engine.runner import Runner
from engine.plugin_loader import build_scanned_plugin_loader


class RunnerLike(Protocol):
    def run(self, script_payload: dict[str, Any], should_cancel: Any = None) -> dict[str, Any]: ...


class AccountFeedbackLike(Protocol):
    def handle_terminal_failure(self, payload: dict[str, Any], error: str) -> None: ...


@dataclass
class TaskFinalizeOutcome:
    retry_record: TaskRecord | None = None
    should_enqueue_retry: bool = False
    feedback_error: str | None = None


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
        self._plugin_loader = build_scanned_plugin_loader()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        
        # 并发线程池，最大并发数可以根据云机数量动态调整，默认给 32
        import concurrent.futures
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._recover_stale_running_tasks()
        self._enqueue_pending_tasks()
        
        import concurrent.futures
        max_workers = int(os.environ.get("MYT_MAX_CONCURRENT_TASKS", "32"))
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, 
            thread_name_prefix="task-worker"
        )
        
        self._worker = threading.Thread(target=self._work_loop, name="task-controller-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._executor is not None:
            self._executor.shutdown(wait=False)
        if self._worker is not None:
            self._worker.join(timeout=2)

    def submit(self, payload: dict[str, Any], devices: list[int], ai_type: str) -> TaskRecord:
        task_id = str(uuid.uuid4())
        with self._store.transaction(immediate=True) as conn:
            self._store.create_task(
                task_id=task_id,
                payload=payload,
                devices=devices,
                ai_type=ai_type,
                idempotency_key=None,
                max_retries=0,
                retry_backoff_seconds=2,
                priority=50,
                run_at=None,
                conn=conn,
            )
            self._events.append_event(
                task_id,
                "task.created",
                {"priority": 50, "run_at": None, "max_retries": 0, "retry_backoff_seconds": 2},
                conn=conn,
            )
            record = self._store.get_task(task_id, conn=conn)
        self._queue.enqueue(task_id, priority=50)
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
        idempotency_key: str | None = None,
    ) -> TaskRecord:
        with self._store.transaction(immediate=True) as conn:
            record, created = self._store.create_or_get_active_task(
                payload=payload,
                devices=devices,
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
                        self._metrics_payload_from_record(record, {"reason": "user_pending"}),
                        conn=conn,
                    )
        return state

    def clear_all(self) -> None:
        """Wipe all tasks from store and clear the execution queue."""
        self._store.clear_all_tasks()
        # Note: Depending on backend, clear might not be supported on all QueueBackend.
        # But we attempt to clear the store first which is the source of truth.
        # Re-initialize the queue if possible or let the dequeue fail gracefully.
        try:
            # Most backends used in this project support a simple clear or re-init
            self._queue = create_task_queue()
        except Exception:
            pass

    def task_metrics(
        self,
        window_seconds: int = 3600,
        failure_rate_threshold: float = 0.2,
        cancellation_rate_threshold: float = 0.2,
        min_terminal_samples: int = 20,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(seconds=max(0, int(window_seconds)))
        since_iso = since.isoformat()
        event_counts = self._events.count_by_type(since=since_iso)
        status_counts = self._store.status_counts()
        terminal_outcomes = {
            "completed": int(event_counts.get("task.completed", 0)),
            "failed": int(event_counts.get("task.failed", 0)),
            "cancelled": int(event_counts.get("task.cancelled", 0)),
        }
        terminal_total = max(0, sum(int(v) for v in terminal_outcomes.values()))
        completion_rate = float(terminal_outcomes["completed"]) / terminal_total if terminal_total > 0 else 0.0
        failure_rate = float(terminal_outcomes["failed"]) / terminal_total if terminal_total > 0 else 0.0
        cancellation_rate = float(terminal_outcomes["cancelled"]) / terminal_total if terminal_total > 0 else 0.0

        threshold_failure = min(1.0, max(0.0, float(failure_rate_threshold)))
        threshold_cancel = min(1.0, max(0.0, float(cancellation_rate_threshold)))
        min_samples = max(1, int(min_terminal_samples))
        evaluated = terminal_total >= min_samples
        reasons: list[str] = []
        if evaluated and failure_rate >= threshold_failure:
            reasons.append("failure_rate_exceeded")
        if evaluated and cancellation_rate >= threshold_cancel:
            reasons.append("cancellation_rate_exceeded")

        return {
            "generated_at": now.isoformat(),
            "window_seconds": max(0, int(window_seconds)),
            "since": since_iso,
            "status_counts": status_counts,
            "event_type_counts": event_counts,
            "terminal_outcomes": terminal_outcomes,
            "rates": {
                "completion_rate": completion_rate,
                "failure_rate": failure_rate,
                "cancellation_rate": cancellation_rate,
            },
            "alerts": {
                "evaluated": evaluated,
                "triggered": bool(reasons),
                "reasons": reasons,
                "thresholds": {
                    "failure_rate": threshold_failure,
                    "cancellation_rate": threshold_cancel,
                    "min_terminal_samples": min_samples,
                },
                "terminal_total": terminal_total,
            },
        }

    def task_metrics_prometheus(
        self,
        window_seconds: int = 3600,
        failure_rate_threshold: float = 0.2,
        cancellation_rate_threshold: float = 0.2,
        min_terminal_samples: int = 20,
    ) -> str:
        metrics = self.task_metrics(
            window_seconds=window_seconds,
            failure_rate_threshold=failure_rate_threshold,
            cancellation_rate_threshold=cancellation_rate_threshold,
            min_terminal_samples=min_terminal_samples,
        )

        lines = [
            "# HELP new_task_status_count Current task count by status.",
            "# TYPE new_task_status_count gauge",
        ]
        status_counts = metrics.get("status_counts", {})
        for status in sorted(status_counts):
            lines.append(
                f'new_task_status_count{{status="{self._prometheus_escape(str(status))}"}} {int(status_counts[status])}'
            )

        lines.extend(
            [
                "# HELP new_task_event_type_count Task event count by event type within window.",
                "# TYPE new_task_event_type_count gauge",
            ]
        )
        event_type_counts = metrics.get("event_type_counts", {})
        for event_type in sorted(event_type_counts):
            lines.append(
                f'new_task_event_type_count{{event_type="{self._prometheus_escape(str(event_type))}"}} {int(event_type_counts[event_type])}'
            )

        lines.extend(
            [
                "# HELP new_task_terminal_outcome_total Task terminal outcomes within window.",
                "# TYPE new_task_terminal_outcome_total gauge",
            ]
        )
        terminal_outcomes = metrics.get("terminal_outcomes", {})
        for outcome in sorted(terminal_outcomes):
            lines.append(
                f'new_task_terminal_outcome_total{{outcome="{self._prometheus_escape(str(outcome))}"}} {int(terminal_outcomes[outcome])}'
            )

        rates = metrics.get("rates", {})
        lines.extend(
            [
                "# HELP new_task_completion_rate Completion rate in terminal outcomes window.",
                "# TYPE new_task_completion_rate gauge",
                f'new_task_completion_rate {float(rates.get("completion_rate", 0.0))}',
                "# HELP new_task_failure_rate Failure rate in terminal outcomes window.",
                "# TYPE new_task_failure_rate gauge",
                f'new_task_failure_rate {float(rates.get("failure_rate", 0.0))}',
                "# HELP new_task_cancellation_rate Cancellation rate in terminal outcomes window.",
                "# TYPE new_task_cancellation_rate gauge",
                f'new_task_cancellation_rate {float(rates.get("cancellation_rate", 0.0))}',
            ]
        )

        alerts = metrics.get("alerts", {})
        lines.extend(
            [
                "# HELP new_task_alert_evaluated Whether alert thresholds were evaluated.",
                "# TYPE new_task_alert_evaluated gauge",
                f'new_task_alert_evaluated {1 if bool(alerts.get("evaluated")) else 0}',
                "# HELP new_task_alert_triggered Whether any alert threshold was triggered.",
                "# TYPE new_task_alert_triggered gauge",
                f'new_task_alert_triggered {1 if bool(alerts.get("triggered")) else 0}',
                "# HELP new_task_alert_terminal_total Terminal task sample size used for alert evaluation.",
                "# TYPE new_task_alert_terminal_total gauge",
                f'new_task_alert_terminal_total {int(alerts.get("terminal_total", 0))}',
            ]
        )

        reasons = alerts.get("reasons", [])
        lines.extend(
            [
                "# HELP new_task_alert_reason Indicates which alert reasons are currently active.",
                "# TYPE new_task_alert_reason gauge",
            ]
        )
        if isinstance(reasons, list):
            for reason in sorted(str(item) for item in reasons):
                lines.append(f'new_task_alert_reason{{reason="{self._prometheus_escape(reason)}"}} 1')

        return "\n".join(lines) + "\n"

    @staticmethod
    def _prometheus_escape(value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        escaped = escaped.replace("\n", "\\n")
        return escaped.replace('"', '\\"')

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
                delay, run_at_epoch = build_queue_schedule(record, self._iso_to_epoch, self._delay_seconds)
                self._queue.enqueue(
                    task_id,
                    delay_seconds=delay,
                    priority=record.priority,
                    run_at_epoch=run_at_epoch,
                )
            return

        if record is None:
            return

        task_name = str(record.payload.get("task") or "anonymous")
        payload_for_run = dict(record.payload)
        raw_targets = payload_for_run.pop("_dispatch_targets", None)
        dispatch_targets = normalize_dispatch_targets(raw_targets, record.devices)

        result: dict[str, Any]
        try:
            target_results: list[dict[str, Any]] = []
            first_failure: dict[str, Any] | None = None
            should_resolve_target = (os.getenv("MYT_ENABLE_RPC", "1") != "0") and self._plugin_loader.has(task_name)

            for target in dispatch_targets:
                target_runtime: dict[str, Any] | None = None
                target_error: dict[str, Any] | None = None
                if should_resolve_target:
                    target_runtime, target_error = self._resolve_target_runtime(target, enforce_availability=True)
                if target_error is not None:
                    target_result = {"target": target, "result": target_error}
                    target_results.append(target_result)
                    if first_failure is None:
                        first_failure = target_error
                    continue

                target_payload = dict(payload_for_run)
                target_payload["_task_id"] = task_id
                target_payload["_cloud_target"] = f"Unit #{target.get('device_id')}-{target.get('cloud_id')}"
                if target_runtime is not None:
                    target_payload["_target"] = target_runtime

                single_result = self._runner.run(
                    target_payload,
                    should_cancel=lambda task_id=task_id: self._store.is_cancel_requested(task_id),
                )
                target_results.append({"target": target_runtime or target, "result": single_result})
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
            outcome = self._finalize_exception_attempt(task_id=task_id, task_name=task_name, error=str(exc))
            if outcome.should_enqueue_retry and outcome.retry_record is not None and outcome.retry_record.next_retry_at is not None:
                self._queue.enqueue(
                    task_id,
                    delay_seconds=self._delay_seconds(outcome.retry_record.next_retry_at),
                    priority=outcome.retry_record.priority,
                    run_at_epoch=self._iso_to_epoch(outcome.retry_record.next_retry_at),
                )
            time.sleep(0)
            return

        outcome = self._finalize_result_attempt(task_id=task_id, task_name=task_name, result=result)
        if outcome.should_enqueue_retry and outcome.retry_record is not None and outcome.retry_record.next_retry_at is not None:
            self._queue.enqueue(
                task_id,
                delay_seconds=self._delay_seconds(outcome.retry_record.next_retry_at),
                priority=outcome.retry_record.priority,
                run_at_epoch=self._iso_to_epoch(outcome.retry_record.next_retry_at),
            )
        if outcome.feedback_error is not None:
            self._account_feedback.handle_terminal_failure(record.payload, outcome.feedback_error)
        time.sleep(0)


    def _resolve_target_runtime(
        self,
        target: dict[str, int],
        enforce_availability: bool,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        return self._target_runtime_resolver.resolve(target, enforce_availability)

    def _append_dispatch_result_event(
        self,
        conn: Any,
        task_id: str,
        task_name: str,
        result: dict[str, Any],
    ) -> None:
        self._events.append_event(
            task_id,
            "task.dispatch_result",
            {
                "task": str(result.get("task") or task_name),
                "status": str(result.get("status") or "unknown"),
                "ok": bool(result.get("ok")),
                "checkpoint": str(result.get("checkpoint") or ""),
            },
            conn=conn,
        )

    def _finalize_exception_attempt(self, task_id: str, task_name: str, error: str) -> TaskFinalizeOutcome:
        outcome = TaskFinalizeOutcome()
        with self._store.transaction(immediate=True) as conn:
            self._append_dispatch_result_event(
                conn=conn,
                task_id=task_id,
                task_name=task_name,
                result={"task": task_name, "status": "exception", "ok": False, "checkpoint": ""},
            )
            outcome.retry_record = self._store.schedule_retry(task_id, error=error, conn=conn)
            if outcome.retry_record is not None and outcome.retry_record.next_retry_at is not None:
                self._events.append_event(
                    task_id,
                    "task.retry_scheduled",
                    {
                        "retry_count": outcome.retry_record.retry_count,
                        "max_retries": outcome.retry_record.max_retries,
                        "next_retry_at": outcome.retry_record.next_retry_at,
                        "error": error,
                    },
                    conn=conn,
                )
                outcome.should_enqueue_retry = True
            else:
                current = self._store.get_task(task_id, conn=conn)
                if current is not None and current.cancel_requested:
                    self._store.mark_cancelled(task_id, message="cancelled by user", conn=conn)
                    cancelled = self._store.get_task(task_id, conn=conn)
                    self._events.append_event(
                        task_id,
                        "task.cancelled",
                        self._metrics_payload_from_record(cancelled, {"reason": "user_exception_path"}),
                        conn=conn,
                    )
                else:
                    self._store.mark_failed(task_id, error=error, conn=conn)
                    failed = self._store.get_task(task_id, conn=conn)
                    self._events.append_event(
                        task_id,
                        "task.failed",
                        self._metrics_payload_from_record(failed, {"error": error}),
                        conn=conn,
                    )
        return outcome

    def _finalize_result_attempt(
        self,
        task_id: str,
        task_name: str,
        result: dict[str, Any],
    ) -> TaskFinalizeOutcome:
        outcome = TaskFinalizeOutcome()
        with self._store.transaction(immediate=True) as conn:
            self._append_dispatch_result_event(conn=conn, task_id=task_id, task_name=task_name, result=result)
            current = self._store.get_task(task_id, conn=conn)
            cancel_requested = bool(current.cancel_requested) if current is not None else False
            if cancel_requested or str(result.get("status")) == "cancelled":
                self._store.mark_cancelled(task_id, message="cancelled by user", conn=conn)
                cancelled = self._store.get_task(task_id, conn=conn)
                self._events.append_event(
                    task_id,
                    "task.cancelled",
                    self._metrics_payload_from_record(cancelled, {"reason": "user"}),
                    conn=conn,
                )
            elif bool(result.get("ok")):
                self._store.mark_completed(task_id, result=result, conn=conn)
                completed = self._store.get_task(task_id, conn=conn)
                self._events.append_event(
                    task_id,
                    "task.completed",
                    self._metrics_payload_from_record(completed, {"ok": True}),
                    conn=conn,
                )
            else:
                error = str(result.get("message", "task failed"))
                outcome.retry_record = self._store.schedule_retry(task_id, error=error, conn=conn)
                if outcome.retry_record is not None and outcome.retry_record.next_retry_at is not None:
                    self._events.append_event(
                        task_id,
                        "task.retry_scheduled",
                        {
                            "retry_count": outcome.retry_record.retry_count,
                            "max_retries": outcome.retry_record.max_retries,
                            "next_retry_at": outcome.retry_record.next_retry_at,
                            "error": error,
                        },
                        conn=conn,
                    )
                    outcome.should_enqueue_retry = True
                else:
                    current = self._store.get_task(task_id, conn=conn)
                    if current is not None and current.cancel_requested:
                        self._store.mark_cancelled(task_id, message="cancelled by user", conn=conn)
                        cancelled = self._store.get_task(task_id, conn=conn)
                        self._events.append_event(
                            task_id,
                            "task.cancelled",
                            self._metrics_payload_from_record(cancelled, {"reason": "user_exception_path"}),
                            conn=conn,
                        )
                    else:
                        self._store.mark_failed(task_id, error=error, result=result, conn=conn)
                        failed = self._store.get_task(task_id, conn=conn)
                        self._events.append_event(
                            task_id,
                            "task.failed",
                            self._metrics_payload_from_record(failed, {"error": error}),
                            conn=conn,
                        )
                        outcome.feedback_error = error
        return outcome

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

    def _metrics_payload(self, task_id: str, extra: dict[str, Any]) -> dict[str, Any]:
        record = self._store.get_task(task_id)
        return self._metrics_payload_from_record(record, extra)

    def _metrics_payload_from_record(self, record: TaskRecord | None, extra: dict[str, Any]) -> dict[str, Any]:
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
            delay, run_at_epoch = build_queue_schedule(record, self._iso_to_epoch, self._delay_seconds)
            self._queue.enqueue(
                record.task_id,
                delay_seconds=delay,
                priority=record.priority,
                run_at_epoch=run_at_epoch,
            )

    def _enqueue_pending_tasks(self) -> None:
        for record in self._store.list_pending_tasks():
            delay, run_at_epoch = build_queue_schedule(record, self._iso_to_epoch, self._delay_seconds)
            self._queue.enqueue(
                record.task_id,
                delay_seconds=delay,
                priority=record.priority,
                run_at_epoch=run_at_epoch,
            )

    @staticmethod
    def _stale_running_seconds() -> int:
        raw = os.environ.get("MYT_TASK_STALE_RUNNING_SECONDS", "300").strip()
        try:
            parsed = int(raw)
        except ValueError:
            return 300
        return max(0, parsed)


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
